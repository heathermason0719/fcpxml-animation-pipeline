---
name: fcpxml-animation-pipeline
description: Use when a user provides a Final Cut Pro rough-cut workspace, FCPXML/FCPXMLD, proxy reference video, narration subtitles or transcript, or asks whether a rough cut is ready for animation analysis.
---

# FCPXML Animation Pipeline

## Overview

Treat the user's actual project workspace as the source of context. Establish the Skill's user-visible work directory, discover and inspect existing materials before asking for files, preserve the rough cut exactly, and ask only for information that blocks reliable continuation.

This version implements one-time AfterForge project instructions, project intake and readiness analysis, an isolated HyperFrames Vn scaffold, native transparent delivery rendering, and a deterministic FCPXMLD delivery backend. Never alter a Final Cut Pro library directly. Render, register, or build a new FCPXMLD only in the implemented phase and with the user's current authorization.

## Start From the Workspace

1. Obtain the project workspace directory. If the user already supplied it, do not ask for individual files first.
2. Create or recognize the user-visible work directory:

   ```bash
   python3 <skill-directory>/scripts/init_user_workspace.py "/absolute/project/workspace"
   ```

   The default display name is `AfterForge`. Treat it only as a replaceable directory name. Keep the Skill ID, repository name, schemas, fields, and internal references as `fcpxml-animation-pipeline`. If the command returns `existing`, reuse the directory without changing its contents. If it returns `blocked`, report its concrete error and stop.
3. Create or recognize the user-maintained input directory:

   ```bash
   python3 <skill-directory>/scripts/init_user_inbox.py "/absolute/project/workspace"
   ```

   `user-inbox/` and everything below it are user-owned and Skill-read-only. If the command returns `existing`, leave every existing version and file unchanged. If it returns `blocked`, report its concrete error and stop. Never create, increment, rename, move, or delete a version directory.
4. Initialize the AfterForge project-level Agent instructions once:

   ```bash
   python3 <skill-directory>/scripts/init_afterforge_project.py "/absolute/project/workspace"
   ```

   This command owns only `<display-name>/AGENTS.md` and `<display-name>/CLAUDE.md`. It creates a missing file but preserves every existing file byte-for-byte. It must not create or update canonical `frame.md`, any Vn directory, manifest, storyboard, composition, or media asset. If it returns `blocked`, report its concrete error and stop.
5. Use the exact `user-inbox/YYYY-MM-DD_Vn/` directory identified by the user as the intake source. Version directories are flat: read materials from that directory itself, not from generated subdirectories. If the user has not identified a version, ask which existing version to use; do not choose the latest or invent V1.
6. Run the read-only project intake against that version directory:

   ```bash
   python3 <skill-directory>/scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
   ```

7. Read `references/project-intake.md` when interpreting the JSON report, diagnosing a blocker, or explaining a text-classification ambiguity.
8. Treat every discovered input as read-only. The only permitted project mutations in this phase are creating the top-level `AfterForge/` and `user-inbox/` directories and initializing the two project-level Agent instruction files described above. Never write inside `user-inbox/`.

## Create an Approved Vn Scaffold

After the user has approved the project's canonical `AfterForge/frame.md` and identified the target `YYYY-MM-DD_Vn`, create that version with:

```bash
python3 <skill-directory>/scripts/scaffold_hyperframes.py "/absolute/project/workspace" "YYYY-MM-DD_Vn"
```

The command creates only a previously absent `AfterForge/YYYY-MM-DD_Vn/`. It copies the current canonical `frame.md` and project fonts as version snapshots, fixes the HyperFrames CLI version in the local package scripts, and creates the minimum independently checkable project structure. If canonical `frame.md` is missing or the target already exists, stop on the returned `blocked` result. Never call generic `hyperframes init` as a substitute, merge into an existing Vn, generate or update project-level `AGENTS.md` or `CLAUDE.md`, or write inside `user-inbox/`.

