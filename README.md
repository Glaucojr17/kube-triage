# kube-triage

**A small, read-only first pass for Kubernetes pod incidents.** When a pod is stuck or restarting, the hard part for someone on call is often deciding which signal to trust first and what to inspect next. kube-triage reads pod status and namespace events, groups a few well-defined symptoms, and prints evidence plus the next `kubectl` command. It does not call an AI service, read application logs, change resources, or claim to identify the definitive root cause.

The same analysis runs against local JSON examples. Newcomers can practice without a cluster; teams can test a sanitized snapshot before using the CLI against a namespace. Python 3.10+ and `kubectl` (only for live mode) are required. There are no runtime Python dependencies.

## Try it without Kubernetes

```bash
git clone https://github.com/Glaucojr17/kube-triage.git
cd kube-triage
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
kube-triage --pods-file examples/pods.json --events-file examples/events.json -n demo
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. The exit status is **2** when findings exist, even though the command successfully analyzed the file. This is useful for scripts; it is not a program crash. Use `--format json` for structured output or `--format markdown` for a local incident note.

The sample contains a scheduling issue, an image pull failure, a crash loop and a readiness issue. All names and UIDs are fictitious.

## Inspect a real namespace

First confirm the context name with `kubectl config get-contexts`. Then explicitly select it:

```bash
kube-triage --context my-sandbox -n demo --selector app=checkout
kube-triage --context my-sandbox -n demo --format markdown
```

Only these API reads are performed: `kubectl --context CONTEXT -n NAMESPACE get pods -o json` and `get events -o json`, each with a 10-second request timeout. The optional label selector applies to pods; events from the namespace are matched back to selected pods by UID. If RBAC denies events, pod status analysis continues with a warning. The tool never invokes a suggested command automatically. A suggested `kubectl logs --previous` may display secrets if *you* run it, so review and handle that output privately.

| Finding | Observed signal | First verification |
| --- | --- | --- |
| `PENDING` | Pod pending without a recognized container wait; `FailedScheduling` event when present | Describe pod; inspect scheduler events and placement |
| `IMAGE_PULL` | `ImagePullBackOff`, `ErrImagePull`, `InvalidImageName` | Image name, registry access, pull secrets |
| `CRASH_LOOP` | `CrashLoopBackOff` or `RunContainerError` | Previous container logs, termination reason |
| `CONFIG` | Container creation/configuration error | References to ConfigMaps and Secrets |
| `OOM` / `RESTARTS` | Previous OOM kill or restart threshold (default 3) | Memory limits, probes, recent events |
| `NOT_READY` | Running pod with unready container or Ready=False | Probe and application dependencies |
| `MOUNT` | `FailedMount` event | Volumes, PVCs and references |
| `POD_FAILED` | Failed phase | Termination and owning workload |

Output is a **triage aid**, not a health or security certification. Healthy pods produce no finding even though the application could still have errors or poor latency. Events are transient, may be absent, and some issues require node, service, DNS, network policy, storage or application logs to investigate. The tool does not scrape metrics or check deployments. See [how the signals are interpreted](docs/SIGNALS.md).

## Data handling and exit codes

- No telemetry, credentials, external API, automatic upload or saved report. Live output stays on your terminal unless you redirect it.
- Raw event messages are deliberately omitted from reports because they can contain sensitive values. Output includes pod names, context names, high-level reasons and suggested commands; review before sharing.
- Offline files are read as provided. **Sanitize exports before putting them in issues or Git.** The included examples are synthetic.
- Exit `0`: no supported finding. Exit `2`: at least one finding. Exit `1`: input or kubectl collection error. Argument errors follow `argparse` exit `2`.

## Contribute

Run `python -m unittest discover -s tests -v`. [Contributions](CONTRIBUTING.md) that add a reproducible synthetic case, test and a cautious next step are welcome. Licensed under [MIT](LICENSE).

### Em português

O **kube-triage** ajuda a fazer a primeira triagem de pods com falha. Ele lê status e eventos, mostra a evidência encontrada e sugere o próximo comando de investigação. Não altera o cluster, não coleta logs e não envia dados para serviços externos. Para experimentar sem Kubernetes:

```bash
kube-triage --pods-file examples/pods.json --events-file examples/events.json -n demo
```

Em um cluster sob seu acesso, informe o contexto e o namespace explicitamente: `kube-triage --context meu-lab -n minha-aplicacao`. Os diagnósticos e comandos de saída estão em inglês para facilitar uso e colaboração entre equipes; o [guia de sinais](docs/SIGNALS.md) explica seus limites.
