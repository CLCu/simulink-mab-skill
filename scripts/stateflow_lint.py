#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fail-closed target modeling guideline v5 checks for exported R2025b Stateflow geometry."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "maab.stateflow_geometry/v1"
TARGET_STANDARD = "TARGET_MODELING_GUIDELINE_V5"
TOL = 1.0
DEVIATIONS_FILE = (
    Path(__file__).resolve().parent.parent / "assets" / "project-deviations.json"
)


def load_project_deviations() -> list[dict[str, Any]]:
    """Load the single authoritative project-deviation register."""
    with DEVIATIONS_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("standard") != TARGET_STANDARD:
        raise SystemExit("project deviations must use the target modeling guideline v5 baseline")
    if data.get("profiles") != ["NA-MAAB", "JMAAB"]:
        raise SystemExit("project deviations must target NA-MAAB and JMAAB")
    items = data.get("items")
    if not isinstance(items, list):
        raise SystemExit("project deviations must contain an items array")
    for item in items:
        if not item.get("rule") or item.get("decision") != "MANUAL":
            raise SystemExit("each project deviation must be a MANUAL rule item")
        if not item.get("close_condition"):
            raise SystemExit("each project deviation requires a close condition")
    return items


PROJECT_DEVIATIONS = load_project_deviations()

RULES = {
    "db_0129-a": ("a", "a", "转移线不得相互交叉"),
    "db_0129-b": ("b", "b", "转移线不得相互重叠"),
    "db_0129-c": ("c", "c", "转移线不得穿过状态"),
    "db_0129-d": ("d", "d", "转移线水平或垂直；flow chart 例外"),
    "db_0129-e": ("e", "e", "不得有冗余 junction"),
    "jc_0531-a": ("a", "a", "默认转移位于 OR 层级顶部/状态正下方"),
    "jc_0531-b": ("b", "b", "Parallel 层级不得有默认转移"),
    "jc_0531-c": ("c", "c", "同一层不得有多条默认转移"),
    "jc_0531-d": ("d", "d", "默认转移直接且纵向接至目标上部"),
    "jc_0531-e": ("e", "e", "默认转移目标位于同层左上"),
    "jc_0531-f": ("f", "f", "默认转移不得越出状态边界"),
    "jc_0531-g": ("g", "g", "No unconditional default transitions 应为 Error"),
    "db_0137-a": ("a", "a", "OR 层级至少有两个状态"),
    "jc_0721-a": ("a", "a", "并行状态的子状态不得再为并行"),
    "jc_0797-a": ("a", "a", "不得有未连接转移"),
    "jc_0797-b": ("b", "b", "OR 状态和 junction 必须有转移来源"),
    "jc_0760-a": ("a", "a", "内部转移从左边缘出发"),
    "jc_0736-a": (None, "a", "状态动作类型与可执行语句的缩进"),
    "jc_0736-b": (None, "b", "转移标签中 [ { / 前无空格"),
    "jc_0736-c": (None, "c", "转移动作 / 后至少一个半角空格"),
    "jc_0501-a": ("a", "a", "动作语句不得与动作类型同行"),
    "jc_0731-a": ("a", "a", "状态名后换行且该行不含 /"),
    "jc_0739-a": ("a", "a", "状态内文字不得越出状态边界"),
    "jc_0770-a1": (None, "a1", "转移标签位于起点"),
    "jc_0770-a2": (None, "a2", "转移标签位于转移线中部"),
    "jc_0730-a": ("a", "a", "同一 Chart 状态名唯一"),
    "jc_0732-a": ("a", "a", "状态、数据和事件名不得冲突"),
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
        na, jmaab, text = RULES[rule]
        self.items.append(
            {
                "rule": rule,
                "sub_id": {"na_maab": na, "jmaab": jmaab},
                "rule_text": text,
                "status": status,
                "where": where,
                "fact": fact,
                "fix": fix,
                "evidence": evidence,
            }
        )

    def mark(self, rule: str, where: str, fact: str) -> None:
        self.add(rule, "COMPLIANT", where, fact)

    def violation(self, rule: str, where: str, fact: str, fix: str) -> None:
        self.add(rule, "VIOLATION", where, fact, fix)

    def unknown(self, rule: str, where: str, fact: str, fix: str = "") -> None:
        self.add(rule, "UNVERIFIABLE", where, fact, fix)

    def manual(self, rule: str, where: str, fact: str, fix: str = "") -> None:
        """项目偏离项：照常报告，但不计入自动门禁。"""
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
        result = {}
        for profile, key in (("NA-MAAB", "na_maab"), ("JMAAB", "jmaab")):
            counts: Counter[str] = Counter()
            for item in self.items:
                if item["sub_id"][key] is not None:
                    counts[item["status"]] += 1
            result[profile] = dict(sorted(counts.items()))
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "maab.stateflow_lint_report/v1",
            "source_geometry": self.source,
            "standard": TARGET_STANDARD,
            "matlab_version": "R2025b",
            "overall": self.overall(),
            "schema_errors": self.schema_errors,
            "profile_summary": self.profile_summary(),
            "project_deviations": PROJECT_DEVIATIONS,
            "items": self.items,
            "coverage": {
                "full_chapter_audit": False,
                "checked_rules": sorted({item["rule"].split("-")[0] for item in self.items}),
                "note": (
                    "This lint covers API-verifiable Stateflow layout/label rules. "
                    "Inspect the final Chart PNG and layout-stateflow.md for the "
                    "visual and readability subset."
                ),
            },
        }


