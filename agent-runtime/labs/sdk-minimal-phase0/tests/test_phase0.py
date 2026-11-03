"""Offline contract tests. FakeHarness is NOT a real model or SDK execution."""
from __future__ import annotations
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import run_phase0
import session_report


class SessionLogTests(unittest.TestCase):
    def test_classify_known_and_unknown(self):
        self.assertEqual(session_report.classify({"kind": "tool/call", "data": {"secret": "NO"}}), "tool/call")
        self.assertEqual(session_report.classify({"event": {"type": "turn/end"}}), "turn/end")
        self.assertEqual(session_report.classify({"payload": "unrecognized"}), "unknown")

    def test_summary_hides_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "sessions"
            folder.mkdir()
            (folder / "s1.jsonl").write_text(
                json.dumps({"kind": "user/message", "data": {"secret": "DO_NOT_PRINT"}}) + "\n"
                + json.dumps({"kind": "tool/result", "data": {"token": "NEVER_LOG"}}) + "\n"
                + "invalid\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                status = session_report.main(["--dsh-home", temp])
            text = capture.getvalue()
            self.assertEqual(status, 0)
            self.assertEqual(session_report.summarize(Path(temp))["file_count"], 1)
            self.assertIn("tool/result", text)
            self.assertNotIn("DO_NOT_PRINT", text)
            self.assertNotIn("NEVER_LOG", text)
            self.assertIn("invalid_json_lines", text)

    def test_empty_session_store_is_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "sessions").mkdir()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = session_report.main(["--dsh-home", temp])
            self.assertEqual(code, 1)


class SDKRunnerTests(unittest.TestCase):
    def test_missing_credential_fails_before_import(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            with contextlib.redirect_stderr(io.StringIO()):
                code = run_phase0.main([
                    "--workspace", "/unused", "--dsh-home", "/unused",
                    "--patch", "/unused", "--output", "/unused",
                    "--session-id", "s0",
                ])
        self.assertEqual(code, 2)

    def test_sdk_contract_via_fake_sdk(self):
        """Only tests our glue code; does not validate vendor SDK behavior."""
        captured = {}
        class FakeHarness:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def run(self, prompt, session_id):
                captured["prompt"] = prompt
                return SimpleNamespace(
                    session_id=session_id, finish_reason="completed",
                    events=[{"kind": "turn/start"}, {"kind": "turn/end"}],
                    notifications=[{"type": "session/event"}],
                    final_response="完成了模拟测试",
                )

        fake_module = ModuleType("deepseek_harness")
        fake_module.DeepSeekHarness = FakeHarness
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace, home = root / "ws", root / "home"
            workspace.mkdir()
            home.mkdir()
            patch = root / "patch.yml"
            patch.write_text("- id: session-log-deepseek\n  config:\n    enabled: false\n")
            out = root / "result.json"
            with mock.patch.dict(sys.modules, {"deepseek_harness": fake_module}), \
                 mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake-token"}), \
                 mock.patch.object(run_phase0.metadata, "version", return_value="test-only"), \
                 contextlib.redirect_stdout(io.StringIO()):
                code = run_phase0.main([
                    "--workspace", str(workspace), "--dsh-home", str(home),
                    "--patch", str(patch), "--output", str(out), "--session-id", "test-s",
                ])
            self.assertEqual(code, 0)
            value = json.loads(out.read_text())
            self.assertEqual(value["root_event_count"], 2)
            self.assertEqual(value["root_event_kinds"]["turn/end"], 1)
            self.assertEqual(value["finish_reason"], "completed")
            self.assertEqual(captured["profile"], "sdk-minimal")
            self.assertEqual(captured["patches"], (str(patch),))
            self.assertIn("bash", captured["prompt"])

    def test_home_workspace_must_differ(self):
        with tempfile.TemporaryDirectory() as temp:
            patch = Path(temp) / "patch.yml"
            patch.write_text("[]")
            with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake"}), \
                 contextlib.redirect_stderr(io.StringIO()):
                code = run_phase0.main([
                    "--workspace", temp, "--dsh-home", temp,
                    "--patch", str(patch), "--output", str(patch),
                    "--session-id", "s0",
                ])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
