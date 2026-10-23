"""AfterForge's shared application API: work, feedback, artifacts and releases.

The HTTP server and CLI both call this module.  User decisions are explicit
records; neither file freezing nor rendering manufactures an approval.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import uuid
from contextlib import nullcontext
from pathlib import Path

from scripts.manifest_transaction import manifest_transaction
from scripts.work_model_store import (atomic_bytes, atomic_json, digest, layout, load, now,
                                     project_lock, remember, request_check, safe, save, sha, user_source, verified_operation)
from scripts.work_model_inputs import animation_cues, dependencies, timeline_key


MEMORY_SEED = """# 系列创作记忆

## 当前理解

按本集目标记录理解；尚无用户确认的系列创作历史。

## 已确认偏好及适用范围

仅记录用户明确表达的选择、范围与出处，不把单次批准推广成长期偏好。

## 案例与取舍

按需记录采用、放弃原因与成片反馈。Agent 推测须明确标注。
"""

# Rebuildable process-local UI projection. Production decisions never read it.
_DISPLAY_CACHE = {}


def _display_signature(root, afterforge):
    paths = [root / name for name in ("animation-manifest.json", "package.json", "hyperframes.json", "frame.md")]
    paths += [afterforge / "工程" / name for name in ("project.json", "创作记忆.md", "frame.md")]
    for folder in ("compositions", "assets", "previews"):
        paths.extend(p for p in (root / folder).rglob("*") if p.is_file())
    paths.extend((root / "jobs").glob("*.json"))
    result = []
    for path in sorted(paths):
        try:
            stat = path.stat()
            result.append((str(path), stat.st_size, stat.st_mtime_ns, stat.st_ino))
        except OSError:
            result.append((str(path), None))
    return tuple(result)


def _identifier(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12]


def _blank(identity):
    return {"schemaVersion": "3.0", "workModelVersion": "2.2.0", "sourceVersion": None,
            "identity": identity, "editRevision": 0,
            "project": {"source": None, "preview": {"width": 854, "height": 480},
                        "delivery": {"width": 1920, "height": 1080}},
            "brief": {"summary": "", "segments": []}, "cues": [], "artifacts": [], "reviewSets": [],
            "feedback": [], "decisions": [], "deliveries": [], "requests": {},
            "creativeObjects": [], "concepts": [], "storyboards": [], "storyboardHandoffs": [], "sceneReviews": [], "reviewRounds": [], "explorations": [], "productionRuns": []}


def _legacy_visual_defaults(text):
    """Adapt the known legacy boilerplate, never classify arbitrary design prose."""
    old_review = (
        "A8 确认整体方向，A11 通过真实文案与静态主审/辅助帧确认实际画面，"
        "A13 审核全运动 Demo，A14 独立授权原生渲染。任何机器验证不能替代用户审美批准。"
        "Review 外壳属于仓库基础设施，不随项目视觉变更。"
    )
    text = text.replace(old_review, "任何机器验证不能替代用户审美批准。Review 外壳属于仓库基础设施，不随项目视觉变更。")
    notice = (
        "\n<!-- afterforge:work-model-visual-defaults -->\n"
        "本副本从历史版本仅继承视觉与运动默认。文中的历史阶段、静态冻结、storyboard 审批及重开要求"
        "不作为本副本的工作指令；schema 3.0 的操作、反馈和交付以当前 Skill 与 work model 2.2 合同为准。"
        "新 2.2 制作先确认真实概念图再发布代码；Storyboard 检查实际制作，普通实现反馈沿用概念确认。正式交付仍需当前完整审阅集合的用户批准与制作授权。\n\n"
    )
    # Keep YAML byte-for-byte at the start for consumers of visual tokens.
    lines = text.splitlines(keepends=True)
    offset = 1 if text.startswith("\ufeff") else 0
    if lines and lines[0].lstrip("\ufeff").strip() == "---":
        for index, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                offset = sum(len(part) for part in lines[:index + 1])
                break
    return text[:offset] + notice + text[offset:]


def _copy_version(source_root, destination, manifest):
    source_root = Path(source_root).expanduser().resolve()
    source_hash = sha(source_root / 'animation-manifest.json')
    old = load(source_root)
    manifest["project"] = copy.deepcopy(old["project"])
    manifest["sourceVersion"] = old.get("sourceVersion")
    manifest["brief"] = copy.deepcopy(old.get("brief", {"summary": "", "segments": []}))
    manifest["cues"] = copy.deepcopy(old["cues"])
    files = set()
    for cue in manifest["cues"]:
        cue.pop("deliveryAsset", None)
        cue.pop("objectId", None)
        adapter = cue.get("renderAdapters", {}).get("hyperframes", {})
        adapter.pop("layoutLock", None)
        cue.setdefault("segmentIds", [])
        if cue["productionMode"] == "animation":
            from scripts.work_model_sources import inspect_sources
            if adapter.get('compositionSrc'):
                files.update(p for p in inspect_sources(source_root, cue)['files'] if (source_root / p).is_file())
            # Explicitly commissioned copies include their real static design
            # materials, independently of the Motion dependency closure.
            if adapter.get('stillSrc'):
                files.add(adapter['stillSrc'])
            files.update(frame['stillSrc'] for frame in cue.get('storyboard', {}).get('frames', []) if frame.get('stillSrc'))
    for name in ("package.json", "hyperframes.json", "meta.json", "frame.md", "assets/vendor/gsap.min.js"):
        if (source_root / name).is_file():
            files.add(name)
    files.update(p.relative_to(source_root).as_posix() for p in (source_root / "assets/source").glob("narration-*") if p.is_file())
    project_adapter = manifest["project"].get("renderAdapters", {}).get("hyperframes", {})
    media = project_adapter.get("previewMediaSrc")
    if media and (source_root / media).is_file():
        files.add(media)
        manifest.setdefault("sourceHashes", {})["referenceVideo"] = sha(safe(source_root, media))
    source = manifest["project"].get("source")
    source_base = old.get("provenance", {}).get("sourceReferenceBase")
    if source and source.get("fcpxml"):
        xml = (source_root / source["fcpxml"]).resolve()
        source_base = source_base or str(xml.parent)
        if not xml.is_file() or xml.is_symlink():
            raise ValueError("legacy source FCPXML is unavailable")
        dest = safe(destination, "assets/source/Info.fcpxml", exists=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(xml, dest)
        source["fcpxml"] = "assets/source/Info.fcpxml"
        manifest.setdefault("sourceHashes", {})["fcpxml"] = sha(dest)
    for name in files:
        origin = safe(source_root, name)
        dest = safe(destination, name, exists=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, dest)
    if old["schemaVersion"] == "2.0":
        frame = destination / "frame.md"
        if frame.is_file():
            frame.write_bytes(_legacy_visual_defaults(frame.read_bytes().decode("utf-8")).encode("utf-8"))
        # v2's canonical parent path and lock hash do not describe this v3 copy.
        manifest["project"].get("creativeDirection", {}).pop("visualSpec", None)
    manifest["provenance"] = {**copy.deepcopy(old.get("provenance", {})), "copiedFrom": str(source_root), "sourceManifestSha256": sha(source_root / "animation-manifest.json"),
                              "legacySchema": old["schemaVersion"], "copiedAt": now()}
    if source_base:
        manifest["provenance"]["sourceReferenceBase"] = source_base
    if sha(source_root / 'animation-manifest.json') != source_hash:
        raise ValueError('copy source changed while reading the commissioned version')
    return old, source_hash


def _bind_source(afterforge, root, manifest, input_directory, selections=None):
    from scripts.intake_project import analyze_workspace
    from scripts.validate_delivery import probe_delivery
    from scripts.hyperframes_adapter import parse_time
    from fractions import Fraction
    inbox = afterforge.parent / "user-inbox"
    chosen = Path(input_directory).expanduser().resolve()
    if not inbox.is_dir() or not chosen.is_relative_to(inbox.resolve()) or chosen == inbox.resolve():
        raise ValueError("input directory must be an explicitly selected user-inbox version")
    if Path(input_directory).is_symlink():
        raise ValueError("input directory cannot use symlinks")
    report = analyze_workspace(chosen, recursive=False, selections=selections)
    if report["status"] != "ready":
        raise ValueError("input discovery blocked: " + json.dumps(report["blockers"], ensure_ascii=False))
    timeline = report["timeline"]
    xml = Path(timeline["source_xml"])
    video = Path(report["selected"]["reference_video"])
    probe = probe_delivery(video)
    frame = parse_time(timeline["frame_duration"])
    duration = parse_time(timeline["duration"])
    if frame <= 0 or (duration / frame).denominator != 1:
        raise ValueError("source FCPXML time base is invalid")
    if Fraction(str(probe["r_frame_rate"])) != 1 / frame or abs(Fraction(str(probe["duration"])) - duration) > frame:
        raise ValueError("reference video does not match source duration/frame rate")
    old_source = manifest["project"].get("source")
    manifest["project"]["source"] = {"fcpxml": "assets/source/Info.fcpxml", "width": timeline["width"],
        "height": timeline["height"], "frameDuration": timeline["frame_duration"], "duration": timeline["duration"]}
    relative_video = "assets/source/rough-cut" + video.suffix.lower()
    manifest["project"].setdefault("renderAdapters", {}).setdefault("hyperframes", {})["previewMediaSrc"] = relative_video
    for origin, name in ((xml, "assets/source/Info.fcpxml"), (video, relative_video)):
        target = safe(root, name, exists=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    manifest["sourceHashes"] = {"fcpxml": sha(xml), "referenceVideo": sha(video)}
    manifest["sourceVersion"] = chosen.name
    manifest.setdefault("provenance", {})["input"] = {"directory": str(chosen), "fcpxml": str(xml),
        "referenceVideo": str(video), "boundAt": now(), "narrationSources": report["materials"]["narration_sources"],
        "timelineText": timeline["text_items"]}
    manifest["provenance"]["sourceReferenceBase"] = str(xml.parent)
    for index, origin in enumerate(report["materials"]["narration_sources"]):
        p = Path(origin)
        dest = safe(root, f"assets/source/narration-{index}{p.suffix}", exists=False)
        shutil.copy2(p, dest)
    if old_source:
        for cue in manifest["cues"]:
            if cue.get("productionMode") == "animation":
                cue["status"] = "draft"
                cue.pop("resolvedTimeline", None)


@verified_operation
def open_project(afterforge_root, request=None):
    afterforge = Path(afterforge_root).expanduser().absolute()
    if request is None:
        return project_status(afterforge)
    if afterforge.is_symlink():
        raise ValueError("AfterForge root cannot be a symlink")
    afterforge = afterforge.parent.resolve() / afterforge.name
    if afterforge.exists() and not afterforge.is_dir():
        raise ValueError("AfterForge root is not a directory")
    engine = afterforge / "工程"
    if engine.is_symlink():
        raise ValueError("engine root cannot be a symlink")
    engine.mkdir(parents=True, exist_ok=True)
    with project_lock(afterforge):
        marker = engine / "project.json"
        index = json.loads(marker.read_text()) if marker.is_file() else {
            "schemaVersion": "2.0", "projectId": _identifier("project"),
            "title": request.get("title", "电影系列"), "revision": 0, "episodes": [], "requests": {}, "protocolBaselines": {}}
        previous = request_check(index, request)
        if previous is not None:
            return previous
        episode_id = request.get("episodeId")
        if episode_id:
            found = [ep for ep in index["episodes"] if ep["id"] == episode_id]
            if not found:
                raise ValueError("unknown episodeId")
            episode = found[0]
        else:
            title = request.get("episodeTitle")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("new episode requires episodeTitle")
            episode = {"id": _identifier("episode"), "title": title.strip(), "versions": []}
            index["episodes"].append(episode)
        version_id = _identifier("version")
        version_title = request.get("versionTitle", f"制作{len(episode['versions']) + 1}")
        relative = f"工程/episodes/{episode['id']}/{version_id}"
        destination = safe(afterforge, relative, exists=False)
        parent = destination.parent
        parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".new-", dir=parent))
        manifest = _blank({"projectId": index["projectId"], "episodeId": episode["id"], "versionId": version_id,
                           "episodeTitle": episode["title"], "versionTitle": version_title})
        installed = False
        try:
            if request.get("copyFrom"):
                commission = user_source(request.get("commission"))
                origin, source_hash = _copy_version(request["copyFrom"], stage, manifest)
                manifest.setdefault("provenance", {})["commission"] = commission
                from scripts.work_model_policy import copy_object_relations
                copy_object_relations(manifest, origin, request, source_hash)
            elif (engine / "frame.md").is_file():
                if type(request.get("useSeriesDefaults")) is not bool:
                    raise ValueError("series visual defaults exist; specify the user-intended useSeriesDefaults")
                if request["useSeriesDefaults"]:
                    commission = user_source(request.get("commission"))
                    shutil.copy2(safe(engine, "frame.md"), stage / "frame.md")
                    manifest.setdefault("provenance", {})["commission"] = commission
            if request.get("inputDirectory"):
                from scripts.intake_project import normalize_input_selection
                _bind_source(afterforge, stage, manifest, request["inputDirectory"],
                             normalize_input_selection(request, request["inputDirectory"]))
            if "brief" in request:
                manifest["brief"] = copy.deepcopy(request["brief"])
            save(stage, manifest)
            os.replace(stage, destination)
            installed = True
            version = {"id": version_id, "title": version_title, "root": relative,
                       "sourceVersion": manifest["sourceVersion"], "legacy": False}
            episode["versions"].append(version)
            index["revision"] += 1
            result = {"status": "opened", "root": str(destination), "identity": manifest["identity"],
                      "editRevision": 0, "projectRevision": index["revision"]}
            remember(index, request, result)
            atomic_json(marker, index)
        except BaseException:
            if installed:
                shutil.rmtree(destination)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        for name in ("AGENTS.md", "CLAUDE.md"):
            target = afterforge / name
            if not target.exists():
                template = Path(__file__).resolve().parents[1] / "assets/afterforge-project" / name
                atomic_bytes(target, template.read_bytes())
        memory = engine / "创作记忆.md"
        if not memory.exists():
            atomic_bytes(memory, MEMORY_SEED.encode())
        return result


def project_status(afterforge_root):
    afterforge = Path(afterforge_root).expanduser().resolve()
    marker = afterforge / "工程/project.json"
    if marker.is_file():
        index = json.loads(marker.read_text())
        result = {key: copy.deepcopy(index[key]) for key in ("projectId", "title", "revision", "episodes")}
    else:
        result = {"projectId": "legacy", "title": afterforge.name, "revision": 0, "episodes": []}
    if afterforge.is_dir():
        for child in sorted(afterforge.iterdir()):
            if child.is_symlink() or not (child / "animation-manifest.json").is_file():
                continue
            old = load(child)
            if old.get("schemaVersion") != "2.0":
                continue
            key = "legacy-" + digest(child.name)[:12]
            result["episodes"].append({"id": key, "title": child.name + " · 旧工程", "versions": [
                {"id": key, "title": child.name, "root": child.name, "legacy": True}]})
    return result


def _artifact_current(root, manifest, artifact):
    try:
        if sha(safe(root, artifact["path"])) != artifact["sha256"]:
            return False
        if artifact.get('purpose') in {'storyboard', 'still'}:
            from scripts.work_model_storyboard import frame_current
            return frame_current(root, manifest, artifact)
        if artifact.get('purpose') == 'exploration':
            from scripts.work_model_exploration import candidate_manifest
            from scripts.work_model_storyboard import frame_current
            return frame_current(root, candidate_manifest(manifest, artifact), artifact)
        from scripts.hyperframes_adapter import parse_time
        from scripts.work_model_inputs import cue_key
        if artifact["kind"] == "cue-preview":
            from scripts.work_model_jobs import supplemental_key
            cue = next(c for c in manifest["cues"] if c["id"] == artifact["cueIds"][0])
            return artifact["inputKey"] == supplemental_key(root, manifest, cue)
        if 'previewRequest' in artifact:
            from scripts.work_model_jobs import _spec
            return artifact['inputKey'] == digest(_spec(root, manifest, 'preview', artifact['previewRequest'],
                job_id=artifact['eventId'])['timeline'])
        return artifact["inputKey"] == timeline_key(root, manifest,
            start=parse_time(artifact["range"]["start"]), duration=parse_time(artifact["range"]["duration"]),
            allow_draft=not artifact["complete"], excluded_cue_ids=artifact.get('excludedCueIds', []))
    except (ValueError, OSError, KeyError, StopIteration):
        return False


def current_review_set(root, manifest):
    from scripts.work_model_policy import artifact_eligible
    for review in reversed(manifest["reviewSets"]):
        try:
            if review["inputKey"] != timeline_key(root, manifest):
                continue
            artifacts = {a["id"]: a for a in manifest["artifacts"]}
            selected = [artifacts[key] for key in review["artifactIds"]]
            from scripts.hyperframes_adapter import parse_time
            from scripts.work_model_inputs import timeline_inputs
            from scripts.work_model_jobs import _overlap_ids
            total = parse_time(manifest["project"]["source"]["duration"])
            if not any(a["kind"] == "full-preview" and parse_time(a["range"]["start"]) == 0 and parse_time(a["range"]["duration"]) == total for a in selected):
                continue
            required = _overlap_ids(timeline_inputs(root, manifest)["overlays"])
            supplied = {a["cueIds"][0] for a in selected if a["kind"] == "cue-preview"}
            if not required.issubset(supplied):
                continue
            if selected and all(a["complete"] and artifact_eligible(manifest, a)
                                and _artifact_current(root, manifest, a) for a in selected):
                return review
        except (ValueError, OSError, KeyError):
            pass
    return None


def _populate_delivery_media(root, releases):
    for release in releases:
        release.pop("inventory", None)
        if release.get("protocolVersion") == "3":
            continue
        snapshot = safe(root, release["snapshotPath"], exists=False)
        frozen_path = snapshot / "animation-manifest.json"
        # Snapshot layout is owned by the delivery backend; expose only recorded MOVs.
        if not frozen_path.is_file():
            frozen_path = snapshot / "files/animation-manifest.json"
        if "media" not in release:
            release["media"] = []
        if frozen_path.is_file() and not release["media"]:
            frozen = json.loads(frozen_path.read_text())
            for cue in frozen["cues"]:
                asset = cue.get("deliveryAsset")
                if asset:
                    for base in (snapshot, snapshot / "files"):
                        candidate = base / asset["relativePath"]
                        if candidate.is_file():
                            release["media"].append({"path": candidate.relative_to(root).as_posix(), "label": asset["fileName"]})
                            break


def media_status(version_root):
    """Resolve recorded media only; playback must not wait for review qualification.

    History is already readable through Review. Currentness and authorization
    are still computed by status/actions, never inferred by this media index.
    """
    root = Path(version_root).expanduser().resolve()
    manifest = load(root)
    if manifest["schemaVersion"] != "3.0":
        return status(root)
    result = {key: copy.deepcopy(manifest[key]) for key in ("artifacts", "deliveries")}
    result['concepts'] = copy.deepcopy(manifest.get('concepts', []))
    _populate_delivery_media(root, result["deliveries"])
    return result


@verified_operation
def status(version_root, *, view='full', cue_id=None, feedback_id=None):
    from scripts.work_model_content import content_context
    from scripts.work_model_summary import project_view
    root = Path(version_root).expanduser().resolve()
    manifest = load(root)
    if manifest["schemaVersion"] == "2.0":
        artifacts = []
        def historical(relative, kind, cue_ids, expected=None):
            try:
                path = safe(root, relative)
                if not path.is_file():
                    return
            except (ValueError, TypeError):
                return
            artifacts.append({"id": "legacy-" + digest(relative)[:20], "kind": kind, "path": relative,
                "sha256": expected, "complete": True, "current": False, "legacy": True, "cueIds": cue_ids,
                "range": {"start": "0s", "duration": manifest["project"]["source"].get("duration", "0s")}})
        demo = manifest.get("workflow", {}).get("stageEvidence", {}).get("A12", {})
        if demo.get("preview"):
            historical(demo["preview"], "full-preview", [], demo.get("sha256"))
        for cue in manifest["cues"]:
            adapter = cue.get("renderAdapters", {}).get("hyperframes", {})
            lock = adapter.get("layoutLock") or {}
            for frame in lock.get("reviewFrames", []):
                historical(frame.get("path"), "still", [cue["id"]], frame.get("sha256"))
            if not lock.get("reviewFrames") and adapter.get("stillSrc"):
                historical(adapter["stillSrc"], "still", [cue["id"]])
        result = {"legacy": True, "editRevision": 0, "identity": {"projectId": "legacy", "episodeId": root.name,
            "versionId": "legacy-" + digest(root.name)[:12], "episodeTitle": root.name, "versionTitle": "旧工程"},
            "brief": {"summary": "历史工程只读；继续制作请创建新工作副本。", "segments": []},
            "cues": manifest["cues"], "artifacts": artifacts, "feedback": [], "deliveries": [], "tasks": [],
            "availableActions": ["copy"], "reviewSet": None}
        return project_view(manifest, result, view=view, cue_id=cue_id, feedback_id=feedback_id)
    afterforge, index = layout(root)
    signature = _display_signature(root, afterforge)
    cached = _DISPLAY_CACHE.get(str(root))
    if cached and cached[0] == signature:
        return project_view(manifest, copy.deepcopy(cached[1]), view=view, cue_id=cue_id, feedback_id=feedback_id)
    result = {key: copy.deepcopy(manifest[key]) for key in ("identity", "editRevision", "brief", "cues", "artifacts", "feedback", "decisions", "deliveries")}
    result["legacy"] = False
    result['workModelVersion'] = manifest.get('workModelVersion', '2.0.0')
    from scripts import work_model_concepts as concepts
    result['concepts'] = copy.deepcopy(manifest.get('concepts', []))
    if concepts.enabled(manifest):
        result['conceptDesign'] = concepts.status(root, manifest)
    result['workingIntent'] = copy.deepcopy(manifest.get('workingIntent', {'items': []}))
    from scripts.work_model_planning import status as planning_status
    result['creativePlanning'] = planning_status(manifest)
    from scripts.work_model_scene_review import status as scene_review_status
    result['sceneReviews'] = scene_review_status(root, manifest)
    from scripts.work_model_policy import artifact_eligible, first_confirmed, storyboard_current
    for artifact in result["artifacts"]:
        artifact["mediaCurrent"] = _artifact_current(root, manifest, artifact)
        artifact["reviewEligible"] = artifact.get('purpose') in {'storyboard', 'exploration', 'still'} or artifact_eligible(manifest, artifact)
        artifact["current"] = artifact["mediaCurrent"] and artifact["reviewEligible"]
    artifacts = {a['id']: a for a in result['artifacts']}
    cards = []
    for cue in animation_cues(manifest):
        board = next((s for s in reversed(manifest.get('storyboards', [])) if s['cueId'] == cue['id']
                      and s['objectId'] == cue.get('objectId')), None)
        confirmed = first_confirmed(manifest, cue.get('objectId'))
        from scripts.work_model_confirmation import confirmation_problems
        problems = confirmation_problems(root, manifest, [board]) if board else [{'code': 'missing-storyboard', 'message': 'Generate a current Storyboard first.'}]
        frame_narrations = {item['frameId']: item.get('narration') for item in board.get('frameNarrations', [])} if board else {}
        cards.append({'id': cue['id'], 'objectId': cue.get('objectId'), 'title': cue.get('title', cue['id']),
            'animationNotes': copy.deepcopy(board.get('animationNotes', [])) if board else [],
            'reviewInputKey': board.get('reviewInputKey') if board else None,
            'narration': board.get('narration', '') if board else cue.get('narrationAnchor', ''),
            'contentContext': board.get('contentContext', {}) if board else content_context(manifest, cue),
            'finalAnimationDescription': board.get('finalAnimationDescription', '') if board else cue.get('finalAnimationDescription', ''),
            'storyboardId': board['id'] if board else None,
            'frames': [{**artifacts[i], 'artifactId': i, 'frameNarration': frame_narrations.get(artifacts[i]['frameId'])}
                       for i in board['artifactIds']] if board else [],
            'canConfirm': not problems and not concepts.enabled(manifest),
            'confirmationProblems': [] if concepts.enabled(manifest) else problems, 'firstConfirmed': confirmed})
        cards[-1]['sceneReview'] = {kind: next((r for r in reversed(result['sceneReviews'])
            if r['objectId'] == cue.get('objectId') and r['kind'] == kind), None)
            for kind in ('storyboard', 'animation')}
        if concepts.enabled(manifest):
            from scripts.work_model_storyboard_production import cue_status
            cards[-1].update(cue_status(root, manifest, cue, board, problems))
    from scripts.work_model_storyboard_production import latest_request
    result['storyboard'] = {'cues': cards, 'rounds': copy.deepcopy(manifest.get('reviewRounds', [])),
                            'productionRequest': copy.deepcopy(latest_request(manifest))}
    from scripts.work_model_storyboard import review_snapshots
    result['storyboard']['snapshots'] = review_snapshots(manifest, artifacts, cards)
    result['explorations'] = copy.deepcopy(manifest.get('explorations', []))
    result['workScopeCueIds'] = []
    result['presentationCueIds'] = [c['id'] for c in animation_cues(manifest)]
    result['excludedCueIds'] = []
    result['production'] = []
    from scripts.work_model_inputs import cue_key
    for cue in animation_cues(manifest):
        technical = {'cueId': cue['id'], 'objectId': cue.get('objectId'),
                     'firstConfirmed': first_confirmed(manifest, cue.get('objectId'))}
        try:
            technical['mediaKey'] = cue_key(root, manifest, cue)
            technical['implementationAvailable'] = cue.get('status', 'ready') == 'ready'
        except (ValueError, OSError, KeyError, TypeError) as error:
            technical.update(implementationAvailable=False, problem=str(error))
        result['production'].append(technical)
    result["reviewSet"] = current_review_set(root, manifest)
    result["tasks"] = []
    job_dir = root / "jobs"
    if job_dir.is_dir():
        for path in sorted(job_dir.glob("*.json")):
            if not path.is_symlink():
                job = json.loads(path.read_text())
                result["tasks"].append({key: job[key] for key in ("id", "action", "status", "inputKey", "createdAt", "updatedAt", "completedCueIds", "error") if key in job})
                if job.get("request", {}).get("requestId"):
                    result["tasks"][-1]["requestId"] = job["request"]["requestId"]
    memory = afterforge / "工程/创作记忆.md"
    result["memorySha256"] = sha(memory) if memory.is_file() else None
    frame = afterforge / "工程/frame.md"
    result["frameSha256"] = sha(frame) if frame.is_file() else None
    result["availableActions"] = ["update", "preview"]
    if result["reviewSet"]:
        result["availableActions"] += ["approve", "approve-and-deliver", "deliver"]
        if any(d.get("reviewSetId") == result["reviewSet"]["id"] and d["kind"] == "approve" for d in manifest["decisions"]):
            result["availableActions"].append("authorize")
    _populate_delivery_media(root, result["deliveries"])
    for release in result["deliveries"]:
        release["accepted"] = any(d.get("kind") == "accept-import" and d.get("deliveryId") == release["id"] for d in manifest["decisions"])
        release["roundTripRequired"] = release["protocolVersion"] not in index.get("protocolBaselines", {})
    if len(_DISPLAY_CACHE) >= 32:
        _DISPLAY_CACHE.pop(next(iter(_DISPLAY_CACHE)))
    _DISPLAY_CACHE[str(root)] = (signature, copy.deepcopy(result))
    return project_view(manifest, result, view=view, cue_id=cue_id, feedback_id=feedback_id)


def _validate_edit(manifest):
    from scripts.hyperframes_adapter import parse_time
    ids = [c["id"] for c in manifest["cues"]]
    segment_ids = [s["id"] for s in manifest["brief"]["segments"]]
    if len(set(ids)) != len(ids) or len(set(segment_ids)) != len(segment_ids):
        raise ValueError("duplicate cue or segment id")
    for field, expected in (("preview", (854, 480)), ("delivery", (1920, 1080))):
        size = manifest["project"][field]
        if (size.get("width"), size.get("height")) != expected:
            raise ValueError("work model requires 480p preview and 1080p native delivery dimensions")
    from scripts.work_model_content import validate_content_declarations
    for cue in manifest["cues"]:
        if 'storyboard' in cue:
            from scripts.work_model_storyboard import animation_notes
            animation_notes(cue)
        problems = validate_content_declarations(manifest, cue)
        if problems:
            raise ValueError('; '.join(p['code'] + ': ' + p['message'] for p in problems))
        if not set(cue.get("segmentIds", [])).issubset(segment_ids):
            raise ValueError("unknown cue segmentId")
        timeline = cue.get("resolvedTimeline")
        if timeline and (parse_time(timeline["start"]) < 0 or parse_time(timeline["duration"]) <= 0):
            raise ValueError("invalid cue time")


def _cue_updates(manifest, updates):
    """Expand bounded Cue edits before the ordinary validators/publication path."""
    allowed = {'title','purpose','visualPlan','narrationAnchor','finalAnimationDescription','screenText',
               'segmentIds','contentContext','storyboard','resolvedTimeline','layer','status'}
    if not isinstance(updates, list) or not updates:
        raise ValueError('cueUpdates requires a nonempty list')
    cues = copy.deepcopy(manifest['cues'])
    known = {c['id']:c for c in cues}
    selected = set()
    def merge(previous, changes):
        result = copy.deepcopy(previous)
        for key,value in changes.items():
            result[key] = merge(result[key],value) if isinstance(result.get(key),dict) and isinstance(value,dict) else copy.deepcopy(value)
        return result
    for item in updates:
        if not isinstance(item,dict) or set(item) != {'cueId','changes'} or not isinstance(item['cueId'],str):
            raise ValueError('cueUpdates items require cueId and changes')
        cid, changes = item['cueId'], item['changes']
        if cid not in known or cid in selected:
            raise ValueError('cueUpdates requires unique known cueIds')
        if not isinstance(changes,dict) or not changes or set(changes) - allowed:
            raise ValueError('cueUpdates may change only descriptive, timing and Storyboard fields')
        selected.add(cid)
        known[cid].update(merge(known[cid], changes))
    return cues


def _record_decision(root, manifest, request):
    kind = request.get("kind")
    if kind == 'confirm-concept':
        from scripts.work_model_concepts import confirm
        return confirm(root, manifest, request)
    if kind in {"confirm-design", "explore-motion", "authorize-demo"}:
        from scripts.work_model_policy import creative_decision
        return creative_decision(root, manifest, request)
    source = user_source(request.get("source"))
    if kind in {"approve", "authorize", "approve-and-deliver"}:
        review = current_review_set(root, manifest)
        if not review or request.get("reviewSetId") != review["id"]:
            raise ValueError("current complete review set is required; refresh stale review")
        if kind == "authorize" and not any(d.get("reviewSetId") == review["id"] and d["kind"] in {"approve", "approve-and-deliver"} for d in manifest["decisions"]):
            raise ValueError("user must approve this complete review before authorizing delivery")
        record = {"id": _identifier("decision"), "kind": kind, "source": source,
                  "reviewSetId": review["id"], "createdAt": now()}
        if kind in {"approve", "approve-and-deliver"}:
            accepted = set(request.get("feedbackIds", []))
            if not accepted.issubset({f["id"] for f in manifest["feedback"]}):
                raise ValueError("unknown explicitly accepted feedback")
            for feedback in manifest["feedback"]:
                if feedback["id"] in accepted:
                    feedback.update(status="accepted", acceptedSource=source)
            from scripts.work_model_policy import blocking_feedback
            from scripts.work_model_feedback_targets import review_target
            if blocking_feedback(manifest, review_target(manifest, review)):
                raise ValueError("pending feedback must be addressed or explicitly accepted before approval")
    elif kind == "accept-import":
        from scripts.work_model_delivery import verify_release
        afterforge, _ = layout(root)
        release = next((d for d in manifest["deliveries"] if d["id"] == request.get("deliveryId")), None)
        if release is None:
            raise ValueError("unknown deliveryId")
        verify_release(root, afterforge, release)
        record = {"id": _identifier("decision"), "kind": kind, "source": source,
                  "deliveryId": release["id"], "infoFcpxmlSha256": release["infoFcpxmlSha256"], "createdAt": now()}
    else:
        raise ValueError("unsupported decision kind")
    manifest["decisions"].append(record)
    return record


def _prepare_files(root, request):
    installs = []
    for item in request.get("files", []):
        name = Path(item["path"]).as_posix()
        if not (name.startswith(("compositions/", "assets/")) or name == 'frame.md'):
            raise ValueError("source update cannot overwrite evidence, cache or release files")
        if name == 'assets/vendor/gsap.min.js':
            raise ValueError('controlled runtime files require operation=runtime')
        if name.startswith("assets/source/"):
            raise ValueError("bound roughcut inputs are immutable")
        if name.startswith('assets/concepts/'):
            raise ValueError('concept image evidence is immutable; register a new concept instead')
        destination = safe(root, name, exists=False)
        staged = Path(item["source"]).expanduser().absolute()
        if not staged.is_relative_to(root / ".staging"):
            raise ValueError("source file must be prepared in version .staging")
        staged = safe(root, staged.relative_to(root).as_posix())
        if not staged.is_file():
            raise ValueError("staged source must be a regular file")
        installs.append((destination, staged.read_bytes(), destination.read_bytes() if destination.exists() else None))
    return installs


@verified_operation
def update(version_root, request):
    root = Path(version_root).expanduser().resolve()
    if 'cueUpdates' in request and request.get('operation') != 'edit':
        raise ValueError('cueUpdates is available only within operation=edit')
    # Check read-only before creating a lock in a historical directory.
    load(root, writable=True)
    afterforge, _ = layout(root)
    if request.get('operation') in {'working-intent', 'scene-review', 'concept-handoff', 'creative-planning'}:
        # These short writes must not upgrade policy or correct unrelated
        # production history. A concept handoff confirms only its selected images.
        with manifest_transaction(root):
            manifest = load(root, writable=True)
            previous = request_check(manifest, request)
            if previous is not None:
                return previous
            if request['operation'] == 'working-intent':
                from scripts.work_model_intent import update_intent
                record = update_intent(manifest, request)
            elif request['operation'] == 'creative-planning':
                from scripts.work_model_planning import update_planning
                record = update_planning(manifest, request)
            elif request['operation'] == 'scene-review':
                from scripts.work_model_scene_review import acknowledge
                record = acknowledge(root, manifest, request)
            else:
                from scripts.work_model_concepts import handoff
                record = handoff(root, manifest, request)
            manifest['editRevision'] += 1
            result = {'status': 'updated', 'editRevision': manifest['editRevision'], 'record': record}
            remember(manifest, request, result)
            save(root, manifest)
            return result
    if request.get("operation") in {"memory", "visual-defaults"}:
        with project_lock(afterforge), manifest_transaction(root):
            manifest = load(root, writable=True)
            previous = request_check(manifest, request)
            if previous is not None:
                return previous
            from scripts.work_model_policy import upgrade
            upgrade(manifest)
            is_memory = request["operation"] == "memory"
            memory = afterforge / ("工程/创作记忆.md" if is_memory else "工程/frame.md")
            current_sha = sha(memory) if memory.is_file() else None
            if current_sha != request.get("expectedMemorySha256" if is_memory else "expectedFrameSha256"):
                raise ValueError("stale series memory; reread current text")
            text = request.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 16000:
                raise ValueError("series memory must be concise nonempty text")
            before = memory.read_bytes() if memory.is_file() else None
            result = {"status": "updated", "editRevision": manifest["editRevision"] + 1}
            manifest["editRevision"] += 1
            remember(manifest, request, result)
            try:
                atomic_bytes(memory, text.encode())
                save(root, manifest)
            except BaseException:
                if before is None:
                    memory.unlink(missing_ok=True)
                else:
                    atomic_bytes(memory, before)
                raise
            return result
    with (project_lock(afterforge) if request.get("operation") == "roundtrip" else nullcontext()), manifest_transaction(root):
        manifest = load(root, writable=True)
        previous = request_check(manifest, request)
        if previous is not None:
            return previous
        from scripts.work_model_policy import upgrade
        upgrade(manifest)
        from scripts.work_model_policy import correct_incomplete_runs
        correct_incomplete_runs(root, manifest)
        before_manifest = copy.deepcopy(manifest)
        operation = request.get("operation")
        installs = []
        runtime_change = None
        record = None
        if operation == "runtime":
            from scripts.work_model_runtime import runtime_files, runtime_transition
            supplied = None
            if request.get("vendorSource"):
                candidate = Path(request["vendorSource"]).expanduser().absolute()
                if not candidate.is_relative_to(root / ".staging"):
                    raise ValueError("vendorSource must be prepared in version .staging")
                supplied = safe(root, candidate.relative_to(root).as_posix())
            payload = runtime_files(root, manifest, request.get("version"), supplied)
            runtime_change = runtime_transition(root, manifest, payload, request.get("version"))
            manifest['runtimeIdentity'] = runtime_change['identity']
            for name, data in payload.items():
                destination = safe(root, name, exists=False)
                installs.append((destination, data, destination.read_bytes() if destination.exists() else None))
        elif operation in {"edit", "exploration-adopt"}:
            patch = request.get("patch", {})
            if not isinstance(patch, dict) or set(patch) - {"brief", "cues", "project"}:
                raise ValueError("edit may change only brief, cues and project settings")
            if 'cueUpdates' in request:
                if operation != 'edit' or 'cues' in patch:
                    raise ValueError('cueUpdates requires edit and cannot be combined with patch.cues')
                patch = {**patch, 'cues':_cue_updates(manifest, request['cueUpdates'])}
            if "project" in patch:
                project = copy.deepcopy(manifest["project"])
                project.update(patch["project"])
                if project.get("source") != manifest["project"].get("source"):
                    raise ValueError("source replacement requires a new production version")
                if project.get("renderAdapters", {}).get("hyperframes", {}).get("previewMediaSrc") != manifest["project"].get("renderAdapters", {}).get("hyperframes", {}).get("previewMediaSrc"):
                    raise ValueError("reference video replacement requires a new version")
                patch = {**patch, "project": project}
            manifest.update(copy.deepcopy(patch))
            if any("deliveryAsset" in c or c.get("renderAdapters", {}).get("hyperframes", {}).get("layoutLock") for c in manifest["cues"]):
                raise ValueError("edit cannot register delivery or approval evidence")
            from scripts.work_model_policy import bind_objects
            bind_objects(before_manifest, manifest, request.get("objectRelations"))
            _validate_edit(manifest)
            installs.extend(_prepare_files(root, request))
            if operation == "exploration-adopt":
                from scripts.work_model_concepts import require_concepts
                require_concepts(root, manifest, request.get('cueIds', []))
                from scripts.work_model_exploration import adoption
                record = adoption(manifest, request, root=root)
                allowed = set(request['cueIds'])
                old_cues = {c['id']: c for c in before_manifest['cues']}
                new_cues = {c['id']: c for c in manifest['cues']}
                changed = {cid for cid in old_cues.keys() | new_cues.keys() if old_cues.get(cid) != new_cues.get(cid)}
                if not changed.issubset(allowed) or set(patch) - {'cues'}:
                    raise ValueError('visual adoption exceeds the explicitly selected cue scope')
                changed_paths = {p.relative_to(root).as_posix() for p, data, old in installs if data != old}
                for cue in before_manifest['cues']:
                    if cue['id'] in allowed or cue['productionMode'] != 'animation':
                        continue
                    if changed_paths.intersection(dependencies(root, cue, require_motion=False)):
                        raise ValueError('shared visual dependency would change an unselected cue')
        elif operation == "exploration":
            from scripts.work_model_exploration import set_exploration
            from scripts.work_model_concepts import enabled, require_concepts
            if enabled(manifest):
                if not request.get('cueIds'):
                    raise ValueError('code exploration requires explicit canonical cueIds with confirmed concepts')
                require_concepts(root, manifest, request['cueIds'])
            installs.extend(_prepare_files(root, request))
            overrides = {p.relative_to(root).as_posix(): data for p, data, _ in installs}
            record = set_exploration(manifest, request, root=root, overrides=overrides)
            if enabled(manifest):
                record['cueIds'] = list(request['cueIds'])
            prefixes = ('compositions/explorations/' + record['id'] + '/', 'assets/explorations/' + record['id'] + '/')
            if any(not p.relative_to(root).as_posix().startswith(prefixes) for p, _, _ in installs):
                raise ValueError('visual exploration may write only its own candidate files')
        elif operation == 'concept':
            from scripts.work_model_concepts import update_concept
            record, images = update_concept(root, manifest, request)
            installs.extend(images)
        elif operation == "feedback":
            from scripts.work_model_feedback import add_feedback
            record = add_feedback(manifest, request, root=root)
        elif operation == "review-submit":
            from scripts.work_model_feedback import submit_round
            record = submit_round(root, manifest, request)
            if request.get('decision'):
                from scripts.work_model_feedback import rework_decision
                _record_decision(root, manifest, rework_decision(root, manifest, request, record))
        elif operation == "review-progress":
            from scripts.work_model_feedback import round_progress
            record = round_progress(manifest, request)
        elif operation == "feedback-applicability":
            record = next((f for f in manifest["feedback"] if f["id"] == request.get("feedbackId")), None)
            if not record or request.get("kind") not in {"current", "deferred", "not-applicable"}:
                raise ValueError("unknown feedback or applicability")
            record["applicability"] = {"kind": request["kind"], "source": user_source(request.get("source"))}
        elif operation == "feedback-status":
            record = next((f for f in manifest["feedback"] if f["id"] == request.get("feedbackId")), None)
            if not record:
                raise ValueError("unknown feedbackId")
            value = request.get("status")
            if value == "accepted":
                if request.get("actor") != "user":
                    raise ValueError("only user can accept feedback")
                record["acceptedSource"] = user_source(request.get("source"))
            elif value not in {"pending", "needs-clarification", "addressed"}:
                raise ValueError("unsupported feedback status")
            if value == "addressed" and not request.get("resolution"):
                raise ValueError("addressed feedback requires a resolution")
            record.update(status=value, updatedAt=now(), resolution=request.get("resolution", ""))
        elif operation == "decision":
            record = _record_decision(root, manifest, request)
        elif operation == "decisions":
            record = [_record_decision(root, manifest, item) for item in request.get("decisions", [])]
        elif operation == "roundtrip":
            return _register_roundtrip(root, manifest, request)
        else:
            raise ValueError("unsupported update operation")
        if operation in {"edit", "exploration-adopt", "runtime"}:
            from scripts.work_model_policy import check_motion_edit
            check_motion_edit(root, before_manifest, manifest, request,
                [(path.relative_to(root).as_posix(), data, old) for path, data, old in installs],
                runtime_transition=runtime_change)
        if operation == 'exploration':
            overrides = {p.relative_to(root).as_posix(): data for p, data, _ in installs}
            # Exploration is a static comparison workspace, not another Motion
            # publisher. Validate unpublished bytes using the same source rule.
            from scripts.work_model_sources import inspect_sources, _content
            for path, data in overrides.items():
                if Path(path).suffix.lower() in {'.js', '.mjs', '.html', '.htm', '.svg', '.css'}:
                    dynamic, refs = _content(path, data.decode('utf-8'))
                    if dynamic or any(executable is True for _, executable in refs):
                        raise ValueError('visual exploration cannot publish Motion; use bounded Cue exploration')
            for variant in record['variants']:
                for cue in variant['cues']:
                    adapter = cue.get('renderAdapters', {}).get('hyperframes', {})
                    if adapter.get('compositionSrc'):
                        analysis = inspect_sources(root, cue, overrides, allow_missing=True)
                        if set(analysis['motionFiles']) & overrides.keys():
                            raise ValueError('visual exploration cannot publish Motion sources')
        manifest["editRevision"] += 1
        result = {"status": "updated", "editRevision": manifest["editRevision"]}
        if record is not None:
            result["record"] = copy.deepcopy(record)
        remember(manifest, request, result)
        installed = []
        try:
            for path, data, before in installs:
                atomic_bytes(path, data)
                installed.append((path, before))
            save(root, manifest)
        except BaseException:
            for path, before in reversed(installed):
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_bytes(path, before)
            raise
        return result


def preview(version_root, request):
    from scripts.work_model_jobs import preview as run
    return run(Path(version_root), request)


def deliver(version_root, request):
    from scripts.work_model_jobs import deliver as run
    return run(Path(version_root), request)


def resume(version_root, request):
    from scripts.work_model_jobs import resume as run
    return run(Path(version_root), request)


def _register_roundtrip(root, manifest, request):
    from scripts.work_model_delivery import verify_release
    from scripts.compare_fcpxml_roundtrip import compare_roundtrip
    from scripts.work_model_store import fresh_hashes
    afterforge, index = layout(root)
    release = next((d for d in manifest["deliveries"] if d["id"] == request.get("deliveryId")), None)
    if release is None:
        raise ValueError("unknown deliveryId")
    verify_release(root, afterforge, release)
    if not any(d["kind"] == "accept-import" and d.get("deliveryId") == release["id"] for d in manifest["decisions"]):
        raise ValueError("record actual FCP import acceptance first")
    snapshot = safe(root, release["snapshotPath"])
    frozen = json.loads((snapshot / release["manifestPath"]).read_text())
    delivered = safe(afterforge, release["packagePath"]) / release.get("xmlFileName", "Info.fcpxml")
    reexported = Path(request["reexportedPath"]).expanduser().resolve()
    delivered_sha, reexported_sha = sha(delivered), sha(reexported)
    result = compare_roundtrip(delivered, reexported, frozen)
    fresh_hashes()
    if sha(delivered) != delivered_sha or sha(reexported) != reexported_sha:
        raise ValueError("round-trip XML changed during comparison; no baseline registered")
    verify_release(root, afterforge, release)
    fresh_hashes()
    if sha(delivered) != delivered_sha or sha(reexported) != reexported_sha:
        raise ValueError("round-trip XML changed during final verification; no baseline registered")
    record = {"id": _identifier("decision"), "kind": "roundtrip", "source": user_source(request.get("source")),
              "deliveryId": release["id"], "createdAt": now(), "result": result,
              "reexportedSha256": reexported_sha, "infoFcpxmlSha256": delivered_sha}
    manifest["decisions"].append(record)
    manifest["editRevision"] += 1
    response = {"status": "verified", "editRevision": manifest["editRevision"], "record": record}
    remember(manifest, request, response)
    # Baseline is recorded only from a verified real re-export and its package.
    with project_lock(afterforge):
        marker = afterforge / "工程/project.json"
        previous_index = marker.read_bytes()
        previous_manifest = (root / "animation-manifest.json").read_bytes()
        index = json.loads(previous_index)
        index.setdefault("protocolBaselines", {})[release["protocolVersion"]] = {"versionRoot": root.relative_to(afterforge).as_posix(),
              "deliveryId": release["id"], "decisionId": record["id"], "verifiedAt": now()}
        try:
            save(root, manifest)
            atomic_json(marker, index)
        except BaseException:
            atomic_bytes(root / "animation-manifest.json", previous_manifest)
            atomic_bytes(marker, previous_index)
            raise
    return response
