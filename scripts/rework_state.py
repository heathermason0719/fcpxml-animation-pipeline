"""Linear rework identity and artifact locations, independent of stage semantics."""
from pathlib import Path


def rework_revision(manifest: dict) -> int:
    rework = manifest.get("workflow", {}).get("rework")
    if rework is None:
        return 0
    revision = rework.get("revision") if isinstance(rework, dict) else None
    if type(revision) is not int or revision < 1 or rework.get("schemaVersion") != 1:
        raise ValueError("invalid rework revision")
    return revision


def revision_label(revision: int) -> str:
    if type(revision) is not int or revision < 0:
        raise ValueError("invalid rework revision")
    return f"r{revision:04d}"


def revision_evidence(manifest: dict) -> dict:
    revision = rework_revision(manifest)
    return {"reworkRevision": revision} if revision else {}


def evidence_is_current_revision(manifest: dict, evidence) -> bool:
    if not isinstance(evidence, dict):
        return False
    revision = evidence.get("reworkRevision", 0)
    return type(revision) is int and revision == rework_revision(manifest)


def delivery_directory(root: Path, manifest: dict) -> Path:
    revision = rework_revision(manifest)
    relative = "delivery" if not revision else f"delivery/revisions/{revision_label(revision)}"
    path = root / relative
    for candidate in (path, *path.parents):
        if candidate == root.parent:
            break
        if candidate.is_symlink():
            raise ValueError("delivery directory must not be a symlink")
    return path


def render_ledger_path(root: Path, manifest: dict) -> Path:
    return delivery_directory(root, manifest) / "render-ledger.json"


def delivery_identity(manifest: dict) -> str:
    if manifest.get("schemaVersion") == "3.0":
        delivery = manifest.get("delivery")
        if not isinstance(delivery, dict) or not isinstance(delivery.get("identity"), str):
            raise ValueError("schema-3 delivery identity is missing")
        identity = manifest.get("identity")
        release_id = delivery.get("id")
        if not isinstance(identity, dict) or not all(
            isinstance(identity.get(key), str) and identity[key]
            for key in ("projectId", "episodeId", "versionId")
        ) or not isinstance(release_id, str) or not release_id:
            raise ValueError("schema-3 delivery identity is invalid")
        expected = "AfterForge__{}__{}__{}__{}".format(
            identity["projectId"], identity["episodeId"], identity["versionId"], release_id
        )
        if delivery["identity"] != expected:
            raise ValueError("schema-3 delivery identity does not match release")
        return expected
    identity = f"AfterForge__{manifest['sourceVersion']}"
    revision = rework_revision(manifest)
    return f"{identity}__{revision_label(revision)}" if revision else identity
