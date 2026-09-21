---
name: fcpxml-animation-pipeline
description: Plan animation for film-video series from scripts or Final Cut Pro rough cuts, review real stills and motion, apply feedback, and deliver transparent ProRes animations in verified FCPXMLD packages using the AfterForge work model.
---

# AfterForge

Work on the user's current creative goal. A project is a film series; an episode is one video; each episode can have independent production versions. Understand the episode, develop an expression, try it with real pictures and sound, revise, deliver, and retain useful experience. These activities repeat in any order. Do not narrate stage bookkeeping.

## Enter the work

Use the user's workspace and explicit episode/version selection. Inspect existing inputs before asking for files. Default writes stay in `AfterForge/`; `user-inbox/` is user-owned and read-only. Never alter original FCPXML, media, or an FCP library. Do not infer input selection from the newest folder name.

Read the concise `AfterForge/工程/创作记忆.md` first when it exists, then only relevant cases. Read this version's `frame.md` for concrete visual defaults. Series memory describes understanding and choices; it does not silently override an existing version's visual source.

When resuming a version, read `status.workingIntent.items` as well as current feedback. These mutable focus/preserve reminders are user requirements, but never approval, qualification or a production gate. Update them through `update operation: "working-intent"` with explicit `upserts` / `removeIds`; each upsert supplies stable `id`, `kind`, `text`, `locator` (readable `description`, optional object/Cue/frame/note IDs) and the actual user `source`. The writer supplies `updatedAt`. Replace only requirements superseded by the user's words, keep unrelated preserve items, and never clear them on a generic “continue”. After regrouping frames, repair locators where known; a stale locator does not block work or erase its text/source. Do not store this temporary intent in series memory or copy it into a new version automatically.

Visual specifications supply typography, color, layout and motion defaults only. Historical stage, approval or reopening instructions embedded in a copied specification have no authority over schema 3.0 work. Use this Skill and the work-model contract for operations and user decisions. When explicitly continuing a legacy project, check its root Agent instructions and series defaults before production; synchronize them only within the user's migration/cleanup authorization, leaving historical versions untouched.

Use `scripts/afterforge.py` for normal work-model operations. Read `references/work-model-contract.json` for vocabulary and `references/hyperframes-single-source.md` when authoring/rendering. No Stage Contract or stage resolver is needed for schema 3.0 work.

```bash
python3 <skill>/scripts/afterforge.py open "/workspace/AfterForge"
python3 <skill>/scripts/afterforge.py open "/workspace/AfterForge" --request-file /tmp/open.json
python3 <skill>/scripts/afterforge.py status "<version-root>"
```

The first command lists existing episodes/versions. Creation supplies `requestId`, project `expectedRevision`, and `episodeTitle`, or an existing `episodeId`. Explicit `commission: {channel, text, reference}` records cross-version copying or adoption of series defaults. A `copyFrom` request must also choose `copyMode: "restart"`, or provide `objectContinuity` for every animated target Cue as `{kind:"new"}` or `{kind:"continue",sourceObjectId:"..."}`. Continuation retains only the prior first-design qualification provenance; it never transfers a Review, approval, or Demo authorization. When defaults exist, state `useSeriesDefaults: true|false`; do not infer adoption from paths. Multiple plausible input candidates require canonical `inputSelection: {fcpxml, reference_video}`. `selections` remains a compatible alias, but if both fields are supplied their normalized complete maps must match; no field wins a conflict. Ranking is descriptive only, and delivery currently requires one Project sequence. Optional `brief` allows text-only planning; `inputDirectory` explicitly binds a user's existing input version; `copyFrom` creates a new working copy. IDs and paths are returned by the API. Input folder names, production versions and delivery numbers are different identities.

Creation never installs a runtime. Before rendering a fresh version, `update` with `operation: "runtime"` and an exact locally cached `version` initializes offline package scripts and local GSAP. If that installation has no GSAP, supply an existing local copy through `.staging/` and `vendorSource`. If unavailable, report the missing dependency; installation requires its own authorization. `runtimeIdentity` distinguishes fresh bootstrap, first enrollment and exact-byte repair from an actual runtime change; the exact pin never drifts, and only an actual change requires a new version and review of its render inputs.

## Understand and design

Start from the whole argument: what should the audience understand differently, what does the original footage show, and what does narration establish? Model meaningful segments in `brief.segments`. A segment may have zero or many animation cues. Do not allocate animation sentence by sentence or impose a fixed percentage.

Read supplied scripts and inspect the actual rough cut. Preserve intent when normalizing outdated timing or example materials. For substantial visual routing, use `references/visual-grammar.md` as an optional reasoning aid, not a required checklist. A cue-specific style has priority within its stated scope; source timing, output safety and implementation limits still apply.

Ask one focused question only when multiple reasonable interpretations would materially change the commissioned object, scope, continuity, or authorization. Decide implementation methods and reversible local creative choices yourself; do not ask again when the user already made the objective clear. Apply this equally to first design and later Review/chat feedback. Do not make the user choose static/motion categories or perform a stage rollback. Continue unaffected work while a necessary clarification is pending.