## Route Animation Design Before Choosing Form

When subsequent workflow capabilities turn aligned content into animation proposals, read `references/visual-grammar.md` before proposing the project's visual direction or designing individual cues.

Use two internal passes without adding a user gate. Before A8, identify each candidate cue's information function and relationship to the source image so the project-level visual package is grounded in the video's actual needs. After A8 approves that package, choose useful reference language within the approved `frame.md` and complete the route before designing the concrete cue. Choose one primary function and one primary source relationship; secondary functions and a mixed source relationship are allowed only when they remain subordinate and have a stated reason. Preserving source visibility alone does not make a cue source-led; apply the reference's double-deletion test before using a mixed relationship. Treat both indexes as open vocabularies rather than fixed enums.

Record the resulting route in the draft manifest and expose it through the existing A11 storyboard review together with real copy and static keyframes. Do not add a per-cue approval step. Ask separately only when a branch would materially change scope, violate an approved constraint, or create a hard-to-reverse consequence. Do not copy the cross-project grammar into project `frame.md`; that file records only the current video's approved visual package.

## Deliver A8 and A11 for User Review

At A8 and A11, prioritize handing the reviewable result to the user promptly. Run low-cost deterministic checks only when they are immediately available; treat their findings as non-blocking self-checks unless they prove that the user cannot review the result.

Block delivery only for an observable review failure, such as a storyboard that cannot open, a critical referenced asset that is missing, or a page with an obvious runtime error that prevents the intended result from being viewed. A lint/check command failure, browser-automation failure, screenshot mismatch, aesthetic uncertainty, or an Agent's own content/structure/visual review does not block delivery when the user can still inspect the result. Do not repeat checks to decide whether the work is attractive, polished, or visually approved; aesthetic approval belongs to the user. After making an A8 or A11 revision, hand it back for review as soon as the result remains viewable.

## Build A11 and A12 From One Layout Source

Before authoring or revising an A11 storyboard frame or an A12 animation, read `references/hyperframes-single-source.md`. For every animated cue, author the final copy, DOM, layout, and CSS end state only in `compositions/cues/<cue>.html`. Put timing and motion in `compositions/motion/<cue>.js`; motion must not rewrite layout properties. Generate `compositions/review/`, `STORYBOARD.md`, and the composited `index.html` from manifest v2 with the deterministic scripts. Never hand-maintain a second A11 layout or copy its DOM/CSS into A12.

After the user approves A11, freeze the canonical cue and its declared styles/fonts with `layout_lock.py freeze` using the approved hero poster. If a later change invalidates the lock, return the affected cue to A11 review instead of silently moving dependent elements. Cues explicitly approved as source-only have no formal composition, motion file, or render slot.

Every new animated canonical cue must declare the exact `project.delivery` dimensions, currently 1920×1080 for horizontal self-media projects. `sync_storyboard.py` and `assemble_hyperframes.py` generate 854×480 projections that scale the delivery-native cue; they never own editable layout. Before final rendering, run `sync_delivery.py` to generate one renderable 1920×1080 host per animated cue. Render only after the 480p full-motion review is approved and every projection-aware layout lock verifies. `render_animations.py` renders at composition resolution and must not use HyperFrames `--resolution` or a post-render resize.

When an older Vn still has 854×480 canonical cues, run `migrate_delivery_layout.py`. The migration wraps the existing layout in a deterministic delivery-native stage, invalidates the old A11 locks, and requires a new 480p equivalence review. Do not freeze revision 2 locks or batch-render delivery files until the user approves that regenerated review.

## Register and Build the FCPXMLD Delivery

After the user approves the full-motion review and native transparent MOV rendering succeeds, register the actual media before FCPXML injection:

```bash
python3 <skill-directory>/scripts/register_delivery_assets.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
```

