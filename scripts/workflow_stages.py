"""Load the repository-owned AfterForge workflow stage contract."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references/workflow-stage-contract.json"
STAGE_ID_PATTERN = re.compile(r"^([AD])([1-9][0-9]*)$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
REQUIRED_STAGE_FIELDS = (
    "id",
    "name",
    "displayNameZh",
    "responsibility",
    "userMeaning",
    "userAction",
)


def validate_stage_contract(contract: dict[str, Any]) -> None:
    if not isinstance(contract.get("contractVersion"), str) or not SEMVER_PATTERN.fullmatch(
        contract["contractVersion"]
    ):
        raise ValueError("contractVersion must be semantic version X.Y.Z")
    stages = contract.get("stages")
    if not isinstance(stages, list):
        raise ValueError("stage contract must contain an ordered stages array")
    seen: set[str] = set()
    orders: dict[str, list[int]] = {"A": [], "D": []}
    for stage in stages:
        if isinstance(stage, dict):
            for field in REQUIRED_STAGE_FIELDS:
                if not isinstance(stage.get(field), str) or not stage[field]:
                    raise ValueError(f"every stage must have a non-empty {field}")
        stage_id = stage.get("id") if isinstance(stage, dict) else None
        if not isinstance(stage_id, str):
            raise ValueError("every stage must have a string id")
        if stage_id in seen:
            raise ValueError(f"duplicate stage id: {stage_id}")
        seen.add(stage_id)
        match = STAGE_ID_PATTERN.fullmatch(stage_id)
        if match is None:
            raise ValueError(f"unsupported stage id: {stage_id}")
        orders[match.group(1)].append(int(match.group(2)))
    for namespace, actual in orders.items():
        expected = list(range(1, len(actual) + 1))
        if actual != expected:
            raise ValueError(f"{namespace} stage order must be contiguous")


def load_stage_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    validate_stage_contract(contract)
    return contract


def assess_stage_evidence(
    contract: dict[str, Any],
    stage_id: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    stage = next((item for item in contract["stages"] if item["id"] == stage_id), None)
    if stage is None or evidence.get("stageId") != stage_id:
        return {"status": "unknown", "usable": False}
    evidence_contract = evidence.get("contractVersion")
    evidence_semantics = evidence.get("semanticVersion")
    current_semantics = stage.get(
        "semanticVersion", contract.get("defaultStageSemanticVersion")
    )
    if evidence_contract == contract["contractVersion"]:
        if evidence_semantics == current_semantics:
            return {"status": "current", "usable": True}
        return {"status": "semantic-mismatch", "usable": False}
    compatible = stage.get("compatibleEvidence", [])
    if any(
        item.get("contractVersion") == evidence_contract
        and item.get("semanticVersion") == evidence_semantics
        for item in compatible
    ):
        return {"status": "compatible-historical", "usable": True}
    return {"status": "historical-incompatible", "usable": False}


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_stage_contract_markdown(
    contract: dict[str, Any],
    *,
    contract_sha256: str,
) -> str:
    lines = [
        "# AfterForge Workflow Stage Contract",
        "",
        "> 本文件由 `workflow-stage-contract.json` 确定性生成，请勿手工修改。",
        "",
        f"Contract version：`{contract['contractVersion']}`",
        f"Canonical SHA-256：`{contract_sha256}`",
        "",
    ]
    for namespace_id, namespace in contract["namespaces"].items():
        lines.extend(
            [
                f"## {namespace_id}-stage：{namespace['displayNameZh']}",
                "",
                f"{namespace['name']}；稳定性：`{namespace['stability']}`。",
                "",
                "| ID | Formal name | 中文名称 | 稳定职责 | 用户含义 | 用户动作 |",
                "|---|---|---|---|---|---|",
            ]
        )
        for stage in contract["stages"]:
            if not stage["id"].startswith(namespace_id):
                continue
            lines.append(
                "| {id} | {name} | {display} | {responsibility} | {meaning} | `{action}` |".format(
                    id=stage["id"],
                    name=_markdown_cell(stage["name"]),
                    display=_markdown_cell(stage["displayNameZh"]),
                    responsibility=_markdown_cell(stage["responsibility"]),
                    meaning=_markdown_cell(stage["userMeaning"]),
                    action=stage["userAction"],
                )
            )
        lines.append("")
    conditional = [stage for stage in contract["stages"] if "applicability" in stage]
    if conditional:
        lines.extend(["## 条件适用", ""])
        for stage in conditional:
            lines.append(f"- `{stage['id']}`：`{stage['applicability']}`")
        lines.append("")
    lines.extend(
        [
            "## 使用规则",
            "",
            "- Stage ID 在同一 contract version 下不得改义或复用。",
            "- Vn 保存自己的实例 evidence，不复制本合同定义。",
            "- 旧 contract version 的合法 evidence 可以作为其原语义下的历史事实保留；只有未知、损坏或与当前所需 stage semantics 不兼容的 evidence 才不得用于当前判断。",
            "- 当前阶段由实际 evidence 确定性推导，不在 manifest 中手工维护单值 `currentStage`。",
            "",
        ]
    )
    return "\n".join(lines)
