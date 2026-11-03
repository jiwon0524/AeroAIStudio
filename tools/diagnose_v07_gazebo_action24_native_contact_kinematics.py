#!/usr/bin/env python3
"""Capture native Gazebo link twist and derive Action24 contact kinematics.

This diagnostic replays actions 1--23 through current production and calls the
production ``env.step('up')`` for action 24. A diagnostic-only Gazebo Sim
PostUpdate system observes native world-frame link velocities; no production
runtime/SDF source is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.process_manager import GazeboProcessManager
import tools.diagnose_v07_gazebo_action24_wheel_joint_state as joint_diag
import tools.diagnose_v07_gazebo_action24_wheel_ground_contact as contact_diag
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)

DEFAULT_OUTPUT = Path(
    "validation/v071-host/gazebo-action24-native-contact-kinematics-phase3hl")
PLUGIN_SOURCE = ROOT / "tools/gazebo_native_link_velocity_observer.cc"
LINKS = {"simple_agent::body": "body",
         "simple_agent::left_wheel": "left_wheel",
         "simple_agent::right_wheel": "right_wheel"}
GROUND_COLLISION = "ground::body::collision"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _vadd(a, b): return tuple(x + y for x, y in zip(a, b))
def _vsub(a, b): return tuple(x - y for x, y in zip(a, b))
def _vmul(a, k): return tuple(x * k for x in a)
def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])
def _norm(a): return math.sqrt(_dot(a, a))


def contact_point_velocity(position_world, origin_world, linear_world, angular_world):
    """Derived world contact-point velocity from native world-frame link twist."""
    return _vadd(linear_world, _cross(angular_world,
        _vsub(position_world, origin_world)))


def relative_contact_velocity(position_world, normal_world, origin_world,
                              linear_world, angular_world, *, ground_static):
    if ground_static is not True:
        raise ValueError("zero ground velocity requires proven static ground")
    n_len = _norm(normal_world)
    if not math.isfinite(n_len) or n_len <= 1e-15:
        raise ValueError("invalid contact normal")
    n = _vmul(normal_world, 1.0 / n_len)
    v_contact = contact_point_velocity(position_world, origin_world,
                                       linear_world, angular_world)
    vn = _dot(v_contact, n)
    vt = _vsub(v_contact, _vmul(n, vn))
    values = (*v_contact, vn, *vt, _norm(vt))
    if not all(math.isfinite(x) for x in values):
        raise ValueError("nonfinite derived contact kinematics")
    return {"wheel_contact_velocity_world_m_s": v_contact,
        "ground_contact_velocity_world_m_s": (0.0, 0.0, 0.0),
        "relative_velocity_world_m_s": v_contact,
        "normal_relative_velocity_m_s": vn,
        "tangential_relative_velocity_world_m_s": vt,
        "tangential_relative_speed_m_s": _norm(vt),
        "provenance": "DERIVED_FROM_NATIVE_WORLD_LINK_TWIST_AND_WORLD_CONTACT_GEOMETRY"}


def classify_native_samples(samples):
    if not samples:
        return "INSUFFICIENT_EVIDENCE"
    stamps, iters = [], []
    for row in samples:
        stamp, iteration = row.get("simulation_time_s"), row.get("iteration")
        if (not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or
                not isinstance(iteration, int)):
            return "NATIVE_VELOCITY_INVALID"
        stamps.append(float(stamp)); iters.append(iteration)
        if len(row.get("links", [])) != 3:
            return "NATIVE_VELOCITY_INVALID"
        if {link.get("name") for link in row["links"]} != set(LINKS):
            return "NATIVE_VELOCITY_INVALID"
        for link in row["links"]:
            for field in ("position_world_m", "orientation_world_xyzw",
                          "linear_velocity_world_m_s", "angular_velocity_world_rad_s"):
                value = link.get(field)
                if not isinstance(value, list) or len(value) != (4 if "orientation" in field else 3):
                    return "NATIVE_VELOCITY_INVALID"
                if not all(math.isfinite(float(x)) for x in value):
                    return "NATIVE_VELOCITY_INVALID"
    # PostUpdate may publish several health/native snapshots while Gazebo is
    # paused. Those snapshots legitimately share the same sim time and
    # iteration. Reject reversals, but do not mistake repeated paused
    # observations for invalid physical velocity data.
    if any(b < a for a, b in zip(stamps, stamps[1:])) or any(
            b < a for a, b in zip(iters, iters[1:])):
        return "NATIVE_VELOCITY_INVALID"
    return "NATIVE_WORLD_LINK_VELOCITY_VALID"


def _native_sample_signature(sample):
    return tuple(tuple(float(x) for x in (link.get(field) or []))
        for link in sample.get("links", []) for field in (
            "position_world_m", "orientation_world_xyzw",
            "linear_velocity_world_m_s", "angular_velocity_world_rad_s"))


def select_native_physics_samples(samples):
    """Select one simulation-state sample per exact time/iteration.

    Prefer the unpaused PostUpdate observation, which corresponds to the
    advancing physics tick. Paused copies are transport/observer heartbeats,
    not additional physics samples. If a time has no unpaused observation,
    retain it only when all copies contain identical physical state.
    """
    grouped = {}
    for sample in samples:
        stamp_ns = round(float(sample["simulation_time_s"]) * 1e9)
        key = (stamp_ns, int(sample["iteration"]))
        grouped.setdefault(key, []).append(sample)
    selected, ambiguous = [], []
    for key, group in grouped.items():
        if len(group) == 1:
            selected.append(group[0])
            continue
        advancing = [row for row in group if row.get("paused") is False]
        if len(advancing) == 1:
            selected.append(advancing[0])
        elif len(advancing) > 1:
            ambiguous.append({"simulation_time_ns": key[0], "iteration": key[1],
                              "reason": "multiple_unpaused_samples", "count": len(advancing)})
        elif len({_native_sample_signature(row) for row in group}) == 1:
            selected.append(group[0])
        else:
            ambiguous.append({"simulation_time_ns": key[0], "iteration": key[1],
                              "reason": "paused_samples_disagree", "count": len(group)})
    selected.sort(key=lambda row: (int(row["iteration"]), float(row["simulation_time_s"])))
    return selected, ambiguous


def native_sample_validation_audit(samples):
    """Count structural failures separately from repeated paused timestamps."""
    counts = {key: 0 for key in (
        "missing_body", "missing_left_wheel", "missing_right_wheel",
        "unresolved_entity", "linear_velocity_unavailable",
        "angular_velocity_unavailable", "malformed_vector", "nonfinite_vector",
        "duplicate_link", "unexpected_link", "timestamp_invalid",
        "iteration_invalid", "timestamp_decrease", "iteration_decrease",
        "repeated_timestamp_edges", "repeated_iteration_edges")}
    expected = set(LINKS)
    previous_stamp = previous_iteration = None
    for sample in samples:
        stamp, iteration = sample.get("simulation_time_s"), sample.get("iteration")
        if not isinstance(stamp, (int, float)) or not math.isfinite(float(stamp)):
            counts["timestamp_invalid"] += 1
        elif previous_stamp is not None:
            if float(stamp) < previous_stamp: counts["timestamp_decrease"] += 1
            elif float(stamp) == previous_stamp: counts["repeated_timestamp_edges"] += 1
        if isinstance(stamp, (int, float)) and math.isfinite(float(stamp)):
            previous_stamp = float(stamp)
        if not isinstance(iteration, int):
            counts["iteration_invalid"] += 1
        elif previous_iteration is not None:
            if iteration < previous_iteration: counts["iteration_decrease"] += 1
            elif iteration == previous_iteration: counts["repeated_iteration_edges"] += 1
        if isinstance(iteration, int): previous_iteration = iteration
        links = sample.get("links", [])
        names = [link.get("name") for link in links]
        counts["duplicate_link"] += len(names) - len(set(names))
        counts["unexpected_link"] += sum(name not in expected for name in names)
        name_set = set(names)
        for expected_name, counter in (("simple_agent::body", "missing_body"),
                ("simple_agent::left_wheel", "missing_left_wheel"),
                ("simple_agent::right_wheel", "missing_right_wheel")):
            if expected_name not in name_set: counts[counter] += 1
        for link in links:
            if link.get("resolved") is False: counts["unresolved_entity"] += 1
            for field in ("position_world_m", "orientation_world_xyzw",
                          "linear_velocity_world_m_s", "angular_velocity_world_rad_s"):
                vector = link.get(field)
                if field == "linear_velocity_world_m_s" and link.get("world_linear_velocity_available") is False:
                    counts["linear_velocity_unavailable"] += 1
                if field == "angular_velocity_world_rad_s" and link.get("world_angular_velocity_available") is False:
                    counts["angular_velocity_unavailable"] += 1
                expected_len = 4 if "orientation" in field else 3
                if not isinstance(vector, list) or len(vector) != expected_len:
                    counts["malformed_vector"] += 1
                elif not all(math.isfinite(float(value)) for value in vector):
                    counts["nonfinite_vector"] += 1
    return counts


def _phase_interval_from_execution_phases(execution, phase_name):
    for phase in execution.get("execution_phases", []) or []:
        if phase.get("phase") == phase_name:
            return (phase.get("start_sim_time"), phase.get("end_sim_time"))
    return (None, None)


def _phase_intervals_from_replay_evidence(replay):
    """Read physical phase times from the production replay evidence schema."""
    action23 = replay.get("action23", {}).get("production_telemetry", {}) \
        .get("execution_evidence", {})
    action24 = replay.get("action24_production_macro_evidence", {})
    brake = action24.get("braking_phase", {})
    acquire = action24.get("acquisition_phase_evidence", {})
    return {
        "action23_down_acquisition": _phase_interval_from_execution_phases(
            action23, "ACQUIRE_LINEAR"),
        "action24_brake": (brake.get("start_sim_time"), brake.get("end_sim_time")),
        "action24_up_acquisition": (acquire.get("start_sim_time"), acquire.get("end_sim_time")),
    }


def instrument_native_velocity_plugin(diagnostic_sdf, production_sdf, library):
    diagnostic_sdf, production_sdf = Path(diagnostic_sdf), Path(production_sdf)
    before = production_sdf.read_bytes()
    tree = ET.parse(diagnostic_sdf)
    root = tree.getroot()
    world = root.find("world")
    if world is None:
        raise ValueError("diagnostic SDF has no world")
    if world.find("plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']") is not None:
        raise ValueError("native velocity observer already configured")
    topic = f"/aero/{world.get('name')}/native_link_velocity_diagnostic"
    plugin = ET.SubElement(world, "plugin", filename=str(Path(library).resolve()),
        name="aero_diagnostic::NativeLinkVelocityObserver")
    ET.SubElement(plugin, "topic").text = topic
    ET.indent(tree)
    tree.write(diagnostic_sdf, encoding="utf-8", xml_declaration=True)
    if production_sdf.read_bytes() != before:
        raise RuntimeError("native velocity instrumentation modified production SDF")
    return {"diagnostic_sdf": str(diagnostic_sdf),
        "diagnostic_sdf_sha256": _sha256(diagnostic_sdf),
        "production_sdf_sha256_before": hashlib.sha256(before).hexdigest(),
        "production_sdf_sha256_after": _sha256(production_sdf),
        "production_sdf_unchanged": True, "topic": topic,
        "message_type": "gz.msgs.StringMsg (JSON payload)",
        "plugin_library": str(Path(library).resolve()),
        "plugin_class_name": "aero_diagnostic::NativeLinkVelocityObserver",
        "plugin_scope": "world",
        "plugin_search_path_env_at_injection": os.environ.get("GZ_SIM_SYSTEM_PLUGIN_PATH"),
        "instrumentation_delta": "one world-scoped diagnostic PostUpdate observer plugin",
        "observation_contract": "Link.EnableVelocityChecks requests velocity components; PostUpdate reads const ECM and publishes only. No command, force, joint, collision, or dynamics setters are called."}


def build_observer_library(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    library = output_dir / "libaero_native_link_velocity_observer.so"
    pkg = subprocess.run(["pkg-config", "--cflags", "--libs", "gz-sim8",
        "gz-transport13", "gz-msgs10"], check=True, text=True,
        capture_output=True)
    cmd = ["c++", "-std=c++17", "-shared", "-fPIC", str(PLUGIN_SOURCE),
        "-o", str(library), *shlex.split(pkg.stdout)]
    completed = subprocess.run(cmd, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError("native velocity observer build failed: " +
            completed.stderr[-4000:])
    inspection = inspect_observer_library(library)
    return library, {"command": cmd, "compiler_stderr": completed.stderr,
        "source_sha256": _sha256(PLUGIN_SOURCE), "library_sha256": _sha256(library),
        "static_inspection": inspection}


def inspect_observer_library(library):
    library = Path(library)
    info = {"library_exists": library.is_file(), "library_absolute_path": str(library.resolve()),
        "registration_status": "UNINSPECTED", "dependencies_status": "UNINSPECTED"}
    if not library.is_file():
        return info
    gz_plugin = shutil.which("gz")
    if gz_plugin:
        result = subprocess.run([gz_plugin, "plugin", "--info", "--plugin", str(library)],
            text=True, capture_output=True)
        info["plugin_info_exit_code"] = result.returncode
        info["plugin_info_stdout"] = result.stdout
        info["plugin_info_stderr"] = result.stderr
        info["registration_status"] = "PASS" if result.returncode == 0 and \
            "aero_diagnostic::NativeLinkVelocityObserver" in result.stdout and \
            "ISystemPostUpdate" in result.stdout and "ISystemConfigure" in result.stdout else "FAIL"
    ldd = shutil.which("ldd")
    if ldd:
        result = subprocess.run([ldd, "-r", str(library)], text=True, capture_output=True)
        info["ldd_exit_code"] = result.returncode
        info["unresolved_dependencies"] = [line.strip() for line in
            (result.stdout + result.stderr).splitlines() if "not found" in line or "undefined symbol" in line]
        info["dependencies_status"] = "PASS" if result.returncode == 0 and not info[
            "unresolved_dependencies"] else "FAIL"
    return info


def parse_native_message(data, receive_sequence, wall_receive):
    payload = data.get("data")
    if not isinstance(payload, str):
        raise ValueError("native observer StringMsg has no JSON data")
    row = json.loads(payload)
    row["receive_sequence"] = int(receive_sequence)
    row["wall_receive_monotonic_seconds"] = float(wall_receive)
    return row


class NativeVelocityCapture:
    def __init__(self, base_capture):
        self.base_capture = base_capture
        self.samples = []
        self.heartbeat_messages = []
        self.parse_failures = []
        self.raw_callback_count = 0
        self.callback = None
        self.topic = None
        self.subscribed = False

    def subscribe(self, adapter, topic):
        from gz.msgs10 import stringmsg_pb2
        transport = adapter.env.transport
        self.topic = topic

        def callback(message):
            self.raw_callback_count += 1
            try:
                data = transport.json.MessageToDict(message,
                    preserving_proto_field_name=True)
                self.receive(data, self.raw_callback_count, time.monotonic())
            except Exception as exc:
                self.parse_failures.append({"type": type(exc).__name__,
                    "message": str(exc)})

        self.callback = callback
        self.subscribed = bool(transport.node.subscribe(stringmsg_pb2.StringMsg, topic, callback))
        if not self.subscribed:
            raise RuntimeError("native link velocity subscription failed: " + topic)

    def receive(self, message, receive_sequence, wall_receive):
        try:
            row = parse_native_message(message, receive_sequence, wall_receive)
            self.heartbeat_messages.append(row)
            if native_payload_has_all_velocities(row):
                self.samples.append(row)
        except Exception as exc:
            self.parse_failures.append({"type": type(exc).__name__, "message": str(exc)})


def native_payload_has_all_velocities(row):
    links = row.get("links")
    if not isinstance(links, list) or len(links) != 3:
        return False
    if {link.get("expected_scoped_name", link.get("name")) for link in links} != set(LINKS):
        return False
    required = ("linear_velocity_world_m_s", "angular_velocity_world_rad_s")
    return all(link.get("resolved", True) is True and link.get("velocity_checks_requested", True) is True
        and all(isinstance(link.get(field), list) and len(link[field]) == 3
                   for field in required) for link in links)


def _native_contact_rows(contact_samples, native_samples, collision_map, *, ground_static):
    if ground_static is not True:
        return []
    selected, _ambiguous = select_native_physics_samples(native_samples)
    by_time = {round(float(sample["simulation_time_s"]) * 1e9): sample
        for sample in selected}
    result = []
    for packet in contact_samples:
        timestamp = packet.get("simulation_timestamp")
        if timestamp is None:
            continue
        native = by_time.get(round(float(timestamp) * 1e9))
        if native is None:
            continue
        links = {row["name"].split("::")[-1]: row for row in native["links"]}
        for contact in packet.get("contacts", []):
            pair = contact.get("pair_classification")
            side = {"LEFT_WHEEL_GROUND": "left_wheel",
                    "RIGHT_WHEEL_GROUND": "right_wheel"}.get(pair)
            if side is None:
                continue
            ground_name = collision_map.get("ground")
            if ground_name is None or ground_name not in (
                    contact.get("collision1_name"), contact.get("collision2_name")):
                continue
            points, normals = contact.get("position_native", []), contact.get("normal_native", [])
            wheel = links.get(side)
            if wheel is None:
                continue
            for point, normal in zip(points, normals):
                p = _proto_vector(point); n = _proto_vector(normal)
                derived = relative_contact_velocity(p, n,
                    tuple(wheel["position_world_m"]),
                    tuple(wheel["linear_velocity_world_m_s"]),
                    tuple(wheel["angular_velocity_world_rad_s"]), ground_static=ground_static)
                result.append({"simulation_timestamp_s": float(timestamp),
                    "iteration": native["iteration"], "wheel": side,
                    "contact_pair": pair, "contact_point_world_m": p,
                    "contact_normal_world": n,
                    "native_link_linear_velocity_world_m_s": wheel["linear_velocity_world_m_s"],
                    "native_link_angular_velocity_world_rad_s": wheel["angular_velocity_world_rad_s"],
                    "derived_contact_kinematics": derived})
    return result


def _proto_vector(value):
    if isinstance(value, dict):
        return (float(value.get("x", 0)), float(value.get("y", 0)),
                float(value.get("z", 0)))
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(float(x) for x in value)
    raise ValueError("invalid world-frame contact vector")


def run_diagnostic(artifact_dir, output):
    output = Path(output)
    library, build = build_observer_library(output / "observer_build")
    old_instrument = joint_diag.instrument_diagnostic_sdf
    old_capture = joint_diag.JointStateCapture
    old_plugin_path = os.environ.get("GZ_SIM_SYSTEM_PLUGIN_PATH")
    old_launch = GazeboProcessManager.launch
    capture_box = {}
    launch_box = {}

    def record_launch(manager, world, gui=False, paused=True):
        result = old_launch(manager, world, gui=gui, paused=paused)
        launch_box.update({"command": list(manager.process.args) if manager.process else None,
            "world_file": str(Path(world).resolve()), "gui": bool(gui),
            "paused": bool(paused), "partition": manager.partition,
            "environment": {key: os.environ.get(key) for key in
                ("GZ_SIM_SYSTEM_PLUGIN_PATH", "GZ_SYSTEM_PLUGIN_PATH")}})
        if manager.process:
            launch_box["environment"]["GZ_PARTITION"] = manager.partition
        return result

    def instrument(production_sdf):
        diagnostic_sdf, info = old_instrument(production_sdf)
        native_info = instrument_native_velocity_plugin(diagnostic_sdf,
            production_sdf, library)
        info["native_velocity_observer"] = native_info
        capture_box["info"] = native_info
        return diagnostic_sdf, info

    class NativeJointCapture(old_capture):
        def subscribe(self, adapter, topic):
            super().subscribe(adapter, topic)
            native = NativeVelocityCapture(self)
            native.subscribe(adapter, capture_box["info"]["topic"])
            capture_box["capture"] = native

    joint_diag.instrument_diagnostic_sdf = instrument
    joint_diag.JointStateCapture = NativeJointCapture
    GazeboProcessManager.launch = record_launch
    os.environ["GZ_SIM_SYSTEM_PLUGIN_PATH"] = os.pathsep.join(filter(None,
        [str(library.parent), os.environ.get("GZ_SIM_SYSTEM_PLUGIN_PATH", "")]))
    try:
        base = contact_diag._run_contact_diagnostic(artifact_dir, output / "production_replay")
    finally:
        joint_diag.instrument_diagnostic_sdf = old_instrument
        joint_diag.JointStateCapture = old_capture
        GazeboProcessManager.launch = old_launch
        if old_plugin_path is None:
            os.environ.pop("GZ_SIM_SYSTEM_PLUGIN_PATH", None)
        else:
            os.environ["GZ_SIM_SYSTEM_PLUGIN_PATH"] = old_plugin_path
    native_capture = capture_box.get("capture")
    raw = json.loads(Path(base["evidence_file"]).read_text(encoding="utf-8"))
    replay_path = output / "production_replay" / "production_replay_evidence" / \
        "action24_acquisition_divergence.json"
    replay_evidence = json.loads(replay_path.read_text(encoding="utf-8")) if replay_path.is_file() else {}
    sdf_path = Path((capture_box.get("info") or {}).get("diagnostic_sdf", ""))
    log_path = sdf_path.with_name("gazebo.log") if sdf_path else None
    if log_path and log_path.is_file():
        launch_box["gazebo_log_path"] = str(log_path)
        launch_box["gazebo_log_tail"] = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
    samples = native_capture.samples if native_capture else []
    quality = classify_native_samples(samples)
    sdf_audit = raw.get("static_sdf_audit", {})
    ground_static_value = str(sdf_audit.get("ground", {}).get("static", "")).strip().lower()
    ground_static = ground_static_value in ("true", "1")
    contact_rows = _native_contact_rows(raw.get("contact_samples", []), samples,
        raw.get("collision_entity_map", {}), ground_static=ground_static) \
        if quality == "NATIVE_WORLD_LINK_VELOCITY_VALID" else []
    intervals = _phase_intervals_from_replay_evidence(replay_evidence)
    if not any(start is not None and end is not None for start, end in intervals.values()):
        intervals = _phase_intervals_from_contact_report(raw)
    def in_interval(row, name):
        start, end = intervals[name]
        stamp = row["simulation_timestamp_s"]
        return start is not None and end is not None and start - 1e-9 <= stamp <= end + 1e-9
    action23_rows = [r for r in contact_rows if in_interval(r, "action23_down_acquisition")]
    brake_rows = [r for r in contact_rows if in_interval(r, "action24_brake")]
    acquisition_rows = [r for r in contact_rows if in_interval(r, "action24_up_acquisition")]
    action23_start, action23_end = intervals["action23_down_acquisition"]
    steady_start = (action23_end - .2 * (action23_end - action23_start)
                    if action23_start is not None and action23_end is not None else None)
    steady_rows = [r for r in action23_rows if steady_start is not None and
                   r["simulation_timestamp_s"] >= steady_start]
    report = {"schema_version": "0.7.1",
        "verifier": "diagnostic-only Action24 native contact kinematics; current production replay",
        "status": "DIAGNOSTIC_CAPTURE_COMPLETE" if base.get("status") == "DIAGNOSTIC_CAPTURE_COMPLETE" else base.get("status"),
        "verdict": ("EARLIER_PREFIX_FAILURE" if not raw.get("target_production_step_call_started")
            else "ACTION24_NATIVE_CONTACT_KINEMATICS_CAPTURED"
            if quality == "NATIVE_WORLD_LINK_VELOCITY_VALID" else quality),
        "provenance": raw.get("provenance"), "target": raw.get("target"),
        "actions_1_to_23_used_production_adapter": raw.get("actions_1_to_23_used_production_adapter"),
        "target_used_production_adapter": raw.get("target_used_production_adapter"),
        "target_production_step_call_started": raw.get("target_production_step_call_started"),
        "target_production_step_returned": raw.get("target_production_step_returned"),
        "target_exception": raw.get("target_exception"),
        "production_replay_lifecycle": {key: replay_evidence.get(key) for key in
            ("failure_stage", "last_completed_stage", "prefix_replayed_count",
             "shutdown", "process_start", "final_process_status", "reset_provenance")},
        "action23_to_action24_handoff": raw.get("action23_to_action24_handoff"),
        "production_action24_macro_evidence": raw.get("action24_production_macro_evidence"),
        "action23_production_evidence": raw.get("action23"),
        "static_sdf_audit": raw.get("static_sdf_audit"),
        "collision_entity_map": raw.get("collision_entity_map"),
        "raw_contact_samples": raw.get("contact_samples"),
        "native_joint_telemetry": {"action23": raw.get("action23_sanity_check"),
            "action24_brake": raw.get("action24_brake"),
            "action24_acquisition": raw.get("action24_acquire_up")},
        "world_pose_body_authority_evidence": raw.get("world_pose_body_evidence"),
        "sensor_contact_collision_evidence": raw.get("sensor_collision_process_reset"),
        "native_api": {"api": "gz::sim::Link::WorldLinearVelocity / WorldAngularVelocity",
            "headers": ["gz/sim/Link.hh", "gz/sim/components/LinearVelocity.hh",
                        "gz/sim/components/AngularVelocity.hh"],
            "frame": "world", "linear_units": "m/s", "angular_units": "rad/s",
            "sample_phase": "ISystemPostUpdate after physics at UpdateInfo.simTime / iterations",
            "observation_read_only": True,
            "read_only_basis": "Link::EnableVelocityChecks requests velocity-state components; PostUpdate reads through const ECM. The observer invokes no Link state setters, command components, force APIs, joint APIs, or physics configuration APIs.",
            "no_pose_finite_difference_for_wheel_velocity": True,
            "odometry_or_command_used_as_kinematic_input": False},
        "build": build, "instrumentation": (capture_box.get("info") or {}),
        "runtime_launch": launch_box,
        "native_velocity_quality": quality, "native_velocity_samples": samples,
        "native_velocity_sample_count": len(samples),
        "observer_health": _observer_health(native_capture),
        "observer_pipeline": _observer_pipeline(native_capture, samples, quality,
            contact_rows, intervals),
        "contact_sync": {"method": "exact integer-nanosecond equality of PostUpdate simulation time and Contacts message simulation timestamp",
            "interpolation": False, "contact_iteration_native": False,
            "ground_static_from_production_sdf": ground_static,
            "contact_vectors_world_frame": True},
        "phase_intervals_s": intervals,
        "action23_baseline": {"source_contact_window": raw.get("action23_working_contact_window"),
            "terminal_steady_interval_s": [steady_start, action23_end],
            "terminal_steady_selection": "last 20% of measured 0.1 s Action23 acquisition, matching Phase 3H-I",
            "native_contact_kinematics": action23_rows,
            "terminal_steady_summary": _phase_summary(steady_rows)},
        "action24_brake": {"source_contact_window": raw.get("action24_brake_contact_window"),
            "native_contact_kinematics": brake_rows},
        "action24_acquisition": {"source_contact_window": raw.get("action24_up_acquisition_contact_window"),
            "native_contact_kinematics": acquisition_rows},
        "contact_kinematics_all": contact_rows,
        "body_translation_authority": "World Pose_V production validator remains unchanged; native chassis velocity is corroboration only",
        "left_classification": _side_status(acquisition_rows, "left_wheel",
                                              steady_rows, .01),
        "right_classification": _side_status(acquisition_rows, "right_wheel",
                                               steady_rows, .01),
        "shutdown": replay_evidence.get("shutdown"),
        "process": raw.get("sensor_collision_process_reset", {}).get("process_start"),
        "process_end": raw.get("sensor_collision_process_reset", {}).get("process_end"),
        "reset_provenance": raw.get("reset_provenance"),
        "production_sdf_unchanged": (capture_box.get("info") or {}).get("production_sdf_unchanged"),
        "production_behavior_changed": False,
        "strict_json_audit": {"status": "PENDING"}}
    paths = find_nonfinite_paths(report)
    report["strict_json_audit"] = {"status": "PASS" if not paths else "FAIL",
        "nonfinite_field_paths": paths}
    report["nonfinite_field_paths"] = paths
    report["evidence_file"] = str(output / "action24_native_contact_kinematics.json")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "action24_native_contact_kinematics.json", _strict_json_value(report))
    return report


def _phase_summary(rows):
    result = {}
    for side in ("left_wheel", "right_wheel"):
        selected = [r for r in rows if r["wheel"] == side]
        speeds = sorted(r["derived_contact_kinematics"][
            "tangential_relative_speed_m_s"] for r in selected)
        def percentile(q):
            return speeds[max(0, math.ceil(q * len(speeds)) - 1)] if speeds else None
        result[side] = {"count": len(speeds), "min": speeds[0] if speeds else None,
            "median": statistics.median(speeds) if speeds else None,
            "p95": percentile(.95), "max": speeds[-1] if speeds else None}
    return result


def _side_status(rows, side, baseline_rows, min_span_s):
    selected = [row for row in rows if row["wheel"] == side]
    baseline = [row for row in baseline_rows if row["wheel"] == side]
    stamps = sorted({row["simulation_timestamp_s"] for row in selected})
    span = stamps[-1] - stamps[0] if len(stamps) > 1 else 0.0
    target_stats = _phase_summary(selected)[side]
    base_stats = _phase_summary(baseline)[side]
    if len(selected) < 2 or span < min_span_s or not baseline:
        status = "INSUFFICIENT_OR_UNOBSERVABLE"
    elif target_stats["median"] > base_stats["p95"]:
        status = "SUBSTANTIAL_RELATIVE_SLIDING"
    else:
        status = "ROLLING_LIKE_BASELINE"
    return {"status": status, "sample_count": len(selected),
        "observed_contact_span_s": span, "minimum_span_s": min_span_s,
        "target_tangential_speed": target_stats,
        "action23_terminal_steady_tangential_speed": base_stats,
        "classification_rule": "target median compared with Action23 terminal steady p95; no fixed speed threshold"}


def _observer_health(capture):
    if capture is None:
        return {"subscriber_created": False, "raw_received_message_count": 0,
            "parsed_heartbeat_count": 0, "parse_failures": [],
            "status": "NO_CAPTURE_OBJECT"}
    messages = capture.heartbeat_messages
    return {"subscriber_created": capture.subscribed,
        "topic": capture.topic,
        "message_type": "gz.msgs.StringMsg",
        "raw_received_message_count": capture.raw_callback_count,
        "callback_count": capture.raw_callback_count,
        "parsed_heartbeat_count": len(messages),
        "parse_failures": capture.parse_failures,
        "first_heartbeat": messages[0] if messages else None,
        "last_heartbeat": messages[-1] if messages else None,
        "native_velocity_ready_heartbeat_count": sum(
            row.get("native_velocity_sample_ready") is True for row in messages),
        "status": "HEARTBEAT_RECEIVED" if messages else "NO_HEARTBEAT_RECEIVED"}


def _observer_pipeline(capture, samples, quality, synchronized_contacts, intervals):
    health = _observer_health(capture)
    messages = capture.heartbeat_messages if capture else []
    entity_valid = [row for row in messages if len(row.get("links", [])) == 3 and
        {item.get("expected_scoped_name") for item in row["links"]} == set(LINKS) and
        all(item.get("resolved") is True and item.get("velocity_checks_requested") is True
            for item in row["links"])]
    time_valid = [row for row in entity_valid if isinstance(row.get("simulation_time_s"),
        (int, float)) and math.isfinite(row["simulation_time_s"]) and
        isinstance(row.get("iteration"), int)]
    ready = [row for row in time_valid if row.get("native_velocity_sample_ready") is True and
        native_payload_has_all_velocities(row)]
    action_windows = [window for window in intervals.values()
        if len(window) == 2 and window[0] is not None and window[1] is not None]
    selected_samples, ambiguous = select_native_physics_samples(samples)
    action_window_samples = [row for row in selected_samples if any(
        start - 1e-9 <= row["simulation_time_s"] <= end + 1e-9
        for start, end in action_windows)]
    return {"raw_callback_messages": health.get("callback_count", 0),
        "parsed_heartbeat_messages": health.get("parsed_heartbeat_count", 0),
        "entity_valid_messages": len(entity_valid),
        "timestamp_iteration_valid_messages": len(time_valid),
        "native_velocity_ready_messages": len(ready),
        "finite_monotonic_native_samples": len(selected_samples) if quality == "NATIVE_WORLD_LINK_VELOCITY_VALID" else 0,
        "repeated_paused_observations_collapsed": len(samples) - len(selected_samples) - sum(
            row.get("count", 0) for row in ambiguous),
        "ambiguous_simulation_states_excluded": ambiguous,
        "action_window_native_samples": len(action_window_samples),
        "exact_timestamp_synchronized_contact_samples": len(synchronized_contacts),
        "native_velocity_quality": quality,
        "filtering_note": "Counts distinguish callback, parse, entity resolution, time validity, native availability, and contact synchronization; no interpolation or command/odometry substitution."}


def _phase_intervals_from_contact_report(report):
    windows = {
        "action23_down_acquisition": report.get("action23_working_contact_window", {}),
        "action24_brake": report.get("action24_brake_contact_window", {}),
        "action24_up_acquisition": report.get("action24_up_acquisition_contact_window", {}),
    }
    return {name: tuple(row.get("simulation_interval", (None, None)))
        for name, row in windows.items()}


def reanalyze_existing_evidence(evidence_path, replay_path=None, output_path=None):
    """Reclassify saved H-L telemetry offline; never starts Gazebo."""
    evidence_path = Path(evidence_path)
    report = json.loads(evidence_path.read_text(encoding="utf-8"))
    if replay_path is None:
        replay_path = evidence_path.parent / "production_replay" / \
            "production_replay_evidence" / "action24_acquisition_divergence.json"
    replay_path = Path(replay_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    samples = report.get("native_velocity_samples", [])
    quality = classify_native_samples(samples)
    selected, ambiguous = select_native_physics_samples(samples)
    intervals = _phase_intervals_from_replay_evidence(replay)
    static_value = report.get("static_sdf_audit", {}).get("ground", {}).get("static")
    static = static_value is True or str(static_value).strip().lower() in ("true", "1")
    contacts = report.get("raw_contact_samples", [])
    collision_map = report.get("collision_entity_map", {})
    rows = _native_contact_rows(contacts, selected, collision_map,
                                ground_static=static) if quality == \
        "NATIVE_WORLD_LINK_VELOCITY_VALID" else []
    def inside(row, key):
        start, end = intervals[key]
        return start is not None and end is not None and \
            start - 1e-9 <= row["simulation_timestamp_s"] <= end + 1e-9
    action23 = [row for row in rows if inside(row, "action23_down_acquisition")]
    brake = [row for row in rows if inside(row, "action24_brake")]
    acquire = [row for row in rows if inside(row, "action24_up_acquisition")]
    start23, end23 = intervals["action23_down_acquisition"]
    steady_start = end23 - .2 * (end23 - start23) if start23 is not None and end23 is not None else None
    steady = [row for row in action23 if steady_start is not None and
              row["simulation_timestamp_s"] >= steady_start]
    native_times = sorted({round(float(row["simulation_time_s"])*1e9)
                           for row in selected})
    contact_times = {round(float(row["simulation_timestamp"])*1e9)
                     for row in contacts if row.get("simulation_timestamp") is not None}
    exact_matches = contact_times & set(native_times)
    result = {
        "schema_version": "0.7.1", "analysis": "offline_reanalysis_of_saved_phase3hl_evidence",
        "status": "OFFLINE_REANALYSIS_COMPLETE",
        "source_evidence": str(evidence_path), "source_replay_evidence": str(replay_path),
        "source_host_verdict": report.get("verdict"),
        "production_execution": {"target": report.get("target"),
            "actions_1_to_23_completed": replay.get("prefix_replayed_count") == 23,
            "target_step_started": report.get("target_production_step_call_started"),
            "target_step_returned": report.get("target_production_step_returned"),
            "exception": report.get("target_exception"), "shutdown": replay.get("shutdown")},
        "observer_health": report.get("observer_health"),
        "native_velocity_quality": quality,
        "native_velocity_observability": "NATIVE_WHEEL_LINK_VELOCITY_OBSERVABILITY_CONFIRMED"
            if quality == "NATIVE_WORLD_LINK_VELOCITY_VALID" else quality,
        "native_sample_audit": {"captured_samples": len(samples),
            "pre_fix_invalidity_counts": native_sample_validation_audit(samples),
            "selected_physics_samples": len(selected), "ambiguous_states_excluded": ambiguous,
            "first_time_s": selected[0]["simulation_time_s"] if selected else None,
            "last_time_s": selected[-1]["simulation_time_s"] if selected else None,
            "first_iteration": selected[0]["iteration"] if selected else None,
            "last_iteration": selected[-1]["iteration"] if selected else None,
            "unique_simulation_states": len(native_times),
            "paused_duplicate_observations_collapsed": len(samples)-len(selected)-sum(
                item.get("count", 0) for item in ambiguous),
            "all_samples_structurally_finite": quality == "NATIVE_WORLD_LINK_VELOCITY_VALID",
            "monotonic_rule": "nondecreasing simulation time and iteration; repeated paused observations allowed"},
        "contact_sync": {"method": "exact nanosecond timestamp match; advancing unpaused native sample preferred; identical paused-only repeats may be retained; disagreeing paused-only groups excluded; no interpolation",
            "contact_packet_count": len(contacts), "contact_unique_timestamp_count": len(contact_times),
            "exact_timestamp_matches": len(exact_matches), "unmatched_contact_timestamps": len(contact_times-exact_matches),
            "ambiguous_native_timestamps_excluded": len(ambiguous),
            "ground_static": static},
        "phase_intervals_s": intervals,
        "action23_baseline": {"contact_kinematics_count": len(action23),
            "steady_interval_s": [steady_start, end23], "steady_summary": _phase_summary(steady)},
        "action24_brake": {"contact_kinematics_count": len(brake),
            "tangential_speed_summary": _phase_summary(brake)},
        "action24_acquisition": {"contact_kinematics_count": len(acquire),
            "tangential_speed_summary": _phase_summary(acquire)},
        "left_classification": _side_status(acquire, "left_wheel", steady, .01),
        "right_classification": _side_status(acquire, "right_wheel", steady, .01),
        "contact_kinematics": {"action23_steady": steady, "action24_brake": brake,
            "action24_acquisition": acquire},
        "classification_note": "Native velocity validity is independent of downstream contact/phase validity; this offline result does not revise the production PhysicalControlFailure.",
        "strict_json_audit": {"status": "PENDING"}}
    paths = find_nonfinite_paths(result)
    result["strict_json_audit"] = {"status": "PASS" if not paths else "FAIL",
        "nonfinite_field_paths": paths}
    result["nonfinite_field_paths"] = paths
    output_path = Path(output_path) if output_path else evidence_path.with_name(
        "action24_native_contact_kinematics_reanalysis.json")
    result["output_file"] = str(output_path)
    write_json(output_path, _strict_json_value(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--artifact-dir", type=Path)
    mode.add_argument("--reanalyze-existing", type=Path,
        help="offline reanalysis of an existing JSON artifact; does not launch Gazebo")
    parser.add_argument("--replay-evidence", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.reanalyze_existing:
        result = reanalyze_existing_evidence(args.reanalyze_existing,
            args.replay_evidence, args.output if args.output != DEFAULT_OUTPUT else None)
        print("offline native contact kinematics reanalysis: " + result["native_velocity_quality"])
        print("selected physics samples: " + str(result["native_sample_audit"]["selected_physics_samples"]))
        print("evidence: " + result.get("output_file", str(args.output)))
        return 0 if result["strict_json_audit"]["status"] == "PASS" else 1
    result = run_diagnostic(args.artifact_dir, args.output)
    print("Gazebo action-24 native contact kinematics: " + result["verdict"])
    print("native link samples: " + str(result["native_velocity_sample_count"]))
    print("evidence: " + result["evidence_file"])
    return 0 if result["strict_json_audit"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
