"""Interpret a small, explicit set of pod and event signals.

This module only consumes Kubernetes JSON and never executes commands.
It deliberately reports hypotheses and verification steps, not root causes.
"""

from dataclasses import asdict, dataclass
import shlex


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    namespace: str
    pod: str
    container: str | None
    evidence: str
    next_step: str

    def as_dict(self):
        return asdict(self)


SEVERITY = {"critical": 0, "warning": 1, "info": 2}


def _command(*args):
    return " ".join(shlex.quote(str(arg)) for arg in ("kubectl", *args))


def _pod_args(namespace, pod, context=None):
    args = []
    if context:
        args += ["--context", context]
    return [*args, "-n", namespace, "describe", "pod", pod]


def _log_args(namespace, pod, container, context=None):
    args = []
    if context:
        args += ["--context", context]
    return [*args, "-n", namespace, "logs", pod, "-c", container, "--previous", "--tail=100"]


def _events_by_pod(events, pods):
    """Correlate by UID, falling back to name only for synthetic/older exports."""
    by_uid = {p.get("metadata", {}).get("uid"): p for p in pods if p.get("metadata", {}).get("uid")}
    by_name = {(p.get("metadata", {}).get("namespace", "default"), p.get("metadata", {}).get("name")): p for p in pods}
    indexed = {}
    for event in events:
        obj = event.get("involvedObject") or event.get("regarding") or {}
        if obj.get("kind") != "Pod":
            continue
        uid = obj.get("uid")
        namespace = obj.get("namespace") or event.get("metadata", {}).get("namespace", "default")
        pod = by_uid.get(uid) if uid else by_name.get((namespace, obj.get("name")))
        if not pod or (uid and pod.get("metadata", {}).get("uid") != uid):
            continue
        if not uid and pod.get("metadata", {}).get("uid"):
            continue  # A name alone cannot distinguish a recreated pod.
        name = pod.get("metadata", {}).get("name")
        indexed.setdefault(name, []).append(event)
    return indexed


def analyze(pods_document, events_document, *, namespace=None, context=None, restart_threshold=3):
    """Return sorted findings for one namespace.

    Events are optional. Missing event access reduces evidence but does not
    change the findings inferred directly from pod status.
    """
    pods = pods_document.get("items", [])
    events = events_document.get("items", []) if events_document else []
    if not isinstance(pods, list) or not isinstance(events, list):
        raise ValueError("Expected Kubernetes List JSON with an items array.")
    for pod in pods:
        if not isinstance(pod, dict):
            raise ValueError("Pod items must be objects.")
    found = []
    indexed = _events_by_pod(events, pods)
    if not pods:
        found.append(Finding("warning", "NO_PODS", namespace or "unknown", "-", None,
                             "The query returned no pods.", "Check namespace and label selector with kubectl get pods."))
        return found

    for pod in pods:
        metadata, status = pod.get("metadata") or {}, pod.get("status") or {}
        name = metadata.get("name", "<unnamed>")
        ns = metadata.get("namespace") or namespace or "default"
        if namespace and ns != namespace:
            raise ValueError(f"Pod {name} belongs to namespace {ns}, expected {namespace}.")
        describe = _command(*_pod_args(ns, name, context))
        relevant = indexed.get(name, [])
        reasons = {e.get("reason") for e in relevant if e.get("type") == "Warning"}
        phase = status.get("phase", "Unknown")
        all_statuses = [*(status.get("initContainerStatuses") or []), *(status.get("containerStatuses") or [])]
        recognized_wait = any(
            ((c.get("state") or {}).get("waiting") or {}).get("reason") in {
                "ImagePullBackOff", "ErrImagePull", "InvalidImageName", "CrashLoopBackOff",
                "RunContainerError", "CreateContainerConfigError", "CreateContainerError"
            } for c in all_statuses
        )
        if phase == "Pending" and not recognized_wait:
            hint = "FailedScheduling event" if "FailedScheduling" in reasons else "Pod phase Pending"
            found.append(Finding("warning", "PENDING", ns, name, None, hint,
                                 f"{describe} (inspect scheduler events, requests, selectors and taints)"))
        if phase == "Failed":
            found.append(Finding("critical", "POD_FAILED", ns, name, None, "Pod phase Failed",
                                 f"{describe} (inspect termination reasons and workload controller)"))
        if "FailedMount" in reasons:
            found.append(Finding("warning", "MOUNT", ns, name, None, "FailedMount event",
                                 f"{describe} (inspect volume, PVC and Secret/ConfigMap references)"))

        waiting_found = False
        for container in all_statuses:
            cname = container.get("name", "<unnamed>")
            waiting = (container.get("state") or {}).get("waiting") or {}
            reason = waiting.get("reason")
            previous = ((container.get("lastState") or {}).get("terminated") or {}).get("reason")
            restarts = container.get("restartCount") or 0
            if reason in {"ImagePullBackOff", "ErrImagePull", "InvalidImageName"}:
                waiting_found = True
                found.append(Finding("critical", "IMAGE_PULL", ns, name, cname, reason,
                                     f"{describe} (inspect image name, registry access and imagePullSecrets)"))
            elif reason in {"CrashLoopBackOff", "RunContainerError"}:
                waiting_found = True
                logs = _command(*_log_args(ns, name, cname, context))
                found.append(Finding("critical", "CRASH_LOOP", ns, name, cname,
                                     f"{reason}; restarts={restarts}; previous={previous or 'unknown'}",
                                     f"{logs} (inspect locally; logs may contain secrets)"))
            elif reason in {"CreateContainerConfigError", "CreateContainerError"}:
                waiting_found = True
                found.append(Finding("critical", "CONFIG", ns, name, cname, reason,
                                     f"{describe} (check referenced ConfigMaps, Secrets and runtime configuration)"))
            elif previous == "OOMKilled":
                found.append(Finding("warning", "OOM", ns, name, cname,
                                     f"previous=OOMKilled; restarts={restarts}",
                                     f"{describe} (compare memory limits with usage and application behavior)"))
            elif restarts >= restart_threshold:
                found.append(Finding("warning", "RESTARTS", ns, name, cname,
                                     f"restarts={restarts}; previous={previous or 'unknown'}",
                                     f"{describe} (inspect state, probes and recent events)"))

        if phase == "Running" and not waiting_found:
            unready = [c.get("name", "<unnamed>") for c in (status.get("containerStatuses") or []) if not c.get("ready", False)]
            ready_condition = next((c for c in (status.get("conditions") or []) if c.get("type") == "Ready"), {})
            if unready or ready_condition.get("status") == "False":
                found.append(Finding("warning", "NOT_READY", ns, name, ",".join(unready),
                                     "Pod Ready condition false or container readiness=false",
                                     f"{describe} (inspect readiness probe and application dependencies)"))
    return sorted(found, key=lambda f: (SEVERITY[f.severity], f.namespace, f.pod, f.code, f.container or ""))
