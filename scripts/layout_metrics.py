#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Appearance metrics for exported Simulink geometry (scope or whole model).

Counts the four things that make a diagram look bad -- crossings, collinear
overlaps, through-block segments, diagonal segments -- plus Goto/From budget
and baseline regression. This is a measurement, not a compliance audit:
readability (labels, recognizability, unnecessary bends) is closed by looking
at the rendered PNGs, never by this script.

Exit codes: 0 = clean; 1 = issues to repair (or document as tiny residual);
2 = input/schema invalid (fix the export, never treat as pass).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCHEMA = "maab.simulink_geometry/v2"
MANIFEST_SCHEMA = "maab.simulink_geometry_manifest/v2"
TOL = 1.0
HARD_METRICS = ("crossing_events", "overlap_events", "through_block_events", "diagonal_segments")


def rect(block: dict) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in block["position"])
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def segments(points: list) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    pts = [(float(p[0]), float(p[1])) for p in points]
    return list(zip(pts, pts[1:]))


def polyline_length(points: list) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segments(points))


def bend_count(points: list) -> int:
    dirs = []
    for a, b in segments(points):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy)
        if n > TOL:
            dirs.append((dx / n, dy / n))
    return sum(u[0] * v[0] + u[1] * v[1] < 1 - 1e-6 for u, v in zip(dirs, dirs[1:]))


def is_h(seg) -> bool:
    return abs(seg[0][1] - seg[1][1]) <= TOL


def is_v(seg) -> bool:
    return abs(seg[0][0] - seg[1][0]) <= TOL


def crossing(a, b) -> tuple[float, float] | None:
    if is_h(a) and is_v(b):
        x, y = b[0][0], a[0][1]
        a0, a1 = sorted((a[0][0], a[1][0]))
        b0, b1 = sorted((b[0][1], b[1][1]))
        if a0 + TOL < x < a1 - TOL and b0 + TOL < y < b1 - TOL:
            return x, y
    elif is_v(a) and is_h(b):
        return crossing(b, a)
    return None


def overlap(a, b) -> tuple[float, float] | None:
    if is_h(a) and is_h(b) and abs(a[0][1] - b[0][1]) <= TOL:
        lo, hi = max(min(a[0][0], a[1][0]), min(b[0][0], b[1][0])), min(
            max(a[0][0], a[1][0]), max(b[0][0], b[1][0]))
        if hi - lo > 2 * TOL:
            return (lo + hi) / 2, a[0][1]
    if is_v(a) and is_v(b) and abs(a[0][0] - b[0][0]) <= TOL:
        lo, hi = max(min(a[0][1], a[1][1]), min(b[0][1], b[1][1])), min(
            max(a[0][1], a[1][1]), max(b[0][1], b[1][1]))
        if hi - lo > 2 * TOL:
            return a[0][0], (lo + hi) / 2
    return None


def hits_interior(seg, box) -> bool:
    x0, y0, x1, y1 = box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2
    if is_h(seg):
        y = seg[0][1]
        lo, hi = sorted((seg[0][0], seg[1][0]))
        return y0 < y < y1 and hi > x0 and lo < x1
    if is_v(seg):
        x = seg[0][0]
        lo, hi = sorted((seg[0][1], seg[1][1]))
        return x0 < x < x1 and hi > y0 and lo < y1
    return False


def port_key(value: Any) -> int:
    """Unresolved ports export as [] / null; normalize to a scalar sentinel."""
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def net_key(line: dict) -> tuple[str, int]:
    return str(line.get("src_block") or ""), port_key(line.get("src_port"))


