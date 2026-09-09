"""Work-model contracts exercise production APIs, not historical stage transitions."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkModelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.afterforge = Path(self.directory.name) / "AfterForge"

    def create(self, **extra):
        from scripts import work_model as model
        result = model.open_project(self.afterforge, {
            "requestId": "create", "expectedRevision": 0,
            "title": "电影系列", "episodeTitle": "01 开场", **extra,
        })
        return model, Path(result["root"])

    def edit(self, model, root, **values):
        return model.update(root, {
            "requestId": "edit-" + str(model.status(root)["editRevision"]),
            "expectedRevision": model.status(root)["editRevision"],
            "operation": "edit", **values,
        })

    def test_cli_creates_planning_version_without_timeline_or_runtime(self):
        request = Path(self.directory.name) / "request.json"
        request.write_text(json.dumps({"requestId": "open", "expectedRevision": 0,
                                       "title": "楚门", "episodeTitle": "片头"}))
        completed = subprocess.run([sys.executable, "scripts/afterforge.py", "open", str(self.afterforge),
                                    "--request-file", str(request)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        root = Path(json.loads(completed.stdout)["root"])
        manifest = json.loads((root / "animation-manifest.json").read_text())
        self.assertEqual(manifest["schemaVersion"], "3.0")
        self.assertIsNone(manifest["project"]["source"])
        self.assertFalse((root / "package.json").exists())
        self.assertFalse((self.afterforge.parent / "user-inbox").exists())

    def test_open_is_idempotent_and_episode_identity_is_not_input_folder_name(self):
        model, root = self.create()
        same = model.open_project(self.afterforge, {"requestId": "create", "expectedRevision": 0,
                            "title": "电影系列", "episodeTitle": "01 开场"})
        self.assertEqual(Path(same["root"]), root)
        index = model.project_status(self.afterforge)
        second = model.open_project(self.afterforge, {"requestId": "second", "expectedRevision": index["revision"],
                          "episodeTitle": "02 镜子"})
        self.assertNotEqual(model.status(root)["identity"]["episodeId"],
                            model.status(Path(second["root"]))["identity"]["episodeId"])
        self.assertNotIn("blockingStage", model.status(root))

    def test_edit_retry_conflict_and_metadata_have_separate_content_identity(self):
        model, root = self.create()
        request = {"requestId": "words", "expectedRevision": 0, "operation": "edit",
                   "patch": {"brief": {"summary": "让观众先回答，再怀疑答案。", "segments": []}}}
        result = model.update(root, request)
        self.assertEqual(model.update(root, request), result)
        with self.assertRaisesRegex(ValueError, "request|请求"):
            model.update(root, {**request, "patch": {"brief": {"summary": "changed", "segments": []}}})
        with self.assertRaisesRegex(ValueError, "stale|过期|revision"):
            model.update(root, {**request, "requestId": "stale"})
        self.assertEqual(model.status(root)["brief"]["summary"], "让观众先回答，再怀疑答案。")

    def test_preview_reports_real_missing_inputs_not_static_approval(self):
        model, root = self.create()
        with self.assertRaisesRegex(ValueError, "source|粗剪|输入"):
            model.preview(root, {"requestId": "preview", "expectedRevision": 0, "scope": "full"})

    def test_feedback_keeps_interval_without_selecting_overlapping_cue(self):
        model, root = self.create()
        identity = model.status(root)["identity"]
        result = model.update(root, {"requestId": "feedback", "expectedRevision": 0, "operation": "feedback",
          "body": "这段太抢口播", "source": {"channel": "chat", "text": "这段太抢口播", "reference": "turn1"},
          "target": {"versionId": identity["versionId"], "timeStart": "1/2s", "timeEnd": "2s"}})
        feedback = model.status(root)["feedback"][0]
        self.assertEqual(feedback["target"].get("cueIds", []), [])
        self.assertEqual(feedback["body"], "这段太抢口播")
        self.assertEqual(feedback["status"], "pending")
        model.update(root, {"requestId": "address", "expectedRevision": result["editRevision"],
            "operation": "feedback-status", "feedbackId": feedback["id"], "status": "addressed",
            "resolution": "去掉了多余标注", "actor": "agent"})
        self.assertEqual(model.status(root)["feedback"][0]["status"], "addressed")
        with self.assertRaisesRegex(ValueError, "user|用户"):
            model.update(root, {"requestId": "false-accept", "expectedRevision": 2,
                "operation": "feedback-status", "feedbackId": feedback["id"], "status": "accepted", "actor": "agent"})

    def test_staged_write_rolls_back_and_cannot_overwrite_evidence(self):
        model, root = self.create()
        stage = root / ".staging" / "candidate"
        stage.mkdir(parents=True)
        (stage / "layout.html").write_text("<div>new layout</div>")
        before = (root / "animation-manifest.json").read_bytes()
        with self.assertRaises(ValueError):
            self.edit(model, root, files=[{"path": "releases/old/manifest.json", "source": str(stage / "layout.html")}])
        self.assertEqual((root / "animation-manifest.json").read_bytes(), before)
        self.edit(model, root, files=[{"path": "compositions/cues/title.html", "source": str(stage / "layout.html")}])
        self.assertEqual((root / "compositions/cues/title.html").read_text(), "<div>new layout</div>")

    def test_legacy_read_and_copy_do_not_inherit_authorization_or_modify_source(self):
        from tests.test_hyperframes_single_source import SingleSourceFixture
        legacy_parent = Path(self.directory.name) / "legacy"
        legacy_parent.mkdir()
        legacy = SingleSourceFixture().make_version(str(legacy_parent))
        before = {str(p.relative_to(legacy)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in legacy.rglob("*") if p.is_file()}
        from scripts import work_model as model
        self.assertTrue(model.status(legacy)["legacy"])
        with self.assertRaisesRegex(ValueError, "legacy|旧|read.only"):
            model.update(legacy, {"requestId": "bad", "expectedRevision": 0, "operation": "edit", "patch": {}})
        result = model.open_project(self.afterforge, {"requestId": "copy", "expectedRevision": 0,
            "title": "楚门", "episodeTitle": "开场", "copyFrom": str(legacy)})
        copied = json.loads((Path(result["root"]) / "animation-manifest.json").read_text())
        self.assertEqual(copied["decisions"], [])
        self.assertEqual(copied["deliveries"], [])
        self.assertNotIn("workflow", copied)
        after = {str(p.relative_to(legacy)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in legacy.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_memory_update_preserves_version_visual_snapshot(self):
        model, root = self.create()
        self.edit(model, root, patch={"brief": {"summary": "开场观点", "segments": []}})
        model.update(root, {"requestId": "memory", "expectedRevision": 1, "operation": "memory",
             "text": "# 系列创作记忆\n\n当前共识：开场让口播主导。\n", "expectedMemorySha256": model.status(root)["memorySha256"]})
        self.assertIn("开场让口播主导", (self.afterforge / "工程/创作记忆.md").read_text())
        self.assertFalse((root / "frame.md").exists())


if __name__ == "__main__":
    unittest.main()

class RuntimeSetupTests(unittest.TestCase):
    setUp = WorkModelTests.setUp
    create = WorkModelTests.create
    def test_runtime_setup_uses_local_exact_version_without_install(self):
        from unittest.mock import patch
        model,root=self.create()
        with tempfile.TemporaryDirectory() as directory:
            vendor=Path(directory)/'gsap.min.js';vendor.write_text('/* local test gsap */')
            with patch('scripts.work_model_runtime.local_vendor',return_value=vendor):
                model.update(root,{'requestId':'runtime','expectedRevision':0,'operation':'runtime','version':'0.8.33'})
            from scripts.hyperframes_runtime import read_runtime_pin
            self.assertEqual(read_runtime_pin(root),'0.8.33')
            self.assertIn('--offline',(root/'package.json').read_text())
            with self.assertRaisesRegex(ValueError,'new version|新版本'):
                model.update(root,{'requestId':'migration','expectedRevision':1,'operation':'runtime','version':'0.8.34'})

class SeriesDefaultsTests(unittest.TestCase):
    setUp = WorkModelTests.setUp
    create = WorkModelTests.create

    def test_series_visual_default_does_not_mutate_existing_version_snapshot(self):
        model,root=self.create()
        model.update(root,{'requestId':'style','expectedRevision':0,'operation':'visual-defaults','text':'# 包装\n青绿标题。','expectedFrameSha256':None})
        self.assertFalse((root/'frame.md').exists())
        state=model.status(root)
        second=model.open_project(self.afterforge,{'requestId':'next','expectedRevision':1,'episodeId':state['identity']['episodeId']})
        self.assertEqual((Path(second['root'])/'frame.md').read_text(),'# 包装\n青绿标题。')
        model.update(root,{'requestId':'style2','expectedRevision':1,'operation':'visual-defaults','text':'# 包装\n白色标题。','expectedFrameSha256':state['frameSha256']})
        self.assertEqual((Path(second['root'])/'frame.md').read_text(),'# 包装\n青绿标题。')

class VerifiedHashTests(unittest.TestCase):
    def test_hash_reuse_is_scoped_and_cannot_survive_input_changes(self):
        import os
        from unittest.mock import patch
        from scripts.work_model_store import sha,verification_scope,fresh_hashes
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'input';file.write_bytes(b'one')
            original=hashlib.sha256
            with patch('scripts.work_model_store.hashlib.sha256',wraps=original) as digest:
                with verification_scope():
                    first=sha(file);self.assertEqual(sha(file),first)
                    self.assertEqual(digest.call_count,1)
                    stamp=file.stat();file.write_bytes(b'two');os.utime(file,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
                    self.assertNotEqual(sha(file),first)
                    self.assertEqual(digest.call_count,2)
                    fresh_hashes();sha(file)
                    self.assertEqual(digest.call_count,3)
                with verification_scope(): sha(file)
                self.assertEqual(digest.call_count,4)
