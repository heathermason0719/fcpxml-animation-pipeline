#!/usr/bin/env python3
"""Project-scoped HTTP boundary for the Review v3 work model.

The domain model deliberately stays independent of this local server.  This
module only resolves an opaque version id from the model's project index,
serves the static review shell, and forwards validated requests to the model.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "review-v3"
MAX_BODY_BYTES = 64 * 1024


def _load_model_api() -> ModuleType:
    """Import the work model only when the review server is actually used."""
    from scripts import work_model

    return work_model


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _read_asset(name: str) -> bytes:
    target = (ASSET_ROOT / name).resolve()
    if target.parent != ASSET_ROOT.resolve() or not target.is_file():
        raise ValueError("review asset not found")
    return target.read_bytes()


def _contains_symlink(path: Path, *, stop_at: Path | None = None) -> bool:
    """Return true for a symlink at or below an optional trusted root."""
    current = path
    while True:
        if current.is_symlink():
            return True
        if stop_at is not None and current == stop_at:
            return False
        if current.parent == current:
            return False
        current = current.parent


def _strict_child(root: Path, relative: str) -> Path:
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or any(part in {"", ".", ".."} for part in candidate_relative.parts):
        raise LookupError("path is outside its allowed root")
    candidate = root.joinpath(candidate_relative)
    if _contains_symlink(candidate, stop_at=root):
        raise LookupError("symlinked paths are not available")
    resolved = candidate.resolve()
    if root != resolved and root not in resolved.parents:
        raise LookupError("path is outside its allowed root")
    return resolved


def _project_versions(afterforge_root: Path, model_api: Any) -> tuple[dict[str, Path], dict[str, Any]]:
    project = model_api.project_status(afterforge_root)
    if not isinstance(project, dict) or not isinstance(project.get("episodes"), list):
        raise ValueError("work model returned an invalid project index")
    versions: dict[str, Path] = {}
    for episode in project["episodes"]:
        if not isinstance(episode, dict) or not isinstance(episode.get("versions"), list):
            raise ValueError("work model returned an invalid episode index")
        for version in episode["versions"]:
            if not isinstance(version, dict):
                raise ValueError("work model returned an invalid version index")
            version_id, relative_root = version.get("id"), version.get("root")
            if not isinstance(version_id, str) or not version_id or not isinstance(relative_root, str) or not relative_root:
                raise ValueError("work model version requires id and root")
            try:
                candidate = _strict_child(afterforge_root, relative_root)
            except LookupError as error:
                raise ValueError("work model version root escapes project") from error
            if candidate == afterforge_root:
                raise ValueError("work model version root escapes project")
            if version_id in versions:
                raise ValueError(f"duplicate work model version id: {version_id}")
            versions[version_id] = candidate
    return versions, project


def _resolve_version(afterforge_root: Path, model_api: Any, version_id: str | None) -> tuple[Path, dict[str, Any]]:
    if not isinstance(version_id, str) or not version_id:
        raise LookupError("version is required")
    versions, _ = _project_versions(afterforge_root, model_api)
    root = versions.get(version_id)
    if root is None:
        raise LookupError("unknown version")
    return root, model_api.status(root)


def _allowed_media_paths(state: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for artifact in state.get("artifacts", []):
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
            allowed.add(artifact["path"])
    for delivery in state.get("deliveries", []):
        if not isinstance(delivery, dict):
            continue
        for media in delivery.get("media", []):
            if isinstance(media, dict) and isinstance(media.get("path"), str):
                allowed.add(media["path"])
    return allowed


def _safe_media_target(version_root: Path, state: dict[str, Any], requested: str | None) -> Path:
    if not isinstance(requested, str) or not requested or requested not in _allowed_media_paths(state):
        raise LookupError("unknown media artifact")
    target = _strict_child(version_root, requested)
    if not target.is_file():
        raise LookupError("media artifact is unavailable")
    return target


def _delivery_package(afterforge_root: Path, state: dict[str, Any], delivery_id: str | None) -> Path:
    if not isinstance(delivery_id, str) or not delivery_id:
        raise LookupError("delivery is required")
    matches = [item for item in state.get("deliveries", []) if isinstance(item, dict) and item.get("id") == delivery_id]
    if len(matches) != 1 or not isinstance(matches[0].get("packagePath"), str):
        raise LookupError("unknown delivery")
    package = _strict_child(afterforge_root, matches[0]["packagePath"])
    if package.suffix != ".fcpxmld" or not package.is_dir():
        raise LookupError("delivery package is unavailable")
    return package


def _spooled_package_zip(package: Path):
    """Build a disk-backed temporary archive without touching the release."""
    output = tempfile.SpooledTemporaryFile(max_size=1, mode="w+b")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in sorted(package.rglob("*")):
            if member.is_symlink():
                output.close()
                raise LookupError("symlinked delivery contents are not available")
            if member.is_file():
                archive.write(member, member.relative_to(package.parent))
    output.rollover()
    output.seek(0)
    return output


def _script_markdown(state: dict[str, Any]) -> str:
    """Render the overview's brief and resolved cue text as a Markdown file."""
    identity = state.get("identity", {})
    brief = state.get("brief", {})
    title = identity.get("episodeTitle") or identity.get("versionTitle") or "AfterForge"
    version = identity.get("versionTitle") or identity.get("versionId") or ""
    lines = [f"# {title}{f' · {version}' if version else ''}", ""]
    summary = brief.get("summary") if isinstance(brief, dict) else None
    if isinstance(summary, str) and summary.strip():
        lines.extend(["## 本版说明", "", summary.strip(), ""])
    change_summary = brief.get("changeSummary") if isinstance(brief, dict) else None
    if isinstance(change_summary, str) and change_summary.strip():
        lines.extend(["## 本轮变化", "", change_summary.strip(), ""])
    segments = brief.get("segments", []) if isinstance(brief, dict) else []
    if isinstance(segments, list) and segments:
        lines.extend(["## 段落", ""])
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            name = segment.get("title") or segment.get("id") or "未命名段落"
            detail = next((segment.get(key) for key in ("purpose", "narration", "visualPlan")
                           if isinstance(segment.get(key), str) and segment[key].strip()), None)
            lines.extend([f"### {name}", ""])
            if detail:
                lines.extend([detail.strip(), ""])
    cues = state.get("cues", [])
    if isinstance(cues, list) and cues:
        lines.extend(["## 镜头", ""])
        for cue in cues:
            if not isinstance(cue, dict):
                continue
            name = cue.get("title") or cue.get("id") or "未命名镜头"
            cue_range = cue.get("range") if isinstance(cue.get("range"), dict) else {}
            start = cue_range.get("start")
            description = next((cue.get(key) for key in ("finalAnimationDescription", "resolvedDescription", "purpose", "visualPlan")
                                if isinstance(cue.get(key), str) and cue[key].strip()), None)
            lines.extend([f"### {name}", ""])
            if isinstance(start, str) and start:
                lines.extend([f"- 时间：{start}"])
            if description:
                lines.extend([description.strip()])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def make_handler(afterforge_root: Path, *, model_api: Any | None = None):
    """Create a handler bound to one AfterForge root and a model API."""
    raw_root = Path(afterforge_root).expanduser().absolute()
    if raw_root.is_symlink():
        raise ValueError("AfterForge root may not contain a symlink")
    root = raw_root.resolve()
    api = model_api
    async_failures: dict[str, dict[str, Any]] = {}
    async_lock = threading.Lock()

    def state_with_async_failures(version_root: Path) -> dict[str, Any]:
        state = api.status(version_root) if api is not None else _load_model_api().status(version_root)
        if not isinstance(state, dict):
            raise ValueError("work model returned an invalid version state")
        with async_lock:
            failures = list(async_failures.values())
        tasks = state.get("tasks", [])
        base_tasks = tasks if isinstance(tasks, list) else []
        state["tasks"] = [*base_tasks, *failures]
        return state

    class ReviewV3Handler(BaseHTTPRequestHandler):
        def _api(self) -> Any:
            nonlocal api
            if api is None:
                api = _load_model_api()
            return api

        def _state(self, version_root: Path) -> dict[str, Any]:
            self._api()
            return state_with_async_failures(version_root)

        def end_headers(self) -> None:
            self.send_header("cache-control", "no-store")
            super().end_headers()

        def _json(self, status: int, payload: Any) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _asset(self, name: str, content_type: str) -> None:
            body = _read_asset(name)
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _script(self, state: dict[str, Any]) -> None:
            body = _script_markdown(state).encode("utf-8")
            version = state.get("identity", {}).get("versionId", "script")
            filename = re.sub(r"[^A-Za-z0-9._-]+", "-", str(version)).strip("-") or "script"
            self.send_response(200)
            self.send_header("content-type", "text/markdown; charset=utf-8")
            self.send_header("content-disposition", f'attachment; filename="afterforge-{filename}-script.md"')
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _download(self, package: Path) -> None:
            archive = _spooled_package_zip(package)
            try:
                self.send_response(200)
                self.send_header("content-type", "application/zip")
                self.send_header("content-disposition", f'attachment; filename="{package.name}.zip"')
                self.end_headers()
                if self.command == "HEAD":
                    return
                for chunk in iter(lambda: archive.read(64 * 1024), b""):
                    self.wfile.write(chunk)
            finally:
                archive.close()

        def _file(self, target: Path) -> None:
            with target.open("rb") as source:
                size = os.fstat(source.fileno()).st_size
                start, end, partial = 0, size - 1, False
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
                if match and any(match.groups()) and self.command == "GET":
                    first, last = match.groups()
                    start = int(first) if first else max(0, size - int(last))
                    end = min(int(last), size - 1) if last else size - 1
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header("content-range", f"bytes */{size}")
                        self.send_header("accept-ranges", "bytes")
                        self.send_header("content-length", "0")
                        self.end_headers()
                        return
                    partial = True
                self.send_response(206 if partial else 200)
                self.send_header("content-type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                self.send_header("accept-ranges", "bytes")
                self.send_header("content-length", str(end - start + 1))
                if partial:
                    self.send_header("content-range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if self.command == "HEAD":
                    return
                source.seek(start)
                self.wfile.write(source.read(end - start + 1))

        def _query_version(self) -> str | None:
            values = parse_qs(urlparse(self.path).query).get("version", [])
            return values[0] if len(values) == 1 else None

        def _same_origin_local_post(self) -> bool:
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            if host not in {"127.0.0.1", "localhost", "[::1]"}:
                return False
            origin = self.headers.get("Origin")
            if not origin:
                return True
            parsed = urlparse(origin)
            return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == self.server.server_port

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._asset("index.html", "text/html; charset=utf-8")
                elif parsed.path == "/review-neutral.css":
                    self._asset("review-neutral.css", "text/css; charset=utf-8")
                elif parsed.path == "/review-v3.css":
                    self._asset("review-v3.css", "text/css; charset=utf-8")
                elif parsed.path == "/review-v3.js":
                    self._asset("review-v3.js", "text/javascript; charset=utf-8")
                elif parsed.path == "/api/project":
                    _, project = _project_versions(root, self._api())
                    self._json(200, project)
                elif parsed.path == "/api/state":
                    version_root, _ = _resolve_version(root, self._api(), self._query_version())
                    state = self._state(version_root)
                    self._json(200, state)
                elif parsed.path == "/script":
                    version_root, _ = _resolve_version(root, self._api(), self._query_version())
                    self._script(self._state(version_root))
                elif parsed.path == "/media":
                    version_root, state = _resolve_version(root, self._api(), self._query_version())
                    path = parse_qs(parsed.query).get("path", [None])[0]
                    self._file(_safe_media_target(version_root, state, unquote(path) if isinstance(path, str) else None))
                elif parsed.path == "/download":
                    _, state = _resolve_version(root, self._api(), self._query_version())
                    delivery_id = parse_qs(parsed.query).get("delivery", [None])[0]
                    self._download(_delivery_package(root, state, delivery_id))
                else:
                    self._json(404, {"error": "not found"})
            except LookupError as error:
                self._json(404, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                # Browsers routinely cancel buffered media requests while a
                # video element selects its range; there is no client left to
                # receive an error response.
                return
            except (OSError, ValueError, KeyError) as error:
                self._json(500, {"error": str(error)})

        def _request_body(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("invalid request body length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            return payload

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/action":
                self._json(404, {"error": "not found"})
                return
            if not self._same_origin_local_post():
                self._json(403, {"error": "local same-origin request required"})
                return
            try:
                payload = self._request_body()
                version_id, action, request = payload.get("version"), payload.get("action"), payload.get("request")
                if not isinstance(action, str) or action not in {"update", "preview", "deliver", "resume"}:
                    raise ValueError("unsupported action")
                if not isinstance(request, dict) or not isinstance(request.get("requestId"), str) or not request["requestId"]:
                    raise ValueError("request requires requestId")
                if not isinstance(request.get("expectedRevision"), int):
                    raise ValueError("request requires expectedRevision")
                version_root, _ = _resolve_version(root, self._api(), version_id)
                method = getattr(self._api(), action)
                if action in {"preview", "deliver"}:
                    def run_background() -> None:
                        try:
                            method(version_root, request)
                        except Exception as error:  # Surface setup failures through normal status polling.
                            with async_lock:
                                async_failures[request["requestId"]] = {
                                    "id": request["requestId"], "status": "failed", "error": str(error),
                                }
                    threading.Thread(target=run_background, daemon=True).start()
                    self._json(202, {"status": "started", "requestId": request["requestId"]})
                    return
                self._json(200, method(version_root, request))
            except LookupError as error:
                self._json(404, {"error": str(error)})
            except ValueError as error:
                # A model rejects stale optimistic edits with ValueError.  The UI
                # retains its draft and target when it receives this response.
                status = 409 if "stale" in str(error).lower() else 400
                self._json(status, {"error": str(error)})
            except (OSError, KeyError, json.JSONDecodeError) as error:
                self._json(400, {"error": str(error)})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ReviewV3Handler


def serve(afterforge_root: Path, host: str = "127.0.0.1", port: int = 8765, *, model_api: Any | None = None) -> ThreadingHTTPServer:
    """Return a local server; callers own ``serve_forever`` and shutdown."""
    return ThreadingHTTPServer((host, port), make_handler(afterforge_root, model_api=model_api))


def main() -> int:
    parser = argparse.ArgumentParser(description="启动项目级 AfterForge Review v3。")
    parser.add_argument("afterforge_root", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = serve(args.afterforge_root, args.host, args.port)
    print(json.dumps({"status": "serving", "url": f"http://{args.host}:{server.server_port}"}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
