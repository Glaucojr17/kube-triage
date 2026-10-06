# Contributing

Thanks for helping make first-response troubleshooting more accessible.

1. Open an issue describing a reproducible signal and the specific next verification step. Do not include cluster exports, logs, credentials, real hostnames or internal application names.
2. Add a synthetic PodList/EventList example and a test that fails before the change and passes afterward. Keep the heuristic narrow; say “inspect” when a symptom has multiple possible causes.
3. Run `python -m unittest discover -s tests -v` and verify offline CLI output.
4. Submit a pull request explaining what changed, which Kubernetes status or event field supports it, and what remains ambiguous.

Contributors retain credit for their work. By contributing, you agree to license your contribution under this repository's MIT license.