def point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def rect(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def transition_points(item: dict[str, Any]) -> list[tuple[float, float]]:
    source = point(item.get("source_endpoint"))
    destination = point(item.get("destination_endpoint"))
    midpoints = []
    raw_midpoints = item.get("midpoints")
    if isinstance(raw_midpoints, list):
        for raw in raw_midpoints:
            value = point(raw)
            if value:
                midpoints.append(value)
    result = []
    if source:
        result.append(source)
    result.extend(midpoints)
    if destination:
        result.append(destination)
    return result


def segments(points: list[tuple[float, float]]):
    return list(zip(points, points[1:]))


def is_horizontal(segment) -> bool:
    return abs(segment[0][1] - segment[1][1]) <= TOL


def is_vertical(segment) -> bool:
    return abs(segment[0][0] - segment[1][0]) <= TOL


def crossing(first, second) -> tuple[float, float] | None:
    if is_horizontal(first) and is_vertical(second):
        x, y = second[0][0], first[0][1]
        a0, a1 = sorted((first[0][0], first[1][0]))
        b0, b1 = sorted((second[0][1], second[1][1]))
        if a0 + TOL < x < a1 - TOL and b0 + TOL < y < b1 - TOL:
            return x, y
    if is_vertical(first) and is_horizontal(second):
        return crossing(second, first)
    return None


def overlap(first, second) -> tuple[float, float] | None:
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


def hits_rect(segment, value: tuple[float, float, float, float], margin=2.0) -> bool:
    x0, y0, x1, y1 = (
        value[0] + margin,
        value[1] + margin,
        value[2] - margin,
        value[3] - margin,
    )
    if is_horizontal(segment):
        y = segment[0][1]
        low, high = sorted((segment[0][0], segment[1][0]))
        return y0 < y < y1 and high > x0 and low < x1
    if is_vertical(segment):
        x = segment[0][0]
        low, high = sorted((segment[0][1], segment[1][1]))
        return x0 < x < x1 and high > y0 and low < y1
    return False


def distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def transition_delimiters(label: str) -> dict[str, int | None]:
    result: dict[str, int | None] = {"[": None, "{": None, "/": None}
    square = 0
    curly = 0
    in_line_comment = False
    in_block_comment = False
    quote = None
    index = 0
    while index < len(label):
        if in_line_comment:
            if label[index] == "\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            if label[index:index + 2] == "*/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if label[index:index + 2] == "//":
            in_line_comment = True
            index += 2
            continue
        if label[index:index + 2] == "/*":
            in_block_comment = True
            index += 2
            continue
        char = label[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "[":
            if square == 0 and result["["] is None:
                result["["] = index
            square += 1
        elif char == "]":
            square = max(0, square - 1)
        elif char == "{":
            if curly == 0 and result["{"] is None:
                result["{"] = index
            curly += 1
        elif char == "}":
            curly = max(0, curly - 1)
        elif char == "/" and square == 0 and curly == 0:
            result["/"] = index
            return result
        index += 1
    return result


def validate(geo: Any, report: Report) -> bool:
    if not isinstance(geo, dict):
        report.schema_errors.append("geometry root must be an object")
        return False
    for key in (
        "schema_version",
        "standard",
        "matlab_version",
        "chart",
        "states",
        "transitions",
        "junctions",
        "data",
        "events",
        "settings",
        "coverage",
    ):
        if key not in geo:
            report.schema_errors.append(f"missing top-level field: {key}")
    if report.schema_errors:
        return False
    if geo["schema_version"] != SCHEMA_VERSION:
        report.schema_errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if geo["standard"] != TARGET_STANDARD:
        report.schema_errors.append(f"standard must be {TARGET_STANDARD}")
    if str(geo["matlab_version"]).lower() not in {"r2025b", "2025b"}:
        report.schema_errors.append("matlab_version must be R2025b")
    chart = geo.get("chart")
    if not isinstance(chart, dict) or not chart.get("id"):
        report.schema_errors.append("chart must be an object with id")
    collections = {}
    for name in ("states", "transitions", "junctions", "data", "events"):
        values = geo.get(name)
        if not isinstance(values, list):
            report.schema_errors.append(f"{name} must be an array")
            continue
        ids = set()
        for index, item in enumerate(values):
            if not isinstance(item, dict) or not item.get("id"):
                report.schema_errors.append(f"{name}[{index}] must have id")
                continue
            if item["id"] in ids:
                report.schema_errors.append(f"duplicate id in {name}: {item['id']}")
            ids.add(item["id"])
        collections[name] = values
    if report.schema_errors:
        return False
    object_ids = {chart["id"]} | {
        item["id"]
        for name in ("states", "junctions")
        for item in collections[name]
    }
    for state in collections["states"]:
        if state.get("parent_id") and state["parent_id"] not in object_ids:
            report.schema_errors.append(
                f"state {state['id']} has unknown parent {state['parent_id']}"
            )
    for transition in collections["transitions"]:
        for side in ("source", "destination"):
            kind = transition.get(side + "_kind")
            object_id = transition.get(side + "_id")
            if kind not in (None, "", "none") and object_id not in object_ids:
                report.schema_errors.append(
                    f"transition {transition['id']} {side} object "
                    f"{object_id!r} is unknown"
                )
    return not report.schema_errors


def ancestors(identifier: str, object_map: dict[str, dict]) -> set[str]:
    result = set()
    current = identifier
    for _ in range(64):
        item = object_map.get(current)
        if not item:
            break
        parent = item.get("parent_id")
        if not parent:
            break
        result.add(parent)
        current = parent
    return result


def check_state_labels(states, report):
    state_label_checked = defaultdict(bool)
    action_indent_bad = []
    transition_action_bad = []
    transition_prefix_bad = []
    for state in states:
        label = str(state.get("label") or "")
        where = f"{state.get('name') or state['id']} ({state['id']})"
        if not label:
            report.unknown("jc_0731-a", where, "状态 label 未导出")
            report.unknown("jc_0501-a", where, "状态 label 未导出")
            continue
        lines = label.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        first = lines[0].strip()
        if "/" in first:
            report.violation(
                "jc_0731-a",
                where,
                "状态名后的第一行包含斜杠 /",
                "第一行仅保留状态名，动作从下一行开始",
            )
        elif re.match(
            r"^(?:entry|during|exit|en|du|ex)\s*:",
            first,
            flags=re.IGNORECASE,
        ):
            report.violation(
                "jc_0731-a",
                where,
                "状态名与动作类型写在同一行",
                "状态名单独占第一行",
            )
        else:
            report.mark("jc_0731-a", where, "状态名位于第一行且不含 /")

        action_any = False
        for line in lines:
            match = re.match(
                r"^(\s*)(entry|during|exit|en|du|ex)\s*:(.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            action_any = True
            tail = match.group(3).strip()
            if tail and not tail.startswith(("//", "/*", "%")):
                report.violation(
                    "jc_0501-a",
                    where,
                    f"动作语句与 {match.group(2)}: 同行",
                    "动作类型后立即换行，语句写在下一行",
                )
        if action_any:
            state_label_checked[state["id"]] = True
        else:
            report.not_applicable("jc_0501-a", where, "该状态没有状态动作类型")

        for index, line in enumerate(lines):
            action = re.match(
                r"^(\s*)(entry|during|exit|en|du|ex)\s*:\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if action and action.group(1):
                action_indent_bad.append((where, index + 1, action.group(1)))
        for index in range(len(lines) - 1):
            if re.match(
                r"^(?:entry|during|exit|en|du|ex)\s*:\s*$",
                lines[index],
                flags=re.IGNORECASE,
            ):
                j = index + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and not re.match(
                    r"^(?:entry|during|exit|en|du|ex)\s*:",
                    lines[j],
                    flags=re.IGNORECASE,
                ):
                    statement = lines[j]
                    if not re.match(r"^ [^ \t]", statement):
                        action_indent_bad.append(
                            (where, j + 1, repr(statement[: max(2, len(statement))]))
                        )
    if action_indent_bad:
        for where, line_no, value in action_indent_bad:
            report.violation(
                "jc_0736-a",
                f"{where} line {line_no}",
                f"动作类型不得有前导空格；可执行语句须恰以一个半角空格开头（实际 {value}）",
                "统一使用一个单字节空格缩进语句",
            )
    else:
        report.mark("jc_0736-a", str(report.source), "状态动作缩进可验证且符合")

    for transition in report._transitions:  # populated before label check
        label = str(transition.get("label") or "")
        if not label:
            continue
        where = transition["id"]
        delimiters = transition_delimiters(label)
        for token in ("[", "{", "/"):
            position = delimiters[token]
            if position is not None and position > 0 and label[position - 1] in " \t":
                start = position - 1
                while start > 0 and label[start - 1] in " \t":
                    start -= 1
                transition_prefix_bad.append(
                    (where, token, repr(label[start:position + 1]))
                )
        slash = delimiters["/"]
        if slash is not None:
            after = label[slash + 1:slash + 2]
            if after != " ":
                transition_action_bad.append((where, repr(after)))
    if transition_prefix_bad:
        for where, token, found in transition_prefix_bad:
            report.violation(
                "jc_0736-b",
                where,
                f"{token} 前有空白：{found!r}",
                "移除 [、{、/ 前的空格",
            )
    else:
        report.mark("jc_0736-b", str(report.source), "转移标签未发现 [ { / 前空格")
    if transition_action_bad:
        for where, after in transition_action_bad:
            report.violation(
                "jc_0736-c",
                where,
                f"转移动作 / 后不是至少一个半角空格（实际 {after}）",
                "在 / 后加入至少一个单字节空格",
            )
    else:
        report.mark("jc_0736-c", str(report.source), "所有转移动作 / 后均有半角空格")


def lint(geo: dict[str, Any], source: str) -> Report:
    report = Report(source)
    if not validate(geo, report):
        return report
    chart = geo["chart"]
    states = geo["states"]
    transitions = geo["transitions"]
    junctions = geo["junctions"]
    report._transitions = transitions
    state_map = {state["id"]: state for state in states}
    junction_map = {junction["id"]: junction for junction in junctions}
    object_map = {chart["id"]: chart, **state_map, **junction_map}
    state_rect = {identifier: rect(item.get("position")) for identifier, item in state_map.items()}
    junction_center = {
        identifier: point(item.get("center")) for identifier, item in junction_map.items()
    }

    check_state_labels(states, report)

    # Build transition geometry and graph.
    transition_geometry = {}
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for transition in transitions:
        points = transition_points(transition)
        transition_geometry[transition["id"]] = points
        source_id = transition.get("source_id")
        destination_id = transition.get("destination_id")
        if source_id:
            outgoing[source_id].append(transition)
        if destination_id:
            incoming[destination_id].append(transition)

    # db_0129 a-e.
    cross = []
    overlaps = []
    diagonal_bad = []
    diagonal_allowed = 0
    for index, first in enumerate(transitions):
        first_points = transition_geometry[first["id"]]
        first_segments = segments(first_points)
        for segment in first_segments:
            if is_horizontal(segment) or is_vertical(segment):
                continue
            endpoints = {first.get("source_kind"), first.get("destination_kind")}
            if endpoints <= {"junction", "none"}:
                diagonal_allowed += 1
            else:
                diagonal_bad.append((first["id"], segment))
        for second in transitions[index + 1:]:
            second_points = transition_geometry[second["id"]]
            same_source = (
                first.get("source_id")
                and first.get("source_id") == second.get("source_id")
            )
            for segment_a in first_segments:
                for segment_b in segments(second_points):
                    value = crossing(segment_a, segment_b)
                    if value:
                        cross.append((first["id"], second["id"], value))
                    value = overlap(segment_a, segment_b)
                    if value and not same_source:
                        overlaps.append((first["id"], second["id"], value))
    if cross:
        for first, second, value in cross:
            report.violation(
                "db_0129-a",
                f"{first} × {second}",
                f"转移线在 {value} 交叉",
                "重排状态/转移，改写为不交叉路径",
            )
    else:
        report.mark("db_0129-a", str(geo.get("chart_path") or chart.get("name")), "未发现转移交叉")
    if overlaps:
        for first, second, value in overlaps:
            report.violation(
                "db_0129-b",
                f"{first} × {second}",
                f"转移线在 {value} 附近重叠",
                "分离转移线路由",
            )
    else:
        report.mark("db_0129-b", str(geo.get("chart_path") or chart.get("name")), "未发现转移重叠")

    through = []
    for transition in transitions:
        points = transition_geometry[transition["id"]]
        endpoint_states = {
            identifier
            for identifier in (
                transition.get("source_id"),
                transition.get("destination_id"),
            )
            if identifier in state_map
        }
        excluded = set(endpoint_states)
        for identifier in endpoint_states:
            excluded |= ancestors(identifier, object_map)
        for segment in segments(points):
            for state_id, value in state_rect.items():
                if state_id in excluded or not value:
                    continue
                if hits_rect(segment, value):
                    through.append((transition["id"], state_id))
    if through:
        for transition_id, state_id in through:
            report.violation(
                "db_0129-c",
                f"{transition_id} × {state_id}",
                "转移线穿过状态内部",
                "绕行状态或重新布局",
            )
    else:
        report.mark("db_0129-c", str(geo.get("chart_path") or chart.get("name")), "未发现转移穿越状态")

    if diagonal_bad:
        for transition_id, segment in diagonal_bad:
            report.manual(
                "db_0129-d",
                transition_id,
                f"非 flow chart 转移存在斜线段 {segment}（项目偏离项，不计入自动门禁）",
                "在 Stateflow 编辑器中手工拖出直角折点后人工确认",
            )
    elif not transitions:
        report.not_applicable("db_0129-d", str(report.source), "Chart 无转移")
    else:
        report.mark(
            "db_0129-d",
            str(geo.get("chart_path") or chart.get("name")),
            f"非 flow chart 转移均为正交；flow chart 斜线 {diagonal_allowed} 段",
        )

    redundant = []
    for junction in junctions:
        identifier = junction["id"]
        if len(incoming[identifier]) == 1 and len(outgoing[identifier]) == 1:
            redundant.append(identifier)
    if redundant:
        for identifier in redundant:
            report.violation(
                "db_0129-e",
                identifier,
                "junction 仅有一条入转移和一条出转移，可由直接连接替代",
                "删除冗余 junction 并直接连接",
            )
    else:
        report.mark("db_0129-e", str(report.source), "未发现简单一进一出 junction")

    # Parent/level decomposition, default transitions and unconnected states.
    children = defaultdict(list)
    for state in states:
        if state.get("parent_id"):
            children[state["parent_id"]].append(state)
    for junction in junctions:
        if junction.get("parent_id"):
            children[junction["parent_id"]].append(junction)

    defaults_by_parent = defaultdict(list)
    for transition in transitions:
        if not transition.get("is_default"):
            continue
        destination_id = transition.get("destination_id")
        if destination_id in state_map:
            parent = state_map[destination_id].get("parent_id")
        elif destination_id in junction_map:
            parent = junction_map[destination_id].get("parent_id")
        else:
            parent = None
        if parent:
            defaults_by_parent[parent].append(transition)

    parent_ids = [chart["id"]] + list(state_map)
    for parent_id in parent_ids:
        parent = object_map.get(parent_id)
        if not parent:
            continue
        if (
            parent_id != chart["id"]
            and parent.get("is_grouped") is False
        ):
            # R2025b reports EXCLUSIVE_OR for ordinary atomic states too.
            continue
        decomposition = str(parent.get("decomposition") or "").upper()
        defaults = defaults_by_parent[parent_id]
        where = parent_id
        if "PARALLEL" in decomposition or "AND" in decomposition:
            if defaults:
                for transition in defaults:
                    report.violation(
                        "jc_0531-b",
                        transition["id"],
                        f"parent {parent_id} 为 Parallel(AND)，却存在默认转移",
                        "删除 AND 层级的默认转移",
                    )
            else:
                report.mark("jc_0531-b", where, "Parallel(AND) 层级无默认转移")
        if "EXCLUSIVE" in decomposition or decomposition.endswith("OR"):
            if len(defaults) == 0:
                report.unknown(
                    "jc_0531-a",
                    where,
                    "OR 层级未导出默认转移；不能区分缺失与导出遗漏",
                    "重新导出或人工确认默认转移",
                )
            elif len(defaults) > 1:
                report.violation(
                    "jc_0531-c",
                    where,
                    f"同一层有 {len(defaults)} 条默认转移",
                    "每层仅保留一条默认转移",
                )
            else:
                report.mark("jc_0531-c", where, "同一层只有一条默认转移")
                report.mark("jc_0531-a", where, "OR 层级存在默认转移，位置将在下方几何规则核对")
        if len(defaults) <= 1:
            report.mark("jc_0531-c", where, "默认转移数量不超过 1")

    # Default transition geometry and model diagnostics.
    grid = 10.0
    for parent_id, defaults in defaults_by_parent.items():
        parent = object_map.get(parent_id)
        direct_children = children.get(parent_id, [])
        child_rects = []
        for child in direct_children:
            if child["id"] in state_rect and state_rect[child["id"]]:
                child_rects.append((child["id"], state_rect[child["id"]]))
            elif child["id"] in junction_center and junction_center[child["id"]]:
                x, y = junction_center[child["id"]]
                child_rects.append((child["id"], (x, y, x, y)))
        parent_rect = state_rect.get(parent_id) if parent_id in state_rect else None
        for transition in defaults:
            points = transition_geometry[transition["id"]]
            source = points[0] if points else None
            destination_id = transition.get("destination_id")
            destination_rect = (
                state_rect.get(destination_id)
                if destination_id in state_rect
                else None
            )
            if destination_rect is None and destination_id in junction_center:
                x, y = junction_center[destination_id]
                destination_rect = (x, y, x, y)
            if source is None or destination_rect is None:
                report.unknown(
                    "jc_0531-d",
                    transition["id"],
                    "默认转移源/目标几何不完整",
                    "重新导出 SourceEndpoint 或目标几何",
                )
                report.unknown(
                    "jc_0531-f",
                    transition["id"],
                    "默认转移点集不完整",
                    "重新导出完整转移几何",
                )
                continue

            # a: chart top or immediately beneath an OR state.
            if child_rects and parent_id == chart["id"]:
                top = min(value[1] for _, value in child_rects)
                if source[1] <= top + grid + TOL:
                    report.mark("jc_0531-a", transition["id"], "Chart 默认转移位于顶部区域")
                else:
                    report.violation(
                        "jc_0531-a",
                        transition["id"],
                        "Chart 默认转移未位于顶部",
                        "将默认转移移至 Chart 顶部",
                    )
            elif parent_rect:
                if parent_rect[1] - grid <= source[1] <= parent_rect[3] + grid:
                    report.mark("jc_0531-a", transition["id"], "状态默认转移位于父状态内")
                else:
                    report.violation(
                        "jc_0531-a",
                        transition["id"],
                        "状态默认转移未位于父状态正下方",
                        "将默认转移移至父状态内、子元素上方",
                    )
            else:
                report.unknown("jc_0531-a", transition["id"], "父层级边界不可读取")

            # d: vertical and connects to upper part.
            destination_x = (destination_rect[0] + destination_rect[2]) / 2
            vertical = abs(source[0] - destination_x) <= grid + TOL
            upper = source[1] <= destination_rect[1] + grid + TOL
            if vertical and upper:
                report.mark("jc_0531-d", transition["id"], "默认转移直接纵向接至目标上部")
            else:
                report.violation(
                    "jc_0531-d",
                    transition["id"],
                    f"默认转移未纵向接至目标上部：source={source}, target={destination_rect}",
                    "直接垂直连接到目标状态/junction 的上部",
                )

            # e: top-left among same-level children (ambiguous cases stay open).
            if child_rects:
                min_x = min(value[0] for _, value in child_rects)
                min_y = min(value[1] for _, value in child_rects)
                if (
                    destination_rect[0] <= min_x + grid + TOL
                    and destination_rect[1] <= min_y + grid + TOL
                ):
                    report.mark("jc_0531-e", transition["id"], "目标位于同层左上区域")
                else:
                    report.unknown(
                        "jc_0531-e",
                        transition["id"],
                        "目标几何不是明确左上极值；规则语义需人工确认",
                        "R2025b 图面复核默认目标是否为左上布局",
                    )

            # f: inside parent state boundary.
            if parent_rect:
                outside = [
                    value
                    for value in points
                    if not (
                        parent_rect[0] - grid <= value[0] <= parent_rect[2] + grid
                        and parent_rect[1] - grid <= value[1] <= parent_rect[3] + grid
                    )
                ]
                if outside:
                    report.violation(
                        "jc_0531-f",
                        transition["id"],
                        f"默认转移越出父状态边界：{outside}",
                        "将默认转移完全放入父状态内",
                    )
                else:
                    report.mark("jc_0531-f", transition["id"], "默认转移位于父状态边界内")
            else:
                report.unknown(
                    "jc_0531-f",
                    transition["id"],
                    "Chart 没有可直接读取的内部边界",
                    "使用同层元素边界或人工确认",
                )

    setting = (geo.get("settings") or {}).get(
        "no_unconditional_default_transitions", {}
    )
    if setting.get("status") != "observed":
        report.unknown(
            "jc_0531-g",
            str(report.source),
            "未读取 actual SFNoUnconditionalDefaultTransitionDiag",
            "在 R2025b 模型配置中读取该值",
        )
    elif str(setting.get("value", "")).lower() == "error":
        report.mark("jc_0531-g", str(report.source), "No unconditional default transitions=Error")
    else:
        report.violation(
            "jc_0531-g",
            str(report.source),
            f"No unconditional default transitions={setting.get('value')}",
            "将实际模型诊断设置为 Error",
        )

    # OR state count, parallel nesting.
    for parent_id in parent_ids:
        parent = object_map.get(parent_id)
        decomposition = str(parent.get("decomposition") or "").upper()
        if "EXCLUSIVE" not in decomposition and not decomposition.endswith("OR"):
            continue
        if (
            parent_id != chart["id"]
            and parent.get("is_grouped") is False
        ):
            # R2025b reports EXCLUSIVE_OR for ordinary atomic states too.
            # db_0137 is about the hierarchy of a grouped OR state.
            continue
        count = sum(
            child["id"] in state_map for child in children.get(parent_id, [])
        )
        if count < 2:
            report.violation(
                "db_0137-a",
                parent_id,
                f"OR 层级仅有 {count} 个直接状态",
                "OR 状态机至少包含两个状态，或合并该层级",
            )
        else:
            report.mark("db_0137-a", parent_id, f"OR 层级有 {count} 个直接元素")

    for state in states:
        parent_id = state.get("parent_id")
        if parent_id not in state_map:
            continue
        parent = state_map[parent_id]
        if (
            "PARALLEL" in str(parent.get("decomposition") or "").upper()
            and "PARALLEL" in str(state.get("decomposition") or "").upper()
        ):
            report.violation(
                "jc_0721-a",
                state["id"],
                "Parallel 状态的子状态再次使用 Parallel",
                "取消嵌套 Parallel，改用扁平并发结构",
            )
    if not any(item["rule"] == "jc_0721-a" for item in report.items):
        report.mark("jc_0721-a", str(report.source), "未发现嵌套 Parallel 状态")

    # Unconnected/default-source coverage.
    unconnected = False
    for transition in transitions:
        if (
            str(transition.get("source_kind")) == "none"
            and str(transition.get("destination_kind")) == "none"
        ) or (
            str(transition.get("destination_kind")) == "none"
            and not transition.get("is_default")
        ):
            unconnected = True
            report.violation(
                "jc_0797-a",
                transition["id"],
                "转移缺少可连接目标",
                "连接转移两端或删除未连接转移",
            )
        elif not transition_geometry[transition["id"]]:
            report.unknown(
                "jc_0797-a",
                transition["id"],
                "转移端点几何缺失，无法确认完整性",
                "重新导出转移几何",
            )
    if transitions and not unconnected and not any(
        item["rule"] == "jc_0797-a" and item["status"] == "UNVERIFIABLE"
        for item in report.items
    ):
        report.mark("jc_0797-a", str(report.source), "所有转移均导出目标端点")

    missing_source = []
    for state in states:
        decomposition = str(state.get("decomposition") or "").upper()
        if (
            "EXCLUSIVE" in decomposition or decomposition.endswith("OR")
        ) and not incoming[state["id"]]:
            missing_source.append(state["id"])
    for junction in junctions:
        if junction.get("type", "").upper().startswith("CONNECTIVE") and not incoming[junction["id"]]:
            missing_source.append(junction["id"])
    if missing_source:
        for identifier in missing_source:
            report.violation(
                "jc_0797-b",
                identifier,
                "OR 状态或 connective junction 没有转移来源",
                "增加合法入转移或默认转移；本规则不要求每个状态都有出转移",
            )
    else:
        report.mark("jc_0797-b", str(report.source), "OR 状态和 connective junction 均有转移来源")

    # Internal transition begins at the state's left edge.
    internal_checked = False
    for transition in transitions:
        if (
            transition.get("source_kind") != "state"
            or transition.get("source_id") != transition.get("destination_id")
        ):
            continue
        internal_checked = True
        value = state_rect.get(transition.get("source_id"))
        points = transition_geometry[transition["id"]]
        if not value or not points:
            report.unknown(
                "jc_0760-a",
                transition["id"],
                "内部转移或源状态几何缺失",
                "重新导出内部转移 SourceEndpoint",
            )
        elif abs(points[0][0] - value[0]) <= TOL + 1:
            report.mark("jc_0760-a", transition["id"], "内部转移从左边缘开始")
        else:
            report.violation(
                "jc_0760-a",
                transition["id"],
                f"内部转移起点 x={points[0][0]}，状态左边缘 x={value[0]}",
                "将内部转移起点移到状态左边缘",
            )
    if not internal_checked:
        report.not_applicable("jc_0760-a", str(report.source), "无内部转移")

    # Visible text is not available through Stateflow geometry API.
    if states:
        report.unknown(
            "jc_0739-a",
            str(report.source),
            "R2025b API 不提供渲染后的文字包围盒",
            "用实际 Chart 截图人工验证文字未越界；不得使用自创字符宽度阈值判合规",
        )
    else:
        report.not_applicable("jc_0739-a", str(report.source), "Chart 没有状态")

    # Transition label consistency: origin style vs middle style.
    style_votes = []
    ambiguous = False
    for transition in transitions:
        label_position = point(transition.get("label_position"))
        points = transition_geometry[transition["id"]]
        if not transition.get("label") or label_position is None or not points:
            if transition.get("label"):
                ambiguous = True
            continue
        origin = points[0]
        middle = (
            points[len(points) // 2]
            if len(points) % 2
            else (
                (points[len(points) // 2 - 1][0] + points[len(points) // 2][0]) / 2,
                (points[len(points) // 2 - 1][1] + points[len(points) // 2][1]) / 2,
            )
        )
        origin_distance = distance(label_position, origin)
        middle_distance = distance(label_position, middle)
        if abs(origin_distance - middle_distance) <= TOL:
            ambiguous = True
        elif origin_distance < middle_distance:
            style_votes.append("a1")
        else:
            style_votes.append("a2")
    if not style_votes:
        report.unknown(
            "jc_0770-a1",
            str(report.source),
            "没有可判定的非空转移标签位置",
            "人工核对转移标签位置",
        )
        report.unknown(
            "jc_0770-a2",
            str(report.source),
            "没有可判定的非空转移标签位置",
            "人工核对转移标签位置",
        )
    elif len(set(style_votes)) > 1:
        report.violation(
            "jc_0770-a1",
            str(report.source),
            f"同一 Chart 混用标签位置风格：{Counter(style_votes)}",
            "统一选择起点或中部风格",
        )
        report.violation(
            "jc_0770-a2",
            str(report.source),
            f"同一 Chart 混用标签位置风格：{Counter(style_votes)}",
            "统一选择起点或中部风格",
        )
    else:
        chosen = style_votes[0]
        if chosen == "a1":
            report.mark("jc_0770-a1", str(report.source), "所有标签接近转移起点")
            report.not_applicable("jc_0770-a2", str(report.source), "本 Chart 采用 a1")
        else:
            report.not_applicable("jc_0770-a1", str(report.source), "本 Chart 采用 a2")
            report.mark("jc_0770-a2", str(report.source), "所有标签接近转移中部")
        if ambiguous:
            report.unknown(
                f"jc_0770-{chosen}",
                str(report.source),
                "部分标签位置/几何不完整，当前风格一致性结论不完整",
                "补齐 LabelPosition 和 MidPoint 后重跑",
            )

    # Unique names across Stateflow namespaces.
    state_names = Counter(str(state.get("name") or "") for state in states if state.get("name"))
    duplicates = [name for name, count in state_names.items() if count > 1]
    if duplicates:
        for name in duplicates:
            report.violation(
                "jc_0730-a",
                name,
                f"状态名 {name!r} 在 Chart 内重复 {state_names[name]} 次",
                "为每个状态使用唯一名称",
            )
    else:
        report.mark("jc_0730-a", str(report.source), "状态名唯一")

    namespace = defaultdict(set)
    for state in states:
        if state.get("name"):
            namespace[state["name"]].add("state")
    for data in geo["data"]:
        if data.get("name"):
            namespace[data["name"]].add("data")
    for event in geo["events"]:
        if event.get("name"):
            namespace[event["name"]].add("event")
    conflicts = {name: kinds for name, kinds in namespace.items() if len(kinds) > 1}
    if conflicts:
        for name, kinds in conflicts.items():
            report.violation(
                "jc_0732-a",
                name,
                f"同一 Chart 内跨命名空间重复：{sorted(kinds)}",
                "重命名状态、数据或事件以避免含义混淆",
            )
    else:
        report.mark("jc_0732-a", str(report.source), "状态、数据、事件名无跨类冲突")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed target modeling guideline v5 Stateflow geometry linter"
    )
    parser.add_argument("geometry", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        geometry = json.loads(args.geometry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report = Report(str(args.geometry))
        report.schema_errors.append(f"cannot load geometry: {exc}")
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return 2
    result = lint(geometry, str(args.geometry))
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
    if result.overall() == "COMPLIANT":
        return 0
    if result.overall() == "MANUAL_REVIEW_REQUIRED":
        return 3
    return 1 if result.overall() == "NON_COMPLIANT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
