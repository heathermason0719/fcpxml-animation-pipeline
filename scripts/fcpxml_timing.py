#!/usr/bin/env python3
"""Exact FCPXML timeline placement and positive-lane allocation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET

try:
    from scripts.hyperframes_adapter import parse_time
except ModuleNotFoundError:
    from hyperframes_adapter import parse_time  # type: ignore


def format_time(value: Fraction) -> str:
    """Serialize a rational number of seconds in FCPXML form."""
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def _time_attribute(element: ET.Element, name: str, default: Fraction = Fraction(0)) -> Fraction:
    raw = element.get(name)
    return default if raw is None else parse_time(raw)


def _lane(element: ET.Element) -> int:
    try:
        return int(element.get("lane", "0"))
    except ValueError as error:
        raise ValueError(f"invalid lane on {element.tag}: {element.get('lane')!r}") from error


@dataclass(frozen=True)
class HostPlacement:
    element: ET.Element
    sequence_start: Fraction
    local_start: Fraction
    duration: Fraction


@dataclass(frozen=True)
class TimelineInterval:
    key: str
    start: Fraction
    duration: Fraction
    lane: int = 0

    @property
    def end(self) -> Fraction:
        return self.start + self.duration


def _primary_hosts(spine: ET.Element) -> list[HostPlacement]:
    hosts: list[HostPlacement] = []
    for element in spine:
        if element.tag == "transition" or _lane(element) != 0:
            continue
        duration = _time_attribute(element, "duration")
        if duration <= 0 or element.get("offset") is None:
            continue
        hosts.append(
            HostPlacement(
                element=element,
                sequence_start=_time_attribute(element, "offset"),
                local_start=_time_attribute(element, "start"),
                duration=duration,
            )
        )
    return hosts


def find_primary_host(spine: ET.Element, sequence_time: Fraction) -> HostPlacement:
    """Find the lane-zero story element covering ``sequence_time``.

    Coverage is half-open. A time exactly at one element's end therefore
    belongs to the following primary element. ``timeMap`` affects media
    playback, not the base element's anchor scheduling coordinates.
    """
    for host in _primary_hosts(spine):
        if host.sequence_start <= sequence_time < host.sequence_start + host.duration:
            return host
    raise ValueError(f"no primary host at sequence time {format_time(sequence_time)}")


def anchor_offset(host: HostPlacement, sequence_time: Fraction) -> Fraction:
    if not host.sequence_start <= sequence_time < host.sequence_start + host.duration:
        raise ValueError(
            f"sequence time {format_time(sequence_time)} falls outside host "
            f"{host.element.get('name', host.element.tag)!r}"
        )
    return host.local_start + sequence_time - host.sequence_start


def collect_positive_anchors(spine: ET.Element) -> list[TimelineInterval]:
    """Collect direct positive-lane anchors from every primary story element."""
    intervals: list[TimelineInterval] = []
    for host in _primary_hosts(spine):
        for index, child in enumerate(host.element):
            lane = _lane(child)
            if lane <= 0 or child.get("duration") is None:
                continue
            duration = _time_attribute(child, "duration")
            if duration <= 0:
                continue
            local_offset = _time_attribute(child, "offset")
            intervals.append(
                TimelineInterval(
                    key=child.get("name") or f"{child.tag}[{index}]",
                    start=host.sequence_start + local_offset - host.local_start,
                    duration=duration,
                    lane=lane,
                )
            )
    return sorted(intervals, key=lambda item: (item.start, item.lane, item.key))


def _overlaps(left: TimelineInterval, right: TimelineInterval) -> bool:
    return left.start < right.end and right.start < left.end


def allocate_lanes(
    requests: list[TimelineInterval],
    occupied: list[TimelineInterval] | None = None,
) -> dict[str, int]:
    """Assign the lowest available positive lane to each requested interval."""
    existing = list(occupied or [])
    if any(item.lane <= 0 for item in existing):
        raise ValueError("occupied intervals must use positive lanes")

    assignments: dict[str, int] = {}
    assigned: list[TimelineInterval] = []
    seen: set[str] = set()
    for request in sorted(requests, key=lambda item: (item.start, item.key)):
        if request.key in seen:
            raise ValueError(f"duplicate timeline interval key: {request.key}")
        seen.add(request.key)
        if request.duration <= 0:
            raise ValueError(f"timeline interval duration must be positive: {request.key}")

        lane = 1
        while any(
            item.lane == lane and _overlaps(request, item)
            for item in [*existing, *assigned]
        ):
            lane += 1
        assignments[request.key] = lane
        assigned.append(
            TimelineInterval(request.key, request.start, request.duration, lane)
        )
    return assignments
