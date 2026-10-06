import json
from pathlib import Path
import unittest

from kubetriage.analysis import analyze


ROOT = Path(__file__).resolve().parents[1]


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.pods = json.loads((ROOT / "examples/pods.json").read_text())
        self.events = json.loads((ROOT / "examples/events.json").read_text())

    def test_correlates_state_and_events_without_echoing_messages(self):
        findings = analyze(self.pods, self.events, namespace="demo", context="lab")
        pairs = {(f.pod, f.code) for f in findings}
        self.assertIn(("api-5c64", "CRASH_LOOP"), pairs)
        self.assertIn(("worker-814a", "IMAGE_PULL"), pairs)
        self.assertIn(("checkout-7f9b", "PENDING"), pairs)
        self.assertIn(("frontend-245e", "MOUNT"), pairs)
        self.assertIn(("frontend-245e", "NOT_READY"), pairs)
        self.assertNotIn(("healthy-7d8c", "MOUNT"), pairs)  # stale UID
        self.assertTrue(all(f.pod != "healthy-7d8c" for f in findings))
        self.assertIn("--context lab", next(f.next_step for f in findings if f.code == "CRASH_LOOP"))
        output = json.dumps([f.as_dict() for f in findings])
        self.assertNotIn("do-not-print", output)

    def test_without_events_keeps_status_findings(self):
        findings = analyze(self.pods, None, namespace="demo")
        self.assertIn("CRASH_LOOP", [f.code for f in findings])
        self.assertNotIn("MOUNT", [f.code for f in findings])

    def test_empty_and_wrong_namespace(self):
        empty = analyze({"items": []}, None, namespace="demo")
        self.assertEqual(empty[0].code, "NO_PODS")
        with self.assertRaises(ValueError):
            analyze(self.pods, self.events, namespace="other")

    def test_oom_and_restart_threshold(self):
        pod = {
            "metadata": {"name": "job-1", "namespace": "demo"},
            "status": {"phase": "Running", "containerStatuses": [
                {"name": "one", "ready": True, "restartCount": 4,
                 "lastState": {"terminated": {"reason": "OOMKilled"}}},
                {"name": "two", "ready": True, "restartCount": 4,
                 "lastState": {"terminated": {"reason": "Error"}}},
            ]},
        }
        findings = analyze({"items": [pod]}, None, namespace="demo")
        self.assertEqual({f.code for f in findings}, {"OOM", "RESTARTS"})


if __name__ == "__main__":
    unittest.main()