def measure(blocks: list[dict], lines: list[dict]) -> dict[str, Any]:
    boxes = {b["path"]: rect(b) for b in blocks}
    prepared = []
    for line in lines:
        pts = line.get("points") or []
        prepared.append({**line, "segs": segments(pts) if len(pts) >= 2 else [],
                         "bends": bend_count(pts), "length": polyline_length(pts)})

    diagonals, through, crossings, overlaps = [], [], [], []
    seen_cross, seen_over, seen_through = set(), set(), set()
    pairs = set()
    for line in prepared:
        ends = {line.get("src_block"), line.get("dst_block")}
        for seg in line["segs"]:
            if not (is_h(seg) or is_v(seg)):
                diagonals.append({"line": line["id"], "start": list(seg[0]), "end": list(seg[1])})
            for path, box in boxes.items():
                if path in ends or not hits_interior(seg, box):
                    continue
                key = (line["id"], path)
                if key not in seen_through:
                    seen_through.add(key)
                    through.append({"line": line["id"], "block": path})
    for i, first in enumerate(prepared):
        for second in prepared[i + 1:]:
            same_net = net_key(first) == net_key(second)
            for sa in first["segs"]:
                for sb in second["segs"]:
                    pt = crossing(sa, sb)
                    if pt:
                        key = (first["id"], second["id"], round(pt[0], 3), round(pt[1], 3))
                        if key not in seen_cross:
                            seen_cross.add(key)
                            crossings.append({"line_a": first["id"], "line_b": second["id"],
                                              "point": list(pt)})
                            pairs.add(tuple(sorted((net_key(first), net_key(second)))))
                    pt = overlap(sa, sb)
                    if pt and not same_net:
                        key = (first["id"], second["id"], round(pt[0], 3), round(pt[1], 3))
                        if key not in seen_over:
                            seen_over.add(key)
                            overlaps.append({"line_a": first["id"], "line_b": second["id"],
                                             "point": list(pt)})

    gotos = [b for b in blocks if b.get("type") == "Goto"]
    froms = [b for b in blocks if b.get("type") == "From"]
    by_tag_from = defaultdict(list)
    for b in froms:
        by_tag_from[str(b.get("goto_tag") or "")].append(b)
    tags_goto = {str(b.get("goto_tag") or "") for b in gotos}
    violations = []
    for b in gotos:
        tag, vis = str(b.get("goto_tag") or ""), str(b.get("goto_tag_visibility") or "")
        if not tag:
            violations.append({"kind": "missing_tag", "block": b["path"]})
        if vis != "local":
            violations.append({"kind": "visibility_not_local", "block": b["path"], "value": vis})
        if tag and tag not in by_tag_from:
            violations.append({"kind": "unpaired_goto", "block": b["path"], "tag": tag})
    for b in froms:
        tag = str(b.get("goto_tag") or "")
        if not tag:
            violations.append({"kind": "missing_tag", "block": b["path"]})
        elif tag not in tags_goto:
            violations.append({"kind": "unpaired_from", "block": b["path"], "tag": tag})
    for tag, fs in by_tag_from.items():
        if tag and len(fs) > 2:
            violations.append({"kind": "froms_per_tag_exceeded", "tag": tag, "count": len(fs)})
    types = {b["path"]: b.get("type") for b in blocks}
    for line in prepared:
        st, dt = types.get(line.get("src_block")), types.get(line.get("dst_block"))
        if dt == "Goto" and st == "Inport":
            violations.append({"kind": "inport_to_goto", "line": line["id"]})
        if dt == "Goto" and st == "From":
            violations.append({"kind": "from_to_goto_chaining", "line": line["id"]})

    involved = set()
    for ev in crossings:
        involved.update((ev["line_a"], ev["line_b"]))
    summary = {
        "line_count": len(prepared),
        "crossing_events": len(crossings),
        "crossing_pairs": len(pairs),
        "overlap_events": len(overlaps),
        "through_block_events": len(through),
        "diagonal_segments": len(diagonals),
        "goto_from_blocks": len(gotos) + len(froms),
        "goto_from_pairs": len(gotos),
        "functional_block_count": len(blocks) - len(gotos) - len(froms),
        "total_bends": sum(l["bends"] for l in prepared),
        "total_length": round(sum(l["length"] for l in prepared), 3),
        "max_bends": max((l["bends"] for l in prepared), default=0),
    }
    return {"summary": summary, "crossings": crossings, "overlaps": overlaps,
            "through_blocks": through, "diagonal_segments": diagonals,
            "goto_violations": violations, "involved_lines": sorted(involved),
            "line_metrics": [{"id": l["id"], "bends": l["bends"],
                              "length": round(l["length"], 3)} for l in prepared]}