When a cue recomposes multiple excerpts, require the user's actual selection/order or exact authorized extraction ranges. A rough cut alone does not authorize invented editorial choices. Reuse coherent supplied materials without forcing them to match illustrative filenames. Additional audio production, source recutting and Handles/sourceIn placement remain out of scope.

Motion defaults: readable travel, perceptible easing, useful holding time and editing room, chosen for the cue rather than a universal duration. Purposeful drift or continuous motion is allowed when meaningful. Align the intended visual state to semantic narration anchors; retain rational FCPXML frame time. Never slow original footage without authorization.

## First design and the active creative loop

Before writing or organizing full Motion for a new creative object, present its real static design in Storyboard and obtain an explicit first design confirmation. Input readiness, existing media, a successful render, and ordinary “继续／推进” do not supply that decision or authorize a full Demo. First Storyboard must work without completed Motion or a bound rough cut: use the canonical layout, text, fonts, materials and static state to produce its hero and necessary auxiliary frames, with narration and the intended final animation description.

Keep one big Cue when it expresses a continuous animation. Use `finalAnimationDescription` for its overall intent and optional `cue.storyboard.animationNotes: [{id, frameIds, text}]` for local narration triggers, state changes and final holds. Notes may share frames; some frames need none. Maintain stable IDs and valid references in the same edit when regrouping. Notes have no independent approval or lock. Text-only edits require a new Storyboard snapshot through the normal preview entry point, which reuses verified PNGs without rendering; neither the old snapshot nor its comments silently becomes evidence for the new text. First confirmation still selects the complete current Storyboard/object; existing first qualification survives ordinary revisions.

If the user expressly commissions bounded Motion exploration before confirmation, record `explore-motion` with the actual objects, task and any time limit, and work only within that scope. It does not confirm design or accumulate into full-Demo permission. Do not call complete production an exploration. Otherwise proceed with static design and continue unaffected work.

After first confirmation, the creative object remains active through font, composition, placement, motion changes and complete redesign. Execute explicit requested changes directly, including local tests; do not require a stage rollback, another first confirmation, or completion of a page feedback round. Whether the resulting media/review is still valid is a separate question. Technical deletion, rebuilding, renaming or changing files does not decide whether it is the same creative object. Declare a known relationship; ask one focused question only when reasonable interpretations change the commissioned object, scope, continuity or authorization. Across versions, use the user's explicit commission rather than inferring inheritance.

Full Demo creation requires explicit current task intent as well as first eligibility for every animated layer being produced/presented. A clear “改完给整版” can establish that intent once together with the changes. Do not ask again for the same task or require a duplicate UI click. Record a new commission when a completed task is being extended into a future revision.

## Author once and preview

Canonical layout, text, styles and materials live in `compositions/cues/<cue>.html`; motion lives in `compositions/motion/<cue>.js`. The composition links its motion file. Static layout must be declarative: executable scripts and time-driven behavior belong to Motion and are rejected from Storyboard output. The static profile permits one-frame raster images, local SVG and fonts; animated GIF/APNG/WebP require Motion. Unsupported source capabilities fail closed. `srcset`、`image-set` and SVG resource references join the registered local closure. Rendering uses an isolated closure and restrictive CSP; this boundary does not claim to prove arbitrary JavaScript safe. Declare dependencies in `renderAdapters.hyperframes.layoutDependencies`; remote or missing assets block rendering. Publishing Motion checks the complete declared source dependency closure, not merely whether a `motionSrc` keyword appears. Copy only referenced fonts/materials. Keep needed sources local and reproducible.

Prepare files under the version's `.staging/`, then publish them with one `update` request (`operation: "edit"`, `files: [{path, source}]`, and optional `patch: {brief, cues, project}`). Do not hand-edit live manifests, evidence, jobs or releases. Descriptive changes do not alter media identities; source, duration, screen text or font changes do. Placement-only changes reuse animation MOV and rebuild composition. Existing real samples continue into production rather than being recreated in a second storyboard.

```bash
python3 <skill>/scripts/afterforge.py update "<version-root>" --request-file /tmp/update.json
python3 <skill>/scripts/afterforge.py preview "<version-root>" --request-file /tmp/preview.json
python3 <skill>/scripts/serve_workflow_review.py "/workspace/AfterForge"
```

Every writing request uses a unique `requestId` and the latest version `expectedRevision`. Retry the identical request to deduplicate. On conflict retain the proposal/comment and original location; reread and reconcile rather than silently retargeting.

