#!/usr/bin/env python3
"""Shared contracts for the single-source HyperFrames adapter."""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal, localcontext
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


MANIFEST_NAME = "animation-manifest.json"
SCHEMA_VERSION = "2.0"
GENERATED_REVIEW_MARKER = "generated-by: fcpxml-animation-pipeline sync_storyboard"
GENERATED_INDEX_MARKER = "generated-by: fcpxml-animation-pipeline assemble_hyperframes"
GENERATED_DELIVERY_MARKER = "generated-by: fcpxml-animation-pipeline sync_delivery"


class _CompositionRootParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.dimensions: tuple[int, int] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.dimensions is not None:
            return
        values = dict(attrs)
        if "data-composition-id" not in values:
            return
        try:
            width = int(values["data-width"] or "")
            height = int(values["data-height"] or "")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("composition root must declare integer data-width and data-height") from error
        if width <= 0 or height <= 0:
            raise ValueError("composition root dimensions must be positive")
        self.dimensions = (width, height)


def load_manifest(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    path = root / MANIFEST_NAME
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing regular {MANIFEST_NAME}: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("animation manifest must be a JSON object")
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"animation manifest schemaVersion must be {SCHEMA_VERSION}")
    if not isinstance(payload.get("project"), dict) or not isinstance(payload.get("cues"), list):
        raise ValueError("animation manifest must contain project and cues")
    return payload


def project_dimensions(manifest: dict[str, Any], kind: str) -> tuple[int, int]:
    try:
        dimensions = manifest["project"][kind]
        width = int(dimensions["width"])
        height = int(dimensions["height"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"project.{kind} must declare integer width and height") from error
    if width <= 0 or height <= 0:
        raise ValueError(f"project.{kind} dimensions must be positive")
    return width, height


def composition_dimensions(html: str) -> tuple[int, int]:
    parser = _CompositionRootParser()
    parser.feed(html)
    if parser.dimensions is None:
        raise ValueError("composition HTML lacks a data-composition-id root")
    return parser.dimensions


def projection_scale(manifest: dict[str, Any]) -> tuple[Decimal, Decimal]:
    preview_width, preview_height = project_dimensions(manifest, "preview")
    delivery_width, delivery_height = project_dimensions(manifest, "delivery")
    return Decimal(preview_width) / Decimal(delivery_width), Decimal(preview_height) / Decimal(delivery_height)


def decimal_number(value: Decimal, places: int = 12) -> str:
    rendered = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return rendered or "0"


def delivery_projection_src(adapter: dict[str, Any]) -> str:
    basename = Path(adapter["compositionSrc"]).name
    return f"compositions/delivery/{basename}"


def save_manifest(version_root: Path, manifest: dict[str, Any]) -> None:
    root = version_root.expanduser().resolve()
    target = root / MANIFEST_NAME
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{MANIFEST_NAME}.", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def parse_time(value: str) -> Fraction:
    if not isinstance(value, str) or not value.endswith("s"):
        raise ValueError(f"invalid rational time: {value!r}")
    raw = value[:-1]
    try:
        return Fraction(raw)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid rational time: {value!r}") from error


def decimal_seconds(value: str, places: int = 6) -> str:
    fraction = parse_time(value)
    with localcontext() as context:
        context.prec = max(places + 12, 24)
        decimal = Decimal(fraction.numerator) / Decimal(fraction.denominator)
        rendered = f"{decimal:.{places}f}".rstrip("0").rstrip(".")
    return rendered or "0"


def cue_adapter(cue: dict[str, Any]) -> dict[str, Any]:
    adapters = cue.get("renderAdapters")
    if not isinstance(adapters, dict) or not isinstance(adapters.get("hyperframes"), dict):
        raise ValueError(f"cue {cue.get('id', '<unknown>')} lacks renderAdapters.hyperframes")
    return adapters["hyperframes"]


def find_cue(manifest: dict[str, Any], cue_id: str) -> dict[str, Any]:
    matches = [cue for cue in manifest["cues"] if cue.get("id") == cue_id]
    if len(matches) != 1:
        raise ValueError(f"cue id must identify exactly one cue: {cue_id}")
    return matches[0]


def safe_project_path(version_root: Path, relative: str, *, must_exist: bool = True) -> Path:
    root = version_root.expanduser().resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f"path must be a non-empty project-relative path: {relative!r}")
    raw = root / relative
    if raw.is_symlink():
        raise ValueError(f"symbolic links are not allowed: {relative}")
    resolved = raw.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path escapes version root: {relative}") from error
    if must_exist and (not resolved.is_file() or resolved.is_symlink()):
        raise ValueError(f"missing regular project file: {relative}")
    return resolved


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def project_duration(manifest: dict[str, Any]) -> str:
    return decimal_seconds(manifest["project"]["source"]["duration"])
