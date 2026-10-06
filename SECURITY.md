# Security and sensitive data

The CLI is read-only in normal operation: it asks kubectl for pods and events. Note that kubeconfig files can contain executable credential plugins; use a trusted kubectl installation and kubeconfig. The tool does not fetch or print raw logs, event messages, Secret objects, Pod specs or environment variables. Pod names, context names and evidence fields may still be sensitive.

Do not publish a raw `kubectl get ... -o json` export from a corporate cluster to an issue. Replace names and UIDs with fictitious values and remove messages, annotations, labels, image references and credentials first. The included fixtures are synthetic.

If you discover a vulnerability, avoid posting an exploit or sensitive data in a public issue. Contact the repository owner through the GitHub profile contact before disclosure.
