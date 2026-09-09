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

先理解本集希望观众发生什么认识变化，再决定原片、口播与视觉辅助的主次。允许没有动画，也允许画面安静。

## 已确认的创作经验与适用范围

- 《楚门》新版开场以口播为主，原片承接人物与生活；设计不抢走论证的注意力。这是开场案例，不是所有段落都只能用简单文字。
- “看电影 → 看他”把明确的视觉变化用在论点转折上；“观看授权”保留为概念文字，不必把每个口播比喻做成道具。
- 克制仍需要清楚的排版层级与适当质感，过于单薄也会让观看费力。
- 用户对镜子意象与粗剪淡出的解释优先于旧分镜。实际粗剪可以推动脚本成长。

以上来自用户在新版开场制作与工作模型重构讨论中的明确反馈。旧视觉策划探索文档不作为默认指导。

## 本系列案例

每集仅补充关键取舍、采用或放弃的原因、成片反馈及出处。Agent 推测明确标注，不把单次批准推广成长期偏好。
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
    return {"schemaVersion": "3.0", "workModelVersion": "2.0.0", "sourceVersion": None,
            "identity": identity, "editRevision": 0,
            "project": {"source": None, "preview": {"width": 854, "height": 480},
                        "delivery": {"width": 1920, "height": 1080}},
            "brief": {"summary": "", "segments": []}, "cues": [], "artifacts": [], "reviewSets": [],
            "feedback": [], "decisions": [], "deliveries": [], "requests": {}}


def _copy_version(source_root, destination, manifest):
    source_root = Path(source_root).expanduser().resolve()
    old = load(source_root)
    manifest["project"] = copy.deepcopy(old["project"])
    manifest["sourceVersion"] = old.get("sourceVersion")
    manifest["brief"] = copy.deepcopy(old.get("brief", {"summary": "", "segments": []}))
    manifest["cues"] = copy.deepcopy(old["cues"])
    files = set()
    for cue in manifest["cues"]:
        cue.pop("deliveryAsset", None)
        adapter = cue.get("renderAdapters", {}).get("hyperframes", {})
        adapter.pop("layoutLock", None)
        cue.setdefault("segmentIds", [])
        if cue["productionMode"] == "animation":
            files.update(dependencies(source_root, cue))
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
    manifest["provenance"] = {**copy.deepcopy(old.get("provenance", {})), "copiedFrom": str(source_root), "sourceManifestSha256": sha(source_root / "animation-manifest.json"),
                              "legacySchema": old["schemaVersion"], "copiedAt": now()}
    if source_base:
        manifest["provenance"]["sourceReferenceBase"] = source_base


def _bind_source(afterforge, root, manifest, input_directory):
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
    report = analyze_workspace(chosen, recursive=False)
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
                _copy_version(request["copyFrom"], stage, manifest)
            elif (engine / "frame.md").is_file():
                shutil.copy2(safe(engine, "frame.md"), stage / "frame.md")
            if request.get("inputDirectory"):
                _bind_source(afterforge, stage, manifest, request["inputDirectory"])
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
        from scripts.hyperframes_adapter import parse_time
        from scripts.work_model_inputs import cue_key
        if artifact["kind"] == "cue-preview":
            from scripts.work_model_jobs import supplemental_key
            cue = next(c for c in manifest["cues"] if c["id"] == artifact["cueIds"][0])
            return artifact["inputKey"] == supplemental_key(root, manifest, cue)
        return artifact["inputKey"] == timeline_key(root, manifest,
            start=parse_time(artifact["range"]["start"]), duration=parse_time(artifact["range"]["duration"]),
            allow_draft=not artifact["complete"])
    except (ValueError, OSError, KeyError, StopIteration):
        return False


def current_review_set(root, manifest):
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
            if all(a["complete"] and _artifact_current(root, manifest, a) for a in selected):
                return review
        except (ValueError, OSError, KeyError):
            pass
    return None


