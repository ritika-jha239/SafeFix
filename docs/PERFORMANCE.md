# Cached preparation and overlapping analysis

SafeFix loads the issue report immediately, materializes a private checkout from
its local Git object cache, then runs source analysis and environment preparation
concurrently. The model plan streams as soon as it is ready. Test execution and
source repair start only after both phases finish at the same source revision.
If either phase fails, the other is cancelled between operations; an in-flight
provider call can take its request timeout to finish. Existing test and review
requirements are unchanged.

## What is cached

- **Repository objects:** one shallow fetch per repository/ref, shared across
  private working copies. Jobs never edit a shared working tree. Builds use the
  same local object cache, so they don't clone the repository from GitHub again.
- **Source feature index:** identifier/definition discovery keyed by repository
  and exact commit. Issue-specific ranking still uses the current report, and
  selected source excerpts are read from the job's actual checkout. Model answers
  and repair patches are not reused as if they were fresh analysis.
- **Prepared environment:** an immutable Docker image, indexed by repository,
  source commit, Python version, metadata, dependency/lock file hashes, platform
  and build/entrypoint recipe. Concurrent preparations for the same key share a
  cross-process build lock. A repeated preparation skips Docker build entirely.

The full commit remains in environment keys intentionally: package build hooks
and native extensions can depend on any source file. Identical dependency files
alone are not proof of native compatibility. This version does not share compiled
artifacts across arbitrary source commits. Both phases must agree on the exact
revision before tests run, and jobs use an immutable image ID to avoid tag races.

Pure-Python projects skip installing a full native compiler toolchain. Native
sources are detected from build metadata/source files; `prepare_runner --native`
forces toolchain installation for unusual projects or dependencies built from
source. A first build can still be slow. Legacy prepared images remain usable;
the content-addressed environment cache is populated by the new preparation
command when first used for that recipe/revision.

## Settings

```sh
# Ubuntu defaults to ~/.cache/safefix. Use a persistent worker volume when hosted.
export SAFEFIX_CACHE_DIR="$HOME/.cache/safefix"
export SAFEFIX_AUTO_PREPARE=1
python -m safefix.app
```

`SAFEFIX_GIT_REFRESH_SECONDS` defaults to 60 for latest-branch fetches. Explicit
commit requests use cached objects immediately. A manually prepared image pins
jobs to its recorded revision, as before; rerun preparation to choose a newer
revision, or use `SAFEFIX_REPO_REF=FULL_SHA` for an explicit request. With automatic
preparation off, a missing/mismatched environment still requires operator setup.

Use `python -m safefix.prepare_runner owner/repository --force` to rebuild a
cached environment, including its Docker build layers. No automatic destructive
cache pruning occurs. Stop active jobs before manually clearing caches. Caches
are per worker unless their backing storage/registry is explicitly shared; a
fresh serverless instance without persistent storage starts cold.

The UI separately reports repository-cache status, source-index status,
environment status and analysis status. Background build messages no longer
reactivate the issue-analysis timeline step. Build logs and model events remain
actual events, not timed animations.

Overlapping work can spend model tokens even if a dependency build later fails.
It reduces waiting; it does not eliminate provider latency, free-tier limits or
first-time compilation. On hosted Nebius workers, use persistent cache storage,
warm workers and an image registry/job queue as appropriate. Durable distributed
cache/queue orchestration is still deployment work, not a claim of this local UI.

## Verification record

On the managed worker, a repeated preparation of `pallets/itsdangerous` reused
its immutable environment in **1.81 seconds**, without invoking Docker build.
The job checkout and revision index also reused their caches, and eight real
upstream encoding tests passed using that cached image. This is a setup-cache
measurement, not a model-speed or end-to-end repair benchmark. No inference
requests were made for this measurement.

Tests cover one-fetch/private-checkout behavior, revision refresh, dependency,
recipe/Python/commit invalidation, source-index reuse, concurrent planning before
build completion, cancellation, and the gate preventing tests before readiness.
