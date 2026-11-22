#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Render a Stateflow chart from exported chart geometry JSON to PNG.

Usage:
    python render_chart.py chart_geometry.json [-o out.png] [--dpi 150]

This is a deterministic re-drawing of the exported Stateflow geometry
(scripts/export_stateflow_geometry.m), used when the MATLAB canvas print
of a chart is unavailable or degenerate (headless sessions). It renders
states, transitions, default transitions and label bounding boxes at
their exported coordinates, so label overlap, out-of-canvas labels and
crossing transitions are visible for target-spec visual review (db_0097,
jc_0739-adjacent checks). It is a review aid drawn from the same data
the Stateflow lint consumes, not the editor canvas itself.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402


def rect_of(position) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in position)
    return min(x0, x1), min(y0, y1), max(x0, x1) - min(x0, x1), max(y0, y1) - min(y0, y1)


def draw_state(ax, state: dict, depth: int) -> None:
    if not state.get("position") or len(state["position"]) != 4:
        return
    x, y, w, h = rect_of(state["position"])
    is_chart_child = state.get("parent_kind") == "chart"
    edge = "#1f4e79" if is_chart_child else "#5b7fa6"
    face = "#eef3f8" if is_chart_child else "#fbfcfd"
    ax.add_patch(Rectangle((x, y), w, h, linewidth=1.4 if is_chart_child else 1.0,
                           edgecolor=edge, facecolor=face, zorder=2 + depth))
    label = str(state.get("label") or state.get("name") or "")
    lines = label.splitlines() or [""]
    name = lines[0]
    ax.text(x + 5, y + 5, name, fontsize=9, fontweight="bold",
            color="#1f4e79", va="top", ha="left", zorder=4 + depth)
    if len(lines) > 1:
        ax.text(x + 5, y + 18, "\n".join(lines[1:]), fontsize=6.5,
                color="#333333", va="top", ha="left", zorder=4 + depth)
    if state.get("is_grouped"):
        ax.add_patch(Rectangle((x, y), w, h, linewidth=3.0,
                               edgecolor="#5b7fa6", facecolor="none", zorder=3 + depth))


def draw_junction(ax, junction: dict) -> None:
    center = junction.get("center")
    if not center or len(center) < 2:
        return
    radius = float(junction.get("radius") or 5)
    ax.add_patch(plt.Circle((float(center[0]), float(center[1])), radius,
                            linewidth=1.2, edgecolor="#1f4e79",
                            facecolor="#ffffff", zorder=5))


def draw_transition(ax, transition: dict) -> None:
    points = []
    for key in ("source_endpoint",):
        value = transition.get(key)
        if value:
            points.append((float(value[0]), float(value[1])))
    for mid in transition.get("midpoints") or []:
        points.append((float(mid[0]), float(mid[1])))
    value = transition.get("destination_endpoint")
    if value:
        points.append((float(value[0]), float(value[1])))
    if len(points) < 2:
        return
    for a, b in zip(points, points[1:]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#333333",
                linewidth=1.0, zorder=5, solid_capstyle="round")
    # Arrow head at the destination end.
    a, b = points[-2], points[-1]
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=10,
                                 color="#333333", linewidth=1.0, zorder=5))
    # Default transitions start with a filled dot.
    if transition.get("is_default") or transition.get("source_kind") == "none":
        start = points[0]
        ax.plot([start[0]], [start[1]], marker="o", markersize=4,
                color="#333333", zorder=6)
    # Label at its exported bounding box (x, y, w, h).
    label = str(transition.get("label") or "")
    pos = transition.get("label_position")
    if label and pos and len(pos) >= 2:
        lx, ly = float(pos[0]), float(pos[1])
        lw = float(pos[2]) if len(pos) >= 3 and pos[2] else 0
        lh = float(pos[3]) if len(pos) >= 4 and pos[3] else 12
        if lw:
            ax.add_patch(Rectangle((lx, ly), lw, lh, linewidth=0.5,
                                   edgecolor="#c00000", facecolor="#fff2f2",
                                   linestyle="--", zorder=6))
        ax.text(lx, ly, label, fontsize=6.5, color="#7f1d1d",
                va="top", ha="left", zorder=7)


def render(geo: dict, out_file: Path, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.set_facecolor("white")
    states = list(geo.get("states") or [])
    states.sort(key=lambda s: 0 if s.get("parent_kind") == "chart" else 1)
    for depth, state in enumerate(states):
        draw_state(ax, state, depth)
    for junction in geo.get("junctions") or []:
        draw_junction(ax, junction)
    for transition in geo.get("transitions") or []:
        draw_transition(ax, transition)

    chart = geo.get("chart") or {}
    title = str(geo.get("chart_path") or chart.get("path") or "chart")
    ax.set_title(f"{title} (rendered from exported geometry)", fontsize=10)
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_yaxis()
    ax.grid(True, linestyle=":", linewidth=0.4, color="#bbbbbb")
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(out_file, dpi=dpi)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("geometry", type=Path)
    parser.add_argument("-o", "--out", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()
    out_file = args.out or args.geometry.with_suffix(".render.png")
    try:
        geo = json.loads(args.geometry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot load geometry: {exc}")
        return 2
    if not geo.get("states") and not geo.get("transitions"):
        print("geometry has no states or transitions")
        return 2
    render(geo, out_file, args.dpi)
    print(f"rendered {geo.get('chart_path')} -> {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
