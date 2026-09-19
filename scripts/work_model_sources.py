"""Classify a cue's local source closure without treating file names as trust."""
from __future__ import annotations

import json
import copy
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from scripts.work_model_store import safe

_JS_REF = re.compile(r"(?:\bfrom\s*|\bimport\s*\(|\bimport\s+)[\"']([^\"']+)[\"']")
_SCRIPT = re.compile(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", re.I | re.S)
_ATTR = re.compile(r"\b(?P<name>[\w:-]+)\s*=\s*(?:(?P<quote>[\"'])(?P<quoted>.*?)\2|(?P<bare>[^\s>]+))", re.I | re.S)
_PURE_IMPORT = re.compile(r"^\s*import\s*(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']\s*;?\s*$", re.S)


from scripts.work_model_capabilities import (css, srcset, raster_motion, data_motion,
    HTML_TAGS, SVG_TAGS, TIME_TAGS, ATTRIBUTES, PRESENTATION)


def _css_dynamic(text):
    return css(text)[0]


def _css_references(text):
    return css(text)[1]


def _local(reference: str) -> str | None:
    if reference.startswith("#"):
        return None
    if reference.lower().startswith("blob:"):
        raise ValueError("unverifiable blob resource")
    if reference.lower().startswith("data:"):
        data_motion(reference)
        return None
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"render dependency must be local: {reference}")
    return unquote(parsed.path) or None


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, bool]] = []
        self.dynamic = False
        self.unseekable = False
        self._script: tuple[dict[str, str], list[str]] | None = None
        self._style: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in HTML_TAGS | SVG_TAGS | TIME_TAGS | {'base'}:
            raise ValueError('unsupported HTML/SVG capability: ' + tag)
        if len({key.lower() for key, _ in attrs}) != len(attrs):
            raise ValueError('unsupported duplicate source attribute')
        attrs = {key.lower(): value or "" for key, value in attrs}
        for key in attrs:
            if key not in ATTRIBUTES and not key.startswith(('data-', 'aria-', 'on')):
                raise ValueError('unsupported attribute capability: ' + key)
        if tag == 'marquee': self.dynamic = True; self.unseekable = True
        if any(key.startswith("on") for key in attrs):
            self.dynamic = True
        if tag.lower() in {"iframe", "object", "embed", "video", "audio"}:
            self.dynamic = True
            if tag in {'iframe', 'object', 'embed'} or 'autoplay' in attrs:
                self.unseekable = True
        if tag.lower() == 'base' and attrs.get('href'):
            raise ValueError('base URL overrides are not part of the local source contract')
        if tag.lower() == 'meta' and attrs.get('http-equiv', '').lower() == 'refresh':
            self.dynamic = True; self.unseekable = True
        if attrs.get("poster"): self.references.append((attrs["poster"], "image"))
        for key in ("src", "data-composition-src"):
            if attrs.get(key): self.references.append((attrs[key], 'html' if key == 'data-composition-src' else ('image' if tag in {'img', 'image', 'feimage'} else tag == 'script')))
        if tag.lower() == "object" and attrs.get("data"):
            self.references.append((attrs["data"], False))
        if attrs.get("href"):
            self.references.append((attrs["href"], 'css' if tag == 'link' and 'stylesheet' in attrs.get('rel', '').lower().split() else ('image' if tag in {'image', 'feimage'} else False)))
        if attrs.get("xlink:href"):
            self.references.append((attrs["xlink:href"], "image" if tag in {"image", "feimage"} else False))
        for key in ("href", "xlink:href"):
            if attrs.get(key, "").lower().startswith(("javascript:", "data:")):
                self.references.append((attrs[key], False))
        if attrs.get('srcset'):
            self.references.extend((ref, 'image') for ref in srcset(attrs['srcset']))
        for key in PRESENTATION & attrs.keys():
            timed, refs = css(key + ':' + attrs[key], declarations=True)
            self.references.extend(refs)
        if attrs.get("style"):
            timed, refs = css(attrs['style'], declarations=True)
            self.references.extend(refs)
            self.dynamic = self.dynamic or timed
        if tag.lower() == "script":
            self._script = (attrs, [])
            if not attrs.get('src') and attrs.get('type', '').strip().lower() != 'application/json':
                self.dynamic = True
            if attrs.get("src"): self.references.append((attrs["src"], True))
        elif tag.lower() == "style": self._style = []
        if tag.lower() in {"animate", "animatetransform", "animatemotion", "set"}:
            self.dynamic = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self._script is not None: self._script[1].append(data)
        if self._style is not None: self._style.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script" and self._script is not None:
            attrs, body = self._script
            self._script = None
            if not attrs.get("src"):
                kind = attrs.get("type", "").strip().lower()
                text = "".join(body)
                if kind == "application/json":
                    try: json.loads(text)
                    except json.JSONDecodeError as error: raise ValueError("JSON script must contain strict JSON") from error
                else:
                    self.dynamic = True
                    self.references.extend((value, True) for value in _JS_REF.findall(text))
        elif tag == "style" and self._style is not None:
            text = "".join(self._style); self._style = None
            self.references.extend(_css_references(text))
            self.dynamic = self.dynamic or _css_dynamic(text)