def goto_budget(profile: dict, functional_blocks: int) -> int:
    policy = profile.get("goto_from") or {}
    allowed = 0
    for tier in policy.get("budget_tiers") or []:
        cap, pairs = tier[0], tier[1]
        if cap is None or functional_blocks <= cap:
            allowed = pairs
            break
    return min(allowed, int(policy.get("hard_cap", 3)))


def validate(geo: Any) -> list[str]:
    errors = []
    if not isinstance(geo, dict):
        return ["geometry root must be an object"]
    for key in ("schema_version", "model", "scope", "blocks", "lines", "coordinate_frame"):
        if key not in geo:
            errors.append(f"missing field: {key}")
    if errors:
        return errors
    if geo["schema_version"] != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")
    if geo["coordinate_frame"] != "scope-local":
        errors.append("coordinate_frame must be scope-local")
    if not isinstance(geo["blocks"], list) or not isinstance(geo["lines"], list):
        errors.append("blocks and lines must be arrays")
        return errors
    scope = str(geo["scope"]).rstrip("/")
    paths = set()
    for b in geo["blocks"]:
        if not isinstance(b, dict) or not b.get("path") or not isinstance(b.get("position"), list) \
                or len(b["position"]) != 4:
            errors.append(f"invalid block entry: {b!r}")
            continue
        path = str(b["path"]).rstrip("/")
        if path.rsplit("/", 1)[0] != scope:
            errors.append(f"block {path} is not a direct child of {scope}")
        paths.add(path)
    for line in geo["lines"]:
        if not isinstance(line, dict) or not line.get("id"):
            errors.append(f"invalid line entry: {line!r}")
            continue
        for end in ("src_block", "dst_block"):
            if line.get(end) and str(line[end]).rstrip("/") not in paths:
                errors.append(f"line {line['id']} endpoint {line[end]} outside scope")
    return errors


def evaluate(geo: dict, profile: dict, baseline: dict | None = None) -> dict:
    errors = validate(geo)
    if errors:
        return {"status": "INVALID", "schema_errors": errors, "model": geo.get("model"),
                "scope": geo.get("scope")}
    m = measure(geo["blocks"], geo["lines"])
    issues = []
    for key in HARD_METRICS:
        if m["summary"][key]:
            issues.append(f"{key}={m['summary'][key]}")
    used = m["summary"]["goto_from_pairs"]
    allowed = goto_budget(profile, m["summary"]["functional_block_count"])
    if used > allowed:
        issues.append(f"goto_from_pairs={used} over budget {allowed}")
    for v in m["goto_violations"]:
        issues.append(f"goto:{v['kind']}")
    delta = None
    if baseline is not None:
        berrors = validate(baseline)
        if berrors or str(baseline.get("model")) != str(geo.get("model")) or \
                str(baseline.get("scope")).rstrip("/") != str(geo.get("scope")).rstrip("/"):
            issues.append("baseline invalid or model/scope mismatch")
        else:
            bm = measure(baseline["blocks"], baseline["lines"])["summary"]
            delta = {k: m["summary"][k] - bm[k] for k in HARD_METRICS}
            delta["goto_from_pairs"] = used - bm["goto_from_pairs"]
            for k, d in delta.items():
                if d > 0:
                    issues.append(f"regression vs baseline: {k} +{d}")
    residual = profile.get("residual") or {}
    hop = (geo.get("source_settings") or {}).get("line_crossing") or {}
    other_hard = any(m["summary"][k] for k in HARD_METRICS if k != "crossing_events")
    regressed = bool(delta and any(d > 0 for d in delta.values()))
    residual_ok = (
        0 < m["summary"]["crossing_events"] <= residual.get("max_crossing_events", 2)
        and len(m["involved_lines"]) <= residual.get("max_involved_lines", 2)
        and not other_hard and not m["goto_violations"] and used <= allowed and not regressed
    )
    result = {
        "schema_version": "maab.simulink_metrics/v2",
        "model": geo["model"], "scope": geo["scope"],
        "status": "ISSUES" if issues else "CLEAN",
        "summary": m["summary"], "issues": issues,
        "crossings": m["crossings"], "overlaps": m["overlaps"],
        "through_blocks": m["through_blocks"], "diagonal_segments": m["diagonal_segments"],
        "goto_violations": m["goto_violations"],
        "goto_budget": {"used_pairs": used, "allowed_pairs": allowed,
                        "functional_blocks": m["summary"]["functional_block_count"]},
        "line_metrics": m["line_metrics"],
        "baseline_delta": delta,
        "residual": {
            "eligible": residual_ok,
            "crossing_events": m["summary"]["crossing_events"],
            "involved_lines": m["involved_lines"],
            "editor_crossing_style": hop.get("value") if hop.get("status") == "observed" else None,
            "note": "残留仅在交付报告书面列出线对、且最终 PNG 逐张复核后才可接受。",
        },
    }
    return result


