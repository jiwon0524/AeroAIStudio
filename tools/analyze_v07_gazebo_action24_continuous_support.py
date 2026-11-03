#!/usr/bin/env python3
"""Offline analysis for continuous ContactSensorData support observer NDJSON."""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

SUPPORTS = ("left_wheel", "right_wheel", "front_caster", "rear_caster")
WEIGHT_N = 24.5


def strict_load_jsonl(path):
    rows = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"nonfinite {x}")))
        rows.append(value)
    return rows


def _vec(v):
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return None
    try: result = tuple(float(x) for x in v)
    except (TypeError, ValueError): return None
    return result if all(math.isfinite(x) for x in result) else None


def project_force(force, normal):
    f, n = _vec(force), _vec(normal)
    if f is None or n is None: return None
    norm = math.sqrt(sum(x*x for x in n))
    if norm <= 0: return None
    n = tuple(x/norm for x in n)
    dot = sum(x*y for x,y in zip(f,n))
    fn = abs(dot)
    ft = math.sqrt(max(0.0, sum(x*x for x in f)-dot*dot))
    return {"Fn_N": fn, "Ft_N": ft}


def classify_support_state(support):
    if not isinstance(support, dict):
        return "UNAVAILABLE"
    if support.get("state") == "UNAVAILABLE": return "UNAVAILABLE"
    if not support.get("component_available"):
        return "UNAVAILABLE"
    if support.get("state") == "VALID_EMPTY_CONTACT_SET" and support.get("contact_count") == 0:
        return "VALID_EMPTY_CONTACT_SET"
    if support.get("state") == "VALID_CONTACTS" and support.get("contact_count", 0) > 0:
        return "VALID_CONTACTS"
    raise ValueError("inconsistent ContactSensorData state/count")


def _point_id(epoch, iteration, support, contact, point):
    return (epoch, iteration, support.get("collision", {}).get("entity_id"),
            contact.get("collision1", {}).get("entity_id"),
            contact.get("collision2", {}).get("entity_id"),
            contact.get("contact_index"), point.get("point_index"))