def _read(root: Path, relative: str, overrides: dict[str, bytes], context=None) -> str | None:
    if context not in {'html', 'css'} and Path(relative).suffix.lower() not in {".html", ".htm", ".svg", ".css", ".js", ".mjs"}:
        return None
    if relative in overrides:
        return overrides[relative].decode("utf-8")
    path = safe(root, relative, exists=False)
    if not path.exists(): return None
    if not path.is_file() or path.is_symlink(): raise ValueError(f"missing regular input: {relative}")
    return path.read_text(encoding="utf-8")


def _resolve(root: Path, owner: str, reference: str, overrides: dict[str, bytes], known=()) -> str | None:
    candidate = _local(reference)
    if candidate is None: return None
    root_candidate = Path(root) / candidate
    local_candidate = (Path(root) / owner).parent / candidate
    def relative(path):
        try: return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError: return None
    root_relative, local_relative = relative(root_candidate), relative(local_candidate)
    if root_relative is None and local_relative is None:
        raise ValueError("render dependency escapes version")
    if root_relative is not None and (root_relative in known or root_relative in overrides or root_candidate.exists()):
        return root_relative
    return local_relative


def _content(relative: str, text: str, *, details=False) -> tuple[bool, list[tuple[str, bool]]]:
    suffix = Path(relative).suffix.lower()
    def result(dynamic, refs, unseekable=False):
        return (dynamic, refs, unseekable) if details else (dynamic, refs)
    if suffix in {".js", ".mjs"}: return result(True, [(value, True) for value in _JS_REF.findall(text)])
    if suffix == ".css": return result(_css_dynamic(text), _css_references(text))
    if suffix in {".html", ".htm", ".svg"}:
        parser = _Markup(); parser.feed(text); parser.close()
        if parser._script is not None or parser._style is not None:
            raise ValueError('unclosed script/style cannot be verified as a source')
        return result(parser.dynamic, parser.references, parser.unseekable)
    return result(False, [])


