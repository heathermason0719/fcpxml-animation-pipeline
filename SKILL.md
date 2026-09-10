---
name: fcpxml-animation-pipeline
description: Plan animation for film-video series from scripts or Final Cut Pro rough cuts, review real stills and motion, apply feedback, and deliver transparent ProRes animations in verified FCPXMLD packages using the AfterForge work model.
---

# AfterForge

Work on the user's current creative goal. A project is a film series; an episode is one video; each episode can have independent production versions. Understand the episode, develop an expression, try it with real pictures and sound, revise, deliver, and retain useful experience. These activities repeat in any order. Do not narrate stage bookkeeping.

## Enter the work

Use the user's workspace and explicit episode/version selection. Inspect existing inputs before asking for files. Default writes stay in `AfterForge/`; `user-inbox/` is user-owned and read-only. Never alter original FCPXML, media, or an FCP library. Do not infer input selection from the newest folder name.

Read the concise `AfterForge/工程/创作记忆.md` first when it exists, then only relevant cases. Read this version's `frame.md` for concrete visual defaults. Series memory describes understanding and choices; it does not silently override an existing version's visual source.

Visual specifications supply typography, color, layout and motion defaults only. Historical stage, approval or reopening instructions embedded in a copied specification have no authority over schema 3.0 work. Use this Skill and the work-model contract for operations and user decisions. When explicitly continuing a legacy project, check its root Agent instructions and series defaults before production; synchronize them only within the user's migration/cleanup authorization, leaving historical versions untouched.

Use `scripts/afterforge.py` for normal work-model operations. Read `references/work-model-contract.json` for vocabulary and `references/hyperframes-single-source.md` when authoring/rendering. No Stage Contract or stage resolver is needed for schema 3.0 work.

```bash
python3 <skill>/scripts/afterforge.py open "/workspace/AfterForge"
python3 <skill>/scripts/afterforge.py open "/workspace/AfterForge" --request-file /tmp/open.json
python3 <skill>/scripts/afterforge.py status "<version-root>"
```

The first command lists existing episodes/versions. Creation supplies `requestId`, project `expectedRevision`, and `episodeTitle`, or an existing `episodeId`. Optional `brief` allows text-only planning; `inputDirectory` explicitly binds a user's existing input version; `copyFrom` creates a new working copy. IDs and paths are returned by the API. Input folder names, production versions and delivery numbers are different identities.

Creation never installs a runtime. Before rendering a fresh version, `update` with `operation: "runtime"` and an exact locally cached `version` initializes offline package scripts and local GSAP. If that installation has no GSAP, supply an existing local copy through `.staging/` and `vendorSource`. If unavailable, report the missing dependency; installation requires its own authorization. Production pins never drift. An explicitly requested runtime change uses a new version and requires new review of its render inputs.

## Understand and design

Start from the whole argument: what should the audience understand differently, what does the original footage show, and what does narration establish? Model meaningful segments in `brief.segments`. A segment may have zero or many animation cues. Do not allocate animation sentence by sentence or impose a fixed percentage.

Read supplied scripts and inspect the actual rough cut. Preserve intent when normalizing outdated timing or example materials. For substantial visual routing, use `references/visual-grammar.md` as an optional reasoning aid, not a required checklist. A cue-specific style has priority within its stated scope; source timing, output safety and implementation limits still apply.

Ask one focused question only when missing information changes creative meaning, material selection, or reliable implementation. Apply this equally to first design and later Review/chat feedback. Do not make the user choose static/motion categories or perform a stage rollback. Continue unaffected work while a necessary clarification is pending.

When a cue recomposes multiple excerpts, require the user's actual selection/order or exact authorized extraction ranges. A rough cut alone does not authorize invented editorial choices. Reuse coherent supplied materials without forcing them to match illustrative filenames. Additional audio production, source recutting and Handles/sourceIn placement remain out of scope.

Motion defaults: readable travel, perceptible easing, useful holding time and editing room, chosen for the cue rather than a universal duration. Purposeful drift or continuous motion is allowed when meaningful. Align the intended visual state to semantic narration anchors; retain rational FCPXML frame time. Never slow original footage without authorization.

## Author once and preview directly

Canonical layout, text, styles and materials live in `compositions/cues/<cue>.html`; motion lives in `compositions/motion/<cue>.js`. The composition links its motion file. Declare dependencies in `renderAdapters.hyperframes.layoutDependencies`; remote or missing assets block rendering. Copy only referenced fonts/materials. Keep needed sources local and reproducible.