@verified_operation
def status(version_root):
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
        return {"legacy": True, "editRevision": 0, "identity": {"projectId": "legacy", "episodeId": root.name,
            "versionId": "legacy-" + digest(root.name)[:12], "episodeTitle": root.name, "versionTitle": "旧工程"},
            "brief": {"summary": "历史工程只读；继续制作请创建新工作副本。", "segments": []},
            "cues": manifest["cues"], "artifacts": artifacts, "feedback": [], "deliveries": [], "tasks": [],
            "availableActions": ["copy"], "reviewSet": None}
    afterforge, index = layout(root)
    signature = _display_signature(root, afterforge)
    cached = _DISPLAY_CACHE.get(str(root))
    if cached and cached[0] == signature:
        return copy.deepcopy(cached[1])
    result = {key: copy.deepcopy(manifest[key]) for key in ("identity", "editRevision", "brief", "cues", "artifacts", "feedback", "decisions", "deliveries")}
    result["legacy"] = False
    for artifact in result["artifacts"]:
        artifact["current"] = _artifact_current(root, manifest, artifact)
    result["reviewSet"] = current_review_set(root, manifest)
    result["tasks"] = []
    job_dir = root / "jobs"
    if job_dir.is_dir():
        for path in sorted(job_dir.glob("*.json")):
            if not path.is_symlink():
                job = json.loads(path.read_text())
                result["tasks"].append({key: job[key] for key in ("id", "action", "status", "inputKey", "createdAt", "updatedAt", "completedCueIds", "error") if key in job})
    memory = afterforge / "工程/创作记忆.md"
    result["memorySha256"] = sha(memory) if memory.is_file() else None
    frame = afterforge / "工程/frame.md"
    result["frameSha256"] = sha(frame) if frame.is_file() else None
    result["availableActions"] = ["update", "preview"]
    if result["reviewSet"]:
        result["availableActions"] += ["approve", "approve-and-deliver", "deliver"]
        if any(d.get("reviewSetId") == result["reviewSet"]["id"] and d["kind"] == "approve" for d in manifest["decisions"]):
            result["availableActions"].append("authorize")
    for release in result["deliveries"]:
        release.pop("inventory", None)
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
        release["accepted"] = any(d.get("kind") == "accept-import" and d.get("deliveryId") == release["id"] for d in manifest["decisions"])
        release["roundTripRequired"] = "2" not in index.get("protocolBaselines", {})
    if len(_DISPLAY_CACHE) >= 32:
        _DISPLAY_CACHE.pop(next(iter(_DISPLAY_CACHE)))
    _DISPLAY_CACHE[str(root)] = (signature, copy.deepcopy(result))
    return result


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
    for cue in manifest["cues"]:
        if not set(cue.get("segmentIds", [])).issubset(segment_ids):
            raise ValueError("unknown cue segmentId")
        timeline = cue.get("resolvedTimeline")
        if timeline and (parse_time(timeline["start"]) < 0 or parse_time(timeline["duration"]) <= 0):
            raise ValueError("invalid cue time")


def _record_decision(root, manifest, request):
    kind = request.get("kind")
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
            for feedback in manifest["feedback"]:
                if feedback["status"] == "addressed":
                    feedback.update(status="accepted", acceptedSource=source)
            if any(f["status"] in {"pending", "needs-clarification"} for f in manifest["feedback"]):
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