def analyze_rows(rows, phase_intervals, weight_n=WEIGHT_N):
    advancing = [r for r in rows if r.get("kind") == "support_iteration"]
    seen = set(); last_by_epoch = {}
    for row in advancing:
        it = row.get("iteration")
        if not isinstance(it, int) or row.get("paused") is not False:
            raise ValueError("support iteration must have integer ID and paused=false")
        epoch = row.get("epoch", 0)
        key = (epoch, it)
        if key in seen: raise ValueError(f"duplicate iteration {it} in epoch {epoch}")
        if epoch in last_by_epoch and it <= last_by_epoch[epoch]:
            raise ValueError("iterations are not strictly increasing within epoch")
        seen.add(key); last_by_epoch[epoch] = it
        if set(row.get("supports", {})) != set(SUPPORTS):
            raise ValueError("each advancing sample must contain exactly four supports")
    result = {"sample_count": len(advancing), "phase_intervals_s": phase_intervals,
              "phases": {}, "weight_n": weight_n,
              "sampling_note": "A missing component is unavailable; an existing empty component contributes zero. Contact data equality may retain prior protobuf values within Physics comparison tolerance."}
    for phase, interval in phase_intervals.items():
        if not isinstance(interval, (list, tuple)) or len(interval) != 2 or None in interval:
            result["phases"][phase] = {"status": "PHASE_WINDOW_UNAVAILABLE"}; continue
        start, end = map(float, interval)
        selected = [r for r in advancing if start-1e-9 <= r["sim_time_ns"]*1e-9 <= end+1e-9]
        per = {}; totals = []
        for label in SUPPORTS:
            states=[]; fn=[]; ft=[]; depths=[]; point_count=0; valid_times=[]; invalid_force_iterations=0
            for row in selected:
                sup=row["supports"][label]; state=classify_support_state(sup); states.append(state)
                if state == "UNAVAILABLE": continue
                valid_times.append(row["sim_time_ns"] * 1e-9)
                sample_fn=0.0; sample_ft=0.0; sample_valid=True; dedup=set()
                for contact in sup.get("contacts", []):
                    if contact.get("pair_classification") != "SUPPORT_GROUND": continue
                    for point in contact.get("points", []):
                        key=_point_id(row.get("epoch", 0), row["iteration"], sup, contact, point)
                        if key in dedup: continue
                        dedup.add(key); point_count += 1
                        force=project_force(point.get("body_1_force_world_n"), point.get("normal_world"))
                        if force is None:
                            sample_valid=False
                            continue
                        sample_fn += force["Fn_N"]; sample_ft += force["Ft_N"]
                        depth=point.get("depth_m")
                        if isinstance(depth, (int,float)) and math.isfinite(depth): depths.append(float(depth))
                if sample_valid:
                    fn.append(sample_fn); ft.append(sample_ft)
                else:
                    invalid_force_iterations += 1
            per[label]={"advancing_iterations":len(selected),
                "message_count":len(selected),
                "VALID_CONTACTS":states.count("VALID_CONTACTS"),
                "VALID_EMPTY_CONTACT_SET":states.count("VALID_EMPTY_CONTACT_SET"),
                "UNAVAILABLE":states.count("UNAVAILABLE"),
                "coverage_ratio":(len(selected)-states.count("UNAVAILABLE"))/len(selected) if selected else None,
                "contact_observable_duration_s":max(valid_times)-min(valid_times) if len(valid_times)>1 else (0.0 if valid_times else None),
                "force_invalid_iteration_count":invalid_force_iterations,
                "ground_contact_point_count":point_count,
                "Fn_N":_stats(fn),"Ft_N":_stats(ft),"depth_m":_stats(depths)}
        for row in selected:
            support_values=[]; valid=True
            for label in SUPPORTS:
                sup=row["supports"][label]; state=classify_support_state(sup)
                if state == "UNAVAILABLE": valid=False; break
                total=0.0; ids=set()
                for contact in sup.get("contacts", []):
                    if contact.get("pair_classification") != "SUPPORT_GROUND": continue
                    for point in contact.get("points", []):
                        key=_point_id(row.get("epoch", 0),row["iteration"],sup,contact,point)
                        if key in ids: continue
                        ids.add(key)
                        proj=project_force(point.get("body_1_force_world_n"),point.get("normal_world"))
                        if proj is None: valid=False; break
                        total += proj["Fn_N"]
                    if not valid: break
                if not valid: break
                support_values.append(total)
            if valid: totals.append((sum(support_values), sum(support_values)/weight_n))
        timeline=_timeline(selected)
        transition_indexes=set(range(min(6,len(timeline))))
        if phase == "action24_up_acquisition":
            right=[item["supports"]["right_wheel"]["Fn_N"] for item in timeline]
            onset=next((i for i,v in enumerate(right) if v == 0.0 and any(x is not None and x > 0 for x in right[:i])),None)
            if onset is not None: transition_indexes.update(range(max(0,onset-3),min(len(timeline),onset+6)))
            transition_indexes.update(range(max(0,len(timeline)-5),len(timeline)))
        transition_timeline=[timeline[i] for i in sorted(transition_indexes)]
        result["phases"][phase]={"window_s":[start,end],"iteration_count":len(selected),
            "first_iteration":selected[0]["iteration"] if selected else None,
            "last_iteration":selected[-1]["iteration"] if selected else None,
            "per_support":per,"complete_four_support_iteration_count":len(totals),
            "total_ground_support_fn_N":_stats([x[0] for x in totals]),
            "total_over_weight":_stats([x[1] for x in totals]),
            "transition_timeline":transition_timeline,
            "timeline_note":"Full per-iteration support records remain in NDJSON; this JSON includes phase-start, detected RIGHT force-collapse neighborhood, and late samples only."}
    return result


def _stats(values):
    values=sorted(values)
    if not values:return {"count":0,"median":None,"p05":None,"p95":None,"max":None}
    def p(q): return values[max(0, math.ceil(q*len(values))-1)]
    return {"count":len(values),"median":statistics.median(values),"p05":p(.05),"p95":p(.95),"max":values[-1],"exact_zero_count":sum(x==0.0 for x in values)}


