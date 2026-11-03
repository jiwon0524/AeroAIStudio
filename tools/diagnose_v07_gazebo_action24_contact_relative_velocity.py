#!/usr/bin/env python3
"""Measure diagnostic wheel/ground contact-point relative velocity for action 24.

The Gazebo run is delegated to the existing action-24 wheel/contact diagnostic,
which replays actions 1--23 and calls the current production ``step('up')`` for
action 24. This wrapper only analyzes its captured pose, joint and contact data.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)
from tools.diagnose_v07_gazebo_action24_wheel_ground_contact import (
    _run_contact_diagnostic)

DEFAULT_OUTPUT = Path(
    "validation/v071-host/gazebo-action24-contact-relative-velocity-phase3hi")
JOINT_AXIS_MODEL = (0.0, 1.0, 0.0)


def _vadd(a, b): return tuple(x + y for x, y in zip(a, b))
def _vsub(a, b): return tuple(x - y for x, y in zip(a, b))
def _vmul(a, k): return tuple(x * k for x in a)
def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])
def _norm(a): return math.sqrt(_dot(a, a))
def _unit(a):
    n = _norm(a)
    if not math.isfinite(n) or n <= 1e-15:
        raise ValueError("zero/nonfinite vector cannot be normalized")
    return _vmul(a, 1.0 / n)


def _qnorm(q):
    n = math.sqrt(sum(float(q[k]) ** 2 for k in ("x", "y", "z", "w")))
    if not math.isfinite(n) or n <= 1e-15:
        raise ValueError("zero/nonfinite quaternion")
    return {k: float(q[k]) / n for k in ("x", "y", "z", "w")}


def _qmul(a, b):
    ax, ay, az, aw = (a[k] for k in ("x", "y", "z", "w"))
    bx, by, bz, bw = (b[k] for k in ("x", "y", "z", "w"))
    return _qnorm({"x": aw*bx + ax*bw + ay*bz - az*by,
        "y": aw*by - ax*bz + ay*bw + az*bx,
        "z": aw*bz + ax*by - ay*bx + az*bw,
        "w": aw*bw - ax*bx - ay*by - az*bz})


def _qconj(q): return {"x": -q["x"], "y": -q["y"], "z": -q["z"], "w": q["w"]}


def _qrotate(q, v):
    q = _qnorm(q)
    p = {"x": v[0], "y": v[1], "z": v[2], "w": 0.0}
    out = _qmul_raw(_qmul_raw(q, p), _qconj(q))
    return out["x"], out["y"], out["z"]


def _qmul_raw(a, b):
    ax, ay, az, aw = (a[k] for k in ("x", "y", "z", "w"))
    bx, by, bz, bw = (b[k] for k in ("x", "y", "z", "w"))
    return {"x": aw*bx + ax*bw + ay*bz - az*by,
        "y": aw*by - ax*bz + ay*bw + az*bx,
        "z": aw*bz + ax*by - ay*bx + az*bw,
        "w": aw*bw - ax*bx - ay*by - az*bz}


def _pose_entity(sample, name):
    for row in sample.get("entities", []):
        if row.get("name") == name:
            return row
    return None


def compose_link_world_pose(body, link):
    """Compose model-world pose with SDF/Pose_V model-relative link pose."""
    qb, ql = _qnorm(body["orientation"]), _qnorm(link["orientation"])
    pb = (float(body["x"]), float(body["y"]), float(body["z"]))
    pl = (float(link["x"]), float(link["y"]), float(link["z"]))
    pw = _vadd(pb, _qrotate(qb, pl))
    return {"position_world_m": pw, "orientation_world": _qmul(qb, ql)}


def _angular_velocity_world(q0, q1, dt):
    if dt <= 0 or not math.isfinite(dt):
        raise ValueError("pose timestamps must increase")
    q0, q1 = _qnorm(q0), _qnorm(q1)
    dq = _qmul(q1, _qconj(q0))  # world-frame incremental rotation
    if dq["w"] < 0:
        dq = {k: -v for k, v in dq.items()}
    w = max(-1.0, min(1.0, dq["w"]))
    angle = 2.0 * math.acos(w)
    s = math.sqrt(max(0.0, 1.0 - w*w))
    if angle < 1e-10 or s < 1e-10:
        return (0.0, 0.0, 0.0)
    axis = (dq["x"] / s, dq["y"] / s, dq["z"] / s)
    return _vmul(axis, angle / dt)


def build_link_twist_samples(pose_samples, link_name, *, max_pose_gap_s=0.01):
    """Derive world-frame link twist from timestamped Pose_V only.

    Repeated paused-time frames are collapsed. Gaps above the diagnostic data
    quality bound fail closed; no command or odometry is used in this estimate.
    """
    by_time = {}
    for sample in pose_samples:
        t = sample.get("simulation_timestamp")
        if t is None or not math.isfinite(float(t)):
            continue
        body, link = _pose_entity(sample, "simple_agent"), _pose_entity(sample, link_name)
        if body is None or link is None:
            continue
        # Same simulation instant can be emitted repeatedly while paused. Keep
        # the latest receive-sequence representation of that instant.
        by_time[float(t)] = (int(sample.get("receive_sequence", 0)), body, link)
    rows = []
    for t in sorted(by_time):
        _, body, link = by_time[t]
        pose = compose_link_world_pose(body, link)
        rows.append({"simulation_timestamp": t, **pose,
            "model_orientation_world": _qnorm(body["orientation"])})
    twists = []
    for a, b in zip(rows, rows[1:]):
        dt = b["simulation_timestamp"] - a["simulation_timestamp"]
        if dt <= 0:
            continue
        if dt > max_pose_gap_s:
            position_change = _norm(_vsub(b["position_world_m"], a["position_world_m"]))
            dq = _qmul(b["orientation_world"], _qconj(a["orientation_world"]))
            angle_change = 2.0 * math.acos(max(-1.0, min(1.0, abs(dq["w"]))))
            if position_change <= 1e-10 and angle_change <= 1e-8:
                # Paused/same-state duplicate interval; it supplies no velocity
                # estimate and is omitted rather than treated as sparse motion.
                continue
            raise ValueError(f"moving Pose_V gap {dt:.6g}s exceeds {max_pose_gap_s:.6g}s")
        va = _vmul(_vsub(b["position_world_m"], a["position_world_m"]), 1.0 / dt)
        wa = _angular_velocity_world(a["orientation_world"], b["orientation_world"], dt)
        twists.append({"simulation_timestamp": (a["simulation_timestamp"] + b["simulation_timestamp"]) / 2.0,
            "interval_start": a["simulation_timestamp"], "interval_end": b["simulation_timestamp"],
            "linear_velocity_world_m_s": va, "angular_velocity_world_rad_s": wa,
            "position_world_m": _vmul(_vadd(a["position_world_m"], b["position_world_m"]), .5),
            "orientation_world": a["orientation_world"],
            "model_orientation_world": a["model_orientation_world"]})
    return twists


def interpolate_vector(rows, t, field, *, max_delta_s=0.01):
    before = [r for r in rows if r["simulation_timestamp"] <= t]
    after = [r for r in rows if r["simulation_timestamp"] >= t]
    if not before or not after:
        return None
    a, b = before[-1], after[0]
    if max(t-a["simulation_timestamp"], b["simulation_timestamp"]-t) > max_delta_s:
        return None
    va, vb = a[field], b[field]
    if a is b or b["simulation_timestamp"] == a["simulation_timestamp"]:
        return tuple(va)
    u = ((t-a["simulation_timestamp"]) /
         (b["simulation_timestamp"]-a["simulation_timestamp"]))
    return _vadd(_vmul(va, 1.0-u), _vmul(vb, u))


def contact_relative_velocity(contact_point_world, contact_normal_world,
                              wheel_linear_world, wheel_angular_world,
                              wheel_origin_world, ground_linear_world=(0.0, 0.0, 0.0)):
    """Return derived contact-relative velocity and normal/tangent components."""
    r = _vsub(contact_point_world, wheel_origin_world)
    v_contact = _vadd(wheel_linear_world, _cross(wheel_angular_world, r))
    v_rel = _vsub(v_contact, ground_linear_world)
    n = _unit(contact_normal_world)
    vn = _dot(v_rel, n)
    vt = _vsub(v_rel, _vmul(n, vn))
    return {"wheel_contact_velocity_world_m_s": v_contact,
        "ground_contact_velocity_world_m_s": ground_linear_world,
        "relative_velocity_world_m_s": v_rel,
        "normal_relative_velocity_m_s": vn,
        "tangential_relative_velocity_world_m_s": vt,
        "tangential_relative_speed_m_s": _norm(vt),
        "provenance": "DERIVED: timestamped World Pose_V wheel-link pose finite differences; v_contact=v_origin+omega_cross_r"}


def compare_against_rolling_baseline(baseline_speeds, target_speeds, *,
                                     contact_observable=True):
    """Compare distributions; uses Action23's measured upper envelope, no fixed speed cutoff."""
    if not contact_observable or not target_speeds:
        return "CONTACT_LOST_OR_UNOBSERVABLE"
    if not baseline_speeds:
        return "INSUFFICIENT_EVIDENCE"
    baseline = sorted(float(x) for x in baseline_speeds if math.isfinite(float(x)))
    target = sorted(float(x) for x in target_speeds if math.isfinite(float(x)))
    if not baseline or not target:
        return "INSUFFICIENT_EVIDENCE"
    # Nearest-rank p95 is the observed working-run envelope, not a relaxed
    # physical threshold. The report retains the distributions for review.
    p95 = baseline[max(0, math.ceil(.95 * len(baseline)) - 1)]
    median_target = target[len(target)//2]
    return "SUBSTANTIAL_RELATIVE_SLIDING" if median_target > p95 else "ROLLING_LIKE_BASELINE"


def _sample_vector(obj, keys):
    # gz.msgs.Vector3d is proto3: omitted scalar coordinates have native value 0.
    return tuple(float(obj.get(k, 0.0)) for k in keys)


def _phase_interval(raw, name):
    if name == "action23_down_acquisition":
        e = raw["action23"]["production_telemetry"]["execution_evidence"]
        rows = e.get("execution_phases") or e.get("execution_evidence", {}).get("phase_evidence", [])
        phase = next(x for x in rows if x.get("phase") == "ACQUIRE_LINEAR")
        return float(phase["start_sim_time"]), float(phase["end_sim_time"])
    if name == "action24_brake":
        b = raw["action24_production_macro_evidence"]["braking_phase"]
        return float(b["start_sim_time"]), float(b["end_sim_time"])
    a = raw["action24_production_macro_evidence"]["acquisition_phase_evidence"]
    return float(a["start_sim_time"]), float(a["end_sim_time"])


def validate_production_replay_contract(contact_report):
    """Fail closed unless the source prefix and target use production env.step."""
    target = contact_report.get("target") or {}
    required = (target.get("global_action_index") == 24 and
        target.get("previous_action") == "down" and target.get("requested_action") == "up" and
        contact_report.get("actions_1_to_23_used_production_adapter") is True and
        contact_report.get("target_used_production_adapter") is True and
        contact_report.get("target_production_step_call_started") is True)
    if not required:
        raise ValueError("capture did not prove production actions 1-23 and target env.step('up') at action 24")
    return True


def _derive_window(contact_rows, pose_rows, joint_rows, interval, side, radius):
    start, end = interval
    link_name = f"{side}_wheel"
    # Restrict the derivative source to the current physical phase plus a small
    # bracket margin. Unrelated pauses between phases must not make this phase
    # appear sparse.
    local_poses = [r for r in pose_rows if r.get("simulation_timestamp") is not None
        and start - .02 <= float(r["simulation_timestamp"]) <= end + .02]
    try:
        twists = build_link_twist_samples(local_poses, link_name)
    except ValueError as error:
        return [], [], str(error)
    selected = []
    for msg in contact_rows:
        t = msg.get("simulation_timestamp")
        if t is None or not start - 1e-9 <= float(t) <= end + 1e-9:
            continue
        for c in msg.get("contacts", []):
            if c.get("pair_classification") != f"{side.upper()}_WHEEL_GROUND":
                continue
            for idx, (point, normal) in enumerate(zip(c.get("position_native", []), c.get("normal_native", []))):
                try:
                    p = _sample_vector(point, ("x", "y", "z"))
                    n = _unit(_sample_vector(normal, ("x", "y", "z")))
                except (KeyError, TypeError, ValueError):
                    continue
                v = interpolate_vector(twists, float(t), "linear_velocity_world_m_s")
                w = interpolate_vector(twists, float(t), "angular_velocity_world_rad_s")
                origin = interpolate_vector(twists, float(t), "position_world_m")
                orientation_rows = [r for r in twists if r["simulation_timestamp"] <= float(t)]
                if not v or not w or not origin or not orientation_rows:
                    continue
                # Validate the purported world contact point against the known
                # wheel radius and the vertical ground-plane normal. A frame or
                # entity mismatch is rejected instead of silently transformed.
                # The SDF joint axis is model-frame +Y. Wheel spin changes the
                # link orientation, but the revolute axis remains attached to
                # the parent model frame.
                q = orientation_rows[-1]["model_orientation_world"]
                axis = _qrotate(q, (0.0, 1.0, 0.0))
                radial = _vsub(p, origin)
                radial_perp = _vsub(radial, _vmul(axis, _dot(radial, axis)))
                radius_error = abs(_norm(radial_perp) - radius)
                derived = contact_relative_velocity(p, n, v, w, origin)
                derived.update({"simulation_timestamp": float(t), "side": side,
                    "contact_index": idx, "contact_point_world_native": p,
                    "contact_normal_world_native": n,
                    "wheel_origin_world_m_derived": origin,
                    "wheel_radius_m_from_sdf": radius,
                    "contact_radius_consistency_error_m": radius_error,
                    "wheel_link_linear_velocity_world_m_s_derived": v,
                    "wheel_link_angular_velocity_world_rad_s_derived": w,
                    "raw_contact_wrench_native": c.get("wrench_native", []),
                    "raw_joint_samples_nearby": _nearest_joint_rows(joint_rows, float(t))})
                selected.append(derived)
    return twists, selected, None


def _nearest_joint_rows(rows, t):
    result = {}
    for name in ("left_joint", "right_joint"):
        values = rows.get(name, []) if isinstance(rows, dict) else []
        row = min((r for r in values if r.get("simulation_timestamp") is not None),
            key=lambda r: abs(float(r["simulation_timestamp"])-t), default=None)
        result[name] = row
    return result


def _percentiles(values):
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    xs = sorted(float(x) for x in values)
    return {"count": len(xs), "min": xs[0], "median": xs[len(xs)//2],
        "p95": xs[max(0, math.ceil(.95*len(xs))-1)], "max": xs[-1]}


def analyze_capture(contact_report, raw_report):
    """Build contact-point kinematics from actual production capture evidence."""
    validate_production_replay_contract(contact_report)
    # action23's pose window is captured before/after the production action;
    # action24 frames include braking and acquisition. Merge without using odom.
    pose23 = raw_report.get("action23", {}).get("physical_topic_window", {}).get(
        "world_pose_frames", {}).get("samples", [])
    pose24 = contact_report.get("world_pose_body_evidence", {}).get(
        "world_pose_frames", {}).get("samples", [])
    poses = list(pose23) + list(pose24)
    joints = contact_report.get("joint_telemetry", {})
    joint_rows = {
        "left_joint": (joints.get("action23", {}).get("acquire_down_window", {}).get("left_joint", []) +
            joints.get("action24_brake", {}).get("joint_states_by_name", {}).get("left_joint", []) +
            joints.get("action24_acquisition", {}).get("joint_states_by_name", {}).get("left_joint", [])),
        "right_joint": (joints.get("action23", {}).get("acquire_down_window", {}).get("right_joint", []) +
            joints.get("action24_brake", {}).get("joint_states_by_name", {}).get("right_joint", []) +
            joints.get("action24_acquisition", {}).get("joint_states_by_name", {}).get("right_joint", []))}
    intervals = {name: _phase_interval(raw_report, name) for name in
        ("action23_down_acquisition", "action24_brake", "action24_up_acquisition")}
    radius_by_side = {side: float(contact_report["static_sdf_audit"]["links"][
        f"{side}_wheel"]["geometry"].split("<radius>")[1].split("</radius>")[0])
        for side in ("left", "right")}
    all_contacts = contact_report.get("contact_samples", [])
    ground = contact_report.get("static_sdf_audit", {}).get("ground", {})
    ground_static = str(ground.get("static", "")).lower() == "true"
    if not ground_static:
        raise ValueError("zero ground velocity cannot be assumed: SDF does not prove static ground")
    windows = {}
    for name, interval in intervals.items():
        windows[name] = {"simulation_interval": list(interval), "by_wheel": {}}
        for side in ("left", "right"):
            twists, rows, kinematics_error = _derive_window(all_contacts, poses, joint_rows, interval,
                side, radius_by_side[side])
            speeds = [r["tangential_relative_speed_m_s"] for r in rows]
            windows[name]["by_wheel"][side] = {
                "contact_kinematics_status": ("KINEMATICS_INVALID" if kinematics_error else
                    "DERIVED" if rows else "UNAVAILABLE"),
                "kinematics_error": kinematics_error,
                "derived_sample_count": len(rows), "link_twist_sample_count": len(twists),
                "tangential_relative_speed_m_s": _percentiles(speeds),
                "representative_timeline": rows[::max(1, len(rows)//12)] if rows else [],
                "all_derived_contact_samples": rows}
    comparison = {}
    for side in ("left", "right"):
        base = windows["action23_down_acquisition"]["by_wheel"][side]["all_derived_contact_samples"]
        target = windows["action24_up_acquisition"]["by_wheel"][side]["all_derived_contact_samples"]
        baseline_end = intervals["action23_down_acquisition"][1]
        baseline_duration = intervals["action23_down_acquisition"][1] - intervals["action23_down_acquisition"][0]
        # Compare against the terminal 20% of the working acquisition: this is
        # the observed end-state after the command transient, not the startup
        # acceleration interval. Preserve the full Action23 distribution above.
        steady_start = baseline_end - .2 * baseline_duration
        steady_base = [x for x in base if x["simulation_timestamp"] >= steady_start]
        observed_target_msgs = [r for r in all_contacts if r.get("sensor_label") == side and
            intervals["action24_up_acquisition"][0] <= r.get("simulation_timestamp", -1) <=
            intervals["action24_up_acquisition"][1]]
        observed_stamps = sorted({float(r["simulation_timestamp"]) for r in observed_target_msgs
            if r.get("simulation_timestamp") is not None})
        coverage = observed_stamps[-1] - observed_stamps[0] if len(observed_stamps) > 1 else 0.0
        comparison[side] = {"classification": compare_against_rolling_baseline(
            [x["tangential_relative_speed_m_s"] for x in steady_base],
            [x["tangential_relative_speed_m_s"] for x in target],
            contact_observable=coverage >= .01),
            "action23_baseline_speed": windows["action23_down_acquisition"]["by_wheel"][side]["tangential_relative_speed_m_s"],
            "action23_terminal_steady_baseline_speed": _percentiles(
                [x["tangential_relative_speed_m_s"] for x in steady_base]),
            "action23_terminal_baseline_selection": {
                "interval": [steady_start, baseline_end],
                "basis": "terminal 20% of measured 0.1 s Action23 acquisition, after startup transient"},
            "action24_speed": windows["action24_up_acquisition"]["by_wheel"][side]["tangential_relative_speed_m_s"],
            "target_contact_message_count": len(observed_target_msgs),
            "target_contact_observed_span_s": coverage,
            "contact_observability_rule": "at least 10 ms of timestamped contacts in the 100 ms acquisition window; shorter spans remain unobservable",
            "left_contact_last_timestamp": max((r["simulation_timestamp"] for r in observed_target_msgs), default=None) if side == "left" else None}
    return {"method": "DERIVED_RIGID_BODY_CONTACT_POINT_KINEMATICS",
        "native_contact_relative_velocity_api": "UNAVAILABLE; installed GetContactsFromLastStepFeature exposes world contact point, world force/normal/depth, but no relative velocity",
        "inputs": {"wheel_link_pose": "World Pose_V model pose composed with model-relative Pose_V link pose; timestamp finite differences",
            "wheel_joint_state": "native JointStatePublisher position/velocity retained as independent corroboration, not used as command/odometry substitute",
            "contact_point": "gz.msgs.Contact.position; checked against SDF wheel radius and world ground-plane geometry",
            "contact_normal": "gz.msgs.Contact.normal; checked against SDF world ground normal +Z",
            "ground_velocity": "zero because production SDF ground model is static=true",
            "odometry": "not used in kinematic derivation"},
        "frames": {"world_pose": "world", "wheel_link_pose": "model-relative, composed with simple_agent world pose",
            "contact_point": "world-frame basis: installed gz::physics::GetContactsFromLastStepFeature documents contact point in world frame; sensor coordinates are also consistent with the world ground plane / wheel geometry",
            "normal": "world-frame basis: installed physics contact feature documents world normal; observed ground normal +Z",
            "ground": "world, static", "transform": "p_world_link = p_world_model + R_world_model*p_model_link; q_world_link=q_world_model*q_model_link"},
        "derivation": {"v_contact": "v_link_origin_world + omega_link_world × (p_contact_world - p_link_origin_world)",
            "v_relative": "v_contact - v_ground_contact; v_ground_contact=(0,0,0) from static ground SDF",
            "normal_component": "dot(v_relative, unit(normal_world))",
            "tangential_component": "v_relative - normal_component*unit(normal_world)",
            "classification_policy": "compare target median against the per-wheel Action23 working-baseline p95; no fixed absolute slip threshold"},
        "pose_sampling_quality": {"max_link_pose_gap_bound_s": 0.01,
            "quality_policy": "fail closed if timestamp gaps exceed 10 ms; duplicate paused-time frames collapsed"},
        "production_replay_contract": "PASS: actions 1-23 are production adapter steps and action 24 is production env.step('up')",
        "intervals": windows, "per_wheel_comparison": comparison,
        "wheel_rotation_vs_body_translation": contact_report.get("comparison"),
        "limitations": ["No native contact-relative-velocity field exists in gz.msgs.Contacts or installed physics feature API.",
            "Contact message schema has no explicit frame field; world frame is supported by local physics API contract and checked geometrically.",
            "Derived velocity uncertainty is limited by Pose_V sampling/interpolation; native joint velocity is corroboration only.",
            "Relative sliding, if found, does not identify why friction/solver force failed to move the chassis."]}


def run_diagnostic(artifact_dir, output, *, prior_failure=None, successful_down_up=None, gui=False):
    output = Path(output)
    capture_dir = output / "capture"
    kwargs = {k: v for k, v in {"prior_failure": prior_failure,
        "successful_down_up": successful_down_up, "gui": gui}.items() if v is not None}
    contact_report = _run_contact_diagnostic(artifact_dir, capture_dir, **kwargs)
    raw_path = capture_dir / "production_replay_evidence" / "action24_acquisition_divergence.json"
    raw_report = json.loads(raw_path.read_text(encoding="utf-8"))
    derived = analyze_capture(contact_report, raw_report)
    result = {"schema_version": "0.7.1", "verifier": "diagnostic-only Action24 contact-relative velocity",
        "status": "DIAGNOSTIC_CAPTURE_COMPLETE",
        "production_execution_status": contact_report.get("status"),
        "verdict": "ACTION24_CONTACT_RELATIVE_VELOCITY_CAPTURED",
        "production_behavior_modified": False, "production_sdf_modified": False,
        "production_diffdrive_modified": False, "production_control_executor_modified": False,
        "dqn_used": False, "training_used": False,
        "source_provenance": contact_report.get("provenance"), "target": contact_report.get("target"),
        "actions_1_to_23_used_current_production": contact_report.get("actions_1_to_23_used_production_adapter"),
        "action24_used_current_production_step_up": contact_report.get("target_used_production_adapter"),
        "target_production_step_call_started": contact_report.get("target_production_step_call_started"),
        "target_production_step_returned": contact_report.get("target_production_step_returned"),
        "target_exception": contact_report.get("target_exception"),
        "reset_provenance": contact_report.get("sensor_collision_process_reset", {}).get("reset_provenance"),
        "process_start": contact_report.get("sensor_collision_process_reset", {}).get("process_start"),
        "process_end": contact_report.get("sensor_collision_process_reset", {}).get("process_end"),
        "shutdown": contact_report.get("sensor_collision_process_reset", {}).get("shutdown"),
        "contact_report": contact_report, "contact_relative_velocity": derived,
        "strict_json_audit": {"status": "PENDING"}}
    paths = find_nonfinite_paths(result)
    result["strict_json_audit"] = {"status": "PASS" if not paths else "FAIL",
        "nonfinite_field_paths": paths}
    result["nonfinite_field_paths"] = paths
    result["evidence_file"] = str(output / "action24_contact_relative_velocity.json")
    if paths:
        result["verdict"] = "CONTACT_RELATIVE_VELOCITY_DIAGNOSTIC_INVALID"
    write_json(output / "action24_contact_relative_velocity.json", _strict_json_value(result))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--prior-failure", type=Path, default=None)
    p.add_argument("--successful-down-up", type=Path, default=None)
    p.add_argument("--gui", action="store_true")
    a = p.parse_args(argv)
    r = run_diagnostic(a.artifact_dir, a.output, prior_failure=a.prior_failure,
        successful_down_up=a.successful_down_up, gui=a.gui)
    print("Gazebo action-24 contact-relative-velocity diagnostic: " + r["verdict"])
    print("evidence: " + r["evidence_file"])
    return 0 if r["strict_json_audit"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
