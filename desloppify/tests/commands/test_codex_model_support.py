"""Codex model selection, configuration inheritance, and process integration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from desloppify.app.commands.plan.triage.runner.codex_runner import run_triage_stage
from desloppify.app.commands.runner import codex_batch
from desloppify.base.exception_sets import CommandError


@pytest.fixture(autouse=True)
def isolated_codex_settings(monkeypatch):
    for name in (
        "DESLOPPIFY_CODEX_MODEL",
        "DESLOPPIFY_CODEX_REASONING_EFFORT",
        "DESLOPPIFY_CODEX_SANDBOX",
        "DESLOPPIFY_CODEX_CLI_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("override", [None, "", "  "])
def test_inherits_codex_model_and_effort(monkeypatch, tmp_path, override):
    if override is not None:
        monkeypatch.setenv("DESLOPPIFY_CODEX_MODEL", override)
        monkeypatch.setenv("DESLOPPIFY_CODEX_REASONING_EFFORT", override)
    command = codex_batch.codex_batch_command(
        prompt="review", repo_root=tmp_path, output_file=tmp_path / "out.json"
    )
    assert "--model" not in command
    assert not any("model_reasoning_effort" in arg for arg in command)


@pytest.mark.parametrize(
    "model",
    [
        "gpt-6-astra",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.6",
        "custom-provider/future-model",
    ],
)
def test_model_override_is_passed_through(monkeypatch, tmp_path, model):
    monkeypatch.setenv("DESLOPPIFY_CODEX_MODEL", f"  {model}  ")
    command = codex_batch.codex_batch_command(
        prompt="review", repo_root=tmp_path, output_file=tmp_path / "out.json"
    )
    assert command[command.index("--model") + 1] == model
    assert not any("model_reasoning_effort" in arg for arg in command)


@pytest.mark.parametrize(
    "effort", ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
)
def test_explicit_effort_is_never_downgraded(monkeypatch, tmp_path, effort):
    monkeypatch.setenv("DESLOPPIFY_CODEX_REASONING_EFFORT", f" {effort.upper()} ")
    command = codex_batch.codex_batch_command(
        prompt="review", repo_root=tmp_path, output_file=tmp_path / "out.json"
    )
    assert f'model_reasoning_effort="{effort}"' in command
    assert "--model" not in command


def test_invalid_effort_reports_how_to_fix_it(monkeypatch, tmp_path):
    monkeypatch.setenv("DESLOPPIFY_CODEX_REASONING_EFFORT", 'max" --model other')
    with pytest.raises(CommandError, match="unset it to inherit"):
        codex_batch.codex_batch_command(
            prompt="review", repo_root=tmp_path, output_file=tmp_path / "out.json"
        )


def test_cli_path_override_preserves_paths_with_spaces(monkeypatch, tmp_path):
    executable = str(tmp_path / "Codex App" / "codex")
    monkeypatch.setenv("DESLOPPIFY_CODEX_CLI_PATH", executable)
    monkeypatch.setattr(codex_batch.shutil, "which", lambda name: name)
    command = codex_batch.codex_batch_command(
        prompt="review", repo_root=tmp_path, output_file=tmp_path / "out.json"
    )
    assert command[:2] == [executable, "exec"]


def test_windows_model_and_max_keep_prompt_on_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        codex_batch.shutil, "which", lambda _: r"C:\Program Files\codex.cmd"
    )
    monkeypatch.setenv("DESLOPPIFY_CODEX_MODEL", "gpt-6-astra")
    monkeypatch.setenv("DESLOPPIFY_CODEX_REASONING_EFFORT", "max")
    command = codex_batch.codex_batch_command(
        prompt="review prompt", repo_root=tmp_path, output_file=tmp_path / "out.json"
    )
    assert command[:2] == ["cmd", "/c"]
    assert len(command) == 3
    assert "--model gpt-6-astra" in command[2]
    assert 'model_reasoning_effort=\\"max\\"' in command[2]
    assert "review prompt" not in command[2]
    assert codex_batch._command_reads_prompt_from_stdin(command)


@pytest.mark.parametrize("workflow", ["review", "triage"])
@pytest.mark.parametrize("model", ["gpt-5.6-sol", "gpt-6-astra"])
def test_model_settings_reach_review_and_triage_processes(
    monkeypatch, tmp_path: Path, workflow, model
):
    """Exercise the real subprocess/output path using a local Codex stand-in."""
    script = tmp_path / "fake_codex.py"
    captured = tmp_path / "captured.json"
    output = tmp_path / "result.json"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "prompt = sys.stdin.read() if args[-1] == '-' else args[-1]\n"
        f"Path({str(captured)!r}).write_text(json.dumps({{'args': args, 'prompt': prompt}}))\n"
        "Path(args[args.index('-o') + 1]).write_text('{\"ok\": true}')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        codex_batch, "_resolve_executable", lambda _: [sys.executable, str(script)]
    )
    monkeypatch.setenv("DESLOPPIFY_CODEX_MODEL", model)
    monkeypatch.setenv("DESLOPPIFY_CODEX_REASONING_EFFORT", "max")
    # Force stdin even on POSIX to cover long review packets.
    prompt = "Review the immutable packet. " * 1000
    kwargs = dict(
        prompt=prompt,
        repo_root=tmp_path,
        output_file=output,
        log_file=tmp_path / "run.log",
    )
    if workflow == "triage":
        result = run_triage_stage(**kwargs, timeout_seconds=10)
        assert result.ok
    else:
        deps = codex_batch.CodexBatchRunnerDeps(
            timeout_seconds=10,
            subprocess_run=subprocess.run,
            timeout_error=subprocess.TimeoutExpired,
            safe_write_text_fn=lambda path, text: path.write_text(
                text, encoding="utf-8"
            ),
        )
        assert codex_batch.run_codex_batch(**kwargs, deps=deps) == 0
    recorded = json.loads(captured.read_text())
    assert recorded["args"][recorded["args"].index("--model") + 1] == model
    assert 'model_reasoning_effort="max"' in recorded["args"]
    expected_prompt = prompt.strip() if workflow == "triage" else prompt
    assert recorded["prompt"] == expected_prompt
    assert json.loads(output.read_text()) == {"ok": True}
