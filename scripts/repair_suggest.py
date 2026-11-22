#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase-1 crossing-repair suggester: turn cookbook moves into executable ops.

Reads one exported scope geometry, previews small reversible moves IN MEMORY
(reorder destination ports, align/swap block heights, reassign a corridor or
lane slot) by re-running the appearance metrics on the transformed geometry,
and emits ranked JSON ops for SATK model_edit to apply ONE per round.

This script never touches the model. Previews use approximate port heights
(p/(n+1)); the authoritative judge is re-export + layout_metrics after apply,
and readability still closes on the rendered PNG.

Ops (phase 1, coordinate/port level only):
  reorder_ports   {block, assign:{line_id:port}}
  move_block      {block, position}
  swap_blocks     {blocks:[a,b]}
  reassign_slot   {line, kind:corridor|exit|approach, x}

Exit 0 always (it is a suggester); empty suggestions when nothing improves.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from layout_metrics import HARD_METRICS, goto_budget, measure, rect

SCHEMA = "maab.repair_suggestions/v1"
MAX_PREVIEWS = 80
DEFAULT_PROFILE = Path(__file__).resolve().parent.parent / "assets" / "layout-profile.json"


def port_count(blocks, lines, block, kind) -> int:
    key = "dst_port" if kind == "in" else "src_port"
    end = "dst_block" if kind == "in" else "src_block"
    vals = [l.get(key) or 1 for l in lines if l.get(end) == block]
    return max(vals, default=1)


def port_pos(blocks, lines, block, port, kind) -> tuple[float, float]:
    b = next(x for x in blocks if x["path"] == block)
    x0, y0, x1, y1 = rect(b)
    n = port_count(blocks, lines, block, kind)
    y = y0 + (y1 - y0) * port / (n + 1)
    return (x0 if kind == "in" else x1), y


def center_y(blocks, block) -> float:
    b = next(x for x in blocks if x["path"] == block)
    r = rect(b)
    return (r[1] + r[3]) / 2


def role(line, blocks) -> str:
    pts = line.get("points") or []
    if len(pts) == 6 and abs(pts[2][1] - pts[3][1]) < 1:
        top = min(rect(b)[1] for b in blocks)
        bot = max(rect(b)[3] for b in blocks)
        if pts[2][1] < top:
            return "feedback_lane"
        if pts[2][1] > bot:
            return "multicolumn_lane"
    if len(pts) >= 4:
        return "corridor"
    return "straight"


def _set_ends(pts, src, dst):
    pts = [list(p) for p in pts]
    if src is not None:
        pts[0] = list(src)
    if dst is not None:
        pts[-1] = list(dst)
    if len(pts) == 2:
        if abs(pts[0][1] - pts[1][1]) >= 1:
            mx = (pts[0][0] + pts[1][0]) / 2
            pts = [pts[0], [mx, pts[0][1]], [mx, pts[1][1]], pts[1]]
    elif len(pts) >= 4:
        if src is not None:
            pts[1][1] = pts[0][1]
        if dst is not None:
            pts[-2][1] = pts[-1][1]
    return pts


def preview(blocks, lines) -> dict:
    return measure(blocks, lines)["summary"]


def crossings_set(blocks, lines) -> set:
    m = measure(blocks, lines)
    return {tuple(sorted((c["line_a"], c["line_b"]))) for c in m["crossings"]}


def improves(cur, pre) -> bool:
    if pre["crossing_events"] >= cur["crossing_events"]:
        return False
    return all(pre[k] <= cur[k] for k in HARD_METRICS if k != "crossing_events")


