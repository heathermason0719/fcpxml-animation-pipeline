---
name: fcpxml-animation-pipeline
description: Use when a user provides a Final Cut Pro rough-cut workspace, FCPXML/FCPXMLD, proxy reference video, narration subtitles or transcript, or asks whether a rough cut is ready for animation analysis.
---

# FCPXML Animation Pipeline

## Overview

Treat the user's actual project workspace as the source of context. Establish the Skill's user-visible work directory, discover and inspect existing materials before asking for files, preserve the rough cut exactly, and ask only for information that blocks reliable continuation.

This version implements project intake and readiness analysis only. Do not generate HyperFrames animation, transcode media, rewrite FCPXML, or alter a Final Cut Pro library.

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
4. Use the exact `user-inbox/YYYY-MM-DD_Vn/` directory identified by the user as the intake source. Version directories are flat: read materials from that directory itself, not from generated subdirectories. If the user has not identified a version, ask which existing version to use; do not choose the latest or invent V1.
5. Run the read-only project intake against that version directory:

   ```bash
   python3 <skill-directory>/scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
   ```

6. Read `references/project-intake.md` when interpreting the JSON report, diagnosing a blocker, or explaining a text-classification ambiguity.
7. Treat every discovered input as read-only. Creating the top-level `AfterForge/` and `user-inbox/` directories are the only permitted project mutations in this phase. Do not create files inside `AfterForge/` until a later capability explicitly requires them, and never write inside `user-inbox/`.

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
