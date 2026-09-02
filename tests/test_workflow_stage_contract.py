from __future__ import annotations

import sys
import hashlib
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class WorkflowStageContractTests(unittest.TestCase):
    def load_repository_contract(self):
        from scripts.workflow_stages import load_stage_contract

        return load_stage_contract(REPO_ROOT / "references/workflow-stage-contract.json")

    def write_contract(self, directory: str, contract: dict) -> Path:
        path = Path(directory) / "contract.json"
        path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
        return path

    def test_repository_contract_has_the_only_supported_stage_order(self) -> None:
        try:
            from scripts.workflow_stages import load_stage_contract
        except ModuleNotFoundError:
            self.fail("workflow stage contract loader is not implemented")

        contract = load_stage_contract(REPO_ROOT / "references/workflow-stage-contract.json")

        self.assertEqual(contract["contractVersion"], "1.0.0")
        self.assertEqual(
            [stage["id"] for stage in contract["stages"]],
            [
                "A1", "A2", "A3", "A4", "A5", "A6", "A7",
                "A8", "A9", "A10", "A11", "A12", "A13", "A14",
                "D1", "D2", "D3", "D4", "D5", "D6",
            ],
        )

    def test_duplicate_stage_id_is_rejected(self) -> None:
        from scripts.workflow_stages import load_stage_contract

        contract = deepcopy(self.load_repository_contract())
        contract["stages"].append(deepcopy(contract["stages"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_contract(directory, contract)
            with self.assertRaisesRegex(ValueError, "duplicate stage id: A1"):
                load_stage_contract(path)

    def test_stage_order_must_be_contiguous_inside_each_namespace(self) -> None:
        from scripts.workflow_stages import load_stage_contract

        contract = deepcopy(self.load_repository_contract())
        contract["stages"] = [stage for stage in contract["stages"] if stage["id"] != "A10"]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_contract(directory, contract)
            with self.assertRaisesRegex(ValueError, "A stage order must be contiguous"):
                load_stage_contract(path)

    def test_contract_version_must_be_semver(self) -> None:
        from scripts.workflow_stages import load_stage_contract

        contract = deepcopy(self.load_repository_contract())
        contract["contractVersion"] = "latest"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "contractVersion"):
                load_stage_contract(self.write_contract(directory, contract))

    def test_each_stage_requires_machine_and_human_identity_fields(self) -> None:
        from scripts.workflow_stages import load_stage_contract

        contract = deepcopy(self.load_repository_contract())
        del contract["stages"][0]["userAction"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "userAction"):
                load_stage_contract(self.write_contract(directory, contract))

    def test_human_projection_is_deterministic_and_current(self) -> None:
        try:
            from scripts.workflow_stages import render_stage_contract_markdown
        except ImportError:
            self.fail("workflow stage contract Markdown projection is not implemented")

        contract = self.load_repository_contract()
        source = REPO_ROOT / "references/workflow-stage-contract.json"
        rendered = render_stage_contract_markdown(
            contract,
            contract_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )

        self.assertEqual(
            (REPO_ROOT / "references/workflow-stage-contract.md").read_text(encoding="utf-8"),
            rendered,
        )
        self.assertIn("Contract version：`1.0.0`", rendered)
        self.assertEqual(rendered.count("| A11 |"), 1)
        self.assertEqual(rendered.count("| D6 |"), 1)

    def test_projection_check_command_succeeds_only_when_projection_is_current(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/sync_workflow_stage_contract.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(result.stdout.strip(), "workflow stage contract projection is current")

    def test_older_contract_evidence_is_usable_when_stage_semantics_are_compatible(self) -> None:
        try:
            from scripts.workflow_stages import assess_stage_evidence
        except ImportError:
            self.fail("stage evidence compatibility assessment is not implemented")

        contract = deepcopy(self.load_repository_contract())
        a11 = next(stage for stage in contract["stages"] if stage["id"] == "A11")
        a11["compatibleEvidence"] = [
            {"contractVersion": "0.9.0", "semanticVersion": 1}
        ]

        assessment = assess_stage_evidence(
            contract,
            "A11",
            {"stageId": "A11", "contractVersion": "0.9.0", "semanticVersion": 1},
        )

        self.assertEqual(assessment, {"status": "compatible-historical", "usable": True})

    def test_incompatible_historical_evidence_is_preserved_but_not_currently_usable(self) -> None:
        try:
            from scripts.workflow_stages import assess_stage_evidence
        except ImportError:
            self.fail("stage evidence compatibility assessment is not implemented")

        assessment = assess_stage_evidence(
            self.load_repository_contract(),
            "A11",
            {"stageId": "A11", "contractVersion": "0.8.0", "semanticVersion": 1},
        )

        self.assertEqual(assessment, {"status": "historical-incompatible", "usable": False})


if __name__ == "__main__":
    unittest.main()
