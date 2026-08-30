# Dual-Resolution Single-Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one delivery-native HyperFrames cue composition drive A11 hero frames, A12 480p review, and native 1080p alpha delivery without duplicated layouts or post-render enlargement.

**Architecture:** Canonical animated cues become 1920×1080 delivery compositions. Generated 854×480 review projections scale the same cue source, while generated 1920×1080 delivery hosts mount one cue for alpha rendering. Existing V1 cues use a deterministic legacy-stage wrapper and must be re-approved before revision 2 locks and final batch rendering.

**Tech Stack:** Python 3.11 standard library, `unittest`, HyperFrames 0.8.16, GSAP, FFmpeg/ffprobe, JSON manifest v2.

**Spec:** `docs/superpowers/plans/2026-08-30-dual-resolution-single-source-design.md`

## Global Constraints

- Canonical animated cue dimensions must equal `project.delivery` (`1920×1080` for current V1).
- A11 and A12 remain generated `854×480` projections and contain no editable layout.
- Final rendering runs at composition resolution and never uses `--resolution` or a resize filter.
- The six V1 cues require user equivalence approval before revision 2 layout locks and final batch rendering.
- The Terra worktree and its existing `delivery/` evidence remain untouched.
- Do not commit or push; the user owns both operations.
- Do not inject FCPXML or import into Final Cut Pro in this implementation.

---

### Task 1: Delivery-native dimension contract

**Files:**
- Modify: `tests/test_hyperframes_single_source.py`
- Modify: `scripts/hyperframes_adapter.py`
- Modify: `scripts/validate_hyperframes_adapter.py`
- Modify: `references/animation-manifest.schema.json`

**Interfaces:**
- Produces: `project_dimensions(manifest, kind) -> tuple[int, int]`
- Produces: `composition_dimensions(html) -> tuple[int, int]`
- Validator finding: `composition_dimensions_mismatch`

- [ ] Write a failing test whose 854×480 canonical cue is rejected against a 1920×1080 delivery contract.
- [ ] Run the focused test and confirm failure because no dimension validation exists.
- [ ] Implement dimension parsing and validation with exact integer comparison.
- [ ] Change the test fixture canonical cue to 1920×1080 and confirm the valid project passes.
- [ ] Run the focused tests and the existing single-source suite.

### Task 2: Generated review and delivery projections

**Files:**
- Modify: `tests/test_hyperframes_single_source.py`
- Modify: `scripts/sync_storyboard.py`
- Modify: `scripts/assemble_hyperframes.py`
- Create: `scripts/sync_delivery.py`

**Interfaces:**
- Produces: `projection_scale(manifest) -> tuple[Decimal, Decimal]`
- Produces: `sync_delivery(version_root: Path) -> dict[str, Any]`
- Generated files: `compositions/delivery/<cue>.html`

- [ ] Write failing tests asserting review/A12 hosts remain 854×480 while their cue mount is 1920×1080 and carries deterministic `scaleX`/`scaleY`.
- [ ] Write a failing test asserting one generated 1920×1080 delivery host per animated cue and none for source-only cues.
- [ ] Run the tests and confirm the projection behavior is absent.
- [ ] Implement shared scale formatting and generated projection HTML.
- [ ] Preserve generated-file overwrite protection for handwritten files.
- [ ] Run focused tests and confirm all projection tests pass.

### Task 3: Projection-aware layout lock

**Files:**
- Modify: `tests/test_hyperframes_single_source.py`
- Modify: `scripts/layout_lock.py`
- Modify: `references/animation-manifest.schema.json`

**Interfaces:**
- Layout lock fields: `reviewProjection`, `projectionSpec`
- `reviewProjection`: `{path, sha256}`
- `projectionSpec`: `{mode, previewWidth, previewHeight, deliveryWidth, deliveryHeight}`

- [ ] Write a failing test that freezes a lock, changes only the generated review projection, and expects verification to fail.
- [ ] Run the test and confirm the existing lock incorrectly stays valid.
- [ ] Add the review hash and literal dimension/projection metadata to freeze and verify.
- [ ] Regenerate the review before freezing and reject missing generated projections.
- [ ] Run focused and existing lock tests.