class Suggester:
    def __init__(self, blocks, lines, profile=None):
        self.blocks0, self.lines0 = blocks, lines
        self.profile = profile or {}
        self.cur = preview(blocks, lines)
        self.cur_cross = crossings_set(blocks, lines)
        self.previews = 0
        self.cands = []

    def try_cand(self, op, blocks, lines, reason):
        if self.previews >= MAX_PREVIEWS:
            return
        self.previews += 1
        pre = preview(blocks, lines)
        if not improves(self.cur, pre):
            return
        gone = sorted(self.cur_cross - crossings_set(blocks, lines))
        sig = json.dumps(op, sort_keys=True)
        if any(c["sig"] == sig for c in self.cands):
            return
        self.cands.append({"sig": sig, "op": op, "preview": pre,
                           "reduction": self.cur["crossing_events"] - pre["crossing_events"],
                           "targets_crossings": [f"{a}×{b}" for a, b in gone],
                           "reason": reason})

    def lines_touching(self, lines, block):
        return [l for l in lines if l.get("src_block") == block or l.get("dst_block") == block]

    def with_move(self, block, newpos):
        blocks = copy.deepcopy(self.blocks0)
        for b in blocks:
            if b["path"] == block:
                b["position"] = list(newpos)
        lines = copy.deepcopy(self.lines0)
        for l in self.lines_touching(lines, block):
            src = port_pos(blocks, lines, block, l["src_port"], "out") if l.get("src_block") == block else None
            dst = port_pos(blocks, lines, block, l["dst_port"], "in") if l.get("dst_block") == block else None
            l["points"] = _set_ends(l["points"], src, dst)
        return blocks, lines

    def with_swap(self, a, b):
        blocks = copy.deepcopy(self.blocks0)
        pa = next(x["position"] for x in blocks if x["path"] == a)
        pb = next(x["position"] for x in blocks if x["path"] == b)
        for x in blocks:
            if x["path"] == a:
                x["position"] = list(pb)
            elif x["path"] == b:
                x["position"] = list(pa)
        lines = copy.deepcopy(self.lines0)
        for block in (a, b):
            for l in self.lines_touching(lines, block):
                src = port_pos(blocks, lines, block, l["src_port"], "out") if l.get("src_block") == block else None
                dst = port_pos(blocks, lines, block, l["dst_port"], "in") if l.get("dst_block") == block else None
                l["points"] = _set_ends(l["points"], src, dst)
        return blocks, lines

    def with_reorder(self, block, assign):
        lines = copy.deepcopy(self.lines0)
        for l in lines:
            if l.get("dst_block") == block and l["id"] in assign:
                l["dst_port"] = assign[l["id"]]
                dst = port_pos(self.blocks0, lines, block, assign[l["id"]], "in")
                l["points"] = _set_ends(l["points"], None, dst)
        return self.blocks0, lines

    def with_slot(self, line_id, kind, x):
        lines = copy.deepcopy(self.lines0)
        for l in lines:
            if l["id"] != line_id:
                continue
            pts = [list(p) for p in l["points"]]
            if kind == "corridor" and len(pts) >= 4:
                pts[1][0] = pts[2][0] = x
            elif kind == "exit" and len(pts) == 6:
                pts[1][0] = pts[2][0] = x
            elif kind == "approach" and len(pts) == 6:
                pts[3][0] = pts[4][0] = x
            else:
                return self.blocks0, self.lines0
            l["points"] = pts
        return self.blocks0, lines

    def gen_reorder(self, involved):
        dst_blocks = {l["dst_block"] for l in self.lines0 if l["id"] in involved}
        for B in sorted(dst_blocks):
            incoming = [l for l in self.lines0 if l.get("dst_block") == B]
            if len(incoming) < 2:
                continue
            fb = [l for l in incoming if role(l, self.blocks0) == "feedback_lane"]
            fw = [l for l in incoming if l not in fb]
            orders = [
                sorted(fb, key=lambda l: center_y(self.blocks0, l["src_block"])) +
                sorted(fw, key=lambda l: center_y(self.blocks0, l["src_block"])),
                sorted(incoming, key=lambda l: center_y(self.blocks0, l["src_block"])),
                sorted(incoming, key=lambda l: -center_y(self.blocks0, l["src_block"])),
            ]
            for order in orders:
                assign = {l["id"]: i for i, l in enumerate(order, start=1)}
                if all(assign[l["id"]] == l["dst_port"] for l in incoming):
                    continue
                self.try_cand({"op": "reorder_ports", "block": B, "assign": assign},
                              *self.with_reorder(B, assign),
                              reason=f"重排 {B} 目的端口（反馈置顶/按源高度），消除进线竖线切叶线")

    def gen_move(self, involved):
        for lid in sorted(involved):
            l = next(x for x in self.lines0 if x["id"] == lid)
            src, dst = l.get("src_block"), l.get("dst_block")
            if not src or not dst:
                continue
            out_y = port_pos(self.blocks0, self.lines0, src, l["src_port"], "out")[1]
            in_y = port_pos(self.blocks0, self.lines0, dst, l["dst_port"], "in")[1]
            delta = in_y - out_y
            if abs(delta) >= 1:
                b = next(x for x in self.blocks0 if x["path"] == src)
                newpos = [b["position"][0], b["position"][1] + delta,
                          b["position"][2], b["position"][3] + delta]
                self.try_cand({"op": "move_block", "block": src, "position": newpos},
                              *self.with_move(src, newpos),
                              reason=f"移动 {src} 使输出端口对齐 {dst} 入口高度，变直连去掉横穿段")
            # row swap within same column
            col = [x["path"] for x in self.blocks0
                   if x["path"] != src and abs(rect(x)[0] - rect(next(y for y in self.blocks0 if y["path"] == src))[0]) < 1]
            for other in col:
                self.try_cand({"op": "swap_blocks", "blocks": [src, other]},
                              *self.with_swap(src, other),
                              reason=f"交换同列 {src}/{other} 行序，改变端口高度关系")

    def gen_slot(self, involved):
        from layout_metrics import crossing as xcross
        m = measure(self.blocks0, self.lines0)
        for c in m["crossings"]:
            la = next(x for x in self.lines0 if x["id"] == c["line_a"])
            lb = next(x for x in self.lines0 if x["id"] == c["line_b"])
            for V, H in ((la, lb), (lb, la)):
                for vseg in _segs(V):
                    if not _isv(vseg):
                        continue
                    for hseg in _segs(H):
                        if not _ish(hseg) or not xcross(vseg, hseg):
                            continue
                        vx = vseg[0][0]
                        lo, hi = sorted((hseg[0][0], hseg[1][0]))
                        kind = self._vertical_kind(V, vseg)
                        if kind is None:
                            continue
                        for nx in (hi + 3, lo - 3):
                            self.try_cand({"op": "reassign_slot", "line": V["id"], "kind": kind, "x": nx},
                                          *self.with_slot(V["id"], kind, nx),
                                          reason=f"把 {V['id']} 的{kind}竖线移到 {H['id']} 横线跨度之外")

    def _vertical_kind(self, line, vseg):
        pts = line.get("points") or []
        r = role(line, self.blocks0)
        if len(pts) == 6 and r in ("feedback_lane", "multicolumn_lane"):
            if abs(pts[1][0] - vseg[0][0]) < 1 and abs(pts[2][0] - vseg[0][0]) < 1:
                return "exit"
            if abs(pts[3][0] - vseg[0][0]) < 1 and abs(pts[4][0] - vseg[0][0]) < 1:
                return "approach"
            return None
        if len(pts) >= 4 and abs(pts[1][0] - vseg[0][0]) < 1 and abs(pts[2][0] - vseg[0][0]) < 1:
            return "corridor"
        return None

    def gen_branch_tree(self, involved):
        # Phase 2 (structural, needs consent): collapse a radiating fanout into
        # a shared trunk + spine + leaves so fewer verticals cut other nets.
        groups = {}
        for l in self.lines0:
            if l.get("src_block"):
                groups.setdefault((l["src_block"], l.get("src_port") or 1), []).append(l)
        for (src, port), group in sorted(groups.items()):
            if len(group) < 2 or not any(l["id"] in involved for l in group):
                continue
            sb = next(x for x in self.blocks0 if x["path"] == src)
            sx = rect(sb)[2]
            sy = port_pos(self.blocks0, self.lines0, src, port, "out")[1]
            hgap = float((self.profile.get("spacing") or {}).get("horizontal", 60))
            for frac in (0.3, 0.6, 0.9):
                spine = round(sx + hgap * frac, 3)
                dys = [port_pos(self.blocks0, self.lines0, l["dst_block"], l["dst_port"], "in")[1]
                       for l in group]
                lines = copy.deepcopy(self.lines0)
                for l in lines:
                    if l.get("src_block") == src and (l.get("src_port") or 1) == port:
                        dy = port_pos(self.blocks0, self.lines0, l["dst_block"], l["dst_port"], "in")[1]
                        dx = rect(next(x for x in self.blocks0 if x["path"] == l["dst_block"]))[0]
                        l["points"] = [[sx, sy], [spine, sy], [spine, dy], [dx, dy]]
                op = {"op": "restructure_branch_tree", "source": {"block": src, "port": port},
                      "spine_x": spine, "edges": [l["id"] for l in group],
                      "structural": True, "requires_consent": True}
                self.try_cand(op, self.blocks0, lines,
                              reason=f"把 {src} 扇出改为共享干路+脊线+叶线（结构变更，需用户同意+SATK 重建分支）")

    def gen_goto(self, involved):
        # Phase 2 (structural, needs consent): bounded Goto/From conversion as
        # last resort after geometric means exhausted. Respects scope budget.
        used = sum(1 for b in self.blocks0 if b.get("type") == "Goto")
        functional = sum(1 for b in self.blocks0 if b.get("type") not in ("Goto", "From"))
        allowed = goto_budget(self.profile, functional)
        if used + 1 > allowed:
            return
        m = measure(self.blocks0, self.lines0)
        part = {}
        for c in m["crossings"]:
            for lid in (c["line_a"], c["line_b"]):
                part[lid] = part.get(lid, 0) + 1
        for lid, _n in sorted(part.items(), key=lambda kv: -kv[1]):
            l = next(x for x in self.lines0 if x["id"] == lid)
            src, dst = l.get("src_block"), l.get("dst_block")
            st = next((b.get("type") for b in self.blocks0 if b["path"] == src), "")
            dt = next((b.get("type") for b in self.blocks0 if b["path"] == dst), "")
            if st in ("Inport", "Goto", "From") or dt in ("Goto", "From"):
                continue
            sy = port_pos(self.blocks0, self.lines0, src, l["src_port"], "out")[1]
            dy = port_pos(self.blocks0, self.lines0, dst, l["dst_port"], "in")[1]
            sx = rect(next(x for x in self.blocks0 if x["path"] == src))[2]
            dx = rect(next(x for x in self.blocks0 if x["path"] == dst))[0]
            tag = f"{src.split('/')[-1]}_to_{dst.split('/')[-1]}"
            blocks = copy.deepcopy(self.blocks0)
            blocks.append({"path": f"{src}/G_{tag}", "type": "Goto", "position": [sx + 5, sy - 10, sx + 35, sy + 10],
                           "goto_tag": tag, "goto_tag_visibility": "local"})
            blocks.append({"path": f"{dst}/F_{tag}", "type": "From", "position": [dx - 35, dy - 10, dx - 5, dy + 10],
                           "goto_tag": tag, "goto_tag_visibility": ""})
            lines = [x for x in copy.deepcopy(self.lines0) if x["id"] != lid]
            lines.append({"id": f"{lid}_g", "points": [[sx, sy], [sx + 5, sy]],
                          "src_block": src, "src_port": l["src_port"], "dst_block": f"{src}/G_{tag}", "dst_port": 1})
            lines.append({"id": f"{lid}_f", "points": [[dx - 5, dy], [dx, dy]],
                          "src_block": f"{dst}/F_{tag}", "src_port": 1, "dst_block": dst, "dst_port": l["dst_port"]})
            op = {"op": "goto_from_conversion", "tag": tag, "line": lid,
                  "goto": f"{src}/G_{tag}", "from": f"{dst}/F_{tag}",
                  "structural": True, "requires_consent": True,
                  "budget": {"used": used, "allowed": allowed}}
            self.try_cand(op, blocks, lines,
                          reason=f"几何手段穷尽后受限转换 {lid} 为 Goto/From（预算 {used + 1}/{allowed}，需用户同意）")
            break  # one conversion per round

    def run(self, include_goto=False):
        involved = {l for c in measure(self.blocks0, self.lines0)["crossings"] for l in (c["line_a"], c["line_b"])}
        if not involved:
            return []
        self.gen_reorder(involved)
        self.gen_move(involved)
        self.gen_slot(involved)
        self.gen_branch_tree(involved)
        if include_goto or not self.cands:
            self.gen_goto(involved)
        self.cands.sort(key=lambda c: (-c["reduction"], c["op"]["op"]))
        return self.cands


