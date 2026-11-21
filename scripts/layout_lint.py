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
TARGET_STANDARD = "TARGET_MODELING_GUIDELINE_V5"
TOL = 1.0

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

    def not_applicable(self, rule: str, where: str, fact: str) -> None:
        self.add(rule, "NOT_APPLICABLE", where, fact)

    def overall(self) -> str:
        if self.schema_errors:
            return "INVALID"
        if any(item["status"] == "VIOLATION" for item in self.items):
            return "NON_COMPLIANT"
        if any(item["status"] == "UNVERIFIABLE" for item in self.items):
            return "INCOMPLETE"
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
            "coverage": {
                "full_chapter_audit": False,
                "label_geometry": "estimated (font-size based); confirm with render_check.m PNGs",
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
    normalized = "".join(ch for ch in str(item["value"]).lower() if ch.isalnum())
    return normalized in {"hop", "linehop", "true", "1", "on"}, str(item["value"])


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
        report.unknown(
            "db_0097-a",
            scope,
            "项目 profile 未提供 signal_name 字号，无法估算标签包围盒",
            "补充 profile.font.signal_name.size 并重跑；或用 render_check 渲染复核",
        )
        report.unknown(
            "db_0097-b",
            scope,
            "无法估算标签位置",
            "用 render_check 渲染复核标签是否位于线下方",
        )
        report.unknown(
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
        report.unknown(
            "db_0097-b",
            scope,
            "存在估算违规，标签方位须与 a 项一并人工复核",
            "用 render_check 渲染复核标签是否位于线下方",
        )
        report.unknown(
            "db_0097-c",
            scope,
            "存在估算违规，标签位置须与 a 项一并人工复核",
            "用 render_check 渲染复核标签是否位于连接起点",
        )
    else:
        report.unknown(
            "db_0097-a",
            scope,
            "估算未发现重叠，但 R2025b API 不提供标签实际包围盒",
            "用 render_check 渲染截图复核后签核；估算不等于实测",
        )
        report.unknown(
            "db_0097-b",
            scope,
            "标签是否位于线下方无法由 API 证明",
            "用 render_check 渲染复核",
        )
        report.unknown(
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


def lint(geo: dict[str, Any], profile: dict[str, Any], source: str) -> Report:
    report = Report(source)
    if not validate_geometry(geo, report):
        return report

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
            }
        )
    feedback = cycle_edges(raw_lines)

    # jm_0002 has no numeric target-standard threshold.
    report.unknown(
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
    diagonal_count = 0
    for line in raw_lines:
        for segment in line["segs"]:
            if not (is_horizontal(segment) or is_vertical(segment)):
                diagonal_count += 1
                report.violation(
                    "db_0032-e",
                    line["id"],
                    f"斜线段 {segment[0]} -> {segment[1]}",
                    "改为水平/垂直正交走线",
                )
    if not diagonal_count:
        report.mark("db_0032-e", str(geo["scope"]), "所有导出的线段正交")

    cross_points = []
    overlaps = []
    for i, first in enumerate(raw_lines):
        for second in raw_lines[i + 1:]:
            same_source = (
                first.get("src_block") == second.get("src_block")
                and first.get("src_port") == second.get("src_port")
            )
            for segment_a in first["segs"]:
                for segment_b in second["segs"]:
                    point = crossing(segment_a, segment_b)
                    if point:
                        cross_points.append((first, second, point))
                    point = overlap(segment_a, segment_b)
                    if point and not same_source:
                        overlaps.append((first, second, point))
    if overlaps:
        for first, second, point in overlaps:
            report.violation(
                "db_0032-b",
                f"{first['id']} × {second['id']}",
                f"线在 {point} 附近重叠",
                "分开走线，避免不同信号线共线",
            )
    else:
        report.mark("db_0032-b", str(geo["scope"]), "未发现不同信号线共线重叠")

    if cross_points:
        hop_observed, hop_value = line_crossing_setting(geo)
        for first, second, point in cross_points:
            where = f"{first['id']} × {second['id']} @ {point}"
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
                    f"交叉存在，但无法读取实际 line setting：{hop_value or 'unknown'}",
                    "读取实际 R2025b 设置；不可用 profile 冒充模型设置",
                )
                report.unknown(
                    "db_0032-a2",
                    where,
                    f"交叉存在，实际 line setting={hop_value or 'unknown'}",
                    "读取并记录实际 line crossing style",
                )
    else:
        report.mark("db_0032-a1", str(geo["scope"]), "未发现线交叉")
        report.not_applicable("db_0032-a2", str(geo["scope"]), "没有必须交叉的位置")

    through_block = False
    for line in raw_lines:
        endpoints = {line.get("src_block"), line.get("dst_block")}
        for segment in line["segs"]:
            for path, value in block_rects.items():
                if path in endpoints:
                    continue
                if hits_interior(segment, value):
                    through_block = True
                    report.violation(
                        "db_0032-c",
                        line["id"],
                        f"线段穿过块 {path}",
                        "重排块或线路，使信号线绕开块",
                    )
    if not through_block:
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
                "建立分支树、Goto/From 或显式接口；Mux 不能复制标量",
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
        f"{line['id']}={max(0, len(line['segs']) - 1)}" for line in raw_lines
    )
    project_note = (
        f"；project max={max_bends} 仅作为项目阈值，不是目标规范数值"
        if max_bends is not None
        else "；项目未定义可执行阈值"
    )
    report.unknown(
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

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed target modeling guideline v5 Simulink geometry linter"
    )
    parser.add_argument("geometry", type=Path)
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "assets"
        / "layout-profile.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        geometry = json.loads(args.geometry.read_text(encoding="utf-8"))
        profile = (
            json.loads(args.profile.read_text(encoding="utf-8"))
            if args.profile.exists()
            else {}
        )
    except (OSError, json.JSONDecodeError) as exc:
        result = Report(str(args.geometry))
        result.schema_errors.append(f"cannot load geometry/profile: {exc}")
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 2
    result = lint(geometry, profile, str(args.geometry))
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            f"{result.overall()}: {args.geometry} | "
            + " | ".join(
                f"{profile}={dict(counts)}"
                for profile, counts in result.profile_summary().items()
            )
        )
        for error in result.schema_errors:
            print(f"[SCHEMA] {error}")
        for item in result.items:
            if item["status"] == "COMPLIANT":
                continue
            print(f"[{item['status']}][{item['rule']}] {item['where']}")
            print(f"    {item['fact']}")
            if item["fix"]:
                print(f"    处理: {item['fix']}")
        if not result.schema_errors and all(
            item["status"] == "COMPLIANT" for item in result.items
        ):
            print("PASS: 本 lint 覆盖项均符合；这不代表第 3 章全量合规。")
    if result.overall() == "COMPLIANT":
        return 0
    return 1 if result.overall() == "NON_COMPLIANT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
