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
        self.assertTrue((self.root.parents[3] / record["packagePath"] / record["xmlFileName"]).is_file())

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

    def test_roundtrip_requirement_uses_the_delivery_protocol_not_legacy_protocol_two(self):
        from scripts.work_model_store import layout, atomic_json
        self.preview_and_deliver()
        afterforge, index = layout(self.root)
        for baselines, required in (({}, True), ({"2": {"deliveryId": "old"}}, True), ({"3": {"deliveryId": "d0001"}}, False)):
            index["protocolBaselines"] = baselines
            atomic_json(afterforge / "工程/project.json", index)
            self.assertEqual(model.status(self.root)["deliveries"][0]["roundTripRequired"], required)

    def test_changed_xml_after_comparison_cannot_register_a_roundtrip(self):
        from xml.etree import ElementTree as ET
        from scripts import compare_fcpxml_roundtrip as comparator
        from scripts.work_model_store import layout
        delivery = self.preview_and_deliver()["delivery"]
        source = {"channel": "chat", "text": "合成测试的导入确认", "reference": "synthetic-test"}
        model.update(self.root, self.req("accept", operation="decision", kind="accept-import", deliveryId=delivery["id"], source=source))
        afterforge, _ = layout(self.root)
        delivered = afterforge / delivery["packagePath"] / delivery["xmlFileName"]
        reexported = self.root / "synthetic-reexport.fcpxml"
        doc = ET.parse(delivered)
        for rep in doc.getroot().iter("media-rep"):
            if rep.get("src", "").startswith("./"):
                rep.set("src", (delivered.parent / rep.get("src")[2:]).as_uri())
        doc.write(reexported)
        manifest_before = (self.root / "animation-manifest.json").read_bytes()
        index_before = (afterforge / "工程/project.json").read_bytes()
        compare = comparator.compare_roundtrip
        for index, target in enumerate((delivered, reexported)):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                def compare_then_change(*args):
                    result = compare(*args)
                    target.write_bytes(original + b"\n<!-- changed during comparison -->\n")
                    return result
                with patch.object(comparator, "compare_roundtrip", side_effect=compare_then_change):
                    with self.assertRaisesRegex(ValueError, "changed"):
                        model.update(self.root, self.req("changed-" + str(index), operation="roundtrip", deliveryId=delivery["id"], reexportedPath=str(reexported), source=source))
                self.assertEqual((self.root / "animation-manifest.json").read_bytes(), manifest_before)
                self.assertEqual((afterforge / "工程/project.json").read_bytes(), index_before)
                target.write_bytes(original)

    def test_roundtrip_baseline_and_decision_rollback_together(self):
        import shutil
        from scripts.work_model_store import layout
        delivery=self.preview_and_deliver()['delivery']
        source={'channel':'chat','text':'合成测试的导入确认','reference':'synthetic-test'}
        model.update(self.root,self.req('accept',operation='decision',kind='accept-import',deliveryId=delivery['id'],source=source))
        afterforge,_=layout(self.root)
        reexported=self.root/'synthetic-reexport.fcpxml'
        from xml.etree import ElementTree as ET
        doc = ET.parse(afterforge/delivery['packagePath']/delivery['xmlFileName'])
        for rep in doc.getroot().iter('media-rep'):
            if rep.get('src','').startswith('./'):
                rep.set('src', (afterforge/delivery['packagePath']/rep.get('src')[2:]).as_uri())
        doc.write(reexported)
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
        self.assertEqual(layout(self.root)[1]['protocolBaselines']['3']['deliveryId'],delivery['id'])

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

class DeliveryGateTests(unittest.TestCase):
    setUp=DeliveryJobIntegrationTests.setUp
    req=DeliveryJobIntegrationTests.req
    preview_and_deliver=DeliveryJobIntegrationTests.preview_and_deliver

    def test_complete_job_revalidates_duplicate_and_changed_files(self):
        from scripts.work_model_store import layout
        first=self.preview_and_deliver();record=first['delivery'];af,_=layout(self.root)
        movie=af/record['media'][0]['path']
        duplicate=af/'duplicate.mov';duplicate.write_bytes(movie.read_bytes())
        with self.assertRaisesRegex(ValueError,'duplicate'):
            model.resume(self.root,self.req('resume-corrupt',jobId=first['jobId']))
        duplicate.unlink()
        xml=af/record['packagePath']/record['xmlFileName'];xml.write_bytes(xml.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'inventory'):
            model.resume(self.root,self.req('resume-changed',jobId=first['jobId']))

    def test_old_protocol_job_cannot_return_a_success_receipt(self):
        from scripts.work_model_store import atomic_json
        first=self.preview_and_deliver();path=self.root/'jobs'/(first['jobId']+'.json')
        job=json.loads(path.read_text());job['inputKey']='old-protocol-2-key';atomic_json(path,job)
        with self.assertRaisesRegex(ValueError,'inputs changed'):
            model.resume(self.root,self.req('old-job',jobId=first['jobId']))

    def test_direct_preparation_without_authorized_running_job_is_refused(self):
        from scripts.work_model_delivery import prepare_release
        from scripts.work_model_store import layout,digest
        from scripts.work_model_jobs import _spec
        self.preview_and_deliver()
        manifest=load(self.root);af,_=layout(self.root)
        with self.assertRaisesRegex(ValueError,'authorized delivery job'):
            prepare_release(self.root,manifest,afterforge_root=af,release_id='d0002',
                input_key=digest(_spec(self.root,manifest,'deliver',{})),dependency_paths=[])
        self.assertFalse((self.root/'releases/d0002').exists())
