# Signal guide and operational boundaries

The official Kubernetes [pod debugging guide](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/) recommends inspecting pod state and recent events first. [Events](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_events/) are namespaced. kube-triage reads the namespace's pod and event lists, then joins events by Pod UID to avoid attributing an old event to a recreated pod with the same name. If a synthetic or older export has no UID on either the pod or event, it falls back to namespace plus name. A live query is never widened to every namespace.

| Code | Evidence in report | What it cannot prove |
| --- | --- | --- |
| `PENDING` | Pod phase and optional `FailedScheduling` reason | Which node constraint is decisive; inspect the full scheduler message locally |
| `IMAGE_PULL` | Container waiting reason | Whether the registry, network, authentication or tag is responsible |
| `CRASH_LOOP` | Waiting reason, restart count, prior termination reason | The application-level cause; previous logs are suggested but never fetched |
| `CONFIG` | Container waiting reason | Which key or reference is invalid |
| `MOUNT` | Matching `FailedMount` warning event | The storage or permissions root cause |
| `OOM` | Prior terminated state `OOMKilled` | Whether limits, a leak, workload shape or node pressure drove it |
| `NOT_READY` | Container readiness or Pod Ready condition | Whether the probe or a dependency is the true cause |

An event without a matching UID is ignored when the selected pod has a UID. No event message, container environment, Secret, ConfigMap, Pod spec or raw log is printed. Finding severity is a triage priority, not an assessment of business impact.

When a suggested command includes `logs --previous`, it is intended for local inspection by an authorized operator. Do not paste raw logs or cluster exports into an issue. If there are no findings but users still see errors, examine Services and EndpointSlices, application metrics and traces, ingress, DNS, network policies and dependencies. See the official [Service debugging guide](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/).