The registrar is the only delivery step allowed to consume `delivery/render-ledger.json`. It verifies every animated MOV again, records stable `deliveryAsset` data in the main manifest, and leaves every `source-only` cue unregistered. Registration must not invalidate or rewrite A11 layout locks.

Then build the formal package:

```bash
python3 <skill-directory>/scripts/build_delivery_package.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
```

The builder verifies the source FCPXML hash, complete A11 approval, registered media hashes, exact rational placement, positive lane allocation, source-sequence preservation, flat package contents, references, and the Final Cut Pro bundled DTD. It publishes only a new `AfterForge__<sourceVersion>__d-<fingerprint>.fcpxmld` directly under project-level `AfterForge/`. The package contains only `Info.fcpxml` and the animated MOV files; it never overwrites a package, source FCPXML, canonical MOV, or Final Cut Pro Library. A same-fingerprint package is reusable only after complete validation.

The first real import for a protocol version remains a user acceptance gate. Ask the user to import the new Project, verify media/alpha/editability and the absence of source-only placeholders, then export that imported Project as FCPXML. Compare the re-export with:

```bash
python3 <skill-directory>/scripts/compare_fcpxml_roundtrip.py "/absolute/project/workspace/AfterForge/AfterForge__YYYY-MM-DD_Vn__d-<fingerprint>.fcpxmld/Info.fcpxml" "/absolute/reexported.fcpxml" "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn/animation-manifest.json"
```

Do not describe the FCPXML delivery capability as fully accepted for a new protocol version until this manual import and semantic round-trip pass.

## Decide Whether to Ask

Use the report fields as the decision contract:

- `status: ready`: begin subsequent content analysis with the selected files. Do not ask for an animation brief, storyboard, brand kit, output codec, or duplicate narration format.
- `status: blocked`: ask only the concrete questions in `questions`. Explain the matching `blockers[].why` and stop until the required input is available or uniquely identified.
- `ambiguities`: preserve each item and its evidence. Ask about a specific item only when later analysis cannot proceed reliably without resolving it; do not turn the list into generic setup questions.
- `warnings`: state relevant limitations, then continue. A warning is not permission to request optional material.

## Input Policy

| Material | Intake rule |
|---|---|
| FCPXML or FCPXMLD | Required. Discover it in the workspace; request it only when missing or genuinely ambiguous. |
| Low-bitrate rough-cut reference video | Required. Use it to understand selected shots and adjacent visual context without scanning the full source film. |
| Narration SRT, timeline captions, transcript, or manuscript | Alternative evidence sources. Reuse whichever existing source is sufficient; never demand duplicate forms. |
| Marker, timeline text, notes, or design ideas | Optional constraints. Discover and preserve them when present. Their absence is not missing information. |
| Animation brief or shot-by-shot design | Never a default intake requirement. When supplied, preserve it in `materials.animation_guidance` even when an SRT already exists; its timecodes never override FCPXML. |

If no narration text is found but the selected reference video can provide narration audio for later transcription, keep intake ready and report the limitation instead of asking preemptively for duplicate text.

## Preserve the Rough Cut

Interpret explicit `<gap>` elements and interior timing holes between primary spine clips as candidate animation spaces. Record their exact timeline offsets and durations. Do not close gaps, move clips, replace shots, or perform creative recutting.

Classify timeline text only from inspectable evidence:

- `narration_subtitle`: caption element, subtitle role/name, or verified external-text match;
- `design_text`: design-oriented role/name, Marker, note, or instruction-like material;
- `ambiguous`: insufficient or conflicting evidence.

Keep ambiguous text unchanged and expose the reason. Never infer certainty from typography, placement, or intuition alone.

## Intake Result

At the end of intake, report:

1. selected FCPXML/FCPXMLD and reference video;
2. narration sources, animation guidance, notes, Markers, timeline text, and detected gaps;
3. readiness status and any exact blocker;
4. unresolved text items with evidence and reason;
5. the unchanged boundary: no animation rendering and no FCPXML write-back in this phase.
