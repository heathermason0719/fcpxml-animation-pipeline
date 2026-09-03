from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from fractions import Fraction
from pathlib import Path

from scripts.hyperframes_adapter import load_manifest
from scripts.layout_lock import verify_layouts
from scripts.workflow_status import current_input_fingerprint, resolve_stage_status
from tests.test_hyperframes_single_source import SingleSourceFixture, write_json
from tests import test_workflow_status as status_fixtures


class WorkflowInputFingerprintTests(SingleSourceFixture):
    make_locked_version = status_fixtures.WorkflowStatusTests.make_locked_version
    approve_a11 = status_fixtures.WorkflowStatusTests.approve_a11
    register_a12 = status_fixtures.WorkflowStatusTests.register_a12
    approve_a13 = status_fixtures.WorkflowStatusTests.approve_a13
    authorize_a14 = status_fixtures.WorkflowStatusTests.authorize_a14
    render_d2 = status_fixtures.WorkflowStatusTests.render_d2

    def test_execution_timing_changes_invalidate_demo_without_reopening_static_lock(self):
        mutations = (
            ("cue start", lambda m: m["cues"][0]["resolvedTimeline"].update(start="2s")),
            ("cue duration", lambda m: m["cues"][0]["resolvedTimeline"].update(duration="3s")),
            ("source duration", lambda m: m["project"]["source"].update(duration="11s")),
            ("source fps", lambda m: m["project"]["source"].update(frameDuration="1/25s", frameRate=25)),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = self.make_locked_version(directory)
                self.approve_a11(root)
                self.register_a12(root)
                manifest = load_manifest(root)
                before = current_input_fingerprint(root, manifest)
                mutate(manifest)
                self.assertNotEqual(before, current_input_fingerprint(root, manifest))
                write_json(root / "animation-manifest.json", manifest)
                self.assertEqual(verify_layouts(root)["status"], "valid")
                status = resolve_stage_status(root)
                self.assertEqual(status["blockingStage"], "A12")
                self.assertEqual(status["evidence"]["A12"], "input-fingerprint-mismatch")

    def test_animated_order_is_semantic_but_metadata_and_equivalent_rationals_are_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            manifest = load_manifest(root)
            second = copy.deepcopy(manifest["cues"][0])
            second["id"] = "overlapping-second"
            manifest["cues"].append(second)
            before = current_input_fingerprint(root, manifest)
            same = copy.deepcopy(manifest)
            same["cues"][0]["resolvedTimeline"].update(start="1s", duration="2s")
            same["project"]["source"].update(duration="10s", frameDuration="1/24s", frameRate="48/2")
            same["cues"][0]["notes"] = "history only"
            same["workflow"]["activeReviewContext"] = "A13"
            self.assertEqual(before, current_input_fingerprint(root, same))
            manifest["cues"].reverse()
            self.assertNotEqual(before, current_input_fingerprint(root, manifest))

    def test_render_and_registration_reject_conflicting_fps_declarations(self):
        from scripts.render_animations import _project_fps as render_fps
        from scripts.register_delivery_assets import _project_fps as registration_fps

        with tempfile.TemporaryDirectory() as directory:
            manifest = load_manifest(self.make_locked_version(directory))
            manifest["project"]["source"].update(frameDuration="1001/24000s", frameRate="24000/1001")
            for resolver in (render_fps, registration_fps):
                self.assertEqual(resolver(manifest), Fraction(24000, 1001))
                inconsistent = copy.deepcopy(manifest)
                inconsistent["project"]["source"]["frameRate"] = 24
                with self.assertRaisesRegex(ValueError, "inconsistent|conflict"):
                    resolver(inconsistent)

    def test_unknown_fingerprint_version_cannot_authorize_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            manifest = load_manifest(root)
            for stage in ("A12", "A13", "A14"):
                manifest["workflow"]["stageEvidence"][stage]["inputFingerprintVersion"] = 999
            write_json(root / "animation-manifest.json", manifest)
            status = resolve_stage_status(root)
            self.assertEqual(status["blockingStage"], "A12")
            self.assertEqual(status["evidence"]["A12"], "unsupported-input-fingerprint-version")

    def test_new_render_ledger_records_fingerprint_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            self.render_d2(root)
            ledger = json.loads((root / "delivery/render-ledger.json").read_text())
            self.assertEqual(ledger.get("inputFingerprintVersion"), 2)

    def test_legacy_approval_remains_history_but_cannot_start_new_native_render(self):
        from scripts.render_animations import render_animations

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            manifest = load_manifest(root)
            # Captured from the pre-v2 implementation against this fixed fixture.
            legacy_hash = "6726109959d7135fb52c4bf3f8475461b75a230b9f3e4b7f3b24b0aa9c836f18"
            for stage in ("A12", "A13", "A14"):
                evidence = manifest["workflow"]["stageEvidence"][stage]
                evidence.pop("inputFingerprintVersion", None)
                evidence["inputFingerprint"] = legacy_hash
            write_json(root / "animation-manifest.json", manifest)
            status = resolve_stage_status(root)
            self.assertIn("A14", status["completedStages"])
            self.assertEqual(status["evidence"]["A12"], "compatible-historical")
            self.assertEqual(status["nextEligibleStage"], "A12")
            with self.assertRaisesRegex(ValueError, "fingerprint|migration|review"):
                render_animations(root, runner=lambda *args, **kwargs: self.fail("legacy evidence dispatched renderer"))
            self.assertFalse((root / "delivery").exists())

    def test_completed_legacy_render_stays_readable_under_original_hash_semantics(self):
        from scripts.workflow_inputs import input_fingerprint, require_current_input_evidence
        from scripts.workflow_status import evidence_fingerprint

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            self.render_d2(root)
            manifest = load_manifest(root)
            legacy_hash = "6726109959d7135fb52c4bf3f8475461b75a230b9f3e4b7f3b24b0aa9c836f18"
            self.assertEqual(input_fingerprint(root, manifest, version=1), legacy_hash)
            for stage in ("A12", "A13", "A14"):
                evidence = manifest["workflow"]["stageEvidence"][stage]
                evidence.pop("inputFingerprintVersion")
                evidence["inputFingerprint"] = legacy_hash
            write_json(root / "animation-manifest.json", manifest)
            ledger_path = root / "delivery/render-ledger.json"
            ledger = json.loads(ledger_path.read_text())
            ledger.pop("inputFingerprintVersion")
            ledger["inputFingerprint"] = legacy_hash
            ledger["authorizationFingerprint"] = evidence_fingerprint(manifest["workflow"]["stageEvidence"]["A14"])
            write_json(ledger_path, ledger)
            before = {str(path): path.read_bytes() for path in (root / "animation-manifest.json", ledger_path)}
            status = resolve_stage_status(root)
            self.assertIn("D2", status["completedStages"])
            self.assertEqual(status["evidence"]["D2"], "compatible-historical")
            self.assertEqual(status["nextEligibleStage"], "A12")
            with self.assertRaisesRegex(ValueError, "migration|new review"):
                require_current_input_evidence(root, manifest)
            self.assertEqual(before, {name: Path(name).read_bytes() for name in before})

    def test_version_mismatch_in_linked_approval_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            manifest = load_manifest(root)
            manifest["workflow"]["stageEvidence"]["A13"].pop("inputFingerprintVersion")
            write_json(root / "animation-manifest.json", manifest)
            status = resolve_stage_status(root)
            self.assertEqual(status["blockingStage"], "A13")
            self.assertEqual(status["evidence"]["A13"], "input-fingerprint-version-mismatch")

    def test_missing_legacy_review_or_authorization_requires_v2_demo_first(self):
        for missing_stage in ("A13", "A14"):
            with self.subTest(missing_stage=missing_stage), tempfile.TemporaryDirectory() as directory:
                root = self.make_locked_version(directory)
                self.approve_a11(root)
                self.register_a12(root)
                self.approve_a13(root)
                self.authorize_a14(root)
                manifest = load_manifest(root)
                stages = manifest["workflow"]["stageEvidence"]
                for stage in ("A12", "A13", "A14"):
                    stages[stage].pop("inputFingerprintVersion")
                    stages[stage]["inputFingerprint"] = "6726109959d7135fb52c4bf3f8475461b75a230b9f3e4b7f3b24b0aa9c836f18"
                stages.pop(missing_stage)
                write_json(root / "animation-manifest.json", manifest)
                before = (root / "animation-manifest.json").read_bytes()
                status = resolve_stage_status(root)
                self.assertEqual(status["blockingStage"], "A12")
                self.assertEqual(status["nextEligibleStage"], "A12")
                self.assertEqual(status["evidence"]["A12"], "compatible-historical")
                self.assertEqual(status["evidence"][missing_stage], "input-fingerprint-upgrade-required")
                self.assertIn("A12", status["completedStages"])
                if missing_stage == "A14":
                    self.assertIn("A13", status["completedStages"])
                self.assertEqual((root / "animation-manifest.json").read_bytes(), before)

    def test_blocked_native_render_does_not_generate_or_update_delivery_projection(self):
        from scripts.render_animations import render_animations
        from scripts.sync_delivery import sync_delivery

        for existing_projection in (False, True):
            with self.subTest(existing_projection=existing_projection), tempfile.TemporaryDirectory() as directory:
                root = self.make_locked_version(directory)
                if existing_projection:
                    sync_delivery(root)
                    manifest = load_manifest(root)
                    manifest["cues"][0]["resolvedTimeline"]["duration"] = "3s"
                    write_json(root / "animation-manifest.json", manifest)
                before = {
                    str(path.relative_to(root)): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file() and path.name != ".afterforge-manifest.lock"
                }
                with self.assertRaises(ValueError):
                    render_animations(root, runner=lambda *args, **kwargs: self.fail("blocked render started"))
                after = {
                    str(path.relative_to(root)): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file() and path.name != ".afterforge-manifest.lock"
                }
                self.assertEqual(after, before)
