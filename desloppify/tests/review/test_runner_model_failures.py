"""Report unsupported model settings without retrying a permanent failure."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from desloppify.app.commands.review.runner_failures import (
    classify_runner_failure,
    runner_failure_hints,
)
from desloppify.app.commands.review.runner_process_impl.attempts import (
    handle_failed_attempt,
)
from desloppify.app.commands.review.runner_process_impl.types import (
    CodexBatchRunnerDeps,
    _ExecutionResult,
)


@pytest.mark.parametrize(
    "error",
    [
        "The 'gpt-6-astra' model is not supported when using Codex with a ChatGPT account.",
        "The model `gpt-6-astra` does not exist or you do not have access to it.",
        '{"error": {"code": "model_not_found"}}',
        "Unknown model: custom-provider/typo",
        "The 'gpt-6-astra' model requires a newer version of Codex. Please upgrade to the latest app or CLI and try again.",
        "Unsupported value: 'max' is not supported with the 'gpt-5.5' model.",
        "unknown variant `max`, expected one of `low`, `medium`, `high`, `xhigh` for key `model_reasoning_effort`",
        "reasoning.effort is not supported with this model",
    ],
)
def test_model_errors_take_priority_over_empty_output_warning(error):
    log = f"{error}\nNo last agent message; wrote empty content"
    assert classify_runner_failure(log) == "model_config"


def test_model_backend_outage_remains_transient():
    assert (
        classify_runner_failure("Model server temporarily unavailable")
        == "stream_disconnect"
    )


def test_model_metadata_warning_does_not_mask_network_failure():
    log = (
        "WARN Unknown model gpt-future is used. This will use fallback model metadata.\n"
        "warning: Model metadata for `gpt-future` not found. Defaulting to fallback metadata.\n"
        "ERROR: stream disconnected before completion\n"
    )
    assert classify_runner_failure(log) == "stream_disconnect"


def test_model_failure_has_actionable_hint(tmp_path):
    (tmp_path / "batch-1.log").write_text("Unknown model: gpt-6-astra")
    hints = runner_failure_hints(failures=[0], logs_dir=tmp_path)
    assert len(hints) == 1
    assert "Update the Codex CLI" in hints[0]
    assert "DESLOPPIFY_CODEX_MODEL" in hints[0]
    assert "DESLOPPIFY_CODEX_REASONING_EFFORT" in hints[0]


def test_rejected_model_is_not_retried(tmp_path):
    sleep = Mock()
    log = tmp_path / "batch.log"
    error = "Unknown model: gpt-6-astra\nNo last agent message; wrote empty content"
    deps = CodexBatchRunnerDeps(
        timeout_seconds=60,
        subprocess_run=Mock(),
        timeout_error=TimeoutError,
        safe_write_text_fn=lambda path, text: path.write_text(text),
        sleep_fn=sleep,
    )
    code = handle_failed_attempt(
        result=_ExecutionResult(code=1, stdout_text="", stderr_text=error),
        deps=deps,
        attempt=1,
        max_attempts=3,
        retry_backoff_seconds=2,
        log_file=log,
        log_sections=[error],
    )
    assert code == 1
    sleep.assert_not_called()
    assert log.read_text() == error
