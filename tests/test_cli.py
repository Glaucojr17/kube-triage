import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from kubetriage.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_offline_json_and_exit_code(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--pods-file", str(ROOT / "examples/pods.json"),
                         "--events-file", str(ROOT / "examples/events.json"),
                         "-n", "demo", "--format", "json"])
        self.assertEqual(code, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["source"], "offline:pods.json")
        self.assertGreater(len(report["findings"]), 3)
        self.assertNotIn("TOKEN=", output.getvalue())

    @patch("kubetriage.cli.subprocess.run")
    def test_live_only_reads_namespace_and_handles_event_rbac(self, run):
        pods = {"items": [{
            "metadata": {"name": "ok", "namespace": "demo", "uid": "123"},
            "status": {"phase": "Running", "containerStatuses": [
                {"name": "app", "ready": True, "restartCount": 0}
            ]},
        }]}
        run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout=json.dumps(pods), stderr=""),
            subprocess.CompletedProcess([], 1, stdout="", stderr="forbidden: private details"),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--context", "sandbox", "-n", "demo", "--selector", "app=ok"])
        self.assertEqual(code, 0)
        self.assertIn("Events unavailable", output.getvalue())
        self.assertNotIn("private details", output.getvalue())
        self.assertEqual(len(run.call_args_list), 2)
        pod_cmd = run.call_args_list[0].args[0]
        event_cmd = run.call_args_list[1].args[0]
        self.assertEqual(pod_cmd[:7], ["kubectl", "--context", "sandbox", "-n", "demo", "get", "pods"])
        self.assertIn("-l", pod_cmd)
        self.assertEqual(event_cmd[6], "events")
        self.assertTrue(all(word not in cmd for cmd in (pod_cmd, event_cmd) for word in ("delete", "apply", "logs")))


if __name__ == "__main__":
    unittest.main()
