#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fail-closed target modeling guideline v5 checks for one exported Simulink scope."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "maab.simulink_geometry/v1"
MANIFEST_SCHEMA_VERSION = "maab.simulink_geometry_manifest/v1"
MODEL_REPORT_SCHEMA_VERSION = "maab.simulink_model_lint_report/v1"
TARGET_STANDARD = "TARGET_MODELING_GUIDELINE_V5"
TOL = 1.0
PROJECT_POLICY_ID = "project-visual-quality-v2"
APPEARANCE_METRICS = (
    "crossing_events",
    "overlap_events",
    "through_block_events",
    "diagonal_segments",
    "goto_from_blocks",
)
APPEARANCE_ORDER = (*APPEARANCE_METRICS, "total_bends", "total_length")
HARD_ZERO_METRICS = (
    "crossing_events",
    "overlap_events",
    "through_block_events",
    "diagonal_segments",
)
GOTO_JUSTIFICATION_SCHEMA = "maab.goto_justification/v1"

RULES = {
    "jm_0002-a": {"na": "a", "jmaab": "a", "text": "块图标须可见且可辨识"},
    "jc_0604-a": {"na": "a", "jmaab": "a", "text": "不得启用块阴影"},
    "db_0142-a": {"na": "a", "jmaab": "a", "text": "块名位于块下方"},
    "db_0081-a": {"na": "a", "jmaab": "a", "text": "不得存在未连接信号线"},
    "db_0081-b": {"na": "b", "jmaab": "b", "text": "不得存在未连接块"},
    "db_0032-a1": {
        "na": "a1",
        "jmaab": "a1",
        "text": "水平与垂直信号线不得交叉",
    },
    "db_0032-a2": {
        "na": "a2",
        "jmaab": "a2",
        "text": "必须交叉时实际 Line crossing style 须为 Line hop",
    },
    "db_0032-b": {"na": "b", "jmaab": "b", "text": "信号线不得重叠"},
    "db_0032-c": {"na": "c", "jmaab": "c", "text": "信号线不得穿过块"},
    "db_0032-d": {
        "na": None,
        "jmaab": "d",
        "text": "单个分支点不得超过两条支线",
    },
    "db_0032-e": {
        "na": "e",
        "jmaab": "e",
        "text": "信号线应按布局需要水平或垂直拉伸",
    },
    "db_0097-a": {
        "na": "a",
        "jmaab": "a",
        "text": "信号/总线标签不得与其他标签、线或块重叠",
    },
    "db_0097-b": {
        "na": "b",
        "jmaab": "b",
        "text": "标签位于信号线下方",
    },
    "db_0097-c": {
        "na": "c",
        "jmaab": "c",
        "text": "标签位于连接起点",
    },
    "db_0141-a": {
        "na": None,
        "jmaab": "a",
        "text": "非反馈信号从左向右",
    },
    "db_0141-c": {
        "na": None,
        "jmaab": "c",
        "text": "不得存在无必要的多次折弯",
    },
    "jc_0110-a": {
        "na": "a",
        "jmaab": "a",
        "text": "块输出朝右；仅反馈环 Delay 例外",
    },
    "db_0146-a": {
        "na": "a",
        "jmaab": "a",
        "text": "条件输入块位于子系统顶部",
    },
}


class Report:
    def __init__(self, source: str):
        self.source = source
        self.items: list[dict[str, Any]] = []
        self.schema_errors: list[str] = []
        self.line_metrics: list[dict[str, Any]] = []
        self.appearance_quality: dict[str, Any] = {
            "policy_id": None,
            "overall": "INVALID",
            "summary": {},
            "reasons": ["geometry lint did not complete"],
        }

    def add(
        self,
        rule: str,
        status: str,
        where: str,
        fact: str,
        fix: str = "",
        evidence: str = "",
    ) -> None:
        self.items.append(
            {
                "rule": rule,
                "sub_id": {"na_maab": RULES[rule]["na"], "jmaab": RULES[rule]["jmaab"]},
                "status": status,
                "where": where,
                "fact": fact,
                "fix": fix,
                "evidence": evidence,
            }
        )

    def mark(self, rule: str, where: str, fact: str, evidence: str = "") -> None:
        self.add(rule, "COMPLIANT", where, fact, evidence=evidence)

    def violation(self, rule: str, where: str, fact: str, fix: str) -> None:
        self.add(rule, "VIOLATION", where, fact, fix)

    def unknown(self, rule: str, where: str, fact: str, fix: str = "") -> None:
        self.add(rule, "UNVERIFIABLE", where, fact, fix)

    def manual(self, rule: str, where: str, fact: str, fix: str = "") -> None:
        self.add(rule, "MANUAL", where, fact, fix)

    def not_applicable(self, rule: str, where: str, fact: str) -> None:
        self.add(rule, "NOT_APPLICABLE", where, fact)

    def overall(self) -> str:
        if self.schema_errors:
            return "INVALID"
        if any(item["status"] == "VIOLATION" for item in self.items):
            return "NON_COMPLIANT"
        if any(item["status"] == "UNVERIFIABLE" for item in self.items):
            return "INCOMPLETE"
        if any(item["status"] == "MANUAL" for item in self.items):
            return "MANUAL_REVIEW_REQUIRED"
        return "COMPLIANT"

    def profile_summary(self) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for profile, key in (("NA-MAAB", "na_maab"), ("JMAAB", "jmaab")):
            counts: Counter[str] = Counter()
            for item in self.items:
                if item["sub_id"][key] is None:
                    continue
                counts[item["status"]] += 1
            result[profile] = dict(sorted(counts.items()))
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "maab.simulink_lint_report/v1",
            "source_geometry": self.source,
            "standard": TARGET_STANDARD,
            "matlab_version": "R2025b",
            "overall": self.overall(),
            "schema_errors": self.schema_errors,
            "profile_summary": self.profile_summary(),
            "items": self.items,
            "line_metrics": self.line_metrics,
            "appearance_quality": self.appearance_quality,
            "coverage": {
                "full_chapter_audit": False,
                "label_geometry": "estimated (font-size based); confirm with render_check.m PNGs",
                "line_metrics": "direction changes and raw polyline length in geometry coordinate units",
                "appearance_quality": (
                    "Project appearance policy over exported geometry; "
                    "current-scope PNG review remains required."
                ),
                "note": (
                    "This lint covers deterministic Simulink geometry rules only; "
                    "db_0097 label checks are font-size estimates, not rendered "
                    "bounding boxes. Inspect the final PNG and layout-simulink.md "
                    "for the visual/layout subset."
                ),
            },
        }


def rect(block: dict[str, Any]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in block["position"])
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def center(value: tuple[float, float, float, float]) -> tuple[float, float]:
    return (value[0] + value[2]) / 2, (value[1] + value[3]) / 2


