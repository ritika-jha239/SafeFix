# SafeFix

A Python issue-repair workbench designed for **Nebius Token Factory**. Give it a
public GitHub issue URL: it reads the actual report and repository, prepares an
isolated environment, discovers relevant source/tests, plans a repair, edits code
and streams actual verification evidence. There is no repository allowlist.

It can attempt Python source repairs; it does not guarantee a solution for every
issue. Missing services, credentials, unsupported build/test tooling, already-fixed
reports and failed tests remain explicit outcomes. No canned demo is substituted
for an issue URL.

## Start on Ubuntu

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure the provider in your server terminal using the
[Nebius setup guide](docs/NEBIUS.md). API keys stay server-side. Then either
prepare a repository once:

```sh
python -m safefix.prepare_runner owner/repository
python -m safefix.app
```

or enable automatic dependency preparation on an isolated Docker worker:

```sh
export SAFEFIX_AUTO_PREPARE=1
python -m safefix.app
```

Open the local UI on port 8501 and leave the terminal running. Docker must be
installed and accessible through `/var/run/docker.sock`. First-time native builds
can take several minutes. The app streams build output before making model calls.
The current HTTP server is a local prototype, not a hardened public service.

## Production provider

Nebius Token Factory is the default provider, with configurable 64KB input and
6,000 output-token budgets. Use actual model IDs from your account catalog:

- `TOKEN_FACTORY_API_KEY`: securely injected on the server; never committed.
- `SAFEFIX_PROVIDER=nebius`
- `TOKEN_FACTORY_BASE_URL=https://api.tokenfactory.nebius.com/v1`
- `SAFEFIX_PLANNER_MODEL`: planner model ID.
- `SAFEFIX_REPAIR_MODEL`: repair model ID.

Legacy `NEMOTRON_ULTRA_MODEL` / `NEMOTRON_NANO_MODEL` remain supported. Groq is an
optional test provider with smaller defaults; its limits are not imposed on
Nebius. `python -m safefix.check_provider` lists models without inference or key
output. No live Nebius call has been verified here without your credentials.
`.env.example` documents variables but is not automatically loaded.

## Actual workflow

1. Read the real issue and find/build a repository-specific Docker environment.
   Metadata detection supports pyproject/setup configuration, requirements,
   standard test extras/groups, src layouts and compatible Python selection.
2. Check out the exact revision matching the image's native build artifacts.
3. The planner lists files, searches source, reads metadata and selects tests.
   Invalid paths, malformed JSON and invalid regression syntax receive precise
   correction feedback. Projects without existing tests can use a generated one.
4. Freeze original tests and the generated regression; reproduce the failure.
5. The repair model continues discovery, applies targeted multi-file replacements
   or creates Python source files. Read-only discovery does not consume a tested
   repair round or rerun pytest unnecessarily.
6. Rerun the same tests. Only executed, passing selected tests count as verified
   evidence. This is not proof that the whole repository or issue is fixed.
7. Inspect the real diff, approve it and download the patch and execution report.
   **Issue-mode GitHub publication is not implemented.**

The UI shows actual issue details, source revision, configured provider/model,
environment logs, planner corrections, test results, diffs and blocked actions.
All repository content is treated as untrusted data; no arbitrary model shell
commands are executed. Tests run in a non-root, network-disabled, resource-limited
container. The model key is never passed into builds or test containers.

## Repository environments

`python -m safefix.prepare_runner owner/repository` accepts unknown public Python
repositories. Use `--python 3.13` or `--project-dir packages/my_library` when
needed. `--ref FULL_SHA` pins a revision. Runtime artifacts merge with the actual
edited checkout, so tests do not silently run an unmodified installed wheel.
Custom system dependencies, databases, non-pytest test runners and unusual build
systems can need a custom runner. Docker is not complete hostile multi-tenant
isolation; use deliberately isolated workers before public deployment.

The prepared pandas/scikit-learn/SymPy recipes are optional benchmark build
optimizations, not eligibility checks. `--generic` forces the generic builder.
[Five real issue evaluations](docs/REAL_ISSUES.md) include reproducible failing
baselines with zero model calls; those fixtures never drive the live UI/model.

## Offline demos and publishing

An empty issue URL explicitly selects one of three bundled demos. Offline mode
uses prepared patches, not AI; live demo mode uses the configured provider.
The bait demo's blocked action is labeled as a scripted guardrail probe.

Verified demo patches require **user patch approval** before the final GitHub push
button enables. Publishing confirms the origin, rechecks tests and creates a new
`safefix/...` branch; main is unchanged. Local Git write authentication is needed.
Run IDs are in-memory and expire on restart. Real-issue publication stays disabled
so its patch cannot accidentally go to SafeFix's own origin.

## Verification and deployment status

```sh
python -m pytest -q
# Optional; needs corresponding prepared Docker images:
SAFEFIX_DOCKER_TESTS=1 SAFEFIX_SCIENTIFIC_TESTS=1 python -m pytest -q
```

Tests cover real-issue routing, discovery/correction, source safety, bounded
provider requests, provider profiles, generic metadata, frozen regressions,
Docker source overlays and reviewed demo publishing to a local bare remote.
Unit tests simulate model responses; this is not a claim of live inference.

See [Nebius architecture and remaining deployment work](docs/NEBIUS.md).
NemoClaw, Nebius-hosted API/workers, persistent jobs, public-service controls and
issue-mode publication are not represented as implemented or deployed.
