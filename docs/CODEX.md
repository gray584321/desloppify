## Codex Overlay

This is the canonical Codex overlay used by the README install command.

1. Prefer first-class batch runs: `desloppify review --run-batches --runner codex --parallel --scan-after-import`.
2. The command writes immutable packet snapshots under `.desloppify/review_packets/holistic_packet_*.json`; use those for reproducible retries.
3. Keep reviewer input scoped to the immutable packet and the source files named in each batch.
4. If a batch fails, retry only that slice with `desloppify review --run-batches --packet <packet.json> --only-batches <idxs>`.
5. Manual override is safety-scoped: you cannot combine it with `--allow-partial`, and provisional manual scores expire on the next `scan` unless replaced by trusted internal or attested-external imports.

### Models and reasoning

Review batches and automated triage inherit the model and reasoning effort from your Codex configuration. Desloppify does not pin an older model or force low reasoning. A model selected in a desktop task is not automatically passed to a separate `codex exec` process; use your Codex configuration or the environment overrides below to select it explicitly.

Use a current Codex CLI (`codex --version`) and sign in with `codex login`. Model access depends on your account and provider. Current model IDs include `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`. See the [official Codex model documentation](https://learn.chatgpt.com/docs/models) for availability and model selection.

For npm installations, upgrade with `npm install -g @openai/codex@latest`. Astra rejects older clients even when Sol works. If multiple Codex installations exist, set `DESLOPPIFY_CODEX_CLI_PATH` to the executable you want to use (for example, `/Applications/ChatGPT.app/Contents/Resources/codex` on a Mac with that app installed). An unset or blank path uses `codex` from `PATH`. The override is an executable path, not a shell command with arguments.

To use Sol for reviews and Astra for triage:

```bash
DESLOPPIFY_CODEX_MODEL=gpt-5.6-sol DESLOPPIFY_CODEX_REASONING_EFFORT=high \
  desloppify review --run-batches --runner codex --parallel --scan-after-import

DESLOPPIFY_CODEX_MODEL=gpt-6-astra DESLOPPIFY_CODEX_REASONING_EFFORT=max \
  desloppify plan triage --run-stages --runner codex
```

`DESLOPPIFY_CODEX_MODEL` passes an exact model ID to `codex exec --model`. Model IDs are not allowlisted, so custom providers and future models remain usable without a Desloppify release. Unset or blank overrides inherit Codex's settings.

`DESLOPPIFY_CODEX_REASONING_EFFORT` accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`; the selected model, provider, and installed Codex version determine which levels are supported. `none` and `minimal` are for compatible models/providers, not the current Codex model picker. Invalid values fail with an actionable error instead of silently falling back to `low`. Rejected model/effort combinations are reported without retrying or substituting another model.

Higher reasoning can take longer. Increase `--batch-timeout-seconds` for review or `--stage-timeout-seconds` for triage when needed. Review's `--batch-stall-kill-seconds 0` disables idle-output recovery while retaining the overall batch timeout. Runs that have not yet created an output file are already protected from idle-stall termination.

### Subagent policy

Do not ask Codex review or triage prompts to spawn their own child agents. The supported Codex path is the first-class batch runner above: it already isolates packet slices, supports parallel subprocess execution, preserves retry artifacts, and keeps execution guardrails outside the model prompt. Revisit this only after Codex exposes a stable non-interactive subagent contract that can cap concurrency, preserve blind-packet isolation, and retry failed child tasks without increasing cost or weakening guardrails.

Codex's `ultra` mode adds automatic delegation inside a run. Prefer `max` when you need deeper reasoning with Desloppify-managed batch isolation and concurrency; selecting `ultra` opts into Codex's additional delegation behavior.

### Sandbox

Codex batch runs default to `-s workspace-write`. On hosts where that sandbox cannot run, such as WSL1 systems without the needed Linux namespace support, set `DESLOPPIFY_CODEX_SANDBOX=danger-full-access` in an externally sandboxed environment before running review batches. Supported values are `read-only`, `workspace-write`, and `danger-full-access`; invalid values fall back to `workspace-write`.

### Triage workflow

Prefer automated triage: `desloppify plan triage --run-stages --runner codex`

Options: `--only-stages observe,reflect` (subset), `--dry-run` (prompts only), `--stage-timeout-seconds N` (per-stage).

Run artifacts go to `.desloppify/triage_runs/<timestamp>/` — each run gets its own directory with `run.log` (live timestamped events), `run_summary.json`, per-stage `prompts/`, `output/`, and `logs/`. Check `run.log` to diagnose stalls or failures. Re-running resumes from the last confirmed stage.

If automated triage stalls, check `run.log` for the last event, then use `desloppify plan triage --stage-prompt <stage>` to get the full prompt with gate rules.

<!-- desloppify-overlay: codex -->
<!-- desloppify-end -->