Preview accepts `scope: "storyboard"`, `"exploration"`, `"full"`, or local `cueIds`/`segmentIds` or an explicit rational `range: {start,duration}`. Static frame states and Cue-local times live in `cue.storyboard.frames`; `scope: "still"` selects one Cue's registered static frames. Optional global `time` instead captures an individual sample at that exact Cue-local offset; it does not replace the required Storyboard collection. Local Motion ranges include the affected segment plus two seconds of context, clamped and snapped to source frames. Motion preview requires bound FCPXML/reference video and enough narration context. A requested presentation with missing animated layers is rejected by default. `allowDraft: true` explicitly creates only a discussion draft and cannot finish the task or create a complete review set until the target is covered. An explicit exclusion can satisfy the current commission, but never produces formal full Review coverage.

HyperFrames renders 480p cue media; FFmpeg composites all overlapping cues with original local times, layer order, rough-cut picture and sound. A complete full-length sample plus full-duration supplements for overlapping cues form the formal review set. A local sample cannot substitute for it. Do not track or claim whether the user watched everything.

## Feedback and decisions

Autonomous media playback/navigation requires a fixed sample or a supported seekable implementation; production authority alone does not make autoplay deterministic. Fixed backgrounds record source SHA and sampling time. Explicit no-narration facts may satisfy narration context without inventing placeholder copy.

Use the same `update` API for chat and page feedback. Preserve original text and `source: {channel: "chat"|"review", text, reference}`. Targets may include version, artifact, segment IDs, multiple cues, or a global interval; do not preselect one overlapping cue. The shared target resolver is used for first confirmation, approval and delivery. Record clarification and resolution on feedback; `addressed` means the Agent changed it, `accepted` requires a user decision. Keep the resolved animation description concise and separate from discussion history. A first-design confirmation requires a current valid board, a nonblank final animation description, and complete two-channel `contentContext`: `present` reads real canonical text, `none` has an evidenced basis, and `unknown` blocks confirmation. With a user `source`, `feedbackResolutions: [{feedbackId, action: "accept"|"defer"|"withdraw"}]` may resolve applicable feedback atomically with confirmation.

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

First design uses real, current Storyboard frames and an explicit `decision` with selected `storyboardIds`; it is not inferred from a feedback round. `review-submit` records a handoff of snapshots, saved feedback and valid drafts only. `review-progress` and feedback applicability record later handling without changing confirmation.

“提交本轮反馈／这轮意见提完了” hands over the fixed batch; it approves no Cue, including those without comments. Save comments as the user reviews, then process the submitted batch together unless the user directly commissions an immediate change. Apply clear feedback without asking again. For uncommented, unconfirmed objects, ask only if context still leaves the user's intent materially ambiguous. Explicit approval of several named objects is one batch decision, not repeated per-Cue paperwork. Resolving feedback records `addressed`; only explicit user acceptance of that feedback records `accepted`. Deferred or out-of-scope items retain their reason and do not block unrelated approved work.

Every animated Cue belongs to a product-level creative object. A new technical Cue states `objectRelations` as `new` or `continue` with its basis; a new design of an existing object does not by itself mean a new object. Do not infer object relationships across versions.

Keep work Cue scope, timeline scope and full-Demo presentation scope separate. Full Demo requires a stable `taskId` and explicit `authorize-demo` decision with work, presentation and exclusion Cue lists. Task recovery and necessary pre-completion recalculation reuse that basis; a future task after completion needs a new commission. “只改 A，D 不动” keeps D's valid implementation visible, whereas “Demo 先别放 D” excludes its animation layer without deleting its task. Reuse verifiable existing media by default; a missing cache may be rebuilt from the unchanged implementation. Do not design or repair other Cue sources merely because they fall into the preview's context. Missing or excluded layers make that Demo incomplete for formal approval/delivery.

Optional visual explorations compare an actual open direction question using representative frames and variants in the common Review workspace. They are not a prerequisite or approval stage. Viewing/switching candidates has no adoption effect, and comments on an unused candidate do not block canonical confirmation, approval or delivery. An explicit scoped `exploration-adopt` transaction applies the chosen direction to canonical sources; only the adopted candidate's frozen revision, content identity and object scope become relevant. It does not confer first confirmation, Demo permission, full-review approval, delivery authorization or series-wide defaults.

## Legacy boundary

Schema 2.0 data and packages stay in place. New entry points only read them; explicit `open copyFrom` creates a schema 3.0 copy without inherited approvals. Existing root Agent files are never automatically overwritten. Only to interpret historical evidence, read `references/workflow-stage-contract.md`, `references/legacy/production-v2.md`, and relevant legacy references. Old stage definitions and runtime pins retain their original meanings.

For legacy copies, the new version's frame retains visual parameters, replaces the known old review boilerplate and states its visual-only role. Other historical wording is not automatically classified or deleted. The source frame stays unchanged; legacy canonical paths and frozen visualSpec hashes are not inherited. Fresh versions use `工程/frame.md` only when the user has explicitly chosen those series defaults; a legacy root `frame.md` is not silently adopted. An explicitly authorized project cleanup may copy the reviewed root defaults there before any version is created; later series changes use `update operation: "visual-defaults"`.