def classify_action24_support_case(phase_analysis, failure_reproduced):
    """Conservative future classification using Action23 empirical variability."""
    if not failure_reproduced:
        return {"verdict":"ACTION24_FAILURE_NOT_REPRODUCED","basis":"known physical failure gate did not pass"}
    phases=phase_analysis.get("phases",{})
    baseline=phases.get("action23_down_acquisition",{})
    target=phases.get("action24_up_acquisition",{})
    if baseline.get("complete_four_support_iteration_count") != baseline.get("iteration_count") or \
       target.get("complete_four_support_iteration_count") != target.get("iteration_count"):
        return {"verdict":"CONTINUOUS_SUPPORT_RUNTIME_OBSERVATION_INCOMPLETE","basis":"not every phase iteration has four valid component states and force data"}
    b=baseline.get("total_ground_support_fn_N",{}); t=target.get("total_ground_support_fn_N",{})
    if b.get("count",0)==0 or t.get("count",0)==0 or b.get("p05") is None:
        return {"verdict":"CONTINUOUS_SUPPORT_RUNTIME_OBSERVATION_INCOMPLETE","basis":"empirical baseline or target totals unavailable"}
    supports_b=baseline.get("per_support",{}); supports_t=target.get("per_support",{})
    right_zero=supports_t.get("right_wheel",{}).get("Fn_N",{}).get("exact_zero_count",0)>0
    redistributed=any(supports_t.get(k,{}).get("Fn_N",{}).get("median") is not None and
        supports_b.get(k,{}).get("Fn_N",{}).get("p95") is not None and
        supports_t[k]["Fn_N"]["median"]>supports_b[k]["Fn_N"]["p95"]
        for k in ("left_wheel","front_caster","rear_caster"))
    if right_zero and redistributed and b.get("p05") <= t.get("median") <= b.get("p95"):
        verdict="ACTION24_RIGHT_LOAD_REDISTRIBUTION_CONFIRMED"
    elif t.get("p95") < b.get("p05"):
        verdict="ACTION24_GLOBAL_SUPPORT_FORCE_COLLAPSE_CONFIRMED"
    else:
        verdict="ACTION24_SUPPORT_DISTRIBUTION_PARTIALLY_RESOLVED"
    return {"verdict":verdict,"baseline_empirical_p05_p95_n":[b.get("p05"),b.get("p95")],
        "target_total_median_n":t.get("median"),"right_exact_zero_observed":right_zero,
        "other_support_median_above_action23_p95":redistributed,
        "rule":"Full four-state coverage required; redistribution uses Action23 support p95 and total p05-p95; collapse requires Action24 total p95 below Action23 total p05. No arbitrary force tolerance."}


def _timeline(rows):
    out=[]
    for row in rows:
        values={}; valid=True
        for label in SUPPORTS:
            sup=row["supports"][label]; state=classify_support_state(sup)
            if state=="UNAVAILABLE": valid=False; values[label]={"state":state,"Fn_N":None}; continue
            fn=0.0
            for contact in sup.get("contacts",[]):
                if contact.get("pair_classification")!="SUPPORT_GROUND":continue
                for point in contact.get("points",[]):
                    proj=project_force(point.get("body_1_force_world_n"),point.get("normal_world"))
                    if proj is None: valid=False; break
                    fn+=proj["Fn_N"]
                if not valid: break
            if not valid:
                values[label]={"state":state,"Fn_N":None}
                continue
            values[label]={"state":state,"Fn_N":fn}
        out.append({"iteration":row["iteration"],"sim_time_ns":row["sim_time_ns"],
            "supports":values,"TOTAL_GROUND_SUPPORT_FN_N":sum(v["Fn_N"] for v in values.values()) if valid else None})
    return out


def analyze_file(path, phase_intervals):
    rows=strict_load_jsonl(path); report=analyze_rows(rows, phase_intervals)
    report["source_ndjson"]=str(Path(path)); return report