### Task 4: Native alpha render planning and validation

**Files:**
- Create: `tests/test_render_delivery.py`
- Create: `scripts/render_animations.py`
- Create: `scripts/validate_delivery.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: `build_render_jobs(version_root: Path) -> list[RenderJob]`
- Produces: `render_animations(version_root: Path, cue_ids: list[str] | None = None) -> dict[str, Any]`
- Produces: `probe_delivery(path: Path) -> dict[str, Any]`
- CLI output directory: `delivery/prores4444/`
- Ledger: `delivery/render-ledger.json`

- [ ] Write failing tests asserting only animated cues become jobs, every job targets a generated delivery host, and no command contains `--resolution` or a resize operation.
- [ ] Write failing validation tests for wrong dimensions, missing alpha, wrong codec, frame-rate mismatch and duration beyond one frame.
- [ ] Run the tests and confirm the backend modules are missing.
- [ ] Implement deterministic job planning, subprocess injection, atomic output promotion, ffprobe parsing and ledger writing.
- [ ] Require a valid adapter and valid layout locks before a final render job runs.
- [ ] Run the render backend tests and complete unit suite.

### Task 5: Reusable legacy-stage migration

**Files:**
- Create: `tests/test_migrate_delivery_layout.py`
- Create: `scripts/migrate_delivery_layout.py`

**Interfaces:**
- Produces: `migrate_delivery_layout(version_root: Path) -> dict[str, Any]`
- Marker: `data-afterforge-legacy-stage="854x480"`

- [ ] Write a failing fixture test proving cue content and motion selectors survive conversion from an 854×480 root to a 1920×1080 root.
- [ ] Assert a second run is idempotent and incompatible dimensions block without partial writes.
- [ ] Run the tests and confirm the migration module is absent.
- [ ] Implement preflight for all animated cues, atomic file replacement, lock invalidation and A11 pending state.
- [ ] Run migration tests and full unit suite.

### Task 6: Documentation and adapter verification

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CURRENT.md`
- Modify: `docs/DECISIONS.md`
- Modify: `references/hyperframes-single-source.md`

**Interfaces:**
- Documents the permanent A11/A12 projection and native-delivery contract.
- Adds exact migration, delivery sync, render and validation commands.

- [ ] Update stable workflow and architecture documents after tests establish the behavior.
- [ ] Run `python3 -m unittest discover -s tests -v`.
- [ ] Run the Skill quick validator, `git diff --check`, and inspect `git status`.

### Task 7: Real V1 migration and review handoff

**Files:**
- Modify outside repository: `/Users/xiaobaimac/Movies/trumen/AfterForge/2026-08-26_V1/animation-manifest.json`
- Modify outside repository: six canonical cue HTML files and generated review/delivery projections
- Generate outside repository: a new 854×480 migration-equivalence review MP4 and hero captures

**Interfaces:**
- Consumes: the verified scripts from Tasks 1–6.
- Produces: a migrated V1 with A11 pending, no revision 2 lock until user approval.

- [ ] Run migration preflight, preserve hashes of original canonical cue files, then execute the migration.
- [ ] Regenerate Storyboard, A12 host and delivery hosts; run adapter checks that do not require approved locks.
- [ ] Render the 854×480 equivalence review and capture each hero frame.
- [ ] Run one temporary 1920×1080 alpha engineering probe without promoting it as final delivery.
- [ ] Validate probe dimensions, ProRes 4444 codec, alpha, 24 fps and duration.
- [ ] Hand the 480p review and probe evidence to the user; stop before revision 2 locks or six-cue final rendering.

## Self-review

- Spec coverage: canonical delivery dimensions, generated review/delivery projections, V1 compatibility, projection lock, native alpha rendering and user re-approval each map to a task.
- Placeholder scan: no deferred implementation steps or unspecified error handling remain.
- Interface consistency: projection dimensions come from manifest helpers; sync, lock, validator and renderer share the same adapter paths and generated host contract.
