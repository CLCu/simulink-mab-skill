#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create a Simulink layout plan; never create or modify a MATLAB model.

The output is data for the agent to map to SATK ``model_edit`` operations.
It is not a model-build script.  Structure and final placement remain owned by
``model_edit`` / ``arranging-simulink-layouts``.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "maab.simulink_layout_plan/v1"
STANDARD = "TARGET_MODELING_GUIDELINE_V5"
PROFILES = ["NA-MAAB", "JMAAB"]
MATLAB_VERSION = "R2025b"

DEFAULT_PORTS = {
    "Inport": (0, 1),
    "Outport": (1, 0),
    "Constant": (0, 1),
    "Gain": (1, 1),
    "Sum": (2, 1),
    "Product": (2, 1),
    "Divide": (2, 1),
    "Saturation": (1, 1),
    "UnitDelay": (1, 1),
    "Delay": (1, 1),
    "Integrator": (1, 1),
    "Switch": (3, 1),
    "Mux": (2, 1),
    "Demux": (1, 2),
    "RelationalOperator": (2, 1),
    "LogicalOperator": (2, 1),
    "BusCreator": (2, 1),
    "BusSelector": (1, 1),
    "SubSystem": (1, 1),
}


class PlanError(ValueError):
    """Invalid or incomplete input."""


