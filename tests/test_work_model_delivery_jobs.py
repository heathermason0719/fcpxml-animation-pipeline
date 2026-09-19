"""End-to-end delivery-job boundaries with simulated render media."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as job_fixture
from tests.work_model_fixtures import activate, demo_request


class DeliveryJobIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reuse the established v3 project, two-cue timeline, and media mocks.
        job_fixture.JobTests.setUp(self)

    def req(self, name: str, **extra: object) -> dict:
        if extra.get('scope') == 'full':
            return demo_request(self.root, name, **extra)
        return {"requestId": name, "expectedRevision": load(self.root)["editRevision"], **extra}

    def preview_and_deliver(self, name: str = "deliver") -> dict:
        model.preview(self.root, self.req(f"{name}-preview", scope="full"))
        review = model.status(self.root)["reviewSet"]
        return model.deliver(self.root, self.req(name, decision={
            "kind": "approve-and-deliver", "reviewSetId": review["id"],
            "source": {"channel": "chat", "text": "交付当前完整版本", "reference": name},
        }))

    def edit_placement(self, name: str) -> None:
        manifest = load(self.root)
        manifest["cues"][0]["resolvedTimeline"]["start"] = "0s"
        model.update(self.root, self.req(name, operation="edit", patch={
            "cues": manifest["cues"], "brief": manifest["brief"],
        }))

    def test_approve_and_deliver_publishes_all_cues_and_retries_metadata(self) -> None:
        first = self.preview_and_deliver()
        record = first["delivery"]
        self.assertEqual(first["status"], "complete")
        self.assertEqual({item["cueId"] for item in record["media"]}, {cue["id"] for cue in load(self.root)["cues"] if cue["productionMode"] == "animation"})
        self.assertTrue((self.root / record["snapshotPath"] / record["manifestPath"]).is_file())
        self.assertTrue((self.root.parents[3] / record["packagePath"] / "Info.fcpxml").is_file())

        retry = model.deliver(self.root, self.req("metadata-retry", decision={
            "kind": "approve-and-deliver", "reviewSetId": model.status(self.root)["reviewSet"]["id"],
            "source": {"channel": "chat", "text": "同一交付元数据重试", "reference": "retry"},
        }))
        self.assertTrue(retry["reused"])
        self.assertEqual(retry["delivery"]["id"], record["id"])

    def test_placement_change_reuses_native_mov_but_requires_new_review_and_release(self) -> None:
        first = self.preview_and_deliver("first")["delivery"]
        native_renders = len(self.calls)
        self.edit_placement("placement")
        self.assertIsNone(model.status(self.root)["reviewSet"])
        with self.assertRaisesRegex(ValueError, "review"):
            model.deliver(self.root, self.req("stale-deliver"))

        second = self.preview_and_deliver("second")["delivery"]
        self.assertNotEqual(second["id"], first["id"])
        self.assertNotEqual(second["packagePath"], first["packagePath"])
        self.assertEqual(len(self.calls), native_renders)

    def test_second_version_in_same_episode_receives_next_delivery_number(self) -> None:
        first = self.preview_and_deliver("first")["delivery"]
        afterforge = self.root.parents[3]
        index = json.loads((afterforge / "工程/project.json").read_text(encoding="utf-8"))
        opened = model.open_project(afterforge, {
            "requestId": "second-version", "expectedRevision": index["revision"],
            "episodeId": load(self.root)["identity"]["episodeId"], "versionTitle": "制作二",
            "copyFrom": str(self.root), "copyMode": "restart", "commission": {"channel":"chat","text":"沿用这些设计建立独立版本","reference":"fixture:copy"},
        })
        other = Path(opened["root"])
        original_root = self.root
        self.root = other
        try:
            activate(self.root, 'copied-design')
            second = self.preview_and_deliver("second-version-deliver")["delivery"]
        finally:
            self.root = original_root
        self.assertEqual(first["id"], "d0001")
        self.assertEqual(second["id"], "d0002")

    def test_publish_exception_removes_package_and_snapshot_without_losing_decision(self) -> None:
        model.preview(self.root, self.req("preview", scope="full"))
        review = model.status(self.root)["reviewSet"]
        request = self.req("rollback", decision={
            "kind": "approve-and-deliver", "reviewSetId": review["id"],
            "source": {"channel": "chat", "text": "保留这条批准", "reference": "rollback"},
        })
        with patch("scripts.work_model_delivery.verify_release", side_effect=ValueError("publish validation interrupted")):
            with self.assertRaisesRegex(ValueError, "interrupted"):
                model.deliver(self.root, request)
        manifest = load(self.root)
        self.assertEqual(manifest["decisions"][-1]["kind"], "approve-and-deliver")
        self.assertEqual(manifest["deliveries"], [])
        self.assertFalse((self.root / "releases/d0001").exists())

class RoundtripAtomicTests(unittest.TestCase):
    setUp = DeliveryJobIntegrationTests.setUp
    req = DeliveryJobIntegrationTests.req
    preview_and_deliver = DeliveryJobIntegrationTests.preview_and_deliver

    def test_roundtrip_baseline_and_decision_rollback_together(self):
        import shutil
        from scripts.work_model_store import layout
        delivery=self.preview_and_deliver()['delivery']
        source={'channel':'chat','text':'合成测试的导入确认','reference':'synthetic-test'}
        model.update(self.root,self.req('accept',operation='decision',kind='accept-import',deliveryId=delivery['id'],source=source))
        afterforge,_=layout(self.root)
        reexported=self.root/'synthetic-reexport.fcpxml'
        shutil.copy2(afterforge/delivery['packagePath']/'Info.fcpxml',reexported)
        request=self.req('roundtrip',operation='roundtrip',deliveryId=delivery['id'],reexportedPath=str(reexported),source=source)
        before=(self.root/'animation-manifest.json').read_bytes()
        original=model.atomic_json
        def fail_index(path,value):
            if Path(path).name=='project.json': raise OSError('index interrupted')
            return original(path,value)
        with patch('scripts.work_model.atomic_json',side_effect=fail_index):
            with self.assertRaisesRegex(OSError,'index interrupted'):
                model.update(self.root,request)
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)
        result=model.update(self.root,request)
        self.assertEqual(result['status'],'verified')
        self.assertEqual(layout(self.root)[1]['protocolBaselines']['2']['deliveryId'],delivery['id'])

class PublicationRecoveryTests(unittest.TestCase):
    setUp=DeliveryJobIntegrationTests.setUp
    req=DeliveryJobIntegrationTests.req

    def test_resume_adopts_verified_package_after_lost_publication_response(self):
        from scripts import work_model_delivery as delivery_api
        model.preview(self.root,self.req('preview',scope='full'))
        review=model.status(self.root)['reviewSet']
        request=self.req('interrupted',decision={'kind':'approve-and-deliver','reviewSetId':review['id'],
            'source':{'channel':'chat','text':'合成测试交付','reference':'synthetic'}})
        real_publish=delivery_api.publish_release
        def lost_response(*args,**kwargs):
            real_publish(*args,**kwargs)
            raise OSError('lost publication response')
        with patch('scripts.work_model_delivery.publish_release',side_effect=lost_response):
            with self.assertRaisesRegex(OSError,'lost publication'):
                model.deliver(self.root,request)
        self.assertEqual(load(self.root)['deliveries'],[])
        task=next(t for t in model.status(self.root)['tasks'] if t['action']=='deliver')
        renders=len(self.calls)
        resumed=model.resume(self.root,self.req('resume-release',jobId=task['id']))
        self.assertEqual(resumed['delivery']['id'],'d0001')
        self.assertEqual(len(self.calls),renders)
        self.assertEqual(len(load(self.root)['deliveries']),1)
