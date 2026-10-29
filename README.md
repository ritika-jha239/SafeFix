# SafeFix

A Python issue-repair workbench. An issue URL selects the **actual public GitHub
repository**, not a bundled demo. The dashboard streams the fetched issue,
checkout commit, model analysis, test selection, generated regression, edits,
pytest results and the real unified diff. Empty issue URL selects demo mode.

## Run on Ubuntu

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m safefix.app
```

Open the local server at port 8501; leave the terminal running. Ctrl+C stops it.
Offline demos need no API key and use explicitly labeled prepared patches.

## Configure live API access

Set these in the same terminal **before** starting the server:

- `TOKEN_FACTORY_API_KEY`: enter securely; never commit it.
- `TOKEN_FACTORY_BASE_URL`: HTTPS OpenAI-compatible base URL, including `/v1`.
- `NEMOTRON_ULTRA_MODEL`: exact planner model ID from your provider.
- `NEMOTRON_NANO_MODEL`: exact repair model ID. Both roles can use one model.

Groq's base is `https://api.groq.com/openai/v1`; OpenAI's is
`https://api.openai.com/v1`. Provider compatibility requires chat completions and
JSON-object responses. Model calls include application headers; HTTP diagnostics
omit provider bodies and credentials. A configured key does not prove quota or
model access. No provider credentials were available for live validation here.

For Zsh, enter the key interactively (run this line alone, then paste and Enter):

```zsh
read -rs 'TOKEN_FACTORY_API_KEY?Paste API key: '
```

Then `echo` and `export TOKEN_FACTORY_API_KEY`. Do not put keys in browser inputs,
URLs, shell commands saved in history, Docker images or GitHub files.

## Real GitHub issue workflow

1. Enter a public `https://github.com/owner/repo/issues/123` URL. The demo picker
   becomes disabled; Live API mode is selected.
2. SafeFix reads the actual report from GitHub and clones the default branch into
   a temporary checkout. The UI records its exact commit SHA.
3. The planner gets the issue, a bounded Python path index and ranked source
   excerpts. It selects existing test files and can generate a focused regression.
   That regression is frozen before source changes.
4. Baseline tests run inside Docker. A reproduced test failure is required before
   repair. Setup/collection errors, skipped-only tests and passing baselines do
   **not** count as reproduction.
5. The repair model reads tracked Python files and edits source for up to five
   iterations. Original tests, generated regression, setup scripts and configuration
   cannot be edited through its tools. Proposed diffs stream as edits happen.
6. The same selected tests rerun. A passing suite with at least the baseline
   executed count is required for a verified selected-test result. This is not a
   guarantee that the entire issue or full repository test suite is fixed.
7. Review and approve the real diff; download the patch and execution report.
   **Issue-mode automatic GitHub publishing is not implemented.** It cannot push
   an issue patch to SafeFix's own origin by mistake.

The issue page reader currently supports public GitHub HTML pages; private issues,
rate limits, page-format changes, huge repositories and non-Python projects may
fail explicitly. File context is limited to 40KB per source file and an initial
ranked subset; the model can read other tracked files through its tools. The
workflow uses the latest default-branch revision, so an old report may already be
fixed. Read contribution policies before submitting AI-generated work upstream.

## Prepare the isolated test runner

Real repository tests never execute on the host. Install/start Docker and ensure
`docker info` works as your normal user. Build the default runner once:

```sh
docker build -t safefix-runner:local runner
```

This image includes Python 3.12 and pytest only. Project-specific runtime/test
libraries must be installed in a **derived runner image** before starting jobs.
For example, use a Dockerfile outside the checkout:

```dockerfile
FROM safefix-runner:local
RUN pip install "sympy==1.14.0"
```

Build that file as `safefix-sympy:local`, then set
`SAFEFIX_RUNNER_IMAGE=safefix-sympy:local` before starting the app. Use dependencies
appropriate to the target revision; complex pandas/scikit-learn builds need their
own prepared environments. The app never automatically runs repository install
scripts or Dockerfiles. Missing dependencies appear as actual collection/setup
errors, not model repair failures or successful fixes.

Jobs use a non-root container, disabled network, read-only source, dropped
capabilities, no-new-privileges, memory/CPU/process limits and a 90-second test
limit. No provider keys or host Git credentials are passed into the runner. Do
not expose this local prototype as a hostile multi-tenant service; containers are
not a complete security boundary. Git checkouts and model calls run server-side.

In this managed cloud environment, build with its combined CA trust secret:
`docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t safefix-runner:local runner`.
TLS verification stays enabled. Docker images and dependencies are retained;
running processes do not survive snapshots.

## Demo publishing

With an **empty issue URL**, choose one of three bundled demo repos. Tests run in
local temporary copies. Offline mode applies prepared patches; Live uses models.
The injection-bait demo's blocked command is an explicitly scripted guardrail
probe, not evidence of a model following a malicious instruction.

After tests pass, review the diff and click **I reviewed & approve this patch**.
The final **Push to GitHub** button then enables. It confirms the server checkout's
GitHub origin, verifies destination tests and pushes only the demo's solution.py
to a new `safefix/...` branch. Main is unchanged. Authentication must be configured
locally via your normal Git credential manager or SSH. Never put tokens in remote
URLs. Verified demo run IDs are held in memory (last 50), and expire on restart.

## Validation

```sh
python -m pytest -q
# Optional integration; requires the built image and working Docker daemon:
SAFEFIX_DOCKER_TESTS=1 python -m pytest tests/test_issues_docker.py -q
```

The default suite checks real-issue routing, report parsing, actual source-path
diffs, frozen regression tests, no demo fallback, non-reproduction outcomes,
provider diagnostics, demo repairs and reviewed publication to a local bare Git
remote. Real-issue model responses are simulated in unit tests; this is not a
claim of live provider validation. The Docker integration executes actual pytest.

NemoClaw, Nebius deployment, authentication, durable job storage and public-service
quotas remain future work. GitHub issue-mode publication also remains unimplemented.