def _scalar(value: Any, default: float) -> float:
    if isinstance(value, dict):
        value = value.get("value", default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _snap(value: float, grid: float) -> int:
    if grid <= 0:
        return int(round(value))
    return int(round(value / grid) * grid)


def _port_counts(block: dict[str, Any]) -> tuple[int, int]:
    declared = block.get("ports")
    default_in, default_out = DEFAULT_PORTS.get(block.get("type", "Gain"), (1, 1))
    if isinstance(declared, int):
        return declared, 1
    if isinstance(declared, (list, tuple)):
        if len(declared) >= 2:
            return int(declared[0]), int(declared[1])
    if isinstance(declared, dict):
        inputs = declared.get("in", declared.get("inputs", default_in))
        outputs = declared.get("out", declared.get("outputs", default_out))
        return int(inputs), int(outputs)
    return default_in, default_out


def _edge_record(raw: Any, index: int) -> dict[str, Any]:
    if isinstance(raw, (list, tuple)):
        if len(raw) < 2:
            raise PlanError(f"edge[{index}] must contain source and destination")
        record = {"source": raw[0], "destination": raw[1]}
        if len(raw) >= 3:
            record["source_port"] = raw[2]
        if len(raw) >= 4:
            record["destination_port"] = raw[3]
    elif isinstance(raw, dict):
        record = dict(raw)
        record["source"] = (
            record.get("source")
            or record.get("src")
            or record.get("source_block")
        )
        record["destination"] = (
            record.get("destination")
            or record.get("dst")
            or record.get("destination_block")
        )
    else:
        raise PlanError(f"edge[{index}] must be an array or object")
    if not record.get("source") or not record.get("destination"):
        raise PlanError(f"edge[{index}] has an empty endpoint")
    record["id"] = str(record.get("id") or f"edge_{index + 1}")
    return record


def validate_and_normalize(spec: Any) -> tuple[dict[str, Any], list[dict], list[dict]]:
    if not isinstance(spec, dict):
        raise PlanError("spec must be a JSON object")
    if not str(spec.get("model") or "").strip():
        raise PlanError("spec.model is required")
    blocks = spec.get("blocks")
    edges_raw = spec.get("edges")
    if not isinstance(blocks, list) or not blocks:
        raise PlanError("spec.blocks must be a non-empty array")
    if not isinstance(edges_raw, list):
        raise PlanError("spec.edges must be an array; use [] for no connections")
    normalized_blocks = []
    ids = set()
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise PlanError(f"blocks[{index}] must be an object")
        block_id = str(block.get("id") or "").strip()
        if not block_id:
            raise PlanError(f"blocks[{index}].id is required")
        if block_id in ids:
            raise PlanError(f"duplicate logical block id: {block_id}")
        ids.add(block_id)
        normalized = dict(block)
        normalized["id"] = block_id
        normalized["type"] = str(block.get("type") or "Gain")
        normalized["name"] = str(block.get("name") or block_id)
        normalized["_ports_in"], normalized["_ports_out"] = _port_counts(block)
        if normalized["_ports_in"] < 0 or normalized["_ports_out"] < 0:
            raise PlanError(f"block {block_id} has a negative port count")
        normalized_blocks.append(normalized)
    edges = [_edge_record(raw, i) for i, raw in enumerate(edges_raw)]
    seen_ids = set()
    for edge in edges:
        if edge["id"] in seen_ids:
            raise PlanError(f"duplicate edge id: {edge['id']}")
        seen_ids.add(edge["id"])
        if edge["source"] not in ids or edge["destination"] not in ids:
            raise PlanError(
                f"edge {edge['id']} refers to an unknown block: "
                f"{edge['source']} -> {edge['destination']}"
            )
    return spec, normalized_blocks, edges


def find_back_edges(nodes: list[str], edges: list[dict]) -> tuple[set[str], list[str]]:
    """Return edge IDs that close DFS cycles and a topological order."""
    adjacency: dict[str, list[dict]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["source"]].append(edge)
    state: dict[str, int] = {}
    back: set[str] = set()
    order: list[str] = []
    sys.setrecursionlimit(max(10000, len(nodes) * 4))

    def visit(node: str) -> None:
        state[node] = 1
        for edge in adjacency[node]:
            target = edge["destination"]
            status = state.get(target, 0)
            if status == 0:
                visit(target)
            elif status == 1:
                back.add(edge["id"])
        state[node] = 2
        order.append(node)

    for node in nodes:
        if state.get(node, 0) == 0:
            visit(node)
    return back, list(reversed(order))


def circular_node_edges(edges: list[dict]) -> set[str]:
    """Edges lying in a directed cycle (used only to classify feedback)."""
    adjacency: dict[str, list[int]] = defaultdict(list)
    for index, edge in enumerate(edges):
        adjacency[edge["source"]].append(index)
    cycle_edges: set[str] = set()
    for index, edge in enumerate(edges):
        target = edge["destination"]
        stack = [target]
        visited = set()
        found = False
        while stack and not found:
            node = stack.pop()
            if node == edge["source"]:
                found = True
                break
            if node in visited:
                continue
            visited.add(node)
            stack.extend(edges[n]["destination"] for n in adjacency[node])
        if found:
            cycle_edges.add(edge["id"])
    return cycle_edges


def _block_size(block: dict[str, Any], profile: dict[str, Any]) -> tuple[int, int]:
    explicit = block.get("size")
    if isinstance(explicit, (list, tuple)) and len(explicit) >= 2:
        return int(explicit[0]), int(explicit[1])
    if block.get("type") in ("Inport", "Outport"):
        port = profile.get("port_block", {})
        return (
            int(_scalar(port.get("preferred_width"), 30)),
            int(_scalar(port.get("preferred_height"), 14)),
        )
    block_profile = profile.get("block", {})
    return (
        int(_scalar(block_profile.get("preferred_width"), 40)),
        int(_scalar(block_profile.get("preferred_height"), 40)),
    )


def _layout(blocks: list[dict], edges: list[dict], profile: dict[str, Any]) -> dict[str, Any]:
    by_id = {block["id"]: block for block in blocks}
    nodes = list(by_id)
    back, topo = find_back_edges(nodes, edges)
    cycle_edges = circular_node_edges(edges)
    forward_edges = [edge for edge in edges if edge["id"] not in back]
    incoming: dict[str, list[dict]] = defaultdict(list)
    for edge in forward_edges:
        incoming[edge["destination"]].append(edge)

    rank = {node: 0 for node in topo}
    for node in topo:
        for edge in incoming[node]:
            rank[node] = max(rank[node], rank[edge["source"]] + 1)

    grid = _scalar(profile.get("grid"), 10)
    spacing = profile.get("spacing", {})
    hgap = _scalar(spacing.get("horizontal"), 60)
    vgap = _scalar(spacing.get("vertical"), 40)
    margin = _scalar(profile.get("layout", {}).get("margin"), 40)
    sizes = {block["id"]: _block_size(block, profile) for block in blocks}

    columns: dict[int, list[str]] = defaultdict(list)
    for node in nodes:
        columns[rank[node]].append(node)
    column_count = max(columns) + 1 if columns else 0
    column_x = []
    cursor_x = margin
    for column in range(column_count):
        column_x.append(cursor_x)
        width = max(sizes[node][0] for node in columns[column])
        cursor_x += width + hgap

    centers_y: dict[str, float] = {}
    positions: dict[str, list[int]] = {}
    for column in range(column_count):
        column_nodes = columns[column]

        def preferred_center(node: str) -> float:
            predecessors = [
                centers_y[item["source"]]
                for item in forward_edges
                if item["destination"] == node and item["source"] in centers_y
            ]
            return sum(predecessors) / len(predecessors) if predecessors else margin

        column_nodes.sort(key=lambda node: (preferred_center(node), node))
        cursor_y = margin
        for node in column_nodes:
            width, height = sizes[node]
            center = preferred_center(node)
            y0 = max(_snap(center - height / 2, grid), cursor_y)
            x0 = _snap(column_x[column], grid)
            positions[node] = [x0, y0, x0 + width, y0 + height]
            centers_y[node] = y0 + height / 2
            cursor_y = y0 + height + vgap

    outgoing: dict[tuple[str, int], list[dict]] = defaultdict(list)
    destination_groups: dict[str, list[dict]] = defaultdict(list)
    for edge in edges:
        source_block = by_id[edge["source"]]
        outputs = source_block.get("_ports_out", 0)
        raw_port = edge.get("source_port")
        if raw_port is None:
            port = 1
        else:
            port = int(raw_port)
        if outputs < 1 or port < 1 or port > outputs:
            raise PlanError(
                f"edge {edge['id']} source port {port} is invalid for "
                f"{edge['source']} (outputs={outputs})"
            )
        edge["_source_port"] = port
        outgoing[(edge["source"], port)].append(edge)
        destination_groups[edge["destination"]].append(edge)

    for block in blocks:
        group = destination_groups.get(block["id"], [])
        inputs = block.get("_ports_in", 0)
        explicit = {}
        for edge in group:
            raw = edge.get("destination_port")
            if raw is not None:
                explicit[edge["id"]] = int(raw)
        if explicit and len(set(explicit.values())) != len(explicit):
            raise PlanError(f"multiple edges reuse one input port on {block['id']}")
        if len(group) > inputs:
            raise PlanError(
                f"block {block['id']} declares {inputs} inputs but receives {len(group)} edges"
            )
        remaining = [
            port for port in range(1, inputs + 1) if port not in set(explicit.values())
        ]
        ordered = sorted(
            (edge for edge in group if edge["id"] not in explicit),
            key=lambda edge: (centers_y[edge["source"]], edge["id"]),
        )
        for edge, port in zip(ordered, remaining):
            edge["_destination_port"] = port
        for edge in group:
            edge["_destination_port"] = int(
                explicit.get(edge["id"], edge.get("_destination_port", 0))
            )
            if not 1 <= edge["_destination_port"] <= inputs:
                raise PlanError(f"edge {edge['id']} destination port is invalid")

    def port_y(block_id: str, port: int, count: int, output: bool) -> float:
        x0, y0, x1, y1 = positions[block_id]
        del x0, x1
        return y0 + (y1 - y0) * port / (count + 1)

    top = max(_snap(min(rect[1] for rect in positions.values()) - vgap, grid), 10)
    corridor_edges = [
        edge for edge in edges if abs(port_y(edge["source"], edge["_source_port"],
                                            by_id[edge["source"]]["_ports_out"], True)
                                     - port_y(edge["destination"],
                                              edge["_destination_port"],
                                              by_id[edge["destination"]]["_ports_in"], False)) >= 1
    ]
    slots: dict[int, list[dict]] = defaultdict(list)
    for edge in corridor_edges:
        source_column = rank[edge["source"]]
        slots[source_column].append(edge)
    corridor_x: dict[str, int] = {}
    for column, group in slots.items():
        group.sort(
            key=lambda edge: (
                port_y(edge["destination"], edge["_destination_port"],
                       by_id[edge["destination"]]["_ports_in"], False),
                edge["id"],
            )
        )
        left = column_x[column] + max(sizes[node][0] for node in columns[column])
        right = column_x[column + 1] if column + 1 < len(column_x) else left + hgap
        for index, edge in enumerate(group, start=1):
            corridor_x[edge["id"]] = _snap(
                left + (right - left) * index / (len(group) + 1),
                grid,
            )

    routed = []
    for edge in edges:
        source = edge["source"]
        destination = edge["destination"]
        sx = positions[source][2]
        sy = port_y(source, edge["_source_port"], by_id[source]["_ports_out"], True)
        dx = positions[destination][0]
        dy = port_y(
            destination,
            edge["_destination_port"],
            by_id[destination]["_ports_in"],
            False,
        )
        points = [[_snap(sx, grid), _snap(sy, grid)]]
        if edge["id"] in cycle_edges:
            approach = _snap(positions[destination][0] - hgap / 3, grid)
            source_exit = _snap(sx + hgap / 3, grid)
            points += [
                [source_exit, _snap(sy, grid)],
                [source_exit, top],
                [approach, top],
                [approach, _snap(dy, grid)],
            ]
        elif abs(sy - dy) >= 1:
            x = corridor_x.get(edge["id"], _snap(sx + hgap / 3, grid))
            points += [[x, _snap(sy, grid)], [x, _snap(dy, grid)]]
        points.append([_snap(dx, grid), _snap(dy, grid)])
        routed.append({
            "id": edge["id"],
            "source": {"block": source, "port": edge["_source_port"]},
            "destination": {
                "block": destination,
                "port": edge["_destination_port"],
            },
            "suggested_points": points,
            "feedback": edge["id"] in cycle_edges,
            "cycle": edge["id"] in cycle_edges,
        })

    branch_points = []
    jmaab_violations = []
    for (source, port), group in sorted(outgoing.items()):
        item = {
            "source": {"block": source, "port": port},
            "consumer_count": len(group),
            "edge_ids": [edge["id"] for edge in group],
        }
        branch_points.append(item)
        if len(group) > 2:
            jmaab_violations.append({
                "rule": "db_0032-d",
                "profile": "JMAAB",
                "source": {"block": source, "port": port},
                "consumer_count": len(group),
                "required_action": (
                    "Restructure into a branch tree or an explicit subsystem "
                    "interface; Goto/From only within the project budget with "
                    "crossing justification, and Mux does not duplicate a scalar."
                ),
            })

    return {
        "blocks": [
            {
                "id": block["id"],
                "name": block["name"],
                "type": block["type"],
                "ports": {
                    "in": block["_ports_in"],
                    "out": block["_ports_out"],
                },
                "suggested_position": positions[block["id"]],
                "rank": rank[block["id"]],
                "feedback": position_in_cycle(block["id"], edges, cycle_edges),
                "params": block.get("params", {}),
            }
            for block in blocks
        ],
        "edges": routed,
        "branch_points": branch_points,
        "plan_level_findings": jmaab_violations,
        "feedback_edges": sorted(cycle_edges),
        "topological_order": topo,
    }


def position_in_cycle(node: str, edges: list[dict], cycle_edges: set[str]) -> bool:
    return any(
        edge["id"] in cycle_edges and node in (edge["source"], edge["destination"])
        for edge in edges
    )


def build_plan(spec: dict, blocks: list[dict], edges: list[dict],
               profile: dict[str, Any]) -> dict[str, Any]:
    placement = _layout(blocks, edges, profile)
    return {
        "schema_version": SCHEMA_VERSION,
        "standard": STANDARD,
        "profiles": PROFILES,
        "matlab_version": MATLAB_VERSION,
        "model": str(spec["model"]),
        "scope": str(spec.get("subsystem") or spec.get("scope") or "").strip("/"),
        "coordinate_frame": "scope-local",
        "project_profile": {
            "source": profile.get("source", "unspecified"),
            "values_are_maab_requirements": False,
        },
        **placement,
        "unverified_in_plan": [
            "jm_0002 requires visual recognizability; no numeric target-standard threshold",
            "Line-crossing style must be read from the actual Simulink environment, not this plan",
            "Final routing, bends and crossings must be re-exported after model_edit",
            "Manual readability rules still require the audit evidence matrix",
        ],
        "execution_contract": {
            "structure_operator": "model_edit",
            "layout_operators": ["arranging-simulink-layouts", "model_edit"],
            "plan_is_executable_model_script": False,
            "forbidden_artifacts": ["_build.m"],
            "forbidden_apis": [
                "evaluate_matlab_code model construction",
                "add_block/add_line through a generated MATLAB script",
                "set_param Position outside model_edit",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a target modeling guideline v5 Simulink layout plan JSON"
    )
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "assets"
        / "layout-profile.json",
    )
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        profile = (
            json.loads(args.profile.read_text(encoding="utf-8"))
            if args.profile.exists()
            else {}
        )
        spec, blocks, edges = validate_and_normalize(spec)
        plan = build_plan(spec, blocks, edges, profile)
        output = args.out or args.spec.with_name(args.spec.stem + "_plan.json")
        if output.suffix.lower() != ".json":
            output = output.with_suffix(".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, json.JSONDecodeError, PlanError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"wrote {len(plan['blocks'])} logical blocks / "
        f"{len(plan['edges'])} logical edges -> {output}"
    )
    if plan["plan_level_findings"]:
        print(
            f"JMAAB planning findings: {len(plan['plan_level_findings'])} "
            "(resolve before model_edit)"
        )
    print("This is a plan only; edit the model with SATK model_edit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
