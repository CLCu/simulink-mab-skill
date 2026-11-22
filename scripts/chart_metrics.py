#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Advisory appearance metrics for one exported Stateflow chart.

Counts sampled transition crossings / overlaps / through-state segments.
ADVISORY ONLY: transition polylines are 3-point samples of possibly curved
routes, so counts can miss or invent events. The editor PNG (render_check)
is the authority for chart readability; never deliver on these counts alone.

Exit codes: 0 = readable input (counts may be nonzero); 2 = schema invalid.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from layout_metrics import crossing, hits_interior, overlap, segments

SCHEMA = "maab.stateflow_geometry/v2"
TOL = 1.0


def point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def box(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def polyline(tr: dict) -> list[tuple[float, float]]:
    pts = []
    src = point(tr.get("source_endpoint"))
    if src:
        pts.append(src)
    for raw in tr.get("midpoints") or []:
        p = point(raw)
        if p:
            pts.append(p)
    dst = point(tr.get("destination_endpoint"))
    if dst:
        pts.append(dst)
    return pts


def ancestors(identifier: str, objects: dict) -> set[str]:
    result, current = set(), identifier
    for _ in range(64):
        parent = (objects.get(current) or {}).get("parent_id")
        if not parent:
            break
        result.add(parent)
        current = parent
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Advisory Stateflow chart appearance metrics")
    parser.add_argument("geometry", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        geo = json.loads(args.geometry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: cannot load geometry: {exc}")
        return 2
    errors = []
    if not isinstance(geo, dict) or geo.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")
    for key in ("chart", "states", "junctions", "transitions"):
        if not isinstance(geo.get(key), (dict, list)):
            errors.append(f"missing/invalid {key}")
    if errors:
        print(f"INVALID: {errors}")
        return 2

    objects = {geo["chart"]["id"]: geo["chart"]}
    state_boxes = {}
    for s in geo["states"]:
        objects[s["id"]] = s
        b = box(s.get("position"))
        if b:
            state_boxes[s["id"]] = b
    for j in geo["junctions"]:
        objects[j["id"]] = j
        c = point(j.get("center"))
        if c:
            state_boxes.setdefault(j["id"], None)

    transitions = geo["transitions"]
    polys = {t["id"]: polyline(t) for t in transitions}
    crossings, overlaps, through = [], [], []
    for i, a in enumerate(transitions):
        for b in transitions[i + 1:]:
            if a.get("source_id") and a.get("source_id") == b.get("source_id"):
                continue
            for sa in segments(polys[a["id"]]):
                for sb in segments(polys[b["id"]]):
                    p = crossing(sa, sb)
                    if p:
                        crossings.append({"a": a["id"], "b": b["id"], "point": list(p)})
                    p = overlap(sa, sb)
                    if p:
                        overlaps.append({"a": a["id"], "b": b["id"], "point": list(p)})
    for t in transitions:
        excluded = set()
        for end in (t.get("source_id"), t.get("destination_id")):
            if end in objects:
                excluded.add(end)
                excluded |= ancestors(end, objects)
        for seg in segments(polys[t["id"]]):
            for sid, b in state_boxes.items():
                if b and sid not in excluded and hits_interior(seg, b):
                    through.append({"transition": t["id"], "state": sid})

    result = {
        "schema_version": "maab.stateflow_chart_metrics/v2",
        "chart_path": geo.get("chart_path"),
        "advisory": True,
        "crossing_events": len(crossings),
        "overlap_events": len(overlaps),
        "through_state_events": len(through),
        "crossings": crossings, "overlaps": overlaps, "through_states": through,
        "note": "3 点采样几何，曲线/隐藏路由不可靠；以 render_check 的编辑器 PNG 逐张复核为准。",
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ADVISORY {geo.get('chart_path')}: crossings={len(crossings)} "
              f"overlaps={len(overlaps)} through_states={len(through)}")
        for ev in crossings + overlaps:
            print(f"    {ev['a']} × {ev['b']} @ {ev['point']}")
        for ev in through:
            print(f"    {ev['transition']} 穿过 {ev['state']}")
        print("采样几何仅供参考；最终结论以编辑器 PNG 逐张检查为准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