def _segs(line):
    pts = line.get("points") or []
    return list(zip(pts, pts[1:]))


def _ish(s):
    return abs(s[0][1] - s[1][1]) <= 1


def _isv(s):
    return abs(s[0][0] - s[1][0]) <= 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-1 crossing-repair suggestions (ops JSON, never edits model)")
    parser.add_argument("geometry", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-suggestions", type=int, default=5)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--include-goto", action="store_true",
                        help="also emit bounded Goto/From conversion candidates (adjudication aid)")
    args = parser.parse_args()
    try:
        geo = json.loads(args.geometry.read_text(encoding="utf-8"))
        profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: cannot load geometry/profile: {exc}")
        return 2
    blocks, lines = geo.get("blocks") or [], geo.get("lines") or []
    s = Suggester(blocks, lines, profile)
    cands = s.run(include_goto=args.include_goto)[: args.max_suggestions]
    result = {
        "schema_version": SCHEMA,
        "model": geo.get("model"), "scope": geo.get("scope"),
        "current": s.cur,
        "suggestions": [{k: v for k, v in c.items() if k != "sig"} for c in cands],
        "previews_run": s.previews,
        "apply_contract": "每轮只应用一条建议（SATK model_edit），重新导出+layout_metrics 裁判；预演为近似端口高度，最终以实测为准；PNG 目视仍必须。",
        "stopped_reason": None if cands else ("no crossings" if s.cur["crossing_events"] == 0 else "no improving candidate in phase-1 neighborhood"),
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"scope {geo.get('scope')}: crossings={s.cur['crossing_events']} -> {len(cands)} suggestion(s), {s.previews} previews")
        for c in cands:
            print(f"  [{c['op']['op']}] -{c['reduction']} crossings -> {c['preview']['crossing_events']} | {c['reason']}")
            print(f"      targets: {', '.join(c['targets_crossings']) or '-'}")
        if not cands:
            print(f"  stopped: {result['stopped_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
