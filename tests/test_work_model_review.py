"""HTTP boundary tests for the project-scoped Review v3 server."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import time
import unittest
import subprocess
import sys
from pathlib import Path

from scripts import work_model
from tests import test_work_model_jobs as work_model_jobs
from tests import work_model_fixtures


class FakeModel:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requests: list[tuple[str, Path, dict]] = []

    def project_status(self, root: Path) -> dict:
        self.root = root
        return {"projectId": "p1", "title": "电影旁批", "episodes": [
            {"id": "e1", "title": "第一集", "versions": [
                {"id": "v1", "title": "V1", "root": "episode-1/V1", "legacy": False},
                {"id": "v2", "title": "V2", "root": "episode-1/V2", "legacy": False},
            ]}
        ]}

    def status(self, root: Path) -> dict:
        is_v2 = root.name == "V2"
        return {
            "identity": {"projectId": "p1", "episodeId": "e1", "versionId": "v2" if is_v2 else "v1", "episodeTitle": "第一集", "versionTitle": "V2" if is_v2 else "V1"},
            "editRevision": 7, "brief": ({"summary": "第二版中文说明", "changeSummary": "调整开场节奏", "segments": [{"id": "s1", "title": "开场", "purpose": "先建立人物处境"}]} if is_v2 else {"summary": "", "segments": []}),
            "cues": ([{"id": "cue-v2", "title": "标题镜头", "range": {"start": "5/2s"}, "finalAnimationDescription": "标题从左侧进入并停留。"}] if is_v2 else []),
            "artifacts": [{"id": "demo", "kind": "preview", "path": "previews/demo.mp4", "sha256": "a" * 64,
                           "range": {"start": "0s", "duration": "1s"}, "cueIds": [], "complete": True, "current": True}],
            "reviewSet": {"id": "review-7"}, "feedback": [],
            "deliveries": [{"id": "delivery-1", "packagePath": "Release.fcpxmld", "media": [
                {"path": "delivery/title.mov", "label": "标题动画"}
            ]}], "tasks": [], "availableActions": [], "legacy": False,
        }

    def update(self, root: Path, request: dict) -> dict:
        self.requests.append(("update", root, request))
        if request.get("expectedRevision") != 7:
            raise ValueError("stale edit revision")
        return {"status": "saved"}

    def preview(self, root: Path, request: dict) -> dict:
        self.requests.append(("preview", root, request))
        if getattr(self, "preview_error", False):
            raise ValueError("preview inputs are unavailable")
        time.sleep(0.04)
        return {"status": "done"}

    def deliver(self, root: Path, request: dict) -> dict:
        self.requests.append(("deliver", root, request))
        return {"status": "done"}

    def resume(self, root: Path, request: dict) -> dict:
        self.requests.append(("resume", root, request))
        return {"status": "done"}


class WorkModelReviewServerTests(unittest.TestCase):
    def setUp(self) -> None:
        from scripts.work_model_review import serve

        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.version = self.root / "episode-1/V1"
        (self.version / "previews").mkdir(parents=True)
        (self.version / "previews/demo.mp4").write_bytes(b"0123456789")
        (self.version / "delivery").mkdir()
        (self.version / "delivery/title.mov").write_bytes(b"movie")
        (self.root / "Release.fcpxmld").mkdir()
        (self.root / "Release.fcpxmld/Info.fcpxml").write_text("<fcpxml/>", encoding="utf-8")
        self.model = FakeModel(self.root)
        self.server = serve(self.root, port=0, model_api=self.model)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        raw = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        request_headers = headers or {}
        if raw is not None:
            request_headers = {"content-type": "application/json", **request_headers}
        connection.request(method, path, raw, request_headers)
        response = connection.getresponse()
        result = response.read()
        connection.close()
        return response.status, dict(response.getheaders()), result

    def test_project_index_and_state_use_opaque_allowlisted_version_key(self) -> None:
        status, _, body = self.request("GET", "/api/project")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["episodes"][0]["versions"][0]["id"], "v1")
        status, _, body = self.request("GET", "/api/state?version=v1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["editRevision"], 7)
        status, _, _ = self.request("GET", "/api/state?version=../../etc/passwd")
        self.assertEqual(status, 404)

    def test_feedback_preserves_target_and_rejects_stale_revision(self) -> None:
        request = {"requestId": "r1", "expectedRevision": 7, "operation": "feedback", "body": "文字太小", "source": {"channel": "review", "text": "提交反馈"}, "target": {"versionId": "v1", "artifactId": "demo", "cueIds": ["cue-1"], "timeStart": "1s"}}
        status, _, body = self.request("POST", "/api/action", {"version": "v1", "action": "update", "request": request})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "saved")
        self.assertEqual(self.model.requests[-1][2]["target"], request["target"])
        request["expectedRevision"] = 6
        status, _, body = self.request("POST", "/api/action", {"version": "v1", "action": "update", "request": request})
        self.assertEqual(status, 409)
        self.assertIn("stale", json.loads(body)["error"])

    def test_script_export_uses_selected_version_state_without_mutation(self) -> None:
        before_requests = list(self.model.requests)
        status, headers, body = self.request("GET", "/script?version=v2")
        self.assertEqual(status, 200)
        self.assertEqual(next(value for key, value in headers.items() if key.lower() == "content-type"), "text/markdown; charset=utf-8")
        self.assertIn('filename="afterforge-v2-script.md"', next(value for key, value in headers.items() if key.lower() == "content-disposition"))
        script = body.decode("utf-8")
        self.assertIn("# 第一集 · V2", script)
        self.assertIn("第二版中文说明", script)
        self.assertIn("## 本轮变化", script)
        self.assertIn("调整开场节奏", script)
        self.assertIn("标题从左侧进入并停留。", script)
        self.assertNotIn("delivery-1", script)
        self.assertEqual(self.model.requests, before_requests)

    def test_media_is_limited_to_status_artifacts_and_supports_byte_ranges(self) -> None:
        status, headers, body = self.request("GET", "/media?version=v1&path=previews/demo.mp4", headers={"Range": "bytes=2-5"})
        self.assertEqual(status, 206)
        self.assertEqual(next(value for key, value in headers.items() if key.lower() == "content-range"), "bytes 2-5/10")
        self.assertEqual(body, b"2345")
        status, _, _ = self.request("GET", "/media?version=v1&path=animation-manifest.json")
        self.assertEqual(status, 404)

    def test_long_action_starts_in_background_and_returns_request_id(self) -> None:
        status, _, body = self.request("POST", "/api/action", {"version": "v1", "action": "preview", "request": {"requestId": "slow-1", "expectedRevision": 7}})
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body), {"status": "started", "requestId": "slow-1"})
        for _ in range(20):
            if self.model.requests:
                break
            time.sleep(0.01)
        self.assertEqual(self.model.requests[-1][0], "preview")

    def test_delivery_download_archives_only_the_registered_package(self) -> None:
        from scripts.work_model_review import _spooled_package_zip

        archive = _spooled_package_zip(self.root / "Release.fcpxmld")
        try:
            self.assertTrue(archive._rolled)
        finally:
            archive.close()
        status, headers, body = self.request("GET", "/download?version=v1&delivery=delivery-1")
        self.assertEqual(status, 200)
        self.assertEqual(next(value for key, value in headers.items() if key.lower() == "content-type"), "application/zip")
        self.assertTrue(body.startswith(b"PK"))
        self.assertIn(b"Info.fcpxml", body)
        status, _, _ = self.request("GET", "/download?version=v1&delivery=missing")
        self.assertEqual(status, 404)

    def test_write_requires_a_local_same_origin_request(self) -> None:
        request = {"requestId": "origin-1", "expectedRevision": 7}
        status, _, _ = self.request("POST", "/api/action", {"version": "v1", "action": "resume", "request": request}, {"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.model.requests, [])

    def test_rejects_symlinked_registered_media(self) -> None:
        outside = self.root / "secret.mov"
        outside.write_bytes(b"secret")
        (self.version / "delivery/title.mov").unlink()
        os.symlink(outside, self.version / "delivery/title.mov")
        status, _, _ = self.request("GET", "/media?version=v1&path=delivery/title.mov")
        self.assertEqual(status, 404)

    def test_background_failure_is_exposed_through_state_tasks(self) -> None:
        self.model.preview_error = True
        self.request("POST", "/api/action", {"version": "v1", "action": "preview", "request": {"requestId": "bad-preview", "expectedRevision": 7}})
        for _ in range(20):
            status, _, body = self.request("GET", "/api/state?version=v1")
            tasks = json.loads(body)["tasks"]
            if any(task.get("id") == "bad-preview" for task in tasks):
                break
            time.sleep(0.01)
        self.assertEqual(status, 200)
        failure = next(task for task in tasks if task.get("id") == "bad-preview")
        self.assertEqual(failure["status"], "failed")
        self.assertIn("unavailable", failure["error"])

    def test_direct_cli_bootstraps_package_imports(self) -> None:
        (self.root / "工程").mkdir()
        (self.root / "工程/project.json").write_text("{}", encoding="utf-8")
        process = subprocess.Popen(
            [str(Path(__file__).parents[1] / ".venv/bin/python"), "scripts/serve_workflow_review.py", str(self.root), "--port", "0"],
            cwd=Path(__file__).parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            line = process.stdout.readline()
            self.assertEqual(json.loads(line)["status"], "serving")
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def test_review_v3_client_action_and_stale_draft_contracts(self) -> None:
        harness = Path(__file__).with_name("review_v3_client_harness.cjs")
        for scenario in ("actions", "combined", "incomplete-preview", "time-normalization", "invalid-time-draft", "stale-draft", "storyboard-round", "selection-identity", "version-draft", "late-response"):
            with self.subTest(scenario=scenario):
                subprocess.run(["node", str(harness), scenario], check=True, cwd=Path(__file__).parents[1])

class RealStatusReviewClientTests(unittest.TestCase):
    """Feed the browser harness a status object produced by the public model API."""

    setUp = work_model_jobs.JobTests.setUp

    def test_storyboard_handoff_uses_active_model_status_snapshot(self) -> None:
        work_model_fixtures.activate(self.root, "review-client-real")
        state = work_model.status(self.root)
        self.assertEqual(len(state["storyboard"]["cues"]), 2)
        self.assertTrue(all(cue["canConfirm"] for cue in state["storyboard"]["cues"]))
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as fixture:
            json.dump(state, fixture, ensure_ascii=False)
            fixture.flush()
            harness = Path(__file__).with_name("review_v3_client_harness.cjs")
            subprocess.run(["node", str(harness), "real-status", fixture.name], check=True, cwd=Path(__file__).parents[1])


if __name__ == "__main__":
    unittest.main()
