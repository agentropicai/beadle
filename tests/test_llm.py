import json
import os
import subprocess
import unittest
from contextlib import contextmanager
from unittest import mock

import lib


@contextmanager
def configured(**values):
    old = lib._env
    try:
        lib._env = values
        with mock.patch.dict(os.environ, {}, clear=True):
            yield
    finally:
        lib._env = old


class LlmProviderTests(unittest.TestCase):
    def test_claude_is_backward_compatible_default(self):
        response = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"subtype": "success", "is_error": False, "result": "OK"}), stderr=""
        )
        with configured(), mock.patch.object(lib.shutil, "which", return_value="/bin/claude"), \
                mock.patch.object(lib.subprocess, "run", return_value=response) as run:
            self.assertEqual(lib.llm("hello"), "OK")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/bin/claude")
        self.assertIn("--output-format", command)
        self.assertEqual(command[command.index("--model") + 1], "claude-sonnet-4-6")
        self.assertNotIn("ANTHROPIC_API_KEY", run.call_args.kwargs["env"])

    def test_codex_uses_subscription_cli_in_empty_read_only_workspace(self):
        response = subprocess.CompletedProcess([], 0, stdout="OK\n", stderr="progress")
        with configured(BEADLE_LLM_PROVIDER="codex"), \
                mock.patch.object(lib.shutil, "which", return_value="/bin/codex"), \
                mock.patch.object(lib.subprocess, "run", return_value=response) as run:
            self.assertEqual(lib.llm("hello", model="claude-opus-5"), "OK")
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["/bin/codex", "exec"])
        self.assertIn("--ephemeral", command)
        self.assertIn("read-only", command)
        self.assertIn('forced_login_method="chatgpt"', command)
        self.assertIn('approval_policy="never"', command)
        self.assertIn("tools.web_search=false", command)
        self.assertIn("tools.view_image=false", command)
        self.assertIn("shell_tool", command)
        self.assertIn("unified_exec", command)
        self.assertNotIn("--model", command)  # never pass a Claude model to Codex
        self.assertEqual(command[-1], "-")
        self.assertNotEqual(run.call_args.kwargs["cwd"], lib.BASE)
        self.assertNotIn("OPENAI_API_KEY", run.call_args.kwargs["env"])

    def test_subscription_environment_removes_api_overrides(self):
        source = {
            "PATH": "/bin", "ANTHROPIC_API_KEY": "anthropic-secret",
            "OPENAI_API_KEY": "openai-secret", "CLAUDE_CODE_USE_BEDROCK": "1",
        }
        claude = lib.subscription_env("claude", source)
        codex = lib.subscription_env("codex", source)
        self.assertNotIn("ANTHROPIC_API_KEY", claude)
        self.assertNotIn("CLAUDE_CODE_USE_BEDROCK", claude)
        self.assertEqual(claude["OPENAI_API_KEY"], "openai-secret")
        self.assertNotIn("OPENAI_API_KEY", codex)
        self.assertEqual(codex["ANTHROPIC_API_KEY"], "anthropic-secret")

    def test_provider_specific_codex_model_wins(self):
        response = subprocess.CompletedProcess([], 0, stdout="OK", stderr="")
        with configured(BEADLE_LLM_PROVIDER="codex", BEADLE_CODEX_MODEL="gpt-test"), \
                mock.patch.object(lib.shutil, "which", return_value="/bin/codex"), \
                mock.patch.object(lib.subprocess, "run", return_value=response) as run:
            self.assertEqual(lib.llm("hello", model="claude-opus-5"), "OK")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--model") + 1], "gpt-test")

    def test_quota_error_falls_back_to_other_login(self):
        claude = subprocess.CompletedProcess([], 0, stdout=json.dumps({
            "subtype": "success", "is_error": True, "api_error_status": 429,
            "result": "You've hit your weekly limit",
        }), stderr="")
        codex = subprocess.CompletedProcess([], 0, stdout="OK", stderr="")

        def result(command, **kwargs):
            return claude if command[0].endswith("claude") else codex

        def which(name):
            return "/bin/" + name

        with configured(BEADLE_LLM_PROVIDER="claude", BEADLE_LLM_FALLBACK="codex"), \
                mock.patch.object(lib.shutil, "which", side_effect=which), \
                mock.patch.object(lib.subprocess, "run", side_effect=result) as run:
            self.assertEqual(lib.llm("hello"), "OK")
            self.assertEqual(run.call_count, 2)

    def test_both_provider_errors_keep_llm_error_contract(self):
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="not logged in")
        with configured(BEADLE_LLM_PROVIDER="codex", BEADLE_LLM_FALLBACK="claude"), \
                mock.patch.object(lib.shutil, "which", side_effect=lambda name: "/bin/" + name), \
                mock.patch.object(lib.subprocess, "run", return_value=failed):
            result = lib.llm("hello")
        self.assertTrue(lib.failed(result))
        self.assertIn("codex", result)
        self.assertIn("claude", result)

    def test_invalid_provider_is_a_configuration_error(self):
        with configured(BEADLE_LLM_PROVIDER="other"):
            result = lib.llm("hello")
        self.assertTrue(lib.failed(result))
        self.assertIn("configuration", result)


if __name__ == "__main__":
    unittest.main()