def segments(points: list[Any]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    pts = [(float(point[0]), float(point[1])) for point in points]
    return list(zip(pts, pts[1:]))


def polyline_length(points: list[Any]) -> float:
    """Return raw path length in geometry coordinate units."""
    pts = [(float(point[0]), float(point[1])) for point in points]
    return sum(
        math.hypot(end[0] - start[0], end[1] - start[1])
        for start, end in zip(pts, pts[1:])
    )


def bend_count(points: list[Any]) -> int:
    """Count direction changes, ignoring duplicate and collinear vertices."""
    pts = [(float(point[0]), float(point[1])) for point in points]
    directions = []
    for start, end in zip(pts, pts[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length > TOL:
            directions.append((dx / length, dy / length))
    return sum(
        first[0] * second[0] + first[1] * second[1] < 1 - 1e-6
        for first, second in zip(directions, directions[1:])
    )


def is_horizontal(segment) -> bool:
    return abs(segment[0][1] - segment[1][1]) <= TOL


def is_vertical(segment) -> bool:
    return abs(segment[0][0] - segment[1][0]) <= TOL


def crossing(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float] | None:
    if is_horizontal(first) and is_vertical(second):
        x, y = second[0][0], first[0][1]
        a0, a1 = sorted((first[0][0], first[1][0]))
        b0, b1 = sorted((second[0][1], second[1][1]))
        if a0 + TOL < x < a1 - TOL and b0 + TOL < y < b1 - TOL:
            return x, y
    elif is_vertical(first) and is_horizontal(second):
        return crossing(second, first)
    return None


def overlap(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float] | None:
    if is_horizontal(first) and is_horizontal(second):
        if abs(first[0][1] - second[0][1]) > TOL:
            return None
        a0, a1 = sorted((first[0][0], first[1][0]))
        b0, b1 = sorted((second[0][0], second[1][0]))
        low, high = max(a0, b0), min(a1, b1)
        if high - low > 2 * TOL:
            return (low + high) / 2, first[0][1]
    if is_vertical(first) and is_vertical(second):
        if abs(first[0][0] - second[0][0]) > TOL:
            return None
        a0, a1 = sorted((first[0][1], first[1][1]))
        b0, b1 = sorted((second[0][1], second[1][1]))
        low, high = max(a0, b0), min(a1, b1)
        if high - low > 2 * TOL:
            return first[0][0], (low + high) / 2
    return None


def hits_interior(segment, value: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = value[0] + 2, value[1] + 2, value[2] - 2, value[3] - 2
    if is_horizontal(segment):
        y = segment[0][1]
        low, high = sorted((segment[0][0], segment[1][0]))
        return y0 < y < y1 and high > x0 and low < x1
    if is_vertical(segment):
        x = segment[0][0]
        low, high = sorted((segment[0][1], segment[1][1]))
        return x0 < x < x1 and high > y0 and low < y1
    return False


def cycle_edges(lines: list[dict[str, Any]]) -> set[str]:
    graph: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        if line.get("src_block") and line.get("dst_block"):
            graph[line["src_block"]].add(line["dst_block"])
    result = set()
    for line in lines:
        source = line.get("src_block")
        target = line.get("dst_block")
        if not source or not target:
            continue
        stack = [target]
        visited = set()
        while stack:
            node = stack.pop()
            if node == source:
                result.add(line["id"])
                break
            if node not in visited:
                visited.add(node)
                stack.extend(graph[node])
    return result


def line_crossing_setting(geometry: dict[str, Any]) -> tuple[bool | None, str]:
    settings = geometry.get("source_settings") or {}
    item = settings.get("line_crossing") or {}
    if item.get("status") != "observed" or item.get("value") is None:
        return None, str(item.get("reason") or "R2025b setting was not observed")
    raw = str(item["value"])
    normalized = "".join(ch for ch in raw.lower() if ch.isalnum())
    display = str(item.get("display_value") or raw)
    evidence = raw if display == raw else f"{display} ({raw})"
    if normalized in {"hop", "linehop", "true", "1", "on"}:
        return True, evidence
    if normalized in {"gradpin", "tunnel", "none", "false", "0", "off"}:
        return False, evidence
    return None, f"unrecognized EditorPathXStyle value: {raw}"


def endpoint_signature(line: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return a geometry-stable line identity for appearance comparisons."""
    return tuple(
        str(line.get(key) if line.get(key) is not None else "")
        for key in ("src_block", "src_port", "dst_block", "dst_port")
    )


def normalize_geometry(
    geo: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    dict[str, tuple[float, float, float, float]],
    list[dict[str, Any]],
]:
    """Normalize exported blocks and lines for deterministic measurements."""
    blocks = []
    for raw_block in geo["blocks"]:
        block = dict(raw_block)
        if isinstance(block.get("ports"), dict):
            block["ports"] = [block["ports"]]
        blocks.append(block)
    blocks = [block for block in blocks if block.get("type") != "annotation"]
    block_rects = {block["path"]: rect(block) for block in blocks}
    raw_lines = []
    for line in geo["lines"]:
        points = line.get("points") or []
        raw_lines.append(
            {
                **line,
                "segs": segments(points) if len(points) >= 2 else [],
                "bends": bend_count(points),
                "length": polyline_length(points),
            }
        )
    return blocks, block_rects, raw_lines


def measure_appearance(
    raw_lines: list[dict[str, Any]],
    block_rects: dict[str, tuple[float, float, float, float]],
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Measure project-level line congestion independently of lint verdicts."""
    diagonal_segments: list[dict[str, Any]] = []
    crossings: list[dict[str, Any]] = []
    overlaps: list[dict[str, Any]] = []
    through_blocks: list[dict[str, Any]] = []
    seen_crossings: set[tuple[Any, ...]] = set()
    seen_overlaps: set[tuple[Any, ...]] = set()
    seen_through: set[tuple[str, str]] = set()
    crossing_pairs: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    goto_from_blocks = [
        {
            "path": block["path"],
            "type": block.get("type"),
            "tag": str(block.get("goto_tag") or ""),
            "visibility": str(block.get("goto_tag_visibility") or ""),
        }
        for block in (blocks or [])
        if str(block.get("type")) in {"Goto", "From"}
    ]

    for line in raw_lines:
        for segment in line["segs"]:
            if not (is_horizontal(segment) or is_vertical(segment)):
                diagonal_segments.append(
                    {
                        "line": line["id"],
                        "start": [segment[0][0], segment[0][1]],
                        "end": [segment[1][0], segment[1][1]],
                    }
                )

        endpoints = {line.get("src_block"), line.get("dst_block")}
        for segment in line["segs"]:
            for path, value in block_rects.items():
                if path in endpoints or not hits_interior(segment, value):
                    continue
                key = (line["id"], path)
                if key in seen_through:
                    continue
                seen_through.add(key)
                through_blocks.append(
                    {
                        "line": line["id"],
                        "block": path,
                        "segment": [
                            [segment[0][0], segment[0][1]],
                            [segment[1][0], segment[1][1]],
                        ],
                    }
                )

    for i, first in enumerate(raw_lines):
        for second in raw_lines[i + 1 :]:
            same_source = (
                first.get("src_block") == second.get("src_block")
                and first.get("src_port") == second.get("src_port")
            )
            for segment_a in first["segs"]:
                for segment_b in second["segs"]:
                    point = crossing(segment_a, segment_b)
                    if point:
                        ids = sorted((str(first["id"]), str(second["id"])))
                        key = (*ids, round(point[0], 3), round(point[1], 3))
                        if key not in seen_crossings:
                            seen_crossings.add(key)
                            endpoint_a = endpoint_signature(first)
                            endpoint_b = endpoint_signature(second)
                            crossing_pairs.add(tuple(sorted((endpoint_a, endpoint_b))))
                            crossings.append(
                                {
                                    "line_a": first["id"],
                                    "line_b": second["id"],
                                    "endpoint_a": endpoint_a,
                                    "endpoint_b": endpoint_b,
                                    "point": [point[0], point[1]],
                                }
                            )

                    point = overlap(segment_a, segment_b)
                    if point and not same_source:
                        ids = sorted((str(first["id"]), str(second["id"])))
                        key = (*ids, round(point[0], 3), round(point[1], 3))
                        if key not in seen_overlaps:
                            seen_overlaps.add(key)
                            overlaps.append(
                                {
                                    "line_a": first["id"],
                                    "line_b": second["id"],
                                    "endpoint_a": endpoint_signature(first),
                                    "endpoint_b": endpoint_signature(second),
                                    "point": [point[0], point[1]],
                                }
                            )

    block_types = {str(b.get("path")): str(b.get("type")) for b in (blocks or [])}
    goto_blocks = [b for b in (blocks or []) if str(b.get("type")) == "Goto"]
    from_blocks = [b for b in (blocks or []) if str(b.get("type")) == "From"]
    goto_by_tag: dict[str, list] = defaultdict(list)
    from_by_tag: dict[str, list] = defaultdict(list)
    for b in goto_blocks:
        goto_by_tag[str(b.get("goto_tag") or "")].append(b)
    for b in from_blocks:
        from_by_tag[str(b.get("goto_tag") or "")].append(b)
    goto_violations: list[dict[str, Any]] = []
    for b in goto_blocks:
        tag = str(b.get("goto_tag") or "")
        vis = str(b.get("goto_tag_visibility") or "")
        if not tag:
            goto_violations.append({"kind": "missing_tag", "block": b["path"]})
        if not vis:
            goto_violations.append({"kind": "visibility_missing", "block": b["path"]})
        elif vis != "local":
            goto_violations.append(
                {"kind": "visibility_not_local", "block": b["path"], "value": vis}
            )
        if tag and not from_by_tag.get(tag):
            goto_violations.append(
                {"kind": "unpaired_goto", "block": b["path"], "tag": tag}
            )
    for b in from_blocks:
        tag = str(b.get("goto_tag") or "")
        if not tag:
            goto_violations.append({"kind": "missing_tag", "block": b["path"]})
        if tag and not goto_by_tag.get(tag):
            goto_violations.append(
                {"kind": "unpaired_from", "block": b["path"], "tag": tag}
            )
    for tag, fs in from_by_tag.items():
        if tag and len(fs) > 2:
            goto_violations.append(
                {"kind": "froms_per_tag_exceeded", "tag": tag, "count": len(fs)}
            )
    for line in raw_lines:
        st = block_types.get(str(line.get("src_block")), "")
        dt = block_types.get(str(line.get("dst_block")), "")
        if dt == "Goto" and st == "Inport":
            goto_violations.append(
                {
                    "kind": "inport_to_goto",
                    "line": line["id"],
                    "src": line.get("src_block"),
                    "dst": line.get("dst_block"),
                }
            )
        if dt == "Goto" and st == "From":
            goto_violations.append(
                {
                    "kind": "from_to_goto_chaining",
                    "line": line["id"],
                    "src": line.get("src_block"),
                    "dst": line.get("dst_block"),
                }
            )
    goto_from_pairs = [
        {
            "tag": tag,
            "goto": [b["path"] for b in bs],
            "froms": [b["path"] for b in from_by_tag.get(tag, [])],
        }
        for tag, bs in sorted(goto_by_tag.items())
        if tag
    ]
    participation: Counter[str] = Counter()
    for ev in crossings:
        participation[str(ev["line_a"])] += 1
        participation[str(ev["line_b"])] += 1
    line_by_id = {str(l["id"]): l for l in raw_lines}
    goto_conversion_candidates = []
    for lid, count in participation.items():
        l = line_by_id.get(lid)
        if not l:
            continue
        st = block_types.get(str(l.get("src_block")), "")
        dt = block_types.get(str(l.get("dst_block")), "")
        if st == "Inport" or st in {"Goto", "From"} or dt in {"Goto", "From"}:
            continue
        goto_conversion_candidates.append(
            {
                "line": lid,
                "src_block": l.get("src_block"),
                "dst_block": l.get("dst_block"),
                "src_type": st,
                "dst_type": dt,
                "crossing_events": count,
                "length": round(float(l["length"]), 3),
                "bends": int(l["bends"]),
            }
        )
    goto_conversion_candidates.sort(
        key=lambda c: (-c["crossing_events"], -c["length"], c["line"])
    )

    summary = {
        "line_count": len(raw_lines),
        "crossing_events": len(crossings),
        "crossing_pairs": len(crossing_pairs),
        "overlap_events": len(overlaps),
        "through_block_events": len(through_blocks),
        "diagonal_segments": len(diagonal_segments),
        "goto_from_blocks": len(goto_from_blocks),
        "goto_from_pairs": len(goto_blocks),
        "functional_block_count": len(blocks or []) - len(goto_from_blocks),
        "total_bends": sum(int(line["bends"]) for line in raw_lines),
        "total_length": round(sum(float(line["length"]) for line in raw_lines), 3),
        "max_bends": max((int(line["bends"]) for line in raw_lines), default=0),
    }
    return {
        "summary": summary,
        "crossings": crossings,
        "overlaps": overlaps,
        "through_blocks": through_blocks,
        "diagonal_segments": diagonal_segments,
        "goto_from_blocks": goto_from_blocks,
        "goto_from_pairs": goto_from_pairs,
        "goto_violations": goto_violations,
        "goto_conversion_candidates": goto_conversion_candidates,
    }


def goto_budget(goto_policy: dict[str, Any], functional_blocks: int) -> int:
    """Pair budget tiers by functional block count, capped by hard_cap_pairs."""
    allowed = 0
    for tier in goto_policy.get("budget_tiers") or []:
        if not isinstance(tier, dict):
            continue
        cap = tier.get("max_functional_blocks")
        if cap is None or functional_blocks <= int(cap):
            allowed = int(tier.get("max_pairs", 0))
            break
    return min(allowed, int(goto_policy.get("hard_cap_pairs", 0)))


def evaluate_appearance_quality(
    *,
    profile: dict[str, Any],
    geometry: dict[str, Any],
    measurement: dict[str, Any],
    mode: str,
    baseline_geometry: dict[str, Any] | None,
    baseline_measurement: dict[str, Any] | None,
    baseline_source: str | None,
    goto_justification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the project appearance policy independently of rule compliance."""
    policy = profile.get("appearance_quality")
    current = measurement["summary"]
    result: dict[str, Any] = {
        "policy_id": policy.get("policy_id") if isinstance(policy, dict) else None,
        "status": "project-policy",
        "mode": mode,
        "overall": "INVALID",
        "summary": current,
        "reasons": [],
        "crossings": measurement["crossings"],
        "overlaps": measurement["overlaps"],
        "through_blocks": measurement["through_blocks"],
        "diagonal_segments": measurement["diagonal_segments"],
        "goto_from_blocks": measurement["goto_from_blocks"],
        "goto_from_pairs": measurement.get("goto_from_pairs", []),
        "goto_violations": measurement.get("goto_violations", []),
        "goto_conversion_candidates": measurement.get("goto_conversion_candidates", []),
        "visual_review": {
            "required": True,
            "authority": "current-scope render_check PNG",
            "status": "not evaluated by geometry linter",
        },
    }
    invalid_reasons: list[str] = []
    fail_reasons: list[str] = []

    if not isinstance(policy, dict):
        result["reasons"] = ["layout-profile.json 缺少 appearance_quality 项目策略"]
        return result
    if profile.get("matlab_version") not in {"R2025b", "2025b"}:
        invalid_reasons.append("layout-profile.json 的 matlab_version 必须为 R2025b")
    if set(profile.get("profiles") or []) != {"NA-MAAB", "JMAAB"}:
        invalid_reasons.append("layout-profile.json 的 profiles 必须同时包含 NA-MAAB 和 JMAAB")
    if policy.get("policy_id") != PROJECT_POLICY_ID:
        invalid_reasons.append(
            f"appearance_quality.policy_id 必须为 {PROJECT_POLICY_ID}"
        )
    if policy.get("scope_coverage") != (
        "all_nested_simulink_scopes_with_direct_geometry"
    ):
        invalid_reasons.append(
            "appearance_quality.scope_coverage 必须覆盖所有有直接 Simulink 图面的层级"
        )
    line_metrics_policy = policy.get("line_metrics")
    if not isinstance(line_metrics_policy, dict):
        invalid_reasons.append("appearance_quality.line_metrics 缺失或不是对象")
    else:
        if line_metrics_policy.get("length_unit") != (
            "Simulink geometry coordinate units"
        ):
            invalid_reasons.append(
                "appearance_quality.line_metrics.length_unit 必须声明为 Simulink 坐标单位"
            )
        if line_metrics_policy.get("aggregation") != (
            "sum by scope, never compare coordinates across scopes"
        ):
            invalid_reasons.append(
                "appearance_quality.line_metrics.aggregation 必须按 scope 汇总"
            )
    detection_response = policy.get("detection_response")
    if not isinstance(detection_response, dict):
        invalid_reasons.append("appearance_quality.detection_response 缺失或不是对象")
    else:
        if detection_response.get("crossing_trigger") != (
            "crossing_events > 0 enters repair workflow"
        ):
            invalid_reasons.append(
                "appearance_quality.detection_response 必须要求交叉进入整改流程"
            )
        if detection_response.get("line_hop_closes_gate") is not False:
            invalid_reasons.append(
                "appearance_quality.detection_response.line_hop_closes_gate 必须为 false"
            )
        if detection_response.get("goto_from_is_layout_fix") != "bounded_last_resort":
            invalid_reasons.append(
                "appearance_quality.detection_response.goto_from_is_layout_fix "
                "必须为 bounded_last_resort"
            )

    limits = policy.get("absolute_limits")
    if not isinstance(limits, dict):
        invalid_reasons.append("appearance_quality.absolute_limits 缺失或不是对象")
    else:
        result["absolute_limits"] = limits
        if set(limits.keys()) != set(HARD_ZERO_METRICS):
            invalid_reasons.append(
                "appearance_quality.absolute_limits 必须恰好包含四个硬零指标，"
                "Goto/From 由 goto_from_policy 管辖"
            )
        for key in HARD_ZERO_METRICS:
            maximum = limits.get(key)
            if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
                invalid_reasons.append(
                    f"appearance_quality.absolute_limits.{key} 必须为非负整数"
                )
            elif maximum != 0:
                invalid_reasons.append(
                    f"appearance_quality.absolute_limits.{key} 必须为 0"
                )

    line_hop = policy.get("line_hop")
    result["line_hop"] = line_hop
    if not isinstance(line_hop, dict):
        invalid_reasons.append("appearance_quality.line_hop 缺失或不是对象")
    else:
        if line_hop.get("counts_as_crossing") is not True:
            invalid_reasons.append(
                "appearance_quality.line_hop.counts_as_crossing 必须为 true"
            )
        if line_hop.get("allowed_as_appearance_pass") is not False:
            invalid_reasons.append(
                "appearance_quality.line_hop.allowed_as_appearance_pass 必须为 false"
            )
        waiver = line_hop.get("residual_waiver")
        if not isinstance(waiver, dict):
            invalid_reasons.append(
                "appearance_quality.line_hop.residual_waiver 缺失或不是对象"
            )
        else:
            if waiver.get("max_crossing_events") != 2:
                invalid_reasons.append(
                    "line_hop.residual_waiver.max_crossing_events 必须为 2"
                )
            if waiver.get("max_involved_lines") != 2:
                invalid_reasons.append(
                    "line_hop.residual_waiver.max_involved_lines 必须为 2"
                )
            for flag in (
                "requires_goto_budget_exhausted",
                "requires_geometry_exhausted_attestation",
                "requires_hop_observed",
            ):
                if waiver.get(flag) is not True:
                    invalid_reasons.append(
                        f"line_hop.residual_waiver.{flag} 必须为 true"
                    )

    goto_policy = policy.get("goto_from_policy")
    result["goto_from_policy"] = goto_policy
    if not isinstance(goto_policy, dict):
        invalid_reasons.append("appearance_quality.goto_from_policy 缺失或不是对象")
        goto_policy = {}
    else:
        if goto_policy.get("enabled") is not True:
            invalid_reasons.append("goto_from_policy.enabled 必须为 true")
        expected_tiers = [
            {"max_functional_blocks": 20, "max_pairs": 1},
            {"max_functional_blocks": 60, "max_pairs": 2},
            {"max_functional_blocks": None, "max_pairs": 3},
        ]
        if goto_policy.get("budget_tiers") != expected_tiers:
            invalid_reasons.append(
                "goto_from_policy.budget_tiers 必须为 (<=20:1, <=60:2, 其余:3)"
            )
        if goto_policy.get("hard_cap_pairs") != 3:
            invalid_reasons.append("goto_from_policy.hard_cap_pairs 必须为 3")
        if goto_policy.get("max_froms_per_tag") != 2:
            invalid_reasons.append("goto_from_policy.max_froms_per_tag 必须为 2")
        if goto_policy.get("tag_visibility") != "local":
            invalid_reasons.append("goto_from_policy.tag_visibility 必须为 local")
        for flag in (
            "forbid_inport_to_goto",
            "forbid_from_to_goto_chaining",
            "require_paired",
            "require_justification",
        ):
            if goto_policy.get(flag) is not True:
                invalid_reasons.append(f"goto_from_policy.{flag} 必须为 true")
        mcl = goto_policy.get("min_candidate_line_length")
        if isinstance(mcl, bool) or not isinstance(mcl, int) or mcl <= 0:
            invalid_reasons.append(
                "goto_from_policy.min_candidate_line_length 必须为正整数"
            )

    if policy.get("acceptance_order") != list(APPEARANCE_ORDER):
        invalid_reasons.append(
            "appearance_quality.acceptance_order 必须与 layout_lint.py 的硬指标顺序一致"
        )
    visual_review = policy.get("visual_review")
    if not isinstance(visual_review, dict) or visual_review.get("required") is not True:
        invalid_reasons.append(
            "appearance_quality.visual_review.required 必须为 true"
        )
    elif visual_review.get("authority") != "current-scope render_check PNG":
        invalid_reasons.append(
            "appearance_quality.visual_review.authority 必须为 current-scope render_check PNG"
        )

    if isinstance(limits, dict):
        for key in HARD_ZERO_METRICS:
            value = current.get(key)
            maximum = limits.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                invalid_reasons.append(f"当前测量值 {key} 无效")
            elif isinstance(maximum, int) and not isinstance(maximum, bool) and value > maximum:
                fail_reasons.append(f"{key}={value} 超过项目上限 {maximum}")

    # Bounded Goto/From policy: budget, pairing, visibility, justification.
    functional_blocks = int(current.get("functional_block_count", 0))
    allowed_pairs = goto_budget(goto_policy, functional_blocks)
    used_pairs = int(current.get("goto_from_pairs", 0))
    result["goto_budget"] = {
        "functional_blocks": functional_blocks,
        "allowed_pairs": allowed_pairs,
        "used_pairs": used_pairs,
    }
    for item in measurement.get("goto_violations", []):
        kind = item.get("kind")
        if kind == "visibility_missing":
            invalid_reasons.append(
                f"导出缺少 Goto TagVisibility：{item.get('block')}（fail-closed）"
            )
        else:
            fail_reasons.append(
                "Goto/From 违反项目约束 ["
                + str(kind)
                + "]："
                + json.dumps(item, ensure_ascii=False)
            )
    if used_pairs > allowed_pairs:
        fail_reasons.append(
            f"Goto/From 对数 {used_pairs} 超过 scope 预算 {allowed_pairs}"
            f"（功能块 {functional_blocks}）；不得大面积使用 Goto/From"
        )
    baseline_tags: set[str] = set()
    if mode == "existing" and baseline_measurement is not None:
        baseline_tags = {
            str(p.get("tag"))
            for p in baseline_measurement.get("goto_from_pairs", [])
            if p.get("tag")
        }
    introduced = [
        p
        for p in measurement.get("goto_from_pairs", [])
        if p.get("tag") and p["tag"] not in baseline_tags
    ]
    result["introduced_goto_tags"] = [p["tag"] for p in introduced]
    if introduced and goto_policy.get("require_justification") is True:
        if goto_justification is None:
            fail_reasons.append(
                "新增 Goto/From 缺少交叉裁决证据（--goto-justification）"
            )
        else:
            entries = goto_justification.get("pairs") or []
            by_tag = {
                str(e.get("tag")): e for e in entries if isinstance(e, dict)
            }
            for p in introduced:
                e = by_tag.get(p["tag"])
                if (
                    not e
                    or not str(e.get("reason") or "").strip()
                    or not (e.get("eliminated_crossings") or [])
                ):
                    fail_reasons.append(
                        f"Goto/From tag {p['tag']} 缺少有效交叉裁决证据"
                        "（reason + eliminated_crossings）"
                    )
    mcl = goto_policy.get("min_candidate_line_length", 0)
    result["goto_conversion_candidates"] = [
        c
        for c in measurement.get("goto_conversion_candidates", [])
        if c.get("length", 0) >= mcl
    ][:10]

    crossing_events = int(current.get("crossing_events", 0))
    waiver_granted = False
    if crossing_events:
        involved: set[str] = set()
        for ev in measurement.get("crossings", []):
            involved.add(str(ev.get("line_a")))
            involved.add(str(ev.get("line_b")))
        hop_observed, hop_value = line_crossing_setting(geometry)
        waiver_policy = (
            line_hop.get("residual_waiver") if isinstance(line_hop, dict) else {}
        ) or {}
        budget_exhausted = allowed_pairs > 0 and used_pairs >= allowed_pairs
        residual_claim = (goto_justification or {}).get("residual_waiver") or {}
        attested = bool(
            goto_justification is not None
            and goto_justification.get("geometry_exhausted") is True
            and residual_claim.get("claimed") is True
            and str(residual_claim.get("reason") or "").strip()
        )
        eligible = (
            crossing_events <= int(waiver_policy.get("max_crossing_events", 0))
            and len(involved) <= int(waiver_policy.get("max_involved_lines", 0))
            and hop_observed is True
            and budget_exhausted
            and attested
        )
        if eligible:
            result["residual_waiver"] = {
                "status": "granted",
                "crossing_events": crossing_events,
                "involved_lines": sorted(involved),
                "hop_value": hop_value,
                "closure": "MANUAL：逐张 PNG 复核并在交付报告列出残留线对",
            }
            # 极小豁免成立：撤销 crossing_events 的硬零失败原因，
            # 残留交叉改由 MANUAL 图面复核关闭。
            fail_reasons[:] = [
                r for r in fail_reasons if not r.startswith("crossing_events=")
            ]
            waiver_granted = True
        else:
            detail = []
            if crossing_events > 2 or len(involved) > 2:
                detail.append(
                    f"残留交叉 {crossing_events} 处/涉及 {len(involved)} 条线，"
                    "超出极小豁免范围（≤2 处且 ≤2 线）"
                )
            else:
                if hop_observed is not True:
                    detail.append(
                        f"实际 Line crossing style 非 hop（{hop_value}）"
                    )
                if not budget_exhausted:
                    detail.append(
                        f"Goto/From 预算未耗尽（{used_pairs}/{allowed_pairs}），"
                        "必须先按 goto_conversion_candidates 裁决转换"
                    )
                if not attested:
                    detail.append(
                        "缺少几何手段穷尽与残留豁免的书面裁决"
                        "（--goto-justification）"
                    )
            fail_reasons.append(
                "Line Hop 不能关闭外观门禁：" + "；".join(detail)
            )

    if mode == "existing":
        existing_policy = policy.get("existing_scope")
        if not isinstance(existing_policy, dict):
            invalid_reasons.append("appearance_quality.existing_scope 缺失或不是对象")
            existing_policy = {}
        elif existing_policy.get("require_baseline") is not True:
            invalid_reasons.append(
                "appearance_quality.existing_scope.require_baseline 必须为 true"
            )

        max_delta = existing_policy.get("max_delta")
        if not isinstance(max_delta, dict):
            invalid_reasons.append("appearance_quality.existing_scope.max_delta 缺失或不是对象")
            max_delta = {}
        else:
            if set(max_delta.keys()) != set(HARD_ZERO_METRICS):
                invalid_reasons.append(
                    "existing_scope.max_delta 必须恰好覆盖四个硬零指标"
                )
            for key in HARD_ZERO_METRICS:
                maximum = max_delta.get(key)
                if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
                    invalid_reasons.append(
                        f"appearance_quality.existing_scope.max_delta.{key} 必须为非负整数"
                    )
                elif maximum != 0:
                    invalid_reasons.append(
                        f"appearance_quality.existing_scope.max_delta.{key} 必须为 0"
                    )

        if baseline_geometry is None or baseline_measurement is None:
            invalid_reasons.append("已有模型缺少有效的修改前 baseline 几何")
        else:
            baseline_summary = baseline_measurement["summary"]
            delta = {
                key: int(current.get(key, 0)) - int(baseline_summary.get(key, 0))
                for key in HARD_ZERO_METRICS
            }
            result["goto_delta"] = used_pairs - int(
                baseline_summary.get("goto_from_pairs", 0)
            )
            result["baseline"] = {
                "source": baseline_source,
                "model": baseline_geometry.get("model"),
                "scope": baseline_geometry.get("scope"),
                "summary": baseline_summary,
            }
            result["delta"] = delta
            if str(baseline_geometry.get("model")) != str(geometry.get("model")):
                invalid_reasons.append("baseline 与当前几何的 model 不一致")
            if str(baseline_geometry.get("scope")).rstrip("/") != str(
                geometry.get("scope")
            ).rstrip("/"):
                invalid_reasons.append("baseline 与当前几何的 scope 不一致")
            # Goto/From 的新增不再一律判失败：由 goto_from_policy 的预算、
            # 配对/可见性/直连约束和交叉裁决证据管辖（见上方 introduced 检查）。
            for key in HARD_ZERO_METRICS:
                if waiver_granted and key == "crossing_events":
                    continue
                maximum = max_delta.get(key)
                if isinstance(maximum, int) and not isinstance(maximum, bool):
                    if delta[key] > maximum:
                        fail_reasons.append(
                            f"{key} 相对 baseline 增加 {delta[key]}，超过允许值 {maximum}"
                        )

    result["invalid_reasons"] = invalid_reasons
    result["fail_reasons"] = fail_reasons
    result["reasons"] = [*invalid_reasons, *fail_reasons]
    if invalid_reasons:
        result["overall"] = "INVALID"
    elif fail_reasons:
        result["overall"] = "FAIL"
    else:
        result["overall"] = "PASS"
    return result


# ---------------------------------------------------------------------------
# db_0097 estimated label geometry.
#
# R2025b does not expose rendered label bounding boxes, so line-name labels
# are invisible to pure coordinate checks. To avoid the false
# "VIOLATION = 0" signal seen in real use, estimate each named line's label
# bbox (db_0097-b: below the line; db_0097-c: near the connection origin)
# from the project font size, then test it against other labels, blocks and
# line segments. Estimated hits are reported as VIOLATION with an
# explicit "估算" evidence tag; the authoritative closure is the rendered
# PNG from scripts/render_check.m, not this estimate.

CHAR_WIDTH_FACTOR = 0.6  # average Arial-ish glyph width per font size point
LABEL_HEIGHT_FACTOR = 1.4
LABEL_OFFSET = 2.0  # pixels between the line and the label above/below it


def font_size(profile: dict[str, Any]) -> float | None:
    sizes = profile.get("font") or {}
    value = (sizes.get("signal_name") or {}).get("size")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def estimated_label_bbox(
    line: dict[str, Any], size: float
) -> tuple[float, float, float, float] | None:
    name = str(line.get("name") or "")
    points = line.get("points") or []
    if not name or len(points) < 2:
        return None
    anchor = (float(points[0][0]), float(points[0][1]))
    width = len(name) * size * CHAR_WIDTH_FACTOR
    height = size * LABEL_HEIGHT_FACTOR
    return (anchor[0], anchor[1] + LABEL_OFFSET, anchor[0] + width, anchor[1] + LABEL_OFFSET + height)


def bbox_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return (
        first[0] < second[2] - TOL
        and second[0] < first[2] - TOL
        and first[1] < second[3] - TOL
        and second[1] < first[3] - TOL
    )


def segment_hits_bbox(
    segment: tuple[tuple[float, float], tuple[float, float]],
    value: tuple[float, float, float, float],
) -> bool:
    if is_horizontal(segment):
        y = segment[0][1]
        if not value[1] - TOL < y < value[3] + TOL:
            return False
        low, high = sorted((segment[0][0], segment[1][0]))
        return high > value[0] + TOL and low < value[2] - TOL
    if is_vertical(segment):
        x = segment[0][0]
        if not value[0] - TOL < x < value[2] + TOL:
            return False
        low, high = sorted((segment[0][1], segment[1][1]))
        return high > value[1] + TOL and low < value[3] - TOL
    return False


def lint_db0097(
    raw_lines: list[dict[str, Any]],
    block_rects: dict[str, Any],
    profile: dict[str, Any],
    report: Report,
    scope: str,
) -> None:
    size = font_size(profile)
    named = []
    if size is not None:
        for line in raw_lines:
            bbox = estimated_label_bbox(line, size)
            if bbox is not None:
                named.append((line, bbox))

    if not any(str(line.get("name") or "") for line in raw_lines):
        report.not_applicable("db_0097-a", scope, "本层没有命名信号线")
        report.not_applicable("db_0097-b", scope, "本层没有命名信号线")
        report.not_applicable("db_0097-c", scope, "本层没有命名信号线")
        return

    if size is None or not named:
        report.manual(
            "db_0097-a",
            scope,
            "项目 profile 未提供 signal_name 字号，无法估算标签包围盒",
            "补充 profile.font.signal_name.size 并重跑；或用 render_check 渲染复核",
        )
        report.manual(
            "db_0097-b",
            scope,
            "无法估算标签位置",
            "用 render_check 渲染复核标签是否位于线下方",
        )
        report.manual(
            "db_0097-c",
            scope,
            "无法估算标签位置",
            "用 render_check 渲染复核标签是否位于连接起点",
        )
        return

    violations = 0
    # Label vs label.
    for i, (line_a, bbox_a) in enumerate(named):
        for line_b, bbox_b in named[i + 1:]:
            if line_a is line_b:
                continue
            if bbox_overlap(bbox_a, bbox_b):
                violations += 1
                report.violation(
                    "db_0097-a",
                    f"{line_a['id']} × {line_b['id']}",
                    f"估算标签重叠：{line_a.get('name')!r} 与 {line_b.get('name')!r}",
                    "拉开信号线间距或缩短信号名；以 render_check 截图确认",
                )

    # Label vs blocks (its own source/target blocks may touch the anchor).
    for line, bbox in named:
        endpoints = {line.get("src_block"), line.get("dst_block")}
        for path, block_box in block_rects.items():
            if path in endpoints:
                continue
            if bbox_overlap(bbox, block_box):
                violations += 1
                report.violation(
                    "db_0097-a",
                    line["id"],
                    f"估算标签 {line.get('name')!r} 与块 {path} 重叠",
                    "移动块/线或缩短信号名；以 render_check 截图确认",
                )

    # Label vs other line segments.
    for line, bbox in named:
        own = {line["id"]}
        for other in raw_lines:
            if other["id"] in own or not other["segs"]:
                continue
            for segment in other["segs"]:
                if segment_hits_bbox(segment, bbox):
                    violations += 1
                    report.violation(
                        "db_0097-a",
                        line["id"],
                        f"估算标签 {line.get('name')!r} 被线 {other['id']} 穿过",
                        "改走线或移标签；以 render_check 截图确认",
                    )
                    break

    if violations:
        report.manual(
            "db_0097-b",
            scope,
            "存在估算违规，标签方位须与 a 项一并人工复核",
            "用 render_check 渲染复核标签是否位于线下方",
        )
        report.manual(
            "db_0097-c",
            scope,
            "存在估算违规，标签位置须与 a 项一并人工复核",
            "用 render_check 渲染复核标签是否位于连接起点",
        )
    else:
        report.manual(
            "db_0097-a",
            scope,
            "估算未发现重叠，但 R2025b API 不提供标签实际包围盒",
            "用 render_check 渲染截图复核后签核；估算不等于实测",
        )
        report.manual(
            "db_0097-b",
            scope,
            "标签是否位于线下方无法由 API 证明",
            "用 render_check 渲染复核",
        )
        report.manual(
            "db_0097-c",
            scope,
            "标签是否位于连接起点无法由 API 证明",
            "用 render_check 渲染复核",
        )


def validate_geometry(geo: Any, report: Report) -> bool:
    if not isinstance(geo, dict):
        report.schema_errors.append("geometry root must be an object")
        return False
    required = (
        "schema_version",
        "standard",
        "matlab_version",
        "model",
        "scope",
        "blocks",
        "lines",
        "source_settings",
        "coverage",
    )
    for key in required:
        if key not in geo:
            report.schema_errors.append(f"missing top-level field: {key}")
    if report.schema_errors:
        return False
    if geo["schema_version"] != SCHEMA_VERSION:
        report.schema_errors.append(
            f"schema_version must be {SCHEMA_VERSION}, got {geo['schema_version']!r}"
        )
    if geo["standard"] != TARGET_STANDARD:
        report.schema_errors.append(f"standard must be {TARGET_STANDARD}")
    if str(geo["matlab_version"]).lower() not in {"r2025b", "2025b"}:
        report.schema_errors.append("matlab_version must be R2025b")
    if not isinstance(geo["blocks"], list) or not geo["blocks"]:
        report.schema_errors.append("blocks must be a non-empty array")
    if not isinstance(geo["lines"], list):
        report.schema_errors.append("lines must be an array")
    if report.schema_errors:
        return False
    scope = str(geo["scope"]).rstrip("/")
    paths = set()
    for index, block in enumerate(geo["blocks"]):
        if not isinstance(block, dict):
            report.schema_errors.append(f"blocks[{index}] must be an object")
            continue
        for key in (
            "path",
            "type",
            "position",
            "orientation",
            "shadow",
            "name_placement",
            "ports",
        ):
            if key not in block:
                report.schema_errors.append(f"blocks[{index}] missing {key}")
        if "path" in block:
            path = str(block["path"]).rstrip("/")
            if path in paths:
                report.schema_errors.append(f"duplicate block path: {path}")
            paths.add(path)
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent != scope:
                report.schema_errors.append(
                    f"block {path} is not a direct child of scope {scope}"
                )
        if "position" in block:
            if not isinstance(block["position"], list) or len(block["position"]) != 4:
                report.schema_errors.append(f"block {block.get('path')} position must have 4 numbers")
            else:
                try:
                    _ = rect(block)
                except (TypeError, ValueError):
                    report.schema_errors.append(f"block {block.get('path')} has non-numeric position")
    seen_line_ids = set()
    for index, line in enumerate(geo["lines"]):
        if not isinstance(line, dict):
            report.schema_errors.append(f"lines[{index}] must be an object")
            continue
        for key in ("id", "points", "src_block", "src_port", "dst_block", "dst_port"):
            if key not in line:
                report.schema_errors.append(f"lines[{index}] missing {key}")
        line_id = str(line.get("id", ""))
        if line_id in seen_line_ids:
            report.schema_errors.append(f"duplicate line id: {line_id}")
        seen_line_ids.add(line_id)
        points = line.get("points")
        if not isinstance(points, list) or (points and len(points) < 2):
            report.schema_errors.append(f"line {line_id} points must be empty or have at least 2 points")
        for key in ("src_block", "dst_block"):
            endpoint = line.get(key)
            if endpoint and endpoint not in paths:
                report.schema_errors.append(
                    f"line {line_id} endpoint {endpoint} is not a direct child of {scope}"
                )
    return not report.schema_errors


def lint(
    geo: dict[str, Any],
    profile: dict[str, Any],
    source: str,
    *,
    mode: str = "new",
    baseline_geo: dict[str, Any] | None = None,
    baseline_source: str | None = None,
    goto_justification: dict[str, Any] | None = None,
) -> Report:
    report = Report(source)
    if not validate_geometry(geo, report):
        return report

    blocks, block_rects, raw_lines = normalize_geometry(geo)
    appearance = measure_appearance(raw_lines, block_rects, blocks)
    report.line_metrics = [
        {
            "id": line["id"],
            "vertices": len(line.get("points") or []),
            "bends": line["bends"],
            "length": round(line["length"], 3),
        }
        for line in raw_lines
    ]
    feedback = cycle_edges(raw_lines)
    baseline_measurement = None
    if baseline_geo is not None:
        baseline_report = Report(baseline_source or "<baseline>")
        if validate_geometry(baseline_geo, baseline_report):
            baseline_blocks, baseline_block_rects, baseline_lines = normalize_geometry(
                baseline_geo
            )
            baseline_measurement = measure_appearance(
                baseline_lines, baseline_block_rects, baseline_blocks
            )
        else:
            baseline_measurement = None

    # jm_0002 has no numeric target-standard threshold.
    report.manual(
        "jm_0002-a",
        str(geo["scope"]),
        "块图标与文字的可辨识性不能由坐标尺寸证明",
        "在 R2025b 渲染后人工检查；项目尺寸只能作为内部阈值",
    )

    shadow_values = [
        (block["path"], block.get("shadow")) for block in blocks
        if isinstance(block.get("shadow"), bool)
    ]
    if len(shadow_values) != len(blocks):
        report.unknown("jc_0604-a", str(geo["scope"]), "部分块未导出可用的 shadow 值")
    elif any(value for _, value in shadow_values):
        for path, value in shadow_values:
            if value:
                report.violation("jc_0604-a", path, "shadow=true", "关闭块阴影")
    else:
        report.mark("jc_0604-a", str(geo["scope"]), "所有直接子块 shadow=false")

    placements = [
        (block["path"], block.get("name_placement")) for block in blocks
    ]
    missing_placement = [path for path, value in placements if not value]
    invalid_placement = [
        (path, value)
        for path, value in placements
        if value and str(value).lower() not in {"normal", "below"}
    ]
    if missing_placement:
        for path in missing_placement:
            report.unknown("db_0142-a", path, "未导出真实 NamePlacement")
    elif invalid_placement:
        for path, value in invalid_placement:
            report.violation(
                "db_0142-a",
                path,
                f"NamePlacement={value}",
                "通过 model_edit 将块名恢复为块下方",
            )
    else:
        report.mark("db_0142-a", str(geo["scope"]), "所有块名位于下方")

    # Unconnected blocks and signals.
    unconnected_port_seen = False
    port_information_incomplete = False
    for block in blocks:
        ports = block.get("ports")
        if ports is None:
            port_information_incomplete = True
            continue
        if not ports:
            report.unknown(
                "db_0081-b",
                block["path"],
                "未导出 PortConnectivity，无法确认块连接状态",
            )
            port_information_incomplete = True
            continue
        for port in ports:
            if not isinstance(port.get("connected"), bool):
                port_information_incomplete = True
                continue
            if port["connected"] is False:
                unconnected_port_seen = True
                report.violation(
                    "db_0081-b",
                    block["path"],
                    (
                        f"{port.get('direction', 'unknown')} port "
                        f"#{port.get('number', port.get('index', '?'))} is unconnected"
                    ),
                    "连接端口，或用 Terminator/Ground 明确终止",
                )
    if port_information_incomplete:
        report.unknown(
            "db_0081-b",
            str(geo["scope"]),
            "至少一个块的连接信息不完整；不得按已连接处理",
        )
    elif not unconnected_port_seen:
        report.mark("db_0081-b", str(geo["scope"]), "所有直接子块端口均报告 connected=true")

    line_endpoint_missing = False
    for line in raw_lines:
        if not line["segs"]:
            line_endpoint_missing = True
            report.violation(
                "db_0081-a",
                line["id"],
                "信号线没有可验证的两个以上端点",
                "修复连线或删除悬空线",
            )
        elif not line.get("src_block") or not line.get("dst_block"):
            line_endpoint_missing = True
            report.unknown(
                "db_0081-a",
                line["id"],
                "线的源块或目标块未导出",
                "重新导出直接 scope 的线端点",
            )
    if raw_lines and not line_endpoint_missing:
        report.mark("db_0081-a", str(geo["scope"]), "所有信号线均有源/目标和几何")
    elif not raw_lines:
        report.unknown(
            "db_0081-a",
            str(geo["scope"]),
            "scope 未导出任何信号线；不能据此声称无未连接线",
        )

    # Direction and orientation.
    orientation_unknown = False
    orientation_bad = False
    for block in blocks:
        orientation = str(block.get("orientation") or "").lower()
        if not orientation:
            orientation_unknown = True
            continue
        if orientation == "right":
            continue
        allowed_delay = (
            block.get("type") == "Delay"
            and any(
                line["id"] in feedback
                and block["path"] in (line.get("src_block"), line.get("dst_block"))
                for line in raw_lines
            )
        )
        if orientation == "left" and allowed_delay:
            continue
        orientation_bad = True
        report.violation(
            "jc_0110-a",
            block["path"],
            f"orientation={orientation}",
            "通过 model_edit 将块输出朝右；仅反馈环 Delay 可向左",
        )
    if orientation_unknown:
        report.unknown("jc_0110-a", str(geo["scope"]), "部分块未导出 Orientation")
    elif not orientation_bad:
        report.mark("jc_0110-a", str(geo["scope"]), "block orientation 满足规则")

    # Line geometry and overlap/crossing checks.
    diagonal_count = appearance["summary"]["diagonal_segments"]
    for event in appearance["diagonal_segments"]:
        report.violation(
            "db_0032-e",
            event["line"],
            f"斜线段 {tuple(event['start'])} -> {tuple(event['end'])}",
            "改为水平/垂直正交走线",
        )
    if not diagonal_count:
        report.mark("db_0032-e", str(geo["scope"]), "所有导出的线段正交")

    if appearance["overlaps"]:
        for event in appearance["overlaps"]:
            report.violation(
                "db_0032-b",
                f"{event['line_a']} × {event['line_b']}",
                f"线在 {tuple(event['point'])} 附近重叠",
                "分开走线，避免不同信号线共线",
            )
    else:
        report.mark("db_0032-b", str(geo["scope"]), "未发现不同信号线共线重叠")

    if appearance["crossings"]:
        hop_observed, hop_value = line_crossing_setting(geo)
        for event in appearance["crossings"]:
            where = (
                f"{event['line_a']} × {event['line_b']} "
                f"@ {tuple(event['point'])}"
            )
            if hop_observed is True:
                report.mark("db_0032-a1", where, "交叉存在，实际设置为 Line hop")
                report.mark("db_0032-a2", where, f"实际 Line crossing style={hop_value}")
            elif hop_observed is False:
                report.violation(
                    "db_0032-a1",
                    where,
                    f"水平/垂直线交叉，实际 Line crossing style={hop_value}",
                    "消除交叉，或将实际编辑器设置改为 Line hop",
                )
                report.violation(
                    "db_0032-a2",
                    where,
                    "交叉发生但实际设置不是 Line hop",
                    "在 R2025b 中确认并启用 Line hop",
                )
            else:
                report.unknown(
                    "db_0032-a1",
                    where,
                    f"交叉存在，但无法确定实际 Line crossing style：{hop_value or 'unknown'}",
                    "检查 get_param(0,'EditorPathXStyle')；不可用 profile 冒充实际设置",
                )
                report.unknown(
                    "db_0032-a2",
                    where,
                    f"交叉存在，实际 EditorPathXStyle={hop_value or 'unknown'}",
                    "读取并记录实际 line crossing style",
                )
    else:
        report.mark("db_0032-a1", str(geo["scope"]), "未发现线交叉")
        report.not_applicable("db_0032-a2", str(geo["scope"]), "没有必须交叉的位置")

    if appearance["through_blocks"]:
        for event in appearance["through_blocks"]:
            report.violation(
                "db_0032-c",
                event["line"],
                f"线段穿过块 {event['block']}",
                "重排块或线路，使信号线绕开块",
            )
    else:
        report.mark("db_0032-c", str(geo["scope"]), "未发现信号线穿过块")

    fanout: dict[tuple[str, Any], set[tuple[str, Any]]] = defaultdict(set)
    for line in raw_lines:
        if line.get("src_block"):
            fanout[(line["src_block"], line.get("src_port"))].add(
                (line.get("dst_block"), line.get("dst_port"))
            )
    jmaab_branch_bad = False
    for (source, port), destinations in fanout.items():
        if len(destinations) > 2:
            jmaab_branch_bad = True
            report.violation(
                "db_0032-d",
                f"{source} output {port}",
                f"同一输出端点分出 {len(destinations)} 个消费者",
                "建立分支树或显式 subsystem 接口；Mux 不能复制标量；不得用 Goto+多 From 隐藏扇出绕过本条",
            )
    if not jmaab_branch_bad:
        report.mark("db_0032-d", str(geo["scope"]), "单输出端点消费者数不超过 2")

    # db_0097 label geometry (estimated; render check is authoritative).
    lint_db0097(raw_lines, block_rects, profile, report, str(geo["scope"]))

    # Signal flow and bends.
    flow_bad = False
    flow_unknown = False
    for line in raw_lines:
        source = line.get("src_block")
        destination = line.get("dst_block")
        if source not in block_rects or destination not in block_rects:
            flow_unknown = True
            continue
        sx, _ = center(block_rects[source])
        dx, _ = center(block_rects[destination])
        if dx < sx - TOL and line["id"] not in feedback:
            flow_bad = True
            report.violation(
                "db_0141-a",
                line["id"],
                "非反馈边从右向左",
                "调整块顺序为左到右；仅实际反馈环可反向",
            )
    if flow_unknown:
        report.unknown("db_0141-a", str(geo["scope"]), "部分线端点无法映射到直接子块")
    elif not flow_bad:
        report.mark("db_0141-a", str(geo["scope"]), "非反馈边未发现右向左流动")

    max_bends = profile.get("layout", {}).get("max_unnecessary_bends")
    bend_facts = ", ".join(
        (
            f"{line['id']}=B{line['bends']}"
            f"(L={line['length']:.1f},vertices={len(line.get('points') or [])})"
        )
        for line in raw_lines
    )
    project_note = (
        f"；project max={max_bends} 仅作为项目阈值，不是目标规范数值"
        if max_bends is not None
        else "；项目未定义可执行阈值"
    )
    report.manual(
        "db_0141-c",
        str(geo["scope"]),
        "“无必要”需结合信号语义人工判断；折弯数：" + (bend_facts or "无") + project_note,
        "按 R2025b 图面人工复核，必要时拆分反馈走廊",
    )

    # Conditional input blocks at the top.
    conditional_types = {"Enable", "Trigger", "ActionPort", "Ifaction", "SwitchCase"}
    conditional = [block for block in blocks if block.get("type") in conditional_types]
    if conditional:
        top = min(value[1] for value in block_rects.values())
        grid = float(profile.get("grid", {}).get("value", 10) or 10)
        bad = [block for block in conditional if block_rects[block["path"]][1] > top + grid + TOL]
        if bad:
            for block in bad:
                report.violation(
                    "db_0146-a",
                    block["path"],
                    "条件输入块明显低于 scope 顶部",
                    "通过 model_edit 将条件输入块放到子系统顶部",
                )
        else:
            report.mark("db_0146-a", str(geo["scope"]), "条件输入块位于顶部容差内")
    else:
        report.not_applicable("db_0146-a", str(geo["scope"]), "本层没有条件输入块")

    report.appearance_quality = evaluate_appearance_quality(
        profile=profile,
        geometry=geo,
        measurement=appearance,
        mode=mode,
        baseline_geometry=baseline_geo if baseline_geo is not None else None,
        baseline_measurement=baseline_measurement,
        baseline_source=baseline_source,
        goto_justification=goto_justification,
    )
    if report.appearance_quality.get("goto_budget", {}).get("used_pairs", 0):
        report.manual(
            "db_0032-a1",
            str(geo["scope"]),
            "存在预算内 Goto/From：短桩位置、local 可见性与标签一致性需图面复核",
            "逐张检查当前 scope PNG，确认 Goto 紧贴源、From 紧贴消费者且未隐藏扇出",
        )
    if (report.appearance_quality.get("residual_waiver") or {}).get("status") == "granted":
        report.manual(
            "db_0032-a1",
            str(geo["scope"]),
            "残留交叉已获极小豁免（≤2 线，Line Hop 显示）",
            "逐张 PNG 复核残留线对，并在交付报告中显式列出",
        )
    return report


def collect_manifest_scopes(
    manifest: Any,
    manifest_source: str,
    *,
    expected_model: str | None = None,
    label: str = "manifest",
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Validate a geometry manifest and load each referenced scope geometry."""
    errors: list[str] = []
    loaded: dict[str, dict[str, Any]] = {}
    if not isinstance(manifest, dict):
        return loaded, [f"{label} root must be an object"]

    required = (
        "schema_version",
        "standard",
        "matlab_version",
        "model",
        "status",
        "scope_count",
        "scopes",
        "coverage",
    )
    for key in required:
        if key not in manifest:
            errors.append(f"{label} is missing {key}")
    if errors:
        return loaded, errors

    if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"{label}.schema_version must be {MANIFEST_SCHEMA_VERSION}, "
            f"got {manifest['schema_version']!r}"
        )
    if manifest["standard"] != TARGET_STANDARD:
        errors.append(f"{label}.standard must be {TARGET_STANDARD}")
    if str(manifest["matlab_version"]).lower() not in {"r2025b", "2025b"}:
        errors.append(f"{label}.matlab_version must be R2025b")
    if expected_model is not None and str(manifest["model"]) != str(expected_model):
        errors.append(
            f"{label}.model={manifest['model']!r} does not match {expected_model!r}"
        )
    if manifest["status"] != "COMPLETE":
        errors.append(f"{label}.status must be COMPLETE, got {manifest['status']!r}")
    coverage = manifest["coverage"]
    if not isinstance(coverage, dict):
        errors.append(f"{label}.coverage must be an object")
    else:
        if coverage.get("all_hierarchy") is not True:
            errors.append(f"{label}.coverage.all_hierarchy must be true")
        if coverage.get("coordinate_frames_mixed") is not False:
            errors.append(f"{label}.coverage.coordinate_frames_mixed must be false")
        export_errors = coverage.get("export_errors")
        if export_errors:
            errors.append(
                f"{label} records {len(export_errors)} export error(s); "
                "global lint remains INVALID"
            )

    scopes = manifest["scopes"]
    if not isinstance(scopes, list) or not scopes:
        errors.append(f"{label}.scopes must be a non-empty array")
        return loaded, errors
    if manifest["scope_count"] != len(scopes):
        errors.append(
            f"{label}.scope_count={manifest['scope_count']!r} "
            f"does not match scopes length {len(scopes)}"
        )

    base = Path(manifest_source).resolve().parent
    for index, entry in enumerate(scopes):
        where = f"{label}.scopes[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where} must be an object")
            continue
        missing_entry_field = False
        for key in ("scope", "geometry_file", "status"):
            if not entry.get(key):
                errors.append(f"{where} is missing {key}")
                missing_entry_field = True
        if missing_entry_field:
            continue
        if entry.get("status") != "EXPORTED":
            errors.append(
                f"{where}.status={entry.get('status')!r}; "
                "all scopes must be EXPORTED"
            )
            continue
        scope = str(entry["scope"]).rstrip("/")
        if scope in loaded:
            errors.append(f"{label} contains duplicate scope {scope}")
            continue
        geometry_name = str(entry["geometry_file"])
        geometry_path = Path(geometry_name)
        if not geometry_path.is_absolute():
            geometry_path = base / geometry_path
        try:
            geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{where}: cannot load {geometry_path}: {exc}")
            continue
        if not isinstance(geometry, dict):
            errors.append(f"{where}: geometry root must be an object")
            continue
        if str(geometry.get("model")) != str(manifest["model"]):
            errors.append(
                f"{where}: geometry model {geometry.get('model')!r} "
                f"does not match manifest model {manifest['model']!r}"
            )
        if str(geometry.get("scope", "")).rstrip("/") != scope:
            errors.append(
                f"{where}: geometry scope {geometry.get('scope')!r} "
                f"does not match {scope!r}"
            )
        if geometry.get("coordinate_frame") != "scope-local":
            errors.append(f"{where}: geometry coordinate_frame must be scope-local")
        geometry["_geometry_source"] = str(geometry_path.resolve())
        loaded[scope] = geometry
    return loaded, errors


def crossing_groups(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group crossing events by stable endpoint pair for repair prioritization."""
    grouped: Counter[tuple[tuple[str, ...], tuple[str, ...]]] = Counter()
    for event in events:
        first = tuple(str(value) for value in event.get("endpoint_a") or [])
        second = tuple(str(value) for value in event.get("endpoint_b") or [])
        pair = tuple(sorted((first, second)))
        grouped[pair] += 1
    result = [
        {
            "endpoint_a": list(pair[0]),
            "endpoint_b": list(pair[1]),
            "crossing_events": count,
            "suggested_action": crossing_group_action(pair[0], pair[1]),
        }
        for pair, count in grouped.items()
    ]
    result.sort(key=lambda item: (-item["crossing_events"], item["endpoint_a"]))
    return result


def crossing_group_action(
    first: tuple[str, ...], second: tuple[str, ...]
) -> str:
    """Recommend the smallest layout change that addresses one endpoint group."""
    first_source = first[0] if len(first) > 0 else ""
    first_target = first[2] if len(first) > 2 else ""
    second_source = second[0] if len(second) > 0 else ""
    second_target = second[2] if len(second) > 2 else ""
    if first_source and first_source == second_source:
        return "同一源的分支发生交叉：对齐消费者端口，或将扇出整理为不交叉的分支树"
    if first_target and first_target == second_target:
        return "同一目标的多条输入交叉：重排源块的纵向顺序或目标端口顺序"
    return "调整两端所属功能列、端口对齐和专用布线走廊；几何手段穷尽后按 goto_conversion_candidates 与预算裁决 Goto/From"


def evaluate_manifest(
    manifest: Any,
    manifest_source: str,
    profile: dict[str, Any],
    *,
    baseline_manifest: Any | None = None,
    baseline_manifest_source: str | None = None,
    requested_mode: str | None = None,
    goto_justification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lint every scope and aggregate project appearance metrics by hierarchy."""
    errors: list[str] = []
    justification_by_scope: dict[str, dict[str, Any]] = {}
    if isinstance(goto_justification, dict):
        for entry in goto_justification.get("scopes") or []:
            if isinstance(entry, dict) and entry.get("scope"):
                justification_by_scope[str(entry["scope"]).rstrip("/")] = entry
    current_scopes, current_errors = collect_manifest_scopes(
        manifest, manifest_source, label="manifest"
    )
    errors.extend(current_errors)

    model = str(manifest.get("model", "")) if isinstance(manifest, dict) else ""
    baseline_scopes: dict[str, dict[str, Any]] = {}
    if baseline_manifest is not None:
        baseline_scopes, baseline_errors = collect_manifest_scopes(
            baseline_manifest,
            baseline_manifest_source or "<baseline-manifest>",
            expected_model=model,
            label="baseline_manifest",
        )
        errors.extend(baseline_errors)
    elif requested_mode == "existing":
        errors.append("existing manifest lint requires a baseline manifest")

    mode = requested_mode or ("existing" if baseline_manifest is not None else "new")
    per_scope: list[dict[str, Any]] = []
    full_reports: list[tuple[dict[str, Any], dict[str, Any], Report]] = []
    totals: Counter[str] = Counter()
    max_bends = 0

    for scope in sorted(current_scopes):
        geometry = current_scopes[scope]
        baseline_geometry = baseline_scopes.get(scope)
        if mode == "existing" and baseline_geometry is not None:
            scope_mode = "existing"
        else:
            scope_mode = "new"
        report = lint(
            geometry,
            profile,
            str(geometry.get("_geometry_source") or manifest_source),
            mode=scope_mode,
            baseline_geo=baseline_geometry,
            baseline_source=(
                str(baseline_geometry.get("_geometry_source"))
                if baseline_geometry is not None
                else None
            ),
            goto_justification=justification_by_scope.get(scope.rstrip("/")),
        )
        scope_report = report.as_dict()
        appearance = scope_report["appearance_quality"]
        summary = dict(appearance.get("summary") or {})
        for key in (
            "line_count",
            "crossing_events",
            "crossing_pairs",
            "overlap_events",
            "through_block_events",
            "diagonal_segments",
            "goto_from_blocks",
            "goto_from_pairs",
            "total_bends",
        ):
            totals[key] += int(summary.get(key, 0) or 0)
        totals["total_length_milli_units"] += round(
            float(summary.get("total_length", 0) or 0) * 1000
        )
        max_bends = max(max_bends, int(summary.get("max_bends", 0) or 0))
        per_scope.append(
            {
                "scope": scope,
                "scope_type": geometry.get("scope_type"),
                "geometry_file": geometry.get("_geometry_source"),
                "baseline_geometry_file": (
                    baseline_geometry.get("_geometry_source")
                    if baseline_geometry is not None
                    else None
                ),
                "mode": scope_mode,
                "overall": scope_report["overall"],
                "appearance_overall": appearance.get("overall"),
                "exit_code": exit_code_for(report),
                "block_count": len(geometry.get("blocks") or []),
                "metrics": summary,
                "reasons": appearance.get("reasons") or [],
                "goto_budget": appearance.get("goto_budget"),
                "residual_waiver": appearance.get("residual_waiver"),
                "top_crossing_groups": crossing_groups(
                    appearance.get("crossings") or []
                )[:10],
            }
        )
        full_reports.append((geometry, scope_report, report))

    aggregate = {
        "scope_count": len(current_scopes),
        "line_count": totals["line_count"],
        "crossing_events": totals["crossing_events"],
        "crossing_pairs": totals["crossing_pairs"],
        "overlap_events": totals["overlap_events"],
        "through_block_events": totals["through_block_events"],
        "diagonal_segments": totals["diagonal_segments"],
        "goto_from_blocks": totals["goto_from_blocks"],
        "goto_from_pairs": totals["goto_from_pairs"],
        "total_bends": totals["total_bends"],
        "total_length": round(totals["total_length_milli_units"] / 1000, 3),
        "max_bends": max_bends,
    }

    failed_scope_count = sum(
        item["appearance_overall"] != "PASS" for item in per_scope
    )
    schema_errors_in_scopes = [
        error
        for _, scope_report, _ in full_reports
        for error in scope_report.get("schema_errors") or []
    ]
    if errors or schema_errors_in_scopes:
        overall = "INVALID"
    elif any(
        item["overall"] == "NON_COMPLIANT"
        or item["appearance_overall"] == "FAIL"
        for item in per_scope
    ):
        overall = "NON_COMPLIANT"
    elif any(item["overall"] == "INCOMPLETE" for item in per_scope):
        overall = "INCOMPLETE"
    elif any(item["overall"] == "MANUAL_REVIEW_REQUIRED" for item in per_scope):
        overall = "MANUAL_REVIEW_REQUIRED"
    else:
        overall = "COMPLIANT"

    if errors or schema_errors_in_scopes or any(
        item["appearance_overall"] == "INVALID" for item in per_scope
    ):
        appearance_overall = "INVALID"
    elif any(item["appearance_overall"] == "FAIL" for item in per_scope):
        appearance_overall = "FAIL"
    else:
        appearance_overall = "PASS"

    hotspots = [
        item
        for item in per_scope
        if item["appearance_overall"] != "PASS"
    ]
    hotspots.sort(
        key=lambda item: (
            -int(item["metrics"].get("crossing_events", 0)),
            -int(item["metrics"].get("overlap_events", 0)),
            -int(item["metrics"].get("through_block_events", 0)),
            -int(item["metrics"].get("diagonal_segments", 0)),
            item["scope"],
        )
    )
    for item in hotspots:
        metrics = item["metrics"]
        actions = []
        if metrics.get("crossing_events", 0):
            actions.append("按 top_crossing_groups 调整端口顺序、块分组或专用走廊")
        if metrics.get("overlap_events", 0):
            actions.append("分开共线线段，禁止用 Line Hop 代替")
        if metrics.get("through_block_events", 0):
            actions.append("重新走线，使线段绕开块")
        if metrics.get("diagonal_segments", 0):
            actions.append("改为水平/垂直正交走线")
        if metrics.get("goto_from_blocks", 0):
            actions.append(
                "Goto/From 受 goto_from_policy 管辖：核对预算、配对、local 可见性、"
                "Inport 直连禁令与交叉裁决证据；超限即收敛"
            )
        item["next_actions"] = actions

    baseline_scope_set = set(baseline_scopes)
    current_scope_set = set(current_scopes)
    result = {
        "schema_version": MODEL_REPORT_SCHEMA_VERSION,
        "source_manifest": str(Path(manifest_source).resolve()),
        "baseline_manifest": (
            str(Path(baseline_manifest_source).resolve())
            if baseline_manifest_source is not None
            else None
        ),
        "standard": TARGET_STANDARD,
        "matlab_version": "R2025b",
        "model": model,
        "mode": mode,
        "overall": overall,
        "schema_errors": [*errors, *schema_errors_in_scopes],
        "appearance_quality": {
            "policy_id": (
                profile.get("appearance_quality", {}).get("policy_id")
                if isinstance(profile.get("appearance_quality"), dict)
                else None
            ),
            "overall": appearance_overall,
            "summary": aggregate,
            "failed_scope_count": failed_scope_count,
            "hotspots": hotspots,
            "repair_order": [item["scope"] for item in hotspots],
            "reasons": (
                []
                if appearance_overall == "PASS"
                else [
                    f"appearance quality failed in {failed_scope_count} scope(s); "
                    "repair in hotspots order"
                ]
            ),
            "visual_review": {
                "required": True,
                "authority": "current-scope render_check PNG",
                "status": "not evaluated by geometry linter",
            },
        },
        "per_scope": per_scope,
        "coverage": {
            "all_hierarchy": True,
            "exported_scope_count": len(current_scopes),
            "expected_scope_count": (
                manifest.get("scope_count") if isinstance(manifest, dict) else None
            ),
            "baseline_scope_count": len(baseline_scopes),
            "new_scopes": sorted(current_scope_set - baseline_scope_set),
            "removed_scopes": sorted(baseline_scope_set - current_scope_set),
            "coordinate_frames": "scope-local",
            "line_length_units": "Simulink geometry coordinate units",
        },
    }
    # Full per-scope reports are emitted by the CLI when --out is supplied.
    result["_full_reports"] = full_reports
    return result


def model_exit_code_for(result: dict[str, Any]) -> int:
    """Map a model-level report to the same fail-closed CLI status convention."""
    if result.get("overall") == "INVALID":
        return 2
    if (
        result.get("overall") == "NON_COMPLIANT"
        or result.get("appearance_quality", {}).get("overall") == "FAIL"
    ):
        return 1
    if result.get("overall") == "INCOMPLETE":
        return 2
    return 0


def write_json_file(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def exit_code_for(report: Report) -> int:
    """Map a completed lint report to the documented fail-closed CLI status."""
    appearance = report.appearance_quality
    if report.schema_errors or appearance.get("overall") == "INVALID":
        return 2
    if report.overall() == "NON_COMPLIANT" or appearance.get("overall") == "FAIL":
        return 1
    if any(item["status"] == "UNVERIFIABLE" for item in report.items):
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed target modeling guideline v5 Simulink geometry linter "
            "for one scope or an all-scope manifest"
        )
    )
    parser.add_argument(
        "geometry",
        nargs="?",
        type=Path,
        help="one exported scope geometry JSON",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="manifest.json from export_all_geometry.m",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "assets"
        / "layout-profile.json",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help=(
            "geometry mode: same-scope baseline JSON; "
            "manifest mode: baseline manifest.json"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("new", "existing"),
        help="default: existing when --baseline is supplied, otherwise new",
    )
    parser.add_argument(
        "--goto-justification",
        type=Path,
        help=(
            "Goto/From 交叉裁决与残留豁免证据 JSON"
            "（schema maab.goto_justification/v1）"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write the lint report JSON; manifest mode also writes per-scope reports",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if bool(args.geometry) == bool(args.manifest):
        parser.error("provide exactly one of geometry or --manifest")

    try:
        profile = (
            json.loads(args.profile.read_text(encoding="utf-8"))
            if args.profile.exists()
            else {}
        )
    except (OSError, json.JSONDecodeError) as exc:
        result = Report(str(args.geometry or args.manifest))
        result.schema_errors.append(f"cannot load geometry/profile: {exc}")
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 2

    goto_justification = None
    if args.goto_justification is not None:
        justification_error = None
        try:
            loaded_justification = json.loads(
                args.goto_justification.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            loaded_justification = None
            justification_error = f"cannot load goto justification: {exc}"
        if justification_error is None:
            if not isinstance(loaded_justification, dict):
                justification_error = "goto justification 必须是 JSON 对象"
            elif (
                loaded_justification.get("schema_version")
                != GOTO_JUSTIFICATION_SCHEMA
            ):
                justification_error = (
                    "goto justification schema_version 必须为 "
                    + GOTO_JUSTIFICATION_SCHEMA
                )
            elif not isinstance(loaded_justification.get("scopes"), list) or not all(
                isinstance(entry, dict) and entry.get("scope")
                for entry in loaded_justification["scopes"]
            ):
                justification_error = (
                    "goto justification scopes 必须是含 scope 字段的对象数组"
                )
        if justification_error is not None:
            result = Report(str(args.geometry or args.manifest))
            result.schema_errors.append(justification_error)
            print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
            return 2
        goto_justification = loaded_justification

    if args.manifest is not None:
        try:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            baseline_manifest = (
                json.loads(args.baseline.read_text(encoding="utf-8"))
                if args.baseline is not None
                else None
            )
        except (OSError, json.JSONDecodeError) as exc:
            result = {
                "schema_version": MODEL_REPORT_SCHEMA_VERSION,
                "source_manifest": str(args.manifest.resolve()),
                "standard": TARGET_STANDARD,
                "matlab_version": "R2025b",
                "model": "",
                "mode": args.mode or ("existing" if args.baseline else "new"),
                "overall": "INVALID",
                "schema_errors": [f"cannot load manifest/profile: {exc}"],
                "appearance_quality": {
                    "policy_id": None,
                    "overall": "INVALID",
                    "summary": {},
                    "failed_scope_count": 0,
                    "hotspots": [],
                    "repair_order": [],
                    "reasons": ["manifest did not load"],
                },
                "per_scope": [],
                "coverage": {},
            }
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"INVALID: {args.manifest}: {exc}")
            return 2

        result = evaluate_manifest(
            manifest,
            str(args.manifest),
            profile,
            baseline_manifest=baseline_manifest,
            baseline_manifest_source=(
                str(args.baseline) if args.baseline is not None else None
            ),
            requested_mode=args.mode,
            goto_justification=goto_justification,
        )
        full_reports = result.pop("_full_reports", [])
        report_paths: dict[str, str] = {}
        if args.out is not None:
            out_path = args.out.resolve()
            scope_dir = out_path.parent / f"{out_path.stem}.scopes"
            for index, (_, scope_report, _) in enumerate(full_reports, start=1):
                scope_path = scope_dir / f"scope_{index:03d}.lint.json"
                write_json_file(scope_path, scope_report)
                report_paths[str(scope_report.get("source_geometry"))] = str(
                    scope_path
                )
            for item in result["per_scope"]:
                item["lint_report"] = report_paths.get(item["geometry_file"])
            write_json_file(out_path, result)
        elif not args.json:
            for item in result["per_scope"]:
                item["lint_report"] = None

        appearance = result.get("appearance_quality") or {}
        summary = appearance.get("summary") or {}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                f"{result.get('overall')}: {args.manifest} | "
                f"appearance={appearance.get('overall')} | "
                f"scopes={summary.get('scope_count', 0)} | "
                f"lines={summary.get('line_count', 0)} | "
                f"bends={summary.get('total_bends', 0)} | "
                f"length={summary.get('total_length', 0)} coordinate units | "
                f"crossings={summary.get('crossing_events', 0)} | "
                f"overlaps={summary.get('overlap_events', 0)} | "
                f"through_blocks={summary.get('through_block_events', 0)} | "
                f"goto_pairs={summary.get('goto_from_pairs', 0)}"
            )
            for error in result.get("schema_errors") or []:
                print(f"[SCHEMA] {error}")
            for item in appearance.get("hotspots") or []:
                metrics = item.get("metrics") or {}
                print(
                    f"[FAIL][{item['scope']}] "
                    f"crossings={metrics.get('crossing_events', 0)} "
                    f"overlaps={metrics.get('overlap_events', 0)} "
                    f"through_blocks={metrics.get('through_block_events', 0)} "
                    f"bends={metrics.get('total_bends', 0)}"
                )
                for action in item.get("next_actions") or []:
                    print(f"    处理: {action}")
                if item.get("lint_report"):
                    print(f"    lint: {item['lint_report']}")
            if args.out is not None:
                print(f"model lint report: {args.out.resolve()}")
        return model_exit_code_for(result)

    try:
        geometry = json.loads(args.geometry.read_text(encoding="utf-8"))
        baseline_geo = (
            json.loads(args.baseline.read_text(encoding="utf-8"))
            if args.baseline is not None
            else None
        )
    except (OSError, json.JSONDecodeError) as exc:
        result = Report(str(args.geometry))
        result.schema_errors.append(f"cannot load geometry: {exc}")
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 2

    mode = args.mode or ("existing" if baseline_geo is not None else "new")
    scope_justification = None
    if goto_justification is not None:
        scope_name = str(geometry.get("scope", "")).rstrip("/")
        for entry in goto_justification.get("scopes") or []:
            if str(entry.get("scope", "")).rstrip("/") == scope_name:
                scope_justification = entry
                break
    result = lint(
        geometry,
        profile,
        str(args.geometry),
        mode=mode,
        baseline_geo=baseline_geo,
        baseline_source=str(args.baseline) if args.baseline is not None else None,
        goto_justification=scope_justification,
    )
    result_dict = result.as_dict()
    if args.out is not None:
        write_json_file(args.out.resolve(), result_dict)
    appearance = result.appearance_quality
    if args.json:
        print(json.dumps(result_dict, ensure_ascii=False, indent=2))
    else:
        print(
            f"{result.overall()}: {args.geometry} | "
            + " | ".join(
                f"{profile}={dict(counts)}"
                for profile, counts in result.profile_summary().items()
            )
        )
        appearance_summary = appearance.get("summary") or {}
        print(
            f"APPEARANCE {appearance.get('overall', 'INVALID')}: "
            f"crossings={appearance_summary.get('crossing_events', '?')}, "
            f"overlaps={appearance_summary.get('overlap_events', '?')}, "
            f"through_blocks={appearance_summary.get('through_block_events', '?')}, "
            f"diagonals={appearance_summary.get('diagonal_segments', '?')}, "
            f"goto_from={appearance_summary.get('goto_from_blocks', '?')}"
        )
        goto_budget_info = appearance.get("goto_budget") or {}
        if goto_budget_info:
            print(
                "GOTO BUDGET: "
                f"used={goto_budget_info.get('used_pairs', 0)}/"
                f"{goto_budget_info.get('allowed_pairs', 0)} pairs "
                f"(functional_blocks={goto_budget_info.get('functional_blocks', 0)})"
            )
        waiver_info = appearance.get("residual_waiver") or {}
        if waiver_info.get("status") == "granted":
            print(
                "RESIDUAL WAIVER: granted "
                f"(crossings={waiver_info.get('crossing_events')}, "
                f"lines={waiver_info.get('involved_lines')})；"
                "须逐张 PNG 复核并在交付报告列出残留线对"
            )
        conversion_candidates = appearance.get("goto_conversion_candidates") or []
        if conversion_candidates:
            print(
                f"GOTO CANDIDATES: {len(conversion_candidates)} 条"
                "（按交叉数/线长排序，须先穷尽几何手段再裁决转换）"
            )
            for candidate in conversion_candidates[:5]:
                print(
                    f"    {candidate.get('line')}: "
                    f"crossings={candidate.get('crossing_events')} "
                    f"length={candidate.get('length')} "
                    f"{candidate.get('src_block')} -> {candidate.get('dst_block')}"
                )
        for reason in appearance.get("reasons") or []:
            print(f"    {reason}")
        for error in result.schema_errors:
            print(f"[SCHEMA] {error}")
        for item in result.items:
            if item["status"] == "COMPLIANT":
                continue
            print(f"[{item['status']}][{item['rule']}] {item['where']}")
            print(f"    {item['fact']}")
            if item["fix"]:
                print(f"    处理: {item['fix']}")
        manual_count = sum(item["status"] == "MANUAL" for item in result.items)
        blocking_unknown = any(
            item["status"] == "UNVERIFIABLE" for item in result.items
        )
        if (
            not result.schema_errors
            and not blocking_unknown
            and not any(item["status"] == "VIOLATION" for item in result.items)
            and appearance.get("overall") == "PASS"
        ):
            if manual_count:
                print(
                    f"GEOMETRY PASS: 自动门禁通过，仍有 {manual_count} 个 MANUAL 项；"
                    "必须逐张检查当前 scope PNG 后才能交付，不代表第 3 章全量合规。"
                )
            else:
                print(
                    "PASS: lint 覆盖项与项目外观几何门禁均通过；"
                    "当前 scope PNG 仍不代表第 3 章全量合规。"
                )
        if args.out is not None:
            print(f"scope lint report: {args.out.resolve()}")
    return exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