def load_manifest(path: Path) -> tuple[dict | None, list[str]]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot load manifest: {exc}"]
    errors = []
    if not isinstance(manifest, dict):
        return None, ["manifest root must be an object"]
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        errors.append(f"manifest schema must be {MANIFEST_SCHEMA}")
    if manifest.get("status") != "COMPLETE":
        errors.append(f"manifest status={manifest.get('status')}")
    coverage = manifest.get("coverage") or {}
    if coverage.get("all_hierarchy") is not True or coverage.get("export_errors"):
        errors.append("manifest coverage incomplete or export errors recorded")
    scopes = manifest.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        errors.append("manifest.scopes must be a non-empty array")
        return manifest, errors
    base = path.resolve().parent
    for entry in scopes:
        if not isinstance(entry, dict) or entry.get("status") != "EXPORTED":
            errors.append(f"scope entry not EXPORTED: {entry!r}")
            continue
        geo_path = base / str(entry.get("geometry_file"))
        try:
            geo = json.loads(geo_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot load {geo_path}: {exc}")
            continue
        if str(geo.get("scope")).rstrip("/") != str(entry.get("scope")).rstrip("/") or \
                str(geo.get("model")) != str(manifest.get("model")):
            errors.append(f"scope/model mismatch in {geo_path}")
        entry["_geo"] = geo
    return manifest, errors


def aggregate(manifest: dict, profile: dict, baseline_manifest: dict | None) -> dict:
    errors = []
    base_by_scope = {}
    if baseline_manifest is not None:
        bmanifest, berrors = load_manifest(Path(baseline_manifest))
        errors += [f"baseline: {e}" for e in berrors]
        if bmanifest:
            if str(bmanifest.get("model")) != str(manifest.get("model")):
                errors.append("baseline model mismatch")
            for entry in bmanifest.get("scopes") or []:
                if isinstance(entry, dict) and entry.get("_geo"):
                    base_by_scope[str(entry["scope"]).rstrip("/")] = entry["_geo"]
    per_scope, totals = [], Counter()
    for entry in manifest.get("scopes") or []:
        geo = entry.get("_geo")
        if not geo:
            continue
        scope = str(entry["scope"]).rstrip("/")
        report = evaluate(geo, profile, base_by_scope.get(scope))
        per_scope.append({"scope": scope, **report})
        if report["status"] != "INVALID":
            for k, v in report["summary"].items():
                if isinstance(v, (int, float)):
                    totals[k] += v
    invalid = [s for s in per_scope if s["status"] == "INVALID"]
    issues = [s for s in per_scope if s["status"] == "ISSUES"]
    hotspots = sorted(issues, key=lambda s: (-s["summary"]["crossing_events"],
                                             -s["summary"]["overlap_events"],
                                             -s["summary"]["through_block_events"],
                                             -s["summary"]["diagonal_segments"], s["scope"]))
    for s in hotspots:
        actions = []
        if s["summary"]["crossing_events"]:
            actions.append("按交叉线对调整端口纵向顺序/功能列/专用走廊；扇出>2 拆分支树")
        if s["summary"]["overlap_events"]:
            actions.append("分开共线线段（不同信号不得共享线段）")
        if s["summary"]["through_block_events"]:
            actions.append("重走线绕开块")
        if s["summary"]["diagonal_segments"]:
            actions.append("改为水平/垂直正交走线")
        if s["goto_violations"] or s["goto_budget"]["used_pairs"] > s["goto_budget"]["allowed_pairs"]:
            actions.append("收敛 Goto/From：核对预算、配对、local 可见性与直连禁令")
        s["next_actions"] = actions
    status = "INVALID" if (errors or invalid) else ("ISSUES" if issues else "CLEAN")
    return {"schema_version": "maab.simulink_model_metrics/v2",
            "model": manifest.get("model"), "status": status, "schema_errors": errors,
            "summary": dict(totals), "per_scope": per_scope,
            "repair_order": [s["scope"] for s in hotspots],
            "scope_count": len(per_scope)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulink appearance metrics (not a compliance audit)")
    parser.add_argument("geometry", nargs="?", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--profile", type=Path,
                        default=Path(__file__).resolve().parent.parent / "assets" / "layout-profile.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if bool(args.geometry) == bool(args.manifest):
        parser.error("provide exactly one of geometry or --manifest")
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: cannot load profile: {exc}")
        return 2

    if args.manifest:
        manifest, errors = load_manifest(args.manifest)
        if manifest is None or errors:
            print(f"INVALID: {errors}")
            return 2
        result = aggregate(manifest, profile, args.baseline)
        result["schema_errors"] = errors + result["schema_errors"]
        if errors:
            result["status"] = "INVALID"
        code = 2 if result["status"] == "INVALID" else (1 if result["status"] == "ISSUES" else 0)
    else:
        try:
            geo = json.loads(args.geometry.read_text(encoding="utf-8"))
            baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
        except (OSError, json.JSONDecodeError) as exc:
            print(f"INVALID: cannot load geometry: {exc}")
            return 2
        result = evaluate(geo, profile, baseline)
        code = 2 if result["status"] == "INVALID" else (1 if result["status"] == "ISSUES" else 0)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        s = result.get("summary") or {}
        print(f"{result['status']}: {args.manifest or args.geometry} | "
              f"crossings={s.get('crossing_events', '?')} overlaps={s.get('overlap_events', '?')} "
              f"through={s.get('through_block_events', '?')} diagonals={s.get('diagonal_segments', '?')} "
              f"goto_pairs={s.get('goto_from_pairs', '?')} bends={s.get('total_bends', '?')} "
              f"length={s.get('total_length', '?')}")
        for err in result.get("schema_errors") or []:
            print(f"[SCHEMA] {err}")
        scopes = result.get("per_scope") or [result]
        for sc in scopes:
            if sc.get("status") == "CLEAN":
                continue
            for issue in sc.get("issues") or []:
                print(f"[{sc.get('scope')}] {issue}")
            for action in sc.get("next_actions") or []:
                print(f"    处理: {action}")
            res = sc.get("residual") or {}
            if res.get("crossing_events") and res.get("eligible"):
                print(f"    残留可书面遗留: {res['crossing_events']} 交叉 / 线 {res['involved_lines']} "
                      f"(editor style={res.get('editor_crossing_style')})；须 PNG 复核并列入交付报告")
        if code == 0:
            print("几何度量干净；仍须逐张查看最终 PNG 关闭可读性（标签/可辨识/多余折弯）。")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
