# HyperFrames Runtime Version Governance Design

## Goal

Give every AfterForge Vn one reproducible HyperFrames runtime pin, preserve its creation provenance, make later upgrades explicit and inspectable, and bind review evidence to the runtime that produced it.

## Version authority

`package.json` is the sole machine authority for the current HyperFrames runtime. Every managed npm script must contain the same exact `hyperframes@<semver>` pin. Floating tags, ranges, missing pins, and mixed pins are invalid.

`meta.json` stores provenance rather than a second mutable current-version field:

- `toolchain.hyperframes.createdWithVersion` is immutable;
- `toolchain.hyperframes.migrations` records successful explicit transitions;
- the live runtime version is derived from `package.json` and checked against the migration chain, not duplicated as another authority.

Each migration record names its `fromVersion` and `toVersion`, the concrete compatibility checks that ran, and the disposition of review evidence. A generic `validated` flag is insufficient: the record must distinguish evidence that was preserved, rebound to a proven runtime, or invalidated.

## New Vn creation

When the caller supplies an exact HyperFrames version, the scaffold uses it. Otherwise the scaffold resolves the official current version once during creation. It immediately writes that resolved exact version into every managed npm script and into `createdWithVersion`.

The scaffold performs a HyperFrames compatibility check inside its temporary staging directory before publishing the Vn. Version resolution or compatibility failure blocks creation and leaves no target Vn. It never silently falls back to a repository hard-coded version.

## Existing Vn lifecycle

Normal invocation resume reads and validates the existing exact pin, then continues on that version. It does not probe or adopt npm latest. Repository and project instructions override the generic HyperFrames auto-upgrade behavior for AfterForge Vns.

Changing an existing Vn requires an explicit migration operation. The migration verifies the current pin, changes all managed scripts atomically, runs named compatibility checks, records the transition, and reports the affected review evidence. A failed migration restores the original files and does not record a successful transition.

## Review evidence binding

A11 layout locks and cue approvals record the runtime pin that produced them. A12 and downstream input fingerprints include the same pin. A runtime change therefore makes prior locks and downstream evidence stale unless the migration can prove the existing artifacts were already produced under the target runtime.

The current real `2026-09-01_v1` is a reconciliation case: its executable pin is already `0.8.26`, and its final A11 frames and approvals were generated after that pin was installed. Governance migration may bind those current A11 records to `0.8.26` without reopening A11, while recording the concrete compatibility checks and rebound evidence fingerprint.

## Scope

This change governs HyperFrames runtime versions only. It does not upgrade the current Vn beyond `0.8.26`, render media, alter creative assets, advance workflow stages, or authorize Git operations.