def inspect_sources(root, cue, overrides=None, *, allow_missing=False):
    """Return all local inputs and those capable of changing time-based output.

    ``overrides`` maps version-relative paths to unpublished bytes.  A declared
    motion source may be absent while a static design is being reviewed.
    """
    root = Path(root).resolve(); overrides = overrides or {}
    adapter = cue.get("renderAdapters", {}).get("hyperframes", {})
    composition = adapter.get("compositionSrc")
    if not isinstance(composition, str) or not composition: raise ValueError("cue lacks compositionSrc")
    if Path(composition).suffix.lower() not in {'.html', '.htm'}:
        raise ValueError('compositionSrc must be an HTML source')
    declared_motion = adapter.get("motionSrc")
    if declared_motion is not None and (not isinstance(declared_motion, str) or not declared_motion): raise ValueError("motionSrc must be a nonempty path")
    initial = [composition, *adapter.get("layoutDependencies", [])]
    if declared_motion: initial.append(declared_motion)
    pending = [(item, item == declared_motion, None) for item in initial]
    files, motion, seen, bindings, unseekable = set(), set(), set(), set(), set()
    while pending:
        relative, inherited_motion, context = pending.pop()
        if not isinstance(relative, str) or not relative: raise ValueError("source dependency must be a nonempty path")
        safe(root, relative, exists=not allow_missing and relative not in overrides and relative != declared_motion)
        visit = (relative, inherited_motion, context)
        if visit in seen: continue
        seen.add(visit); files.add(relative)
        text = _read(root, relative, overrides, context)
        if text is None:
            path = safe(root, relative, exists=False)
            data = overrides.get(relative) if relative in overrides else path.read_bytes() if path.is_file() else None
            known_font = data is not None and data[:4] in {b'wOFF', b'wOF2', b'OTTO', b'\x00\x01\x00\x00'}
            if data is not None and raster_motion(data, required=context == 'image' or (context == 'resource' and not known_font)):
                motion.add(relative); unseekable.add(relative)
            if relative == declared_motion and relative not in overrides:
                motion.add(relative); continue
            if relative not in overrides: safe(root, relative, exists=not allow_missing)
            if inherited_motion: motion.add(relative)
            continue
        dynamic, references, untimed = _content(('input.' + context) if context in {'html', 'css'} else relative, text, details=True)
        if untimed: unseekable.add(relative)
        is_motion = inherited_motion or dynamic
        if is_motion: motion.add(relative)
        for reference, executes in references:
            if (executes is True or executes in ('html', 'css')) and reference.lower().startswith(('data:', 'blob:')):
                raise ValueError('active source dependencies must be local files')
            if reference.lower().startswith('data:') and data_motion(reference):
                motion.add(relative); unseekable.add(relative)
            resolved = _resolve(root, relative, reference, overrides, {declared_motion} if declared_motion else set())
            if resolved is not None:
                if executes is True: bindings.add((relative, resolved))
                pending.append((resolved, inherited_motion or executes is True or (is_motion and Path(relative).suffix.lower() in {'.js', '.mjs'}),
                                executes if isinstance(executes, str) else None))
    return {"files": sorted(files), "motionFiles": sorted(motion), 'motionBindings': sorted(bindings), 'unseekableFiles': sorted(unseekable)}


def static_markup(root, cue, markup, *, overrides=None):
    """Remove only declared Motion loaders; reject any remaining executable markup."""
    if not isinstance(markup, str): raise ValueError("markup must be text")
    adapter = cue.get("renderAdapters", {}).get("hyperframes", {})
    source = adapter.get("compositionSrc")
    if not isinstance(source, str) or not source: raise ValueError("cue lacks compositionSrc")
    motion = adapter.get("motionSrc")
    removable = {"assets/vendor/gsap.min.js"}
    if isinstance(motion, str): removable.add(motion)

    def value(attrs, name):
        for match in _ATTR.finditer(attrs):
            if match.group("name").lower() == name:
                return match.group("quoted") if match.group("quote") else match.group("bare")
        return None

    def removable_reference(reference: str) -> bool:
        try: return _resolve(Path(root), source, reference, {}, removable) in removable
        except ValueError: return False

    def script(match):
        src = value(match.group("attrs"), "src")
        if src and removable_reference(src): return ""
        body = match.group("body")
        pure = _PURE_IMPORT.match(body)
        if pure and removable_reference(pure.group(1)): return ""
        return match.group(0)

    result = _SCRIPT.sub(script, markup)
    # A remaining script loader is executable even though the HTML file itself
    # is only a loader.  JSON data is the sole non-executable script form.
    for match in _SCRIPT.finditer(result):
        attrs, body = match.group("attrs"), match.group("body")
        if value(attrs, "src"): raise ValueError("static markup contains executable or time-driven behavior")
        if (value(attrs, "type") or "").lower() != "application/json": raise ValueError("static markup contains executable or time-driven behavior")
        try: json.loads(body)
        except json.JSONDecodeError as error: raise ValueError("JSON script must contain strict JSON") from error
    static_cue = copy.deepcopy(cue)
    static_adapter = static_cue['renderAdapters']['hyperframes']
    static_adapter.pop('motionSrc', None)
    static_adapter['layoutDependencies'] = [p for p in adapter.get('layoutDependencies', []) if p not in removable]
    analysis = inspect_sources(root, static_cue, {**(overrides or {}), source: result.encode("utf-8")})
    remaining = set(analysis["motionFiles"])
    if remaining: raise ValueError("static markup contains executable or time-driven behavior")
    return result