@verified_operation
def update(version_root, request):
    root = Path(version_root).expanduser().resolve()
    # Check read-only before creating a lock in a historical directory.
    load(root, writable=True)
    afterforge, _ = layout(root)
    if request.get("operation") in {"memory", "visual-defaults"}:
        with project_lock(afterforge), manifest_transaction(root):
            manifest = load(root, writable=True)
            previous = request_check(manifest, request)
            if previous is not None:
                return previous
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
        operation = request.get("operation")
        installs = []
        record = None
        if operation == "runtime":
            from scripts.work_model_runtime import runtime_files
            supplied = None
            if request.get("vendorSource"):
                candidate = Path(request["vendorSource"]).expanduser().absolute()
                if not candidate.is_relative_to(root / ".staging"):
                    raise ValueError("vendorSource must be prepared in version .staging")
                supplied = safe(root, candidate.relative_to(root).as_posix())
            for name, data in runtime_files(root, manifest, request.get("version"), supplied).items():
                destination = safe(root, name, exists=False)
                installs.append((destination, data, destination.read_bytes() if destination.exists() else None))
        elif operation == "edit":
            patch = request.get("patch", {})
            if not isinstance(patch, dict) or set(patch) - {"brief", "cues", "project"}:
                raise ValueError("edit may change only brief, cues and project settings")
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
            _validate_edit(manifest)
            for item in request.get("files", []):
                name = item["path"]
                if not (name.startswith(("compositions/", "assets/")) or name in {"frame.md", "package.json", "hyperframes.json", "meta.json"}):
                    raise ValueError("source update cannot overwrite evidence, cache or release files")
                if name.startswith("assets/source/"):
                    raise ValueError("bound roughcut inputs are immutable")
                destination = safe(root, name, exists=False)
                staged = Path(item["source"]).expanduser().absolute()
                if not staged.is_relative_to(root / ".staging"):
                    raise ValueError("source file must be prepared in version .staging")
                staged = safe(root, staged.relative_to(root).as_posix())
                if not staged.is_file():
                    raise ValueError("staged source must be a regular file")
                if destination.exists() and name == "package.json":
                    from scripts.hyperframes_runtime import read_runtime_pin
                    import re
                    pin = read_runtime_pin(root)
                    pins = re.findall(r"--package=hyperframes@([^\s]+)", staged.read_text())
                    if not pins or any(p != pin for p in pins):
                        raise ValueError("runtime migration requires an explicit new version")
                installs.append((destination, staged.read_bytes(), destination.read_bytes() if destination.exists() else None))
        elif operation == "feedback":
            body = request.get("body")
            if not isinstance(body, str) or not body.strip():
                raise ValueError("feedback body is required")
            target = copy.deepcopy(request.get("target", {}))
            if target.get("versionId") != manifest["identity"]["versionId"]:
                raise ValueError("feedback target version mismatch")
            if target.get("artifactId") and target["artifactId"] not in {a["id"] for a in manifest["artifacts"]}:
                raise ValueError("unknown feedback artifact")
            for field, valid in (("cueIds", {c["id"] for c in manifest["cues"]}), ("segmentIds", {s["id"] for s in manifest["brief"]["segments"]})):
                if not set(target.get(field, [])).issubset(valid):
                    raise ValueError("unknown feedback target")
            from scripts.hyperframes_adapter import parse_time
            start = parse_time(target["timeStart"]) if target.get("timeStart") else None
            end = parse_time(target["timeEnd"]) if target.get("timeEnd") else None
            if (start is not None and start < 0) or (end is not None and (start is None or end < start)):
                raise ValueError("invalid feedback time interval")
            if manifest["project"].get("source"):
                total = parse_time(manifest["project"]["source"]["duration"])
                if any(moment is not None and moment > total for moment in (start, end)):
                    raise ValueError("feedback interval outside episode")
            record = {"id": _identifier("feedback"), "body": body.strip(), "target": target,
                      "source": user_source(request.get("source")), "status": "pending", "createdAt": now()}
            manifest["feedback"].append(record)
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
        elif operation == "roundtrip":
            return _register_roundtrip(root, manifest, request)
        else:
            raise ValueError("unsupported update operation")
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
    afterforge, index = layout(root)
    release = next((d for d in manifest["deliveries"] if d["id"] == request.get("deliveryId")), None)
    if release is None:
        raise ValueError("unknown deliveryId")
    verify_release(root, afterforge, release)
    if not any(d["kind"] == "accept-import" and d.get("deliveryId") == release["id"] for d in manifest["decisions"]):
        raise ValueError("record actual FCP import acceptance first")
    snapshot = safe(root, release["snapshotPath"])
    frozen = json.loads((snapshot / release["manifestPath"]).read_text())
    delivered = safe(afterforge, release["packagePath"]) / "Info.fcpxml"
    reexported = Path(request["reexportedPath"]).expanduser().resolve()
    result = compare_roundtrip(delivered, reexported, frozen)
    record = {"id": _identifier("decision"), "kind": "roundtrip", "source": user_source(request.get("source")),
              "deliveryId": release["id"], "createdAt": now(), "result": result,
              "reexportedSha256": sha(reexported), "infoFcpxmlSha256": sha(delivered)}
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
        index.setdefault("protocolBaselines", {})["2"] = {"versionRoot": root.relative_to(afterforge).as_posix(),
              "deliveryId": release["id"], "decisionId": record["id"], "verifiedAt": now()}
        try:
            save(root, manifest)
            atomic_json(marker, index)
        except BaseException:
            atomic_bytes(root / "animation-manifest.json", previous_manifest)
            atomic_bytes(marker, previous_index)
            raise
    return response
