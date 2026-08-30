# Dual-Resolution Single-Source Design

## Status

Approved by the user on 2026-08-30. Implementation must remain on `main`; the detached Terra worktree and its generated `delivery/` evidence remain untouched until this work is complete.

## Problem

The current adapter has one canonical cue file for A11 and A12, but every real cue still declares `854×480`. The manifest's `1920×1080` delivery dimensions are not part of the composition contract. HyperFrames 0.8.16 cannot turn those 854×480 alpha compositions into native 1920×1080 output with `--resolution`, so post-render enlargement creates a delivery that is correctly encoded but not natively rendered.

## Approved Contract

- Every animated canonical cue has a delivery-native `1920×1080` root. Its root dimensions must equal `project.delivery`.
- Layout and final CSS state remain in `compositions/cues/<cue>.html`; motion remains in `compositions/motion/<cue>.js`.
- A11 and A12 never own an editable layout. They are generated 854×480 projections of the canonical cue.
- A11 hero frames are captured from the canonical cue at `heroTime` through the generated review projection.
- A12 is a generated 854×480 composited review MP4 using the same cue source over the rough cut.
- Final alpha rendering uses generated delivery hosts at 1920×1080 and renders at composition resolution. It must not pass `--resolution` and must not upscale a lower-resolution movie.
- `source-only` cues remain absent from delivery rendering.
- The user performs visual acceptance. Automated checks only block missing resources, invalid dimensions, failed mounts, render errors, missing alpha, wrong codec, wrong frame rate, or wrong duration.

## Projection Model

The preview size `854×480` is an encoded approximation of 16:9, so the generated review host uses deterministic independent axis scales:

```text
scaleX = preview.width / delivery.width
scaleY = preview.height / delivery.height
```

The host for the canonical cue remains 1920×1080 and is transformed into the 854×480 review root. This keeps layout and motion in delivery coordinates and avoids a second editable implementation.

Generated delivery hosts live under `compositions/delivery/`. Each host is a full renderable composition at 1920×1080 and mounts exactly one canonical cue at `0s`. The canonical cue remains the sole editable layout source; delivery hosts are disposable projections.

## V1 Migration

The six approved V1 cues were authored in an 854×480 logical space. Rewriting every CSS value would introduce avoidable layout risk. Migration therefore wraps the existing cue contents in a deterministic legacy design stage:

```text
canonical root: 1920×1080
legacy stage:   854×480
stage scale:    1920/854 by 1080/480
```

This produces a delivery-native composition without raster upscaling. Browser text, CSS shapes, borders and shadows are painted into the 1920×1080 capture. In the 854×480 review projection, the outer downscale cancels the legacy-stage upscale, preserving the already approved composition and motion.

The compatibility stage is only for migrated cues. New cues are authored directly in 1920×1080 delivery coordinates.

Migration invalidates the existing A11 locks by design. The migrated V1 is left with A11 pending until the user approves regenerated 480p hero frames and the regenerated 480p full-motion review. Only then may the six cues receive revision 2 locks and proceed to final delivery rendering.

## Layout Lock

The lock fingerprint covers:

- canonical HTML, project CSS and local fonts in `layoutDependencies`;
- the generated review projection file;
- preview and delivery dimensions plus projection mode;
- the approved hero poster.

Changing the canonical layout, projection adapter, or either output dimension invalidates the lock. Motion files remain outside the layout lock unless they modify forbidden layout properties.

## Render Backend

The backend performs these deterministic steps per animated cue:

1. Verify the adapter and layout lock.
2. Generate the delivery host.
3. Render the host as a MOV at its native 1920×1080 composition size and source FCPXML frame rate.
4. Validate with `ffprobe`: ProRes 4444, 1920×1080, alpha pixel format, expected frame rate and cue duration within one frame.
5. Atomically promote the validated file and update a render ledger.

HyperFrames 0.8.16 already emits ProRes 4444 for transparent MOV output, so a second transcode is not part of the normal path. A future fallback transcode may be added only if a supported HyperFrames version emits another validated alpha codec; it must never resize.

## Acceptance Sequence

1. Unit and adapter tests pass.
2. Migrate V1 canonical cues and regenerate projections.
3. Generate and hand off the new 480p hero/full-motion equivalence review.
4. User approves the migrated visual result.
5. Freeze revision 2 layout locks.
6. Render one 1080p alpha cue as an engineering probe and validate it.
7. Render all six cues only after the review gate is approved.

No commit, push, FCPXML injection, Final Cut Pro import, worktree cleanup, or deletion of Terra's evidence is authorized by this implementation.
