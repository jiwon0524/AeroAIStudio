#!/usr/bin/env python3
"""Diagnostic-only complete ground-support contact capture for Action24.

This wraps the established deterministic native-kinematics replay and adds
Contact sensors to the two caster collisions in its diagnostic SDF copy. It
never runs Gazebo at import time; the CLI is intended for Host execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.scenario.models import ScenarioSpec
import tools.diagnose_v07_gazebo_action24_native_contact_kinematics as native_diag
import tools.diagnose_v07_gazebo_action24_wheel_ground_contact as contact_diag
import tools.diagnose_v07_gazebo_action24_wheel_joint_state as joint_diag
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)

SUPPORTS = {
    "left_wheel": ("left_wheel", "left_collision"),
    "right_wheel": ("right_wheel", "right_collision"),
    "front_caster": ("front_caster", "front_collision"),
    "rear_caster": ("rear_caster", "rear_collision"),
    "chassis": ("body", "body_collision"),
}
SENSOR_TO_SUPPORT = {"left": "left_wheel", "right": "right_wheel",
    "front_caster": "front_caster", "rear_caster": "rear_caster",
    "chassis": "chassis"}
DIAGNOSTIC_SENSOR_NAMES = {
    f"{label}_support_contact_diagnostic" for label in SUPPORTS
    if label in ("front_caster", "rear_caster")
} | {"left_wheel_ground_contact_diagnostic",
     "right_wheel_ground_contact_diagnostic"}
DEFAULT_OUTPUT = Path(
    "validation/v071-host/gazebo-action24-support-load-distribution-phase3haa")
WEIGHT_N = 2.5 * 9.8


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _vector(value):
    if not isinstance(value, dict):
        return None
    try:
        result = tuple(float(value.get(axis, 0.0)) for axis in ("x", "y", "z"))
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(x) for x in result) else None


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    return values[max(0, math.ceil(q * len(values)) - 1)]


def add_caster_contact_sensors(diagnostic_sdf: Path, production_sdf: Path,
                               contact_info: dict) -> dict:
    """Add front/rear caster observation sensors and verify production is intact."""
    diagnostic_sdf, production_sdf = Path(diagnostic_sdf), Path(production_sdf)
    original_production = production_sdf.read_bytes()
    root = ET.parse(diagnostic_sdf).getroot()
    model = root.find(".//model[@name='simple_agent']")
    world = root.find("world")
    if model is None or world is None:
        raise ValueError("Diagnostic SDF lacks world or simple_agent")
    topics = contact_info["contact_topics"]
    sensor_defs = contact_info.setdefault("support_contact_sensors", {})
    collision_map = contact_info["collision_entity_map"]
    for label in ("front_caster", "rear_caster"):
        link_name, collision_name = SUPPORTS[label]
        link = model.find(f"link[@name='{link_name}']")
        collision = link.find(f"collision[@name='{collision_name}']") if link is not None else None
        if collision is None:
            raise ValueError(f"Missing support collision {link_name}/{collision_name}")
        sensor_name = f"{label}_support_contact_diagnostic"
        if link.find(f"sensor[@name='{sensor_name}']") is not None:
            raise ValueError(f"Diagnostic sensor already exists: {sensor_name}")
        topic = f"/aero/{world.get('name')}/{label}_ground_contacts_diagnostic"
        sensor = ET.SubElement(link, "sensor", name=sensor_name, type="contact")
        ET.SubElement(sensor, "always_on").text = "true"
        ET.SubElement(sensor, "update_rate").text = "1000"
        contact = ET.SubElement(sensor, "contact")
        ET.SubElement(contact, "collision").text = collision_name
        ET.SubElement(contact, "topic").text = topic
        topics[label] = topic
        sensor_defs[label] = {"sensor_name": sensor_name, "link_name": link_name,
            "collision_name": collision_name, "topic": topic,
            "message_type": "gz.msgs.Contacts", "update_rate_hz": 1000}
        collision_map[label] = f"simple_agent::{link_name}::{collision_name}"

    ET.indent(root)
    ET.ElementTree(root).write(diagnostic_sdf, encoding="utf-8", xml_declaration=True)
    if production_sdf.read_bytes() != original_production:
        raise RuntimeError("Support instrumentation modified production SDF")
    contact_info["production_sdf_sha256_before"] = hashlib.sha256(original_production).hexdigest()
    contact_info["production_sdf_sha256_after"] = _sha256(production_sdf)
    contact_info["production_sdf_unchanged"] = True
    contact_info["diagnostic_sdf"] = str(diagnostic_sdf)
    contact_info["diagnostic_sdf_sha256"] = _sha256(diagnostic_sdf)
    contact_info["support_sensor_labels"] = list(SUPPORTS)
    contact_info["instrumentation_semantics"] = (
        "Adds Contact sensor declarations only to diagnostic SDF copies for left/right "
        "drive wheels and front/rear casters; the production chassis contact sensor is "
        "also subscribed. No collision, surface, inertial, joint, physics, or actuation "
        "elements are changed.")
    return contact_info


def _contact_pair_is_ground(point):
    a = point.get("collision1_name") or ""
    b = point.get("collision2_name") or ""
    return "ground::body::collision" in a or "ground::body::collision" in b


def _deduplicated_points(samples):
    """Expand aligned point arrays; dedupe by time/pair/indexed geometry."""
    unique = {}
    malformed = 0
    duplicate_count = 0
    labels_seen = set()
    for message in samples:
        sensor_label = message.get("sensor_label")
        label = SENSOR_TO_SUPPORT.get(sensor_label)
        if label not in SUPPORTS:
            continue
        stamp = message.get("simulation_timestamp")
        if not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
            malformed += 1
            continue
        stamp_ns = round(float(stamp) * 1e9)
        labels_seen.add(label)
        for contact in message.get("contacts", []):
            if not _contact_pair_is_ground(contact):
                continue
            positions = contact.get("position_native", [])
            normals = contact.get("normal_native", [])
            depths = contact.get("depth_m_native", [])
            wrenches = contact.get("wrench_native", [])
            if not (len(positions) == len(normals) == len(depths) == len(wrenches)):
                malformed += 1
            for index in range(min(map(len, (positions, normals, depths, wrenches)))):
                p, n, wrench = (_vector(positions[index]), _vector(normals[index]),
                                wrenches[index])
                try:
                    depth = float(depths[index])
                except (TypeError, ValueError):
                    depth = float("nan")
                body_wrench = wrench.get("body_1_wrench", {}) if isinstance(wrench, dict) else {}
                force = _vector(body_wrench.get("force"))
                if (p is None or n is None or force is None or not math.isfinite(depth)
                        or math.sqrt(_dot(n, n)) == 0):
                    malformed += 1
                    continue
                norm = math.sqrt(_dot(n, n))
                n = tuple(x / norm for x in n)
                fn = abs(_dot(force, n))
                fmag = math.sqrt(_dot(force, force))
                ft = math.sqrt(max(0.0, fmag * fmag - fn * fn))
                pair = tuple(sorted((contact.get("collision1_name") or "",
                                      contact.get("collision2_name") or "")))
                key = (stamp_ns, pair, tuple(round(x, 9) for x in p), round(depth, 12))
                row = {"time_ns": stamp_ns, "simulation_timestamp_s": stamp_ns * 1e-9,
                    "support": label, "collision_pair": list(pair),
                    "contact_point_world_m": p, "normal_world": n,
                    "depth_m": depth, "normal_force_magnitude_n": fn,
                    "tangential_force_magnitude_n": ft}
                if key in unique:
                    duplicate_count += 1
                    if unique[key]["support"] != label:
                        unique[key]["duplicate_sensor_labels"].append(label)
                    continue
                row["duplicate_sensor_labels"] = []
                unique[key] = row
    return list(unique.values()), malformed, sorted(labels_seen), duplicate_count


def _phase_rows(points, samples, interval):
    start, end = interval
    if start is None or end is None:
        return {"availability": "PHASE_INTERVAL_UNAVAILABLE", "by_support": {},
                "synchronized_load": {"status": "UNAVAILABLE"}}
    start, end = float(start), float(end)
    phase_points = [p for p in points if start - 1e-9 <= p["simulation_timestamp_s"] <= end + 1e-9]
    phase_messages = [m for m in samples if SENSOR_TO_SUPPORT.get(m.get("sensor_label")) in SUPPORTS and
        isinstance(m.get("simulation_timestamp"), (int, float)) and
        start - 1e-9 <= m["simulation_timestamp"] <= end + 1e-9]
    by_support = {}
    for support in SUPPORTS:
        selected = [p for p in phase_points if p["support"] == support]
        messages = [m for m in phase_messages
            if SENSOR_TO_SUPPORT.get(m.get("sensor_label")) == support]
        fn = [p["normal_force_magnitude_n"] for p in selected]
        ft = [p["tangential_force_magnitude_n"] for p in selected]
        depth = [p["depth_m"] for p in selected]
        contacts_by_time = {p["time_ns"] for p in selected}
        message_times = {round(float(m["simulation_timestamp"]) * 1e9) for m in messages}
        by_support[support] = {"contact_point_count": len(selected),
            "message_count": len(messages), "unique_contact_timestamps": len(contacts_by_time),
            "contact_timestamp_coverage_fraction": (
                len(contacts_by_time) / len(message_times) if message_times else None),
            "normal_force_magnitude_n": {"median": statistics.median(fn) if fn else None,
                "p05": _percentile(fn, .05), "p95": _percentile(fn, .95),
                "max": max(fn) if fn else None},
            "tangential_force_magnitude_n": {"median": statistics.median(ft) if ft else None,
                "p95": _percentile(ft, .95)},
            "penetration_depth_m": {"median": statistics.median(depth) if depth else None,
                "p95": _percentile(depth, .95)},
            "contact_state": "CONTACT_GEOMETRY_WITH_REPORTED_ZERO_LOAD" if selected and max(fn) == 0
                else "CONTACT_PRESENT" if selected else
                "NO_GROUND_CONTACT_REPORTED" if messages else "OBSERVATION_UNAVAILABLE"}

    # Only exact same-timestamp packets across all five sensors are complete.
    times_by_label = {label: {round(float(m["simulation_timestamp"]) * 1e9)
        for m in phase_messages if SENSOR_TO_SUPPORT.get(m.get("sensor_label")) == label}
        for label in SUPPORTS}
    common_times = set.intersection(*(times_by_label[label] for label in SUPPORTS)) \
        if all(times_by_label.values()) else set()
    per_time = []
    for stamp in sorted(common_times):
        support_loads = {label: sum(p["normal_force_magnitude_n"] for p in phase_points
            if p["support"] == label and p["time_ns"] == stamp) for label in SUPPORTS}
        total = sum(support_loads.values())
        per_time.append({"simulation_timestamp_s": stamp * 1e-9,
            "support_normal_force_n": support_loads, "total_normal_force_n": total,
            "total_over_weight": total / WEIGHT_N,
            "load_share": ({label: value / total for label, value in support_loads.items()}
                if total > 0 else None)})
    totals = [row["total_over_weight"] for row in per_time]
    return {"simulation_interval_s": [start, end], "availability": "AVAILABLE",
        "by_support": by_support,
        "synchronized_load": {"status": "EXACT_TIMESTAMP_MATCH" if per_time else
                "INSUFFICIENT_EXACT_TIMESTAMP_COVERAGE",
            "method": "integer-nanosecond exact match across all five support sensor topics; no interpolation",
            "complete_timestamp_count": len(per_time),
            "normal_force_over_weight": {"median": statistics.median(totals) if totals else None,
                "p05": _percentile(totals, .05), "p95": _percentile(totals, .95)},
            "per_timestamp": per_time}}


def _quaternion_rpy(q):
    try:
        if isinstance(q, dict):
            x, y, z, w = (float(q.get(k, 0.0)) for k in ("x", "y", "z", "w"))
        elif isinstance(q, (list, tuple)) and len(q) == 4:
            x, y, z, w = (float(value) for value in q)
        else:
            return None
    except (TypeError, ValueError):
        return None
    vals = (x, y, z, w)
    if not all(math.isfinite(v) for v in vals):
        return None
    roll = math.atan2(2 * (w*x + y*z), 1 - 2 * (x*x + y*y))
    s = max(-1.0, min(1.0, 2 * (w*y - z*x)))
    pitch = math.asin(s)
    yaw = math.atan2(2 * (w*z + x*y), 1 - 2 * (y*y + z*z))
    return roll, pitch, yaw


def _body_state(native_samples, interval):
    start, end = interval
    rows = []
    for sample in native_samples:
        t = sample.get("simulation_time_s")
        if not isinstance(t, (int, float)) or start is None or end is None or not start - 1e-9 <= t <= end + 1e-9:
            continue
        body = next((link for link in sample.get("links", [])
            if link.get("name") == "simple_agent::body"), None)
        if not body:
            continue
        pos = body.get("position_world_m") or []
        vel = body.get("linear_velocity_world_m_s") or []
        rpy = _quaternion_rpy(body.get("orientation_world_xyzw"))
        if len(pos) >= 3 and len(vel) >= 3:
            rows.append({"time_s": t, "z_m": pos[2], "vz_m_s": vel[2],
                "roll_pitch_yaw_rad": list(rpy) if rpy else None})
    def summary(field):
        vals = [r[field] for r in rows if r[field] is not None]
        return {"count": len(vals), "min": min(vals) if vals else None,
            "median": statistics.median(vals) if vals else None,
            "max": max(vals) if vals else None}
    attitude = {}
    for axis, index in (("roll", 0), ("pitch", 1), ("yaw", 2)):
        values = [r["roll_pitch_yaw_rad"][index] for r in rows
            if r["roll_pitch_yaw_rad"] is not None]
        attitude[axis] = {"count": len(values),
            "min": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "max": max(values) if values else None}
    return {"sample_count": len(rows), "z_m": summary("z_m"),
        "vertical_velocity_m_s": summary("vz_m_s"),
        "roll_pitch_yaw_rad": attitude, "samples": rows}


def _support_sensor_instrumenter(diagnostic_sdf, production_sdf, *, base_instrumenter):
    info = base_instrumenter(diagnostic_sdf, production_sdf)
    return add_caster_contact_sensors(diagnostic_sdf, production_sdf, info)


def _sdf_semantics_without_diagnostic_observers(node):
    """Canonical SDF structure after removing only diagnostic observer additions."""
    if node.tag == "sensor" and node.get("name") in DIAGNOSTIC_SENSOR_NAMES:
        return None
    if node.tag == "plugin" and node.get("name") == "gz::sim::systems::JointStatePublisher":
        return None
    children = tuple(child for child in
        (_sdf_semantics_without_diagnostic_observers(item) for item in node)
        if child is not None)
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(), children)


def _validate_observation_sdf(diagnostic_sdf, production_sdf, joint_info, contact_info):
    root = ET.parse(diagnostic_sdf).getroot()
    model = root.find(".//model[@name='simple_agent']")
    if model is None:
        raise ValueError("Preflight diagnostic SDF has no simple_agent model")
    if joint_info.get("production_sdf_unchanged") is not True or \
            contact_info.get("production_sdf_unchanged") is not True:
        raise ValueError("Preflight found a production SDF integrity failure")
    if Path(joint_info["production_sdf"]) != Path(production_sdf):
        raise ValueError("Joint-state configuration points at a different production SDF")
    diffdrive = model.find("plugin[@name='gz::sim::systems::DiffDrive']")
    if diffdrive is None:
        raise ValueError("Preflight diagnostic SDF has no production DiffDrive plugin")
    expected_topics = {"left", "right", "front_caster", "rear_caster"}
    if not expected_topics.issubset(contact_info.get("contact_topics", {})):
        raise ValueError("Preflight did not resolve all wheel/caster contact topics")
    for label, (link_name, collision_name) in SUPPORTS.items():
        link = model.find(f"link[@name='{link_name}']")
        collision = link.find(f"collision[@name='{collision_name}']") if link is not None else None
        if collision is None:
            raise ValueError(f"Preflight missing support collision {link_name}/{collision_name}")
        if label in ("left_wheel", "right_wheel", "front_caster", "rear_caster"):
            sensor_name = (f"{label}_wheel_ground_contact_diagnostic" if label.endswith("wheel")
                           else f"{label}_support_contact_diagnostic")
            # Existing wheel diagnostic names use left/right prefixes.
            if label == "left_wheel":
                sensor_name = "left_wheel_ground_contact_diagnostic"
            elif label == "right_wheel":
                sensor_name = "right_wheel_ground_contact_diagnostic"
            sensor = link.find(f"sensor[@name='{sensor_name}']")
            if sensor is None or sensor.get("type") != "contact" or \
                    sensor.findtext("contact/collision") != collision_name:
                raise ValueError(f"Preflight support Contact sensor is invalid for {label}")
    chassis = model.find("link[@name='body']/sensor[@name='body_contacts']")
    if chassis is None or chassis.findtext("contact/collision") != "body_collision":
        raise ValueError("Preflight chassis contact sensor configuration is invalid")
    if not joint_info.get("wheel_geometry") or not joint_info.get("diffdrive_configuration"):
        raise ValueError("Preflight required wheel/joint configuration is unresolved")


def preflight(artifact_dir: Path, output: Path):
    """Exercise replay and diagnostic SDF construction without starting Gazebo."""
    artifact_dir, output = Path(artifact_dir), Path(output)
    if not artifact_dir.is_dir():
        raise FileNotFoundError(f"Action24 artifact directory does not exist: {artifact_dir}")
    replay = extract_reversal_replay(artifact_dir)
    actions = replay["completed_episode_actions"][0]
    if len(actions) < 24 or actions[22:24] != ["down", "up"]:
        raise ValueError("Saved source does not establish deterministic Action23 DOWN → Action24 UP")
    if replay.get("target_action") != "up" or replay.get("previous_action") != "down":
        raise ValueError("Saved reversal source target/previous action contract is invalid")

    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir() or not os.access(output, os.W_OK | os.X_OK):
        raise PermissionError(f"Output directory is not writable: {output}")
    # Verify actual create/unlink permissions without altering existing evidence.
    with tempfile.NamedTemporaryFile(prefix=".h-aa-preflight-", dir=output, delete=True):
        pass

    scenario = ScenarioSpec.from_dict(replay["scenario"])
    with tempfile.TemporaryDirectory(prefix="h-aa-support-preflight-") as temp:
        temp = Path(temp)
        production_sdf = GazeboWorldGenerator().generate(
            scenario, temp, closed_loop=True, control_mode="PHYSICS")
        production_bytes = production_sdf.read_bytes()
        diagnostic_sdf, joint_info = joint_diag.instrument_diagnostic_sdf(production_sdf)
        contact_info = _support_sensor_instrumenter(
            diagnostic_sdf, production_sdf,
            base_instrumenter=contact_diag.instrument_contact_sensors)
        _validate_observation_sdf(diagnostic_sdf, production_sdf, joint_info, contact_info)
        production_root = ET.parse(production_sdf).getroot()
        diagnostic_root = ET.parse(diagnostic_sdf).getroot()
        semantic_diff_pass = (_sdf_semantics_without_diagnostic_observers(production_root) ==
                              _sdf_semantics_without_diagnostic_observers(diagnostic_root))
        if not semantic_diff_pass:
            raise ValueError("Diagnostic SDF contains a non-observation structural difference")
        if production_sdf.read_bytes() != production_bytes:
            raise RuntimeError("Production SDF changed during offline preflight")
        diag_hash = _sha256(diagnostic_sdf)
        prod_hash = _sha256(production_sdf)
        topic_map = dict(contact_info["contact_topics"])
        topic_map["chassis"] = contact_info["body_contact_topic"]
        return {"status": "PREFLIGHT_PASS", "gazebo_started": False,
            "artifact_dir": str(artifact_dir.resolve()),
            "source_sequence": actions[22:24], "source_action_count": len(actions),
            "source_evidence": replay.get("sequence_source"),
            "output_directory": str(output.resolve()), "output_writable": True,
            "production_sdf_sha256": prod_hash,
            "diagnostic_sdf_sha256": diag_hash,
            "diagnostic_sdf_structurally_validated": semantic_diff_pass,
            "production_sdf_unchanged": contact_info.get("production_sdf_unchanged") is True,
            "resolved_joint_configuration": {"joint_state_topic": joint_info["joint_state_topic"],
                "wheel_geometry": joint_info["wheel_geometry"],
                "diffdrive_configuration": joint_info["diffdrive_configuration"]},
            "support_contact_topics": topic_map,
            "support_sensor_count": len(SUPPORTS),
            "physics_or_production_changes": False}


def run_diagnostic(artifact_dir: Path, output: Path):
    artifact_dir, output = Path(artifact_dir), Path(output)
    original = contact_diag.instrument_contact_sensors
    def instrument_with_support_sensors(diagnostic_sdf, production_sdf):
        return _support_sensor_instrumenter(diagnostic_sdf, production_sdf,
            base_instrumenter=original)
    contact_diag.instrument_contact_sensors = instrument_with_support_sensors
    try:
        native = native_diag.run_diagnostic(artifact_dir, output / "native_observation")
    finally:
        contact_diag.instrument_contact_sensors = original
    if not native.get("raw_contact_samples"):
        raise RuntimeError("Replay did not preserve raw contact sensor telemetry")
    samples = native["raw_contact_samples"]
    points, malformed, seen_labels, duplicate_count = _deduplicated_points(samples)
    intervals = native.get("phase_intervals_s", {})
    if any(not (isinstance(value, (list, tuple)) and len(value) == 2
                and all(isinstance(x, (int, float)) for x in value))
           for value in intervals.values()):
        replay_path = output / "native_observation" / "production_replay" / \
            "production_replay_evidence" / "action24_acquisition_divergence.json"
        if replay_path.is_file():
            replay = json.loads(replay_path.read_text(encoding="utf-8"))
            intervals = native_diag._phase_intervals_from_replay_evidence(replay)
    phases = {
        "action23_working_acquisition": _phase_rows(points, samples,
            intervals.get("action23_down_acquisition", (None, None))),
        "action24_brake": _phase_rows(points, samples,
            intervals.get("action24_brake", (None, None))),
        "action24_up_acquisition": _phase_rows(points, samples,
            intervals.get("action24_up_acquisition", (None, None))),
    }
    intervals_by_phase = {
        "action23_working_acquisition": intervals.get("action23_down_acquisition", (None, None)),
        "action24_brake": intervals.get("action24_brake", (None, None)),
        "action24_up_acquisition": intervals.get("action24_up_acquisition", (None, None)),
    }
    selected_native, ambiguous_native = native_diag.select_native_physics_samples(
        native.get("native_velocity_samples", []))
    body = {phase: _body_state(selected_native, window)
        for phase, window in intervals_by_phase.items()}
    raw_contact_report_path = output / "native_observation" / "production_replay" / \
        "action24_wheel_ground_contact.json"
    raw_contact_report = json.loads(raw_contact_report_path.read_text(encoding="utf-8")) \
        if raw_contact_report_path.is_file() else {}
    info = raw_contact_report.get("instrumentation", {})
    expected = set(SUPPORTS)
    observed = set(seen_labels)
    complete = expected.issubset(observed)
    report = {"schema_version": "0.7.1",
        "verifier": "diagnostic-only Action23/Action24 complete ground-support load distribution",
        "status": "SUPPORT_TELEMETRY_CAPTURED" if complete else "SUPPORT_TELEMETRY_INCOMPLETE",
        "verdict": "ACTION24_SUPPORT_DISTRIBUTION_REQUIRES_RUNTIME_TELEMETRY",
        "runtime_backend": "DART (previously confirmed; not re-probed)",
        "source_native_diagnostic": native.get("evidence_file"),
        "production_execution": {key: native.get(key) for key in (
            "actions_1_to_23_used_production_adapter", "target_production_step_call_started",
            "target_production_step_returned", "target_exception", "shutdown")},
        "production_sdf_sha256": raw_contact_report.get("production_sdf_sha256_before"),
        "robot_mass_kg": 2.5, "gravity_m_s2": 9.8, "expected_static_weight_n": WEIGHT_N,
        "support_collision_inventory": {
            "left_wheel": {"link": "simple_agent::left_wheel", "collision": "left_collision",
                "link_pose_in_model": "0 0.21 -0.06 1.5707963267948966 0 0",
                "geometry": "cylinder r=0.1 m, length=0.05 m", "ground_support_capable": True,
                "sensor": "diagnostic contact sensor"},
            "right_wheel": {"link": "simple_agent::right_wheel", "collision": "right_collision",
                "link_pose_in_model": "0 -0.21 -0.06 1.5707963267948966 0 0",
                "geometry": "cylinder r=0.1 m, length=0.05 m", "ground_support_capable": True,
                "sensor": "diagnostic contact sensor"},
            "front_caster": {"link": "simple_agent::front_caster", "collision": "front_collision",
                "link_pose_in_model": "0.16 0 -0.12 0 0 0", "geometry": "sphere r=0.04 m",
                "ground_support_capable": True, "sensor": "diagnostic contact sensor"},
            "rear_caster": {"link": "simple_agent::rear_caster", "collision": "rear_collision",
                "link_pose_in_model": "-0.16 0 -0.12 0 0 0", "geometry": "sphere r=0.04 m",
                "ground_support_capable": True, "sensor": "diagnostic contact sensor"},
            "chassis": {"link": "simple_agent::body", "collision": "body_collision",
                "link_pose_in_model": "model origin (model pose 1.5 1.5 0.16)",
                "geometry": "box 0.45 x 0.32 x 0.16 m", "ground_support_capable": True,
                "sensor": "production body_contacts sensor"}},
        "existing_hl_coverage": {"left_wheel": True, "right_wheel": True,
            "chassis": True, "front_caster": False, "rear_caster": False,
            "classification": "SUPPORT_CONTACT_TELEMETRY_INCOMPLETE"},
        "contact_topics": info.get("contact_topics"),
        "sdf_integrity": {"production_sdf_sha256_before":
                raw_contact_report.get("production_sdf_sha256_before"),
            "production_sdf_sha256_after": raw_contact_report.get("production_sdf_sha256_after"),
            "diagnostic_sdf": info.get("diagnostic_sdf"),
            "diagnostic_sdf_sha256": info.get("diagnostic_sdf_sha256"),
            "production_sdf_unchanged": raw_contact_report.get("production_sdf_unchanged") is True,
            "diagnostic_only_delta": info.get("instrumentation_semantics")},
        "contact_message_type": "gz.msgs.Contacts",
        "force_provenance": "DART Contact.force passed through gz-physics and gz-sim to body_1_wrench; projection magnitude is sign-robust under sensor collision relabeling",
        "projection": "Fn=abs(force dot unit(normal)); Ft=sqrt(max(0, |force|^2-Fn^2)); same indexed contact record; no force summation across duplicate timestamp/pair/point/depth keys",
        "phase_intervals_s": intervals_by_phase,
        "phase_load_distribution": phases,
        "chassis_world_state": body,
        "deduplication": {"rule": "integer-nanosecond time + sorted collision pair + rounded world point + depth",
            "duplicate_contact_points_removed": duplicate_count, "malformed_points": malformed,
            "sensor_labels_with_messages": seen_labels,
            "all_five_support_sensors_observed": complete},
        "synchronization": "exact integer-nanosecond timestamps across all five support topics; absent sensor message means total support unavailable; no interpolation",
        "contact_topic_semantics": "event-only Contact streams; missing packets are not converted into zero force or physical contact loss",
        "production_behavior_modified": False,
        "production_sdf_changed": False,
        "diagnostic_sdf_delta": info.get("instrumentation_semantics"),
        "native_kinematics": {"quality": native.get("native_velocity_quality"),
            "raw_sample_count": native.get("native_velocity_sample_count"),
            "unique_physics_sample_count": len(selected_native),
            "ambiguous_states_excluded": len(ambiguous_native)},
        "strict_json_audit": {"status": "PENDING"}}
    # A phase only supports a redistribution verdict when all sensors have exact
    # common timestamps. Otherwise preserve the evidence and stay conservative.
    support_complete = all(phase.get("synchronized_load", {}).get("status") == "EXACT_TIMESTAMP_MATCH"
        for phase in phases.values())
    report["support_distribution_complete_for_all_phases"] = support_complete
    nonfinite = find_nonfinite_paths(report)
    report["strict_json_audit"] = {"status": "PASS" if not nonfinite else "FAIL",
        "nonfinite_field_paths": nonfinite}
    report["nonfinite_field_paths"] = nonfinite
    report["evidence_file"] = str(output / "action24_support_load_distribution.json")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "action24_support_load_distribution.json", _strict_json_value(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight-only", action="store_true",
        help="validate replay/configuration/SDF instrumentation offline without Gazebo")
    args = parser.parse_args(argv)
    if args.preflight_only:
        result = preflight(args.artifact_dir, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    report = run_diagnostic(args.artifact_dir, args.output)
    print("Gazebo Action23/Action24 support load diagnostic: " + report["verdict"])
    print("support sensors: " + str(report["deduplication"]["sensor_labels_with_messages"]))
    print("evidence: " + report["evidence_file"])
    return 0 if report["strict_json_audit"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
