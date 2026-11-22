#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Suggest a clean Simulink layout as JSON data for SATK model_edit.

Never creates or modifies a model. Placement = rank columns left-to-right,
parallel rows top-to-bottom, ports ordered by neighbour height. Routing =
straight / single corridor for adjacent columns, a shared branch tree for
same-column fanout, and one dedicated lane per feedback or multi-column edge.

By construction the suggestion has no diagonals, no cross-net collinear
overlap and no through-block segment; residual crossings are left to the
metrics + PNG repair loop. A self-check at the end verifies those guarantees.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from layout_metrics import hits_interior, is_h, is_v, overlap, rect, segments

SCHEMA_VERSION = "maab.simulink_layout_plan/v2"

DEFAULT_PORTS = {
    "Inport": (0, 1), "Outport": (1, 0), "Constant": (0, 1), "Gain": (1, 1),
    "Sum": (2, 1), "Product": (2, 1), "Divide": (2, 1), "Saturation": (1, 1),
    "UnitDelay": (1, 1), "Delay": (1, 1), "Integrator": (1, 1), "Switch": (3, 1),
    "Mux": (2, 1), "Demux": (1, 2), "RelationalOperator": (2, 1),
    "LogicalOperator": (2, 1), "BusCreator": (2, 1), "BusSelector": (1, 1),
    "SubSystem": (1, 1),
}


class PlanError(ValueError):
    pass


def _scalar(value: Any, default: float) -> float:
    if isinstance(value, dict):
        value = value.get("value", default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _snap(value: float, grid: float) -> int:
    return int(round(value / grid) * grid) if grid > 0 else int(round(value))


def _ports(block: dict) -> tuple[int, int]:
    declared = block.get("ports")
    din, dout = DEFAULT_PORTS.get(block.get("type", "Gain"), (1, 1))
    if isinstance(declared, int):
        return declared, 1
    if isinstance(declared, (list, tuple)) and len(declared) >= 2:
        return int(declared[0]), int(declared[1])
    if isinstance(declared, dict):
        return int(declared.get("in", declared.get("inputs", din))), \
            int(declared.get("out", declared.get("outputs", dout)))
    return din, dout


def normalize(spec: Any) -> tuple[dict, list[dict], list[dict]]:
    if not isinstance(spec, dict) or not str(spec.get("model") or "").strip():
        raise PlanError("spec.model is required")
    blocks = spec.get("blocks")
    edges_raw = spec.get("edges")
    if not isinstance(blocks, list) or not blocks:
        raise PlanError("spec.blocks must be a non-empty array")
    if not isinstance(edges_raw, list):
        raise PlanError("spec.edges must be an array (use [] for no connections)")
    ids, normalized = set(), []
    for i, b in enumerate(blocks):
        if not isinstance(b, dict) or not str(b.get("id") or "").strip():
            raise PlanError(f"blocks[{i}].id is required")
        bid = str(b["id"]).strip()
        if bid in ids:
            raise PlanError(f"duplicate block id {bid}")
        ids.add(bid)
        n = dict(b)
        n["id"], n["type"] = bid, str(b.get("type") or "Gain")
        n["name"] = str(b.get("name") or bid)
        n["_in"], n["_out"] = _ports(b)
        if n["_in"] < 0 or n["_out"] < 0:
            raise PlanError(f"block {bid} has negative port count")
        normalized.append(n)
    edges = []
    for i, raw in enumerate(edges_raw):
        if isinstance(raw, (list, tuple)):
            if len(raw) < 2:
                raise PlanError(f"edge[{i}] needs source and destination")
            e = {"source": raw[0], "destination": raw[1]}
            if len(raw) >= 3:
                e["source_port"] = raw[2]
            if len(raw) >= 4:
                e["destination_port"] = raw[3]
        elif isinstance(raw, dict):
            e = dict(raw)
            e["source"] = e.get("source") or e.get("src")
            e["destination"] = e.get("destination") or e.get("dst")
        else:
            raise PlanError(f"edge[{i}] must be array or object")
        if not e.get("source") or not e.get("destination"):
            raise PlanError(f"edge[{i}] has empty endpoint")
        if e["source"] not in ids or e["destination"] not in ids:
            raise PlanError(f"edge[{i}] references unknown block")
        e["id"] = str(e.get("id") or f"edge_{i + 1}")
        edges.append(e)
    if len({e["id"] for e in edges}) != len(edges):
        raise PlanError("duplicate edge id")
    return spec, normalized, edges


def back_edges_and_order(nodes: list[str], edges: list[dict]) -> tuple[set[str], list[str]]:
    adj = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e)
    state, back, order = {}, set(), []
    sys.setrecursionlimit(max(10000, len(nodes) * 4))

    def visit(node: str) -> None:
        state[node] = 1
        for e in adj[node]:
            s = state.get(e["destination"], 0)
            if s == 0:
                visit(e["destination"])
            elif s == 1:
                back.add(e["id"])
        state[node] = 2
        order.append(node)

    for n in nodes:
        if state.get(n, 0) == 0:
            visit(n)
    return back, list(reversed(order))


