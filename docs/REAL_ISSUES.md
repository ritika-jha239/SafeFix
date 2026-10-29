# Test the five real issues with a limited API quota

Do not switch to bundled demos. These cases use upstream source, real regression
tests and compiled dependencies where required. No fix is hardcoded.

## One-time setup

Activate SafeFix's virtual environment and ensure `docker info` succeeds. Pull the
updated code, then build the project runners (native builds can take several
minutes and require several GB of disk; each uses two compiler jobs):

```sh
git pull origin main
python -m safefix.prepare_runner --evaluation-set
```

The pinned snapshots are pandas `0988929a21cdcc933b380871a622138eb18cc207`,
scikit-learn `d685424bec8f8585d8017c1aab1db7535d3fa03d`, and
SymPy `16fa855354eb7bcabd3fe10993841e03b1382692`.
The first two snapshots are the inspected project revisions. The SymPy snapshot
is the reported 1.14.0 release. Use `--ref` with a full commit to reproduce that
version; omit it to build the current default branch. The app automatically
selects the matching project's image and pins its checkout to the image commit.
Do not set a single global `SAFEFIX_RUNNER_IMAGE` while switching these projects.
A mismatched image is rejected before spending model tokens.

Compiled pandas/sklearn wheels are built from that exact source snapshot. At test
time a temporary source tree merges its native build artifacts with the edited
checkout's Python files. Tests therefore execute the edited source, not an
unmodified installed wheel. Original checkout/test files stay unchanged on host.
The runner is non-root, network-disabled and resource-limited.

## Confirm the bugs without any API calls

```sh
python -m safefix.evaluate 71755
python -m safefix.evaluate 35143
python -m safefix.evaluate 35195
python -m safefix.evaluate 30874
python -m safefix.evaluate 30849
```

These commands run regressions derived from the linked reports; they do not ask a
model for a fix. `model_calls: 0` is included in the result. A failing assertion
or the reported exception means reproduced. Passing is reported as not reproduced,
not a successful agent repair. Missing dependencies/collection failures are setup
errors. The `evaluations/` files contain tests only, no prepared repair patches.

## Try actual model repairs

Keep the Groq key and endpoint in your server terminal. For example:

```sh
export TOKEN_FACTORY_BASE_URL="https://api.groq.com/openai/v1"
export NEMOTRON_ULTRA_MODEL="qwen/qwen3.8-27b"
export NEMOTRON_NANO_MODEL="$NEMOTRON_ULTRA_MODEL"
export SAFEFIX_INPUT_BYTES=8000
export SAFEFIX_OUTPUT_TOKENS=1500
unset SAFEFIX_RUNNER_IMAGE
python -m safefix.app
```

Use your provider's actual available model ID. Enter one of the five issue URLs
in the UI. It selects Live mode and disables the demo picker. The model develops
its own plan, regression and edits; it does not use the evaluation regressions
or prepared fixes. Inspect the revision, model plan, frozen regression, actual
pytest output and diff. Review the tests' correctness before trusting results.

Initial source context is at most 4.8KB. Requests budget message content to 8KB by
default and cap the serialized request at 14KB. On HTTP 413, one retry halves the
context and output allowance. Larger sources use search_file, targeted line reads
and edit_file exact replacements, rather than full-file rewrites. Old repair
turns do not accumulate. Limits are measured in bytes, not exact provider tokens;
no particular free-tier allowance is guaranteed. A 429 still needs time/quota.
For a stricter account try `SAFEFIX_INPUT_BYTES=3000` and
`SAFEFIX_OUTPUT_TOKENS=512`, accepting less context and shorter model output.

Test one issue at a time. The UI streams real evidence, but a model may fail to
solve a hard issue within five attempts. Issues can also be fixed upstream or
need a different Python/dependency version. Issue-mode publishing is still
unavailable; download the reviewed patch. Respect upstream contribution policies.


## Recorded baseline results

Validated on 30 October 2026 with the pinned revisions above, using zero model
calls. All reported failures below are expected regression failures, not setup
errors and not successful agent fixes.

| Issue | Tests executed | Regression failures | Collection/setup errors |
|---|---:|---:|---:|
| pandas #71755 | 3 | 3 | 0 |
| scikit-learn #35143 | 2 | 2 | 0 |
| scikit-learn #35195 | 1 | 1 | 0 |
| SymPy #30874 (1.14.0) | 1 | 1 | 0 |
| SymPy #30849 (1.14.0) | 1 | 1 | 0 |

SymPy #30874 did **not** reproduce at the initially inspected 1.15-dev revision
`8d955e7ef24b0322e4ae5e168c2b64a881c15f14`, which is why the evaluation set uses
the issue's reported 1.14 release. A passing baseline must never be represented
as the agent repairing it. Machine-readable results are in
[evaluations/results.json](../evaluations/results.json); they are a test record,
not input to the application's live UI or repair model.
