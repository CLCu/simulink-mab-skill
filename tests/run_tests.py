# -*- coding: utf-8 -*-
"""Regression tests for the appearance-only skill (run: python tests/run_tests.py).

Covers the bugs found in the v1 audit: single-scope manifest schema, fail-open
exit codes, branch-tree false violation, unresolved-port crash, planner
feedback-lane overlaps, and Stateflow junction-ancestor through-state false
positive. Fixtures are synthetic; no MATLAB needed.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FX = Path(tempfile.mkdtemp(prefix="mab-skill-fx-"))
PY = sys.executable
FAILURES = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" | {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def run(script, *args):
    p = subprocess.run([PY, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p


def block(path, pos, btype="Gain", **extra):
    return {"path": path, "type": btype, "position": pos, **extra}


def line(lid, pts, src, sp, dst, dp):
    return {"id": lid, "points": pts, "src_block": src, "src_port": sp,
            "dst_block": dst, "dst_port": dp}


def geo(blocks, lines, scope="M"):
    return {"schema_version": "maab.simulink_geometry/v2", "model": "M", "scope": scope,
            "coordinate_frame": "scope-local", "blocks": blocks, "lines": lines,
            "source_settings": {"line_crossing": {"status": "observed", "value": "hop"}},
            "coverage": {}}


def write(name, value):
    path = FX / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


# --- clean single scope + single-scope manifest (v1 P0-1) ---
clean = geo([block("M/Src", [0, 0, 40, 40]), block("M/Dst", [140, 0, 180, 40])],
            [line("line_1", [[40, 20], [140, 20]], "M/Src", 1, "M/Dst", 1)])
gpath = write("fx_clean.json", clean)
p = run("layout_metrics.py", gpath)
check("clean scope exit 0", p.returncode == 0, p.stdout + p.stderr)
manifest = {"schema_version": "maab.simulink_geometry_manifest/v2", "model": "M",
            "status": "COMPLETE", "scope_count": 1,
            "scopes": [{"scope": "M", "geometry_file": "fx_clean.json", "status": "EXPORTED"}],
            "coverage": {"all_hierarchy": True, "coordinate_frames_mixed": False, "export_errors": []}}
mpath = write("fx_manifest_single.json", manifest)
p = run("layout_metrics.py", "--manifest", mpath)
check("single-scope manifest exit 0 (v1 P0-1)", p.returncode == 0, p.stdout + p.stderr)

# --- legal binary branch tree, 3 consumers: no fanout gate (v1 P0-3) ---
tree = geo([block("M/Src", [0, 0, 40, 40]), block("M/A", [140, 0, 180, 40]),
            block("M/B", [140, 80, 180, 120]), block("M/C", [140, 160, 180, 200])],
           [line("line_1", [[40, 20], [140, 20]], "M/Src", 1, "M/A", 1),
            line("line_2", [[70, 20], [70, 180], [140, 180]], "M/Src", 1, "M/C", 1),
            line("line_3", [[90, 20], [90, 100], [140, 100]], "M/Src", 1, "M/B", 1)])
p = run("layout_metrics.py", write("fx_tree.json", tree))
check("branch tree not flagged (v1 P0-3)", p.returncode == 0, p.stdout + p.stderr)

# --- unresolved branch ports ([] / null) must not crash (v1 P1-6) ---
nullport = geo([block("M/Src", [0, 0, 40, 40]), block("M/A", [140, 0, 180, 40]),
                block("M/B", [140, 80, 180, 120])],
               [line("line_1", [[40, 20], [140, 20]], "M/Src", 1, "M/A", 1),
                line("line_2", [[70, 20], [70, 100], [140, 100]], "M/Src", [], "M/B", 1)])
p = run("layout_metrics.py", write("fx_nullport.json", nullport))
check("unresolved port no crash", p.returncode in (0, 1) and "Traceback" not in p.stderr, p.stderr)

# --- crossings -> 1 ; bad schema -> 2 (exit contract, v1 P0-2 analogue) ---
cross = geo([block("M/Src", [0, 0, 40, 40]), block("M/Dst", [140, 0, 180, 40]),
             block("M/S2", [0, 80, 40, 120]), block("M/D2", [140, 80, 180, 120])],
            [line("line_1", [[40, 20], [140, 20]], "M/Src", 1, "M/Dst", 1),
             line("line_2", [[70, 0], [70, 100]], "M/S2", 1, "M/D2", 1)])
p = run("layout_metrics.py", write("fx_cross.json", cross))
check("crossings exit 1", p.returncode == 1, p.stdout)
bad = write("fx_bad.json", {"schema_version": "nope"})
p = run("layout_metrics.py", bad)
check("bad schema exit 2", p.returncode == 2, p.stdout)
p = run("layout_metrics.py", "--manifest", write("fx_manifest_bad.json",
        {**manifest, "scopes": {"scope": "M"}}))
check("manifest scopes-as-object exit 2", p.returncode == 2, p.stdout)

# --- baseline regression detected ---
p = run("layout_metrics.py", write("fx_cross.json", cross), "--baseline", gpath)
check("baseline regression exit 1", p.returncode == 1 and "regression" in p.stdout, p.stdout)
mcross = write("fx_manifest_cross.json",
               {**manifest, "scopes": [{"scope": "M", "geometry_file": "fx_cross.json",
                                       "status": "EXPORTED"}]})
p = run("layout_metrics.py", "--manifest", mpath, "--baseline", mpath)
check("manifest identical baseline exit 0", p.returncode == 0, p.stdout + p.stderr)
p = run("layout_metrics.py", "--manifest", mcross, "--baseline", mpath)
check("manifest baseline regression exit 1", p.returncode == 1 and "regression" in p.stdout, p.stdout)

# --- goto budget ---
gotogeo = geo([block("M/Src", [0, 0, 40, 40]), block("M/Dst", [200, 0, 240, 40]),
               block("M/G1", [80, 0, 110, 20], "Goto", goto_tag="t1", goto_tag_visibility="local"),
               block("M/F1", [150, 0, 180, 20], "From", goto_tag="t1"),
               block("M/G2", [80, 60, 110, 80], "Goto", goto_tag="t2", goto_tag_visibility="local"),
               block("M/F2", [150, 60, 180, 80], "From", goto_tag="t2")],
              [line("l1", [[40, 10], [80, 10]], "M/Src", 1, "M/G1", 1),
               line("l2", [[110, 10], [150, 10]], "M/F1", 1, "M/Dst", 1),
               line("l3", [[40, 70], [80, 70]], "M/Src", 1, "M/G2", 1),
               line("l4", [[110, 70], [150, 70]], "M/F2", 1, "M/Dst", 1)])
p = run("layout_metrics.py", write("fx_goto.json", gotogeo))
check("goto over budget exit 1", p.returncode == 1 and "budget" in p.stdout, p.stdout)

# --- planner: feedback lanes distinct, forward cycle edge direct (v1 P1-5) ---
spec = {"model": "M", "blocks": [{"id": x, "type": "Gain"} for x in "ABCD"],
        "edges": [["A", "B"], ["B", "A"], ["C", "D"], ["D", "C"]]}
spath = write("fx_spec.json", spec)
ppath = FX / "fx_spec_plan.json"
p = run("layout_plan.py", spath, "--out", ppath)
plan = json.loads(ppath.read_text(encoding="utf-8"))
bad_findings = [f for f in plan["plan_level_findings"] if f["kind"].startswith("planner_")]
check("planner guarantees hold (no overlap/diagonal/through)", not bad_findings, str(bad_findings))
kinds = {e["id"]: e["route_kind"] for e in plan["edges"]}
check("forward cycle edge routes direct", kinds["edge_1"] in ("straight", "corridor"), str(kinds))
lanes = [l["y"] for l in plan["lanes"]]
check("feedback lanes distinct y", len(lanes) == len(set(lanes)) and len(lanes) == 2, str(lanes))

# --- planner: multi-column forward edge avoids intermediate blocks ---
spec2 = {"model": "M", "blocks": [{"id": "A", "type": "Gain"}, {"id": "B", "type": "Gain"},
                                  {"id": "D", "type": "Sum", "ports": [2, 1]}],
         "edges": [["A", "B"], ["B", "D"], ["A", "D"]]}
p = run("layout_plan.py", write("fx_spec2.json", spec2), "--out", FX / "fx_spec2_plan.json")
plan2 = json.loads((FX / "fx_spec2_plan.json").read_text(encoding="utf-8"))
bad2 = [f for f in plan2["plan_level_findings"] if f["kind"].startswith("planner_")]
check("multi-column edge no through-block", not bad2, str(bad2))

# --- chart metrics: junction inside state excluded from through-state (v1 P2) ---
chart = {"schema_version": "maab.stateflow_geometry/v2", "model": "M", "chart_path": "M/Chart",
         "chart": {"id": "chart_1", "path": "M/Chart"},
         "states": [{"id": "sA", "name": "A", "parent_id": "chart_1", "position": [0, 0, 80, 60]},
                    {"id": "sS", "name": "S", "parent_id": "chart_1", "position": [200, 0, 400, 200]},
                    {"id": "sB", "name": "B", "parent_id": "sS", "position": [220, 20, 300, 80]}],
         "junctions": [{"id": "jJ", "parent_id": "sS", "center": [350, 150], "radius": 5}],
         "transitions": [
             {"id": "t1", "label": "", "source_kind": "state", "source_id": "sA",
              "destination_kind": "junction", "destination_id": "jJ",
              "source_endpoint": [80, 30], "destination_endpoint": [350, 150],
              "midpoints": [[150, 30], [150, 150]]},
             {"id": "t2", "label": "", "source_kind": "junction", "source_id": "jJ",
              "destination_kind": "state", "destination_id": "sB",
              "source_endpoint": [350, 150], "destination_endpoint": [300, 50],
              "midpoints": [[350, 50]]}]}
p = run("chart_metrics.py", write("fx_chart.json", chart), "--json")
rep = json.loads(p.stdout)
check("junction-container not through-state", rep["through_state_events"] == 0, p.stdout)
check("chart metrics advisory exit 0", p.returncode == 0, p.stderr)

# --- repair_suggest: reorder_ports removes feedback-cutting-leaf crossings ---
def sblock(path, pos, btype="Gain", **extra):
    return {"path": path, "type": btype, "position": pos, **extra}


def sline(lid, pts, src, sp, dst, dp):
    return {"id": lid, "points": pts, "src_block": src, "src_port": sp,
            "dst_block": dst, "dst_port": dp}


reorder_geo = geo([
    sblock("M/S1", [130, 40, 170, 80]), sblock("M/S2", [130, 120, 170, 160]),
    sblock("M/B", [230, 80, 270, 120], "Sum"),
    sblock("M/D1", [430, 90, 470, 130]), sblock("M/D2", [430, 170, 470, 210])],
    [sline("f1", [[170, 60], [190, 60], [190, 88], [230, 88]], "M/S1", 1, "M/B", 1),
     sline("f2", [[170, 140], [200, 140], [200, 96], [230, 96]], "M/S2", 1, "M/B", 2),
     sline("r1", [[470, 110], [510, 110], [510, -20], [222, -20], [222, 104], [230, 104]], "M/D1", 1, "M/B", 3),
     sline("r2", [[470, 190], [520, 190], [520, -40], [217, -40], [217, 112], [230, 112]], "M/D2", 1, "M/B", 4)])
p = run("repair_suggest.py", write("fx_reorder.json", reorder_geo), "--json")
rep = json.loads(p.stdout)
ops = [s["op"]["op"] for s in rep["suggestions"]]
check("suggester emits reorder_ports", "reorder_ports" in ops, str(ops))
best = rep["suggestions"][0]
check("reorder preview reduces 4->0", rep["current"]["crossing_events"] == 4
      and best["preview"]["crossing_events"] == 0, json.dumps(best["preview"]))

# --- repair_suggest: move_block height alignment removes a corridor crossing ---
move_geo = geo([
    sblock("M/In2", [30, 120, 60, 134], "Inport"),
    sblock("M/S1", [130, 40, 170, 80]), sblock("M/S2", [130, 120, 170, 160]),
    sblock("M/B", [230, 80, 270, 120], "Sum"), sblock("M/G3", [230, 160, 270, 200])],
    [sline("i2", [[60, 127], [100, 127], [100, 140], [130, 140]], "M/In2", 1, "M/S2", 1),
     sline("f2", [[170, 140], [200, 140], [200, 96], [230, 96]], "M/S2", 1, "M/B", 2),
     sline("v1", [[170, 60], [193, 60], [193, 180], [230, 180]], "M/S1", 1, "M/G3", 1)])
p = run("repair_suggest.py", write("fx_move.json", move_geo), "--json")
rep = json.loads(p.stdout)
ops = [s["op"]["op"] for s in rep["suggestions"]]
check("suggester emits move_block", "move_block" in ops, str(ops))
check("move preview reduces crossings", rep["current"]["crossing_events"] >= 1
      and rep["suggestions"][0]["preview"]["crossing_events"] < rep["current"]["crossing_events"],
      json.dumps(rep["suggestions"][0]["preview"]))

# --- repair_suggest: reassign_slot moves a vertical out of a horizontal span ---
slot_geo = geo([
    sblock("M/G1", [130, 40, 170, 80]), sblock("M/G3", [230, 160, 270, 200]),
    sblock("M/Sw", [330, 90, 370, 130], "Switch")],
    [sline("c1", [[270, 180], [290, 180], [290, 120], [330, 120]], "M/G3", 1, "M/Sw", 3),
     sline("l1", [[170, 60], [176, 60], [176, 300], [319, 300], [319, 110], [330, 110]], "M/G1", 1, "M/Sw", 2)])
p = run("repair_suggest.py", write("fx_slot.json", slot_geo), "--json")
rep = json.loads(p.stdout)
ops = [s["op"]["op"] for s in rep["suggestions"]]
check("suggester emits reassign_slot", "reassign_slot" in ops, str(ops))
check("slot preview reduces crossings", rep["current"]["crossing_events"] >= 1
      and rep["suggestions"][0]["preview"]["crossing_events"] < rep["current"]["crossing_events"],
      json.dumps(rep["suggestions"][0]["preview"]))

# --- clean geometry -> no suggestions; all suggestions strictly improve ---
p = run("repair_suggest.py", gpath, "--json")
rep = json.loads(p.stdout)
check("clean geometry no suggestions", rep["suggestions"] == []
      and rep["stopped_reason"] == "no crossings", json.dumps(rep["stopped_reason"]))
for fx in ("fx_reorder.json", "fx_move.json", "fx_slot.json"):
    p = run("repair_suggest.py", FX / fx, "--json")
    rep = json.loads(p.stdout)
    ok = all(s["preview"]["crossing_events"] < rep["current"]["crossing_events"]
             and all(s["preview"][k] <= rep["current"][k]
                     for k in ("overlap_events", "through_block_events", "diagonal_segments"))
             for s in rep["suggestions"])
    check(f"{fx}: every suggestion improves & never worsens other hard metrics", ok)

# --- phase 2: branch-tree restructure suggestion (structural, consent) ---
tree_geo = geo([
    sblock("M/S", [0, 0, 40, 40]), sblock("M/A", [200, 0, 240, 40]),
    sblock("M/B", [200, 80, 240, 120]), sblock("M/C", [200, 160, 240, 200]),
    sblock("M/T", [60, -20, 80, 0]), sblock("M/U", [60, 200, 80, 220])],
    [sline("eA", [[40, 20], [200, 20]], "M/S", 1, "M/A", 1),
     sline("eB", [[40, 20], [60, 20], [60, 100], [200, 100]], "M/S", 1, "M/B", 1),
     sline("eC", [[40, 20], [80, 20], [80, 180], [200, 180]], "M/S", 1, "M/C", 1),
     sline("v", [[70, -10], [70, 210]], "M/T", 1, "M/U", 1)])
p = run("repair_suggest.py", write("fx_btree.json", tree_geo), "--json")
rep = json.loads(p.stdout)
bt = [s for s in rep["suggestions"] if s["op"]["op"] == "restructure_branch_tree"]
check("phase2 emits branch-tree suggestion", bool(bt), str([s["op"]["op"] for s in rep["suggestions"]]))
if bt:
    check("branch-tree improves & flagged consent/structural",
          bt[0]["preview"]["crossing_events"] < rep["current"]["crossing_events"]
          and bt[0]["op"]["requires_consent"] and bt[0]["op"]["structural"],
          json.dumps(bt[0]["op"]))

# --- phase 2: goto conversion only via flag / after exhaustion; consent+budget ---
# Crossing in the MIDDLE of a long line so the Goto/From stubs stay clean.
goto_mid = geo([
    sblock("M/S", [0, 0, 40, 40]), sblock("M/D", [400, 0, 440, 40]),
    sblock("M/T", [200, -40, 220, -20]), sblock("M/U", [200, 60, 220, 80])],
    [sline("L", [[40, 20], [400, 20]], "M/S", 1, "M/D", 1),
     sline("V", [[210, -30], [210, 70]], "M/T", 1, "M/U", 1)])
p = run("repair_suggest.py", write("fx_goto_mid.json", goto_mid), "--json", "--include-goto")
rep = json.loads(p.stdout)
gt = [s for s in rep["suggestions"] if s["op"]["op"] == "goto_from_conversion"]
check("goto candidate with --include-goto", bool(gt), str([s["op"]["op"] for s in rep["suggestions"]]))
if gt:
    check("goto flagged consent + within budget",
          gt[0]["op"]["requires_consent"] and gt[0]["op"]["budget"]["used"] + 1 <= gt[0]["op"]["budget"]["allowed"],
          json.dumps(gt[0]["op"]))
p = run("repair_suggest.py", FX / "fx_slot.json", "--json")
rep = json.loads(p.stdout)
check("ladder: no goto while phase-1 improves",
      all(s["op"]["op"] != "goto_from_conversion" for s in rep["suggestions"]),
      str([s["op"]["op"] for s in rep["suggestions"]]))
over = geo([
    sblock("M/G1", [130, 40, 170, 80]), sblock("M/G3", [230, 160, 270, 200]),
    sblock("M/Sw", [330, 90, 370, 130], "Switch"),
    sblock("M/Ga", [80, 0, 110, 20], "Goto", goto_tag="t1", goto_tag_visibility="local"),
    sblock("M/Fa", [150, 0, 180, 20], "From", goto_tag="t1"),
    sblock("M/Gb", [80, 60, 110, 80], "Goto", goto_tag="t2", goto_tag_visibility="local"),
    sblock("M/Fb", [150, 60, 180, 80], "From", goto_tag="t2")],
    [sline("c1", [[270, 180], [290, 180], [290, 120], [330, 120]], "M/G3", 1, "M/Sw", 3),
     sline("l1", [[170, 60], [176, 60], [176, 300], [319, 300], [319, 110], [330, 110]], "M/G1", 1, "M/Sw", 2),
     sline("ga", [[40, 10], [80, 10]], "M/G1", 1, "M/Ga", 1),
     sline("fa", [[110, 10], [150, 10]], "M/Fa", 1, "M/Sw", 1),
     sline("gb", [[40, 70], [80, 70]], "M/G1", 1, "M/Gb", 1),
     sline("fb", [[110, 70], [150, 70]], "M/Fb", 1, "M/Sw", 1)])
p = run("repair_suggest.py", write("fx_goto_over.json", over), "--json", "--include-goto")
rep = json.loads(p.stdout)
check("goto refused when budget exhausted",
      all(s["op"]["op"] != "goto_from_conversion" for s in rep["suggestions"]),
      str([s["op"]["op"] for s in rep["suggestions"]]))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")