def cycle_members(edges: list[dict]) -> set[str]:
    adj = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e["destination"])
    members = set()
    for e in edges:
        stack, seen = [e["destination"]], set()
        while stack:
            n = stack.pop()
            if n == e["source"]:
                members.add(e["id"])
                break
            if n not in seen:
                seen.add(n)
                stack.extend(adj[n])
    return members


def build_plan(spec: dict, blocks: list[dict], edges: list[dict], profile: dict) -> dict:
    by_id = {b["id"]: b for b in blocks}
    back, topo = back_edges_and_order(list(by_id), edges)
    cycles = cycle_members(edges)
    forward = [e for e in edges if e["id"] not in back]
    incoming = defaultdict(list)
    for e in forward:
        incoming[e["destination"]].append(e)
    rank = {n: 0 for n in topo}
    for n in topo:
        for e in incoming[n]:
            rank[n] = max(rank[n], rank[e["source"]] + 1)
    # Only backward cycle edges are feedback; forward edges inside a cycle
    # still flow left-to-right and route directly.
    feedback = {e["id"] for e in edges if e["id"] in cycles and rank[e["destination"]] <= rank[e["source"]]}

    grid = _scalar(profile.get("grid"), 10)
    sp = profile.get("spacing") or {}
    hgap, vgap = _scalar(sp.get("horizontal"), 60), _scalar(sp.get("vertical"), 40)
    margin, lane_gap = _scalar(sp.get("margin"), 40), _scalar(sp.get("lane_gap"), 20)
    blk = profile.get("block") or {}
    sizes = {}
    for b in blocks:
        if isinstance(b.get("size"), (list, tuple)) and len(b["size"]) >= 2:
            sizes[b["id"]] = (int(b["size"][0]), int(b["size"][1]))
        elif b["type"] in ("Inport", "Outport"):
            sizes[b["id"]] = (int(_scalar(blk.get("port_width"), 30)), int(_scalar(blk.get("port_height"), 14)))
        else:
            sizes[b["id"]] = (int(_scalar(blk.get("width"), 40)), int(_scalar(blk.get("height"), 40)))

    columns = defaultdict(list)
    for n in by_id:
        columns[rank[n]].append(n)
    col_count = max(columns) + 1 if columns else 0
    col_x, cursor = [], margin
    for c in range(col_count):
        col_x.append(cursor)
        cursor += max(sizes[n][0] for n in columns[c]) + hgap

    centers, positions = {}, {}
    for c in range(col_count):
        nodes = columns[c]

        def preferred(n: str) -> float:
            preds = [centers[e["source"]] for e in forward
                     if e["destination"] == n and e["source"] in centers]
            return sum(preds) / len(preds) if preds else margin

        # Feedback arrives from the top corridor: keep feedback-consuming
        # blocks high in the column so approach verticals stay short.
        fb_dest = {e["destination"] for e in edges if e["id"] in feedback}
        nodes.sort(key=lambda n: (0 if n in fb_dest else 1, preferred(n), n))
        cursor_y = margin
        for n in nodes:
            w, h = sizes[n]
            y0 = max(_snap(preferred(n) - h / 2, grid), cursor_y)
            x0 = _snap(col_x[c], grid)
            positions[n] = [x0, y0, x0 + w, y0 + h]
            centers[n] = y0 + h / 2
            cursor_y = y0 + h + vgap

    # Ports: explicit first, remaining inputs ordered by source height.
    out_groups = defaultdict(list)
    in_groups = defaultdict(list)
    for e in edges:
        s = by_id[e["source"]]
        port = int(e.get("source_port") or 1)
        if not 1 <= port <= s["_out"]:
            raise PlanError(f"edge {e['id']} source port {port} invalid for {e['source']}")
        e["_sp"] = port
        out_groups[(e["source"], port)].append(e)
        in_groups[e["destination"]].append(e)
    for b in blocks:
        group = in_groups.get(b["id"], [])
        explicit = {e["id"]: int(e["destination_port"]) for e in group if e.get("destination_port") is not None}
        if len(set(explicit.values())) != len(explicit):
            raise PlanError(f"multiple edges reuse one input port on {b['id']}")
        if len(group) > b["_in"]:
            raise PlanError(f"block {b['id']} declares {b['_in']} inputs but receives {len(group)}")
        free = [p for p in range(1, b["_in"] + 1) if p not in set(explicit.values())]
        # Feedback arrives from the top corridor, so feedback-entering edges
        # take the upper ports; forward edges fill the rest by source height.
        ordered = sorted((e for e in group if e["id"] not in explicit),
                         key=lambda e: (0 if e["id"] in feedback else 1,
                                        centers[e["source"]], e["id"]))
        for e, p in zip(ordered, free):
            e["_dp"] = p
        for e in group:
            e["_dp"] = explicit.get(e["id"], e.get("_dp", 0))
            if not 1 <= e["_dp"] <= b["_in"]:
                raise PlanError(f"edge {e['id']} destination port invalid")

    def port_y(n: str, port: int, count: int) -> float:
        x0, y0, x1, y1 = positions[n]
        return y0 + (y1 - y0) * port / (count + 1)

    def sy(e):
        return port_y(e["source"], e["_sp"], by_id[e["source"]]["_out"])

    def dy(e):
        return port_y(e["destination"], e["_dp"], by_id[e["destination"]]["_in"])

    # Gap regions hold every vertical stub; distinct x per request prevents
    # collinear overlap. Gap -1 is the left margin lane for column-0 approaches.
    def gap_region(g: int) -> tuple[float, float]:
        if g < 0:
            return max(10.0, margin - hgap), col_x[0]
        left = col_x[g] + max(sizes[n][0] for n in columns[g])
        right = col_x[g + 1] if g + 1 < col_count else left + hgap
        return left, right

    # Each gap is split into three zones so verticals of different roles do
    # not cross the horizontals of another role: exits far left, forward
    # corridors/spines middle, approaches right (ordered by port height desc
    # so a taller approach never cuts a shorter one's leaf).
    requests = defaultdict(list)  # gap -> (zone, sort_key, key)
    trees = {}
    for (src, port), group in out_groups.items():
        same_col = [e for e in group if rank[e["destination"]] == rank[src] + 1]
        if len(same_col) >= 2:
            trees[(src, port)] = same_col
            requests[rank[src]].append((1, min(dy(e) for e in same_col), f"tree:{src}:{port}"))
    lane_edges = []
    for e in edges:
        if e["id"] in feedback or rank[e["destination"]] > rank[e["source"]] + 1:
            lane_edges.append(e)
            requests[rank[e["source"]]].append((0, sy(e), f"exit:{e['id']}"))
            requests[rank[e["destination"]] - 1].append((2, -dy(e), f"approach:{e['id']}"))
        elif (e["source"], e["_sp"]) not in trees and abs(sy(e) - dy(e)) >= 1:
            requests[rank[e["source"]]].append((1, dy(e), f"corridor:{e['id']}"))
    slot_x = {}
    for g, reqs in requests.items():
        left, right = gap_region(g)
        width = right - left
        for zone in (0, 1, 2):
            group = sorted(r for r in reqs if r[0] == zone)
            if zone == 0:
                for i, (_, _, key) in enumerate(group):
                    slot_x[key] = round(left + width * 0.08 + i * 4, 3)
            else:
                lo, hi = (left + width * 0.3, left + width * 0.55) if zone == 1 \
                    else (left + width * 0.7, right - 3)
                for i, (_, _, key) in enumerate(group, start=1):
                    # Fractional on purpose: grid-snapping narrow gaps can
                    # collapse two slots onto one x (overlap / endpoint cross).
                    slot_x[key] = round(lo + (hi - lo) * i / (len(group) + 1), 3)

    top_base = min(p[1] for p in positions.values()) - vgap
    bottom_base = max(p[3] for p in positions.values()) + vgap
    fb_sorted = sorted((e for e in lane_edges if e["id"] in feedback), key=lambda e: (sy(e), e["id"]))
    mc_sorted = sorted((e for e in lane_edges if e["id"] not in feedback), key=lambda e: (sy(e), e["id"]))
    lane_y = {}
    for i, e in enumerate(fb_sorted, start=1):
        lane_y[e["id"]] = _snap(top_base - i * lane_gap, grid)
    for i, e in enumerate(mc_sorted, start=1):
        lane_y[e["id"]] = _snap(bottom_base + i * lane_gap, grid)

    routed = []
    for e in edges:
        src, dst = e["source"], e["destination"]
        sx, dx = positions[src][2], positions[dst][0]
        # Port endpoints keep fractional heights: snapping them to the grid
        # can collapse distinct ports of a tall block onto one y and create
        # collinear overlap between different nets.
        y_s, y_d = round(sy(e), 3), round(dy(e), 3)
        tree = trees.get((src, e["_sp"]))
        if tree and e in tree:
            spine = slot_x[f"tree:{src}:{e['_sp']}"]
            points = [[_snap(sx, grid), y_s], [spine, y_s], [spine, y_d], [_snap(dx, grid), y_d]]
            kind = "branch_tree"
        elif e["id"] in lane_y:
            exit_x = slot_x[f"exit:{e['id']}"]
            approach_x = slot_x[f"approach:{e['id']}"]
            lane = lane_y[e["id"]]
            points = [[_snap(sx, grid), y_s], [exit_x, y_s], [exit_x, lane],
                      [approach_x, lane], [approach_x, y_d], [_snap(dx, grid), y_d]]
            kind = "feedback_lane" if e["id"] in feedback else "multicolumn_lane"
        elif abs(y_s - y_d) < 1:
            points = [[_snap(sx, grid), y_s], [_snap(dx, grid), y_d]]
            kind = "straight"
        else:
            x = slot_x[f"corridor:{e['id']}"]
            points = [[_snap(sx, grid), y_s], [x, y_s], [x, y_d], [_snap(dx, grid), y_d]]
            kind = "corridor"
        routed.append({"id": e["id"], "source": {"block": src, "port": e["_sp"]},
                       "destination": {"block": dst, "port": e["_dp"]},
                       "suggested_points": points, "feedback": e["id"] in feedback,
                       "route_kind": kind})

    # Self-check the construction guarantees on the suggested geometry.
    findings = []
    boxes = {b["id"]: rect({"position": positions[b["id"]]}) for b in blocks}
    for i, a in enumerate(routed):
        sa = segments(a["suggested_points"])
        for seg in sa:
            if not (is_h(seg) or is_v(seg)):
                findings.append({"kind": "planner_diagonal", "edge": a["id"]})
            ends = {a["source"]["block"], a["destination"]["block"]}
            for bid, box in boxes.items():
                if bid not in ends and hits_interior(seg, box):
                    findings.append({"kind": "planner_through_block", "edge": a["id"], "block": bid})
        for b in routed[i + 1:]:
            net_a = (a["source"]["block"], a["source"]["port"])
            net_b = (b["source"]["block"], b["source"]["port"])
            if net_a == net_b:
                continue
            for seg_a in sa:
                for seg_b in segments(b["suggested_points"]):
                    if overlap(seg_a, seg_b):
                        findings.append({"kind": "planner_overlap", "edges": [a["id"], b["id"]]})
    for (src, port), group in sorted(out_groups.items()):
        if len(group) > 2:
            findings.append({"kind": "fanout_craft_note", "source": {"block": src, "port": port},
                             "consumer_count": len(group),
                             "note": "扇出>2：同列消费者已按分支树走线；跨列消费者走独立走廊。仅为手艺提示，不是门禁。"})

    return {
        "schema_version": SCHEMA_VERSION,
        "model": str(spec["model"]),
        "scope": str(spec.get("subsystem") or spec.get("scope") or "").strip("/"),
        "coordinate_frame": "scope-local",
        "blocks": [{"id": b["id"], "name": b["name"], "type": b["type"],
                    "ports": {"in": b["_in"], "out": b["_out"]},
                    "suggested_position": positions[b["id"]], "rank": rank[b["id"]]} for b in blocks],
        "edges": routed,
        "branch_trees": [{"source": {"block": s, "port": p},
                          "spine_x": slot_x[f"tree:{s}:{p}"],
                          "edges": [e["id"] for e in g]} for (s, p), g in sorted(trees.items())],
        "lanes": [{"edge": e["id"], "y": lane_y[e["id"]],
                   "kind": "feedback" if e["id"] in feedback else "multicolumn"} for e in lane_edges],
        "plan_level_findings": findings,
        "feedback_edges": sorted(feedback),
        "topological_order": topo,
        "guarantees": "建议几何无斜线、无跨信号共线重叠、无穿块；残留交叉由 layout_metrics + PNG 闭环消除。",
        "unverified_in_plan": [
            "最终走线以 SATK 布局后的实际模型为准，重新导出度量",
            "端口端点为 p/(n+1) 近似坐标；实际位置以 Simulink PortHandles（图标几何）为准，由 SATK/修复循环吸附",
            "可读性（标签/可辨识/多余折弯）以最终 PNG 逐张检查为准",
        ],
        "execution_contract": {
            "structure_operator": "model_edit",
            "layout_operators": ["arranging-simulink-layouts", "model_edit"],
            "plan_is_executable_model_script": False,
            "forbidden": ["_build.m", "add_block/add_line via generated script", "set_param Position outside model_edit"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest a clean Simulink layout (JSON plan only)")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--profile", type=Path,
                        default=Path(__file__).resolve().parent.parent / "assets" / "layout-profile.json")
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile.exists() else {}
        spec, blocks, edges = normalize(spec)
        plan = build_plan(spec, blocks, edges, profile)
        output = args.out or args.spec.with_name(args.spec.stem + "_plan.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, PlanError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(plan['blocks'])} blocks / {len(plan['edges'])} edges -> {output}")
    bad = [f for f in plan["plan_level_findings"] if f["kind"].startswith("planner_")]
    if bad:
        print(f"WARNING: planner self-check found {len(bad)} guarantee violation(s): {bad}")
    print("Plan only; build and place with SATK model_edit / arranging-simulink-layouts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
