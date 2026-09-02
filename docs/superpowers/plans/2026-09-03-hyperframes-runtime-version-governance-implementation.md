# HyperFrames Runtime Version Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HyperFrames version selection reproducible at Vn creation and explicit, evidence-aware, and non-automatic thereafter.

**Architecture:** A focused runtime helper parses exact pins, resolves a creation version, and validates metadata. The scaffold consumes it before atomically publishing a new Vn. Layout locks and workflow fingerprints bind the pin, while an explicit migration script owns later transitions and their evidence disposition.

**Tech Stack:** Python 3 standard library, JSON, unittest, npm/HyperFrames CLI at external boundaries.

**Spec:** `docs/superpowers/plans/2026-09-03-hyperframes-runtime-version-governance-design.md`

## Global Constraints

- Current real Vn stays pinned to HyperFrames `0.8.26`.
- Existing Vns never adopt `latest` during ordinary resume.
- New Vns resolve once and store an exact version; resolution failure does not fall back silently.
- Migration records enumerate compatibility checks and review-evidence disposition instead of using an ambiguous aggregate `validated` state.
- No render, workflow-stage advance, commit, push, merge, or rebase is authorized.

---

### Task 1: Runtime pin contract and create-time resolution

**Files:**
- Create: `scripts/hyperframes_runtime.py`
- Create: `tests/test_hyperframes_runtime.py`
- Modify: `tests/test_hyperframes_single_source.py`

**Interfaces:**
- Produces `read_runtime_pin(version_root: Path) -> str` for validators and evidence binding.
- Produces `resolve_creation_version(explicit_version: str | None, runner=...) -> str` for the scaffold.
- Produces metadata and migration validation helpers consumed by the explicit migration path.

- [x] Write failing tests for exact uniform pins, mixed/floating rejection, explicit-version resolution, and one-time latest resolution.
- [x] Run the focused tests and verify the expected missing-module or missing-behavior failures.
- [x] Implement the smallest parser and resolver that satisfy the contract.
- [x] Run the focused tests to green.

### Task 2: Atomic new-Vn version selection

**Files:**
- Modify: `scripts/scaffold_hyperframes.py`
- Modify: `tests/test_scaffold_hyperframes.py`

**Interfaces:**
- Consumes `resolve_creation_version`.
- Produces `meta.json.toolchain.hyperframes.createdWithVersion` and an exact package pin.

- [x] Write failing tests showing that default creation resolves one exact version, records provenance, runs compatibility checking in staging, and leaves no Vn on failure.
- [x] Run the focused tests and verify the old hard-coded default fails them.
- [x] Replace the hard-coded default path with injected resolution and compatibility checking while retaining the explicit CLI override.
- [x] Run the focused tests to green.

### Task 3: Bind review evidence to runtime

**Files:**
- Modify: `scripts/layout_lock.py`
- Modify: `scripts/workflow_review.py`
- Modify: `scripts/workflow_status.py`
- Modify: `tests/test_hyperframes_single_source.py`
- Modify: `tests/test_workflow_status.py`

**Interfaces:**
- Layout locks and cue approvals expose `runtimeVersion`.
- `current_input_fingerprint` includes the live exact runtime pin.

- [x] Write failing tests showing a pin change invalidates A11 locks and A12/downstream fingerprints.
- [x] Run the focused tests and verify current code incorrectly preserves the evidence.
- [x] Add runtime binding to lock creation, verification, cue approval, and input fingerprints.
- [x] Run the focused tests to green.

### Task 4: Explicit observable migration

**Files:**
- Create: `scripts/migrate_hyperframes_runtime.py`
- Create: `tests/test_migrate_hyperframes_runtime.py`

**Interfaces:**
- Produces `migrate_hyperframes_runtime(version_root: Path, target_version: str, ...) -> dict`.
- Records named `compatibilityChecks` and `reviewEvidence` lists grouped as preserved, rebound, and invalidated.

- [x] Write failing tests for explicit migration, compatibility-check rollback, review invalidation, and evidence-aware reconciliation.
- [x] Run the focused tests and verify the migration API is absent.
- [x] Implement atomic pin rewriting, named checks, metadata recording, and evidence disposition.
- [x] Run the focused tests to green.

### Task 5: Invocation policy and documentation

**Files:**
- Modify: `SKILL.md`
- Modify: `assets/afterforge-project/AGENTS.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/CURRENT.md`

**Interfaces:**
- Formal invocations discover that existing Vns remain on their pin and upgrades use only the explicit migration command.
- Repository command documentation exposes creation and migration verification paths.

- [x] Update the existing authoritative documents without duplicating a current version constant.
- [x] Add the migration command to repository verification commands.
- [x] Run documentation projection and repository validation commands.

### Task 6: Reconcile the current real Vn and verify

**Files:**
- Modify: `/Users/xiaobaimac/Movies/trumen/AfterForge/2026-09-01_v1/meta.json`
- Modify: `/Users/xiaobaimac/Movies/trumen/AfterForge/2026-09-01_v1/animation-manifest.json`

**Interfaces:**
- Reconciles creation provenance `0.8.16` with current runtime pin `0.8.26`.
- Rebinds current A11 evidence only after concrete checks prove it was produced under `0.8.26`.

- [x] Capture pre-migration hashes and workflow status.
- [x] Run the explicit reconciliation with named compatibility checks and A11 evidence binding.
- [x] Verify the package remains pinned to `0.8.26`, A11 remains current, and resolver remains blocked at A12.
- [x] Run the full unittest suite, quick skill validation, `git diff --check`, and inspect the complete repository and Vn diffs.