Prepare files under the version's `.staging/`, then publish them with one `update` request (`operation: "edit"`, `files: [{path, source}]`, and optional `patch: {brief, cues, project}`). Do not hand-edit live manifests, evidence, jobs or releases. Descriptive changes do not alter media identities; source, duration, screen text or font changes do. Placement-only changes reuse animation MOV and rebuild composition. Existing real samples continue into production rather than being recreated in a second storyboard.

```bash
python3 <skill>/scripts/afterforge.py update "<version-root>" --request-file /tmp/update.json
python3 <skill>/scripts/afterforge.py preview "<version-root>" --request-file /tmp/preview.json
python3 <skill>/scripts/serve_workflow_review.py "/workspace/AfterForge"
```

Every writing request uses a unique `requestId` and the latest version `expectedRevision`. Retry the identical request to deduplicate. On conflict retain the proposal/comment and original location; reread and reconcile rather than silently retargeting.

Preview accepts `scope: "full"`, local `cueIds`/`segmentIds` or explicit rational `range: {start,duration}`, and `scope: "still"` with one cue and optional global `time`. Local ranges include the affected segment plus two seconds of context, clamped and snapped to source frames. Production preview requires bound FCPXML/reference video and enough narration context. Static approval never blocks motion discussion. `allowDraft: true` explicitly records unfinished cues and cannot create a complete review set.

HyperFrames renders 480p cue media; FFmpeg composites all overlapping cues with original local times, layer order, rough-cut picture and sound. A complete full-length sample plus full-duration supplements for overlapping cues form the formal review set. A local sample cannot substitute for it. Do not track or claim whether the user watched everything.

## Feedback and decisions

Use the same `update` API for chat and page feedback. Preserve original text and `source: {channel: "chat"|"review", text, reference}`. Targets may include version, artifact, segment IDs, multiple cues, or a global interval; do not preselect one overlapping cue. Record clarification and resolution on feedback; `addressed` means the Agent changed it, `accepted` requires a user decision. Keep the resolved animation description concise and separate from discussion history.

Approval and authorization bind the current verified complete review set. `operation: "decision", kind: "approve"` records picture approval only; `authorize` requires that set already approved. A clear instruction to approve and produce this delivery is supplied as `decision: {kind: "approve-and-deliver", reviewSetId, source}` to `deliver`. Never infer authorization from freezing, successful rendering, historical approval, or a positive reaction to an image.

```bash
python3 <skill>/scripts/afterforge.py deliver "<version-root>" --request-file /tmp/deliver.json
python3 <skill>/scripts/afterforge.py resume "<version-root>" --request-file /tmp/resume.json
```

Resume uses `jobId` and current `expectedRevision`. Jobs retain verified cue results after failure. Changed inputs require a new request and reuse unaffected media. Final delivery covers every animated cue, verifying native 1920×1080 ProRes 4444, exact source frame rate/duration, decoded alpha, source timeline invariance, placement, references, DTD and package inventory. No-animation episodes return “无需动画交付”.

## Deliver and learn

Packages are under `AfterForge/交付/<episode>/交付NNNN/`; independent MOV links appear in Review. `releases/` saves immutable source, review and delivery snapshots outside FCPXMLD. Identical delivery input reuses the verified package. Current drafts can change without rewriting releases or waiting for FCP acceptance.

Record actual import acceptance through `update operation: "decision", kind: "accept-import", deliveryId, source`. Protocol 2 requires a first actual FCP re-export; register via `update operation: "roundtrip", deliveryId, reexportedPath, source`. Only actual verified evidence establishes the series protocol baseline. Automated tests cannot replace FCP import.

When useful after an episode, update the single series memory with a short case: why a choice worked or was abandoned, applicability, and its feedback/finished-work source. Distinguish confirmed preferences from hypotheses. Do not turn one approval into a universal rule, load every old conversation, add mandatory retrospective forms, or use the old “电影解读视觉策划探索沉淀” as default guidance.

## Legacy boundary

Schema 2.0 data and packages stay in place. New entry points only read them; explicit `open copyFrom` creates a schema 3.0 copy without inherited approvals. Existing root Agent files are never automatically overwritten. Only to interpret historical evidence, read `references/workflow-stage-contract.md`, `references/legacy/production-v2.md`, and relevant legacy references. Old stage definitions and runtime pins retain their original meanings.

For legacy copies, the new version's frame retains visual parameters, replaces the known old review boilerplate and states its visual-only role. Other historical wording is not automatically classified or deleted. The source frame stays unchanged; legacy canonical paths and frozen visualSpec hashes are not inherited. Fresh versions use `工程/frame.md`; a legacy root `frame.md` is not silently adopted. An explicitly authorized project cleanup may copy the reviewed root defaults there before any version is created; later series changes use `update operation: "visual-defaults"`.
