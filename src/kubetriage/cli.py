"""CLI: explicit context, namespace scope, no automatic data upload."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from . import __version__
from .analysis import analyze


def parser():
    p = argparse.ArgumentParser(
        prog="kube-triage",
        description="Read-only, namespace-scoped Kubernetes pod triage. No logs are collected.",
    )
    p.add_argument("--version", action="version", version=__version__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--context", help="Explicit kubectl context for live read-only queries.")
    source.add_argument("--pods-file", type=Path, help="Offline Kubernetes PodList JSON.")
    p.add_argument("-n", "--namespace", required=True, help="Namespace to inspect.")
    p.add_argument("-l", "--selector", help="Optional Kubernetes label selector (live mode only).")
    p.add_argument("--events-file", type=Path, help="Offline EventList JSON, optional.")
    p.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    p.add_argument("--restart-threshold", type=int, default=3)
    return p


def _read_json(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"{path}: expected a Kubernetes List object with items array")
    return data


def _kubectl(context, namespace, resource, selector=None):
    args = ["kubectl", "--context", context, "-n", namespace, "get", resource, "-o", "json", "--request-timeout=10s"]
    if selector:
        args.extend(["-l", selector])
    result = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    if result.returncode:
        raise RuntimeError(f"kubectl get {resource} failed (exit {result.returncode}). Check context, namespace, RBAC and connectivity privately.")
    data = json.loads(result.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"kubectl get {resource} did not return a Kubernetes List")
    return data


def _render(findings, fmt, source, warnings):
    if fmt == "json":
        return json.dumps({"source": source, "warnings": warnings, "findings": [f.as_dict() for f in findings]}, indent=2)
    if fmt == "markdown":
        lines = ["# Kubernetes pod triage", "", f"Source: `{source}`", ""]
        if warnings:
            lines += [f"> {w}" for w in warnings] + [""]
        if not findings:
            return "\n".join(lines + ["No supported issue detected. This is not a health guarantee."])
        for f in findings:
            lines += [f"## {f.severity.upper()} · {f.code} · `{f.namespace}/{f.pod}`",
                      f"- Container: `{f.container or '-'}`",
                      f"- Evidence: {f.evidence}",
                      f"- Verify: `{f.next_step}`", ""]
        return "\n".join(lines)
    lines = [f"Source: {source}"]
    lines += [f"Warning: {w}" for w in warnings]
    if not findings:
        lines.append("No supported issue detected. This is not a health guarantee.")
    for f in findings:
        lines += [f"[{f.severity.upper()}] {f.code} {f.namespace}/{f.pod} {f.container or ''}".rstrip(),
                  f"  Evidence: {f.evidence}", f"  Verify: {f.next_step}"]
    return "\n".join(lines)


def main(argv=None):
    args = parser().parse_args(argv)
    if args.restart_threshold < 1:
        parser().error("--restart-threshold must be >= 1")
    if args.pods_file and args.selector:
        parser().error("--selector is only available in live mode")
    if args.context and args.events_file:
        parser().error("--events-file is only available with --pods-file")
    warnings = []
    try:
        if args.pods_file:
            pods = _read_json(args.pods_file)
            events = _read_json(args.events_file) if args.events_file else None
            if not args.events_file:
                warnings.append("Events not provided; event-based findings are unavailable.")
            source = f"offline:{args.pods_file.name}"
        else:
            pods = _kubectl(args.context, args.namespace, "pods", args.selector)
            try:
                events = _kubectl(args.context, args.namespace, "events")
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                events = None
                warnings.append("Events unavailable (permissions, connectivity or malformed response). Pod status findings remain available.")
            source = f"context:{args.context} namespace:{args.namespace}"
        findings = analyze(pods, events, namespace=args.namespace, context=args.context,
                           restart_threshold=args.restart_threshold)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"kube-triage: {exc}", file=sys.stderr)
        return 1
    print(_render(findings, args.format, source, warnings))
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
