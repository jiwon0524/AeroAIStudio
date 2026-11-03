#!/usr/bin/env python3
"""Diagnostic-only native wheel-joint telemetry for production action 24.

The normal generated SDF is copied byte-for-byte and left untouched. Only the
diagnostic copy receives Gazebo Sim's read-only JointStatePublisher system.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
import tools.diagnose_v07_gazebo_action24_acquisition_divergence as base_diagnostic
from tools.diagnose_v07_gazebo_action24_acquisition_divergence import run_diagnostic
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)

JOINTS = ("left_joint", "right_joint")
LINKS = {"left_joint": "left_wheel", "right_joint": "right_wheel"}
DEFAULT_OUTPUT = Path(
    "validation/v071-host/gazebo-action24-wheel-joint-state-phase3hd")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instrument_diagnostic_sdf(production_sdf: Path) -> tuple[Path, dict]:
    """Create a diagnostic-only SDF sibling with a read-only joint publisher."""
    production_sdf = Path(production_sdf)
    original = production_sdf.read_bytes()
    tree = ET.parse(production_sdf)
    root = tree.getroot()
    model = root.find(".//model[@name='simple_agent']")
    if model is None:
        raise ValueError("Generated SDF has no simple_agent model")
    joints = {}
    for joint in model.findall("joint"):
        name = joint.get("name")
        if name in JOINTS:
            joints[name] = {
                "parent": (joint.findtext("parent") or "").strip(),
                "child": (joint.findtext("child") or "").strip(),
                "axis_xyz_model": (joint.findtext("axis/xyz") or "").strip(),
            }
    if set(joints) != set(JOINTS):
        raise ValueError(f"Generated SDF wheel joints mismatch: {sorted(joints)}")
    for joint, link in LINKS.items():
        if joints[joint]["child"] != link:
            raise ValueError(f"{joint} child link is not configured as {link}")
    diffdrive = model.find("plugin[@name='gz::sim::systems::DiffDrive']")
    if diffdrive is None:
        raise ValueError("Generated SDF DiffDrive plugin is missing")
    geometry = {}
    for joint_name in JOINTS:
        wheel = model.find(f"link[@name='{LINKS[joint_name]}']")
        radius = wheel.findtext("collision/geometry/cylinder/radius") if wheel is not None else None
        geometry[joint_name] = {"wheel_link": LINKS[joint_name],
            "radius_m": float(radius) if radius is not None else None}
    diffdrive_config = {key: (diffdrive.findtext(key) or "").strip()
        for key in ("left_joint", "right_joint", "wheel_separation", "wheel_radius", "topic")}
    world = root.find("world")
    if world is None:
        raise ValueError("Generated SDF has no world")
    world_name = world.get("name")
    topic = f"/world/{world_name}/model/simple_agent/joint_state"
    if model.find("plugin[@name='gz::sim::systems::JointStatePublisher']") is not None:
        raise ValueError("Production SDF unexpectedly already has JointStatePublisher")
    publisher = ET.SubElement(model, "plugin", filename="gz-sim-joint-state-publisher-system",
        name="gz::sim::systems::JointStatePublisher")
    ET.SubElement(publisher, "topic").text = topic
    ET.SubElement(publisher, "joint_name").text = "left_joint"
    ET.SubElement(publisher, "joint_name").text = "right_joint"
    # 0 means publish every simulation iteration in Gazebo Sim 8.
    ET.SubElement(publisher, "update_rate").text = "0"
    diagnostic_sdf = production_sdf.with_name("world_joint_state_diagnostic.sdf")
    ET.indent(tree)
    tree.write(diagnostic_sdf, encoding="utf-8", xml_declaration=True)
    if production_sdf.read_bytes() != original:
        diagnostic_sdf.unlink(missing_ok=True)
        raise RuntimeError("Diagnostic instrumentation modified production SDF")
    return diagnostic_sdf, {
        "production_sdf": str(production_sdf),
        "production_sdf_sha256_before": hashlib.sha256(original).hexdigest(),
        "production_sdf_sha256_after": _sha256(production_sdf),
        "production_sdf_unchanged": True,
        "diagnostic_sdf": str(diagnostic_sdf),
        "diagnostic_sdf_sha256": _sha256(diagnostic_sdf),
        "world_name": world_name, "model_name": "simple_agent",
        "joint_state_topic": topic, "message_type": "gz.msgs.Model",
        "joint_names": joints, "wheel_geometry": geometry,
        "diffdrive_configuration": diffdrive_config,
        "plugin": {"filename": "gz-sim-joint-state-publisher-system",
            "name": "gz::sim::systems::JointStatePublisher",
            "joint_names": list(JOINTS), "update_rate_hz": 0,
            "publication": "each simulation iteration"},
        "instrumentation_semantics": (
            "Diagnostic-only JointStatePublisher; Gazebo Sim ISystemPostUpdate receives "
            "const EntityComponentManager and publishes observed state. It does not issue "
            "joint commands or change physical parameters."),
        "normal_production_sdf_generator_changed": False,
    }


class JointStateCapture:
    """Subscribe directly with the installed gz.msgs.Model binding."""
    def __init__(self):
        self.samples = []
        self.callback = None
        self.topic = None
        self._json = None

    def subscribe(self, adapter, topic):
        from gz.msgs10 import model_pb2
        transport = adapter.env.transport
        self._json = transport.json
        self.topic = topic

        def callback(message):
            data = self._json.MessageToDict(message, preserving_proto_field_name=True)
            self.samples.append(parse_joint_model_data(data,
                len(self.samples) + 1, time.monotonic()))

        self.callback = callback
        if not transport.node.subscribe(model_pb2.Model, topic, callback):
            raise RuntimeError("Gazebo JointStatePublisher subscription failed: " + topic)


def parse_joint_model_data(data, receive_sequence, wall_receive_monotonic_seconds):
    """Preserve native Model/Joint/Axis1 position and velocity fields."""
    stamp = data.get("header", {}).get("stamp")
    sim_time = None
    if isinstance(stamp, dict) and ("sec" in stamp or "nsec" in stamp):
        sim_time = float(stamp.get("sec", 0)) + float(stamp.get("nsec", 0)) * 1e-9
    joints = []
    for row in data.get("joint", []):
        axis = row.get("axis1", {})
        # Axis position/velocity are native protobuf scalars. Omitted proto3
        # scalars mean their native value is zero, not missing telemetry.
        joints.append({"joint_name": row.get("name"),
            "position_rad_native": float(axis.get("position", 0.0)),
            "velocity_rad_s_native": float(axis.get("velocity", 0.0)),
            "position_source": "gz.msgs.Model.joint.axis1.position native",
            "velocity_source": "gz.msgs.Model.joint.axis1.velocity native"})
    return {"receive_sequence": int(receive_sequence),
        "simulation_timestamp": sim_time,
        "message_timestamp_available": sim_time is not None,
        "wall_receive_monotonic_seconds": float(wall_receive_monotonic_seconds),
        "model_name": data.get("name"), "joint_states": joints}


def _series_in_window(samples, start, end):
    return [row for row in samples if row.get("simulation_timestamp") is not None
        and start - 1e-9 <= row["simulation_timestamp"] <= end + 1e-9]


def _joint_state_rows(samples):
    result = {name: [] for name in JOINTS}
    for sample in samples:
        for joint in sample["joint_states"]:
            name = joint.get("joint_name")
            if name in result:
                result[name].append({"receive_sequence": sample["receive_sequence"],
                    "simulation_timestamp": sample["simulation_timestamp"],
                    "wall_receive_monotonic_seconds": sample["wall_receive_monotonic_seconds"],
                    **joint})
    return result


def _pose_entities_for_diagnostic(frame, body_name, decode_pose):
    """Select chassis plus configured wheel links from raw Pose_V names."""
    selected = []
    for pose in frame.get("pose", []):
        name = pose.get("name", "")
        if name == body_name or name in LINKS.values() or (
                "wheel" in name.lower() and body_name in name):
            selected.append({"name": name, **decode_pose(pose)})
    return selected


def _pose_frame_samples_with_wheels(adapter, sequence):
    topic = adapter.env.controller.pose_topic
    messages = base_diagnostic._all_messages_after(adapter, topic, sequence)
    if messages["status"] != "AVAILABLE":
        return messages
    rows, wheel_names = [], set()
    for receive_sequence, frame in messages["samples"]:
        selected = _pose_entities_for_diagnostic(frame, adapter.env.agent_entity,
            adapter.env.controller.decode_pose)
        for entity in selected:
            if entity["name"] in LINKS.values():
                wheel_names.add(entity["name"])
        if selected:
            rows.append({"receive_sequence": receive_sequence,
                "simulation_timestamp": base_diagnostic._stamp(frame),
                "entities": selected})
    return {"status": "AVAILABLE", "sample_count": len(rows),
        "agent_entity": adapter.env.agent_entity,
        "wheel_link_names_observed": sorted(wheel_names), "samples": rows}


def classify_joint_odometry_body(joint_samples, odometry_linear, body_forward_velocity,
                                 expected_forward_raw_sign=1):
    if not joint_samples:
        return "JOINT_TELEMETRY_UNAVAILABLE"
    if not all(math.isfinite(float(value)) for value in
            (odometry_linear, body_forward_velocity)):
        return "JOINT_TELEMETRY_INVALID"
    if len(joint_samples) < 2:
        return "INSUFFICIENT_EVIDENCE"
    left, right = joint_samples.get("left_joint", []), joint_samples.get("right_joint", [])
    if len(left) < 2 or len(right) < 2:
        return "JOINT_TELEMETRY_INVALID"
    left_v = float(left[-1]["velocity_rad_s_native"])
    right_v = float(right[-1]["velocity_rad_s_native"])
    if not math.isfinite(left_v) or not math.isfinite(right_v):
        return "JOINT_TELEMETRY_INVALID"
    if abs(left_v - right_v) > max(0.5, .25 * max(abs(left_v), abs(right_v))):
        return "JOINTS_ASYMMETRIC_OR_ABNORMAL"
    rotating = abs(left_v) > .1 and abs(right_v) > .1
    if rotating and (left_v * expected_forward_raw_sign <= 0 or
                     right_v * expected_forward_raw_sign <= 0):
        return "JOINTS_ASYMMETRIC_OR_ABNORMAL"
    if rotating and abs(body_forward_velocity) <= .02 and abs(odometry_linear) > .1:
        return "JOINTS_ROTATING_BODY_STATIONARY"
    if not rotating and abs(odometry_linear) > .1 and abs(body_forward_velocity) <= .02:
        return "JOINTS_NOT_ROTATING_ODOMETRY_POSITIVE"
    if rotating and abs(body_forward_velocity) > .02 and abs(odometry_linear) > .1:
        return "JOINTS_AND_BODY_MOVING_CONSISTENTLY"
    return "INSUFFICIENT_EVIDENCE"


def _run_with_instrumented_factory(artifact_dir, output, **kwargs):
    capture = JointStateCapture()
    sdf_info = {}
    original_generate = GazeboWorldGenerator.generate
    original_pose_capture = base_diagnostic._pose_frame_samples

    def generate_with_joint_publisher(generator, scenario, root, closed_loop=False,
                                       control_mode="KINEMATIC"):
        production_sdf = original_generate(generator, scenario, root,
            closed_loop=closed_loop, control_mode=control_mode)
        if control_mode != "PHYSICS" or not closed_loop:
            return production_sdf
        diagnostic_sdf, info = instrument_diagnostic_sdf(production_sdf)
        sdf_info.update(info)
        return diagnostic_sdf

    GazeboWorldGenerator.generate = generate_with_joint_publisher
    # Diagnostic-only enhancement: capture the already-published named wheel
    # link poses as secondary corroboration; no runtime/control code changes.
    base_diagnostic._pose_frame_samples = _pose_frame_samples_with_wheels

    def factory(*args, **factory_kwargs):
        adapter = GazeboPhysicsTrainingEnvironment(*args, **factory_kwargs)
        original_reset = adapter.reset

        def reset_and_subscribe(seed):
            result = original_reset(seed)
            topic = sdf_info.get("joint_state_topic")
            if not topic:
                raise RuntimeError("Diagnostic joint-state SDF was not generated")
            capture.subscribe(adapter, topic)
            return result
        adapter.reset = reset_and_subscribe
        return adapter

    try:
        base_dir = Path(output) / "production_replay_evidence"
        Path(output).mkdir(parents=True, exist_ok=False)
        base = run_diagnostic(artifact_dir, base_dir, env_factory=factory, **kwargs)
    finally:
        GazeboWorldGenerator.generate = original_generate
        base_diagnostic._pose_frame_samples = original_pose_capture

    # Pull the already-written strict production replay report, then add the
    # diagnostic-only joint observations without changing its execution path.
    raw_path = Path(base["evidence_file"])
    base = json.loads(raw_path.read_text(encoding="utf-8"))
    if not sdf_info:
        report = {"schema_version": "0.7.1",
            "verifier": "diagnostic-only action24 native wheel-joint state; production replay",
            "status": "FAILED", "verdict": "ACTION24_JOINT_TELEMETRY_INSTRUMENTATION_FAILED",
            "production_behavior_modified": False, "production_python_changed": False,
            "target": base.get("target"),
            "target_production_step_call_started": base.get("target_production_step_call_started"),
            "target_production_step_returned": base.get("target_production_step_returned"),
            "base_replay_evidence": base,
            "joint_telemetry_availability": {"native_position": False,
                "native_velocity": False, "sample_count": 0,
                "status": "UNAVAILABLE", "reason": "Diagnostic SDF instrumentation was not created."},
            "shutdown": base.get("shutdown"), "production_sdf_changed": False}
        paths = find_nonfinite_paths(report)
        report["nonfinite_field_paths"] = paths
        report["strict_json_audit"] = {"status": "PASS" if not paths else "FAIL",
            "nonfinite_field_paths": paths}
        report["evidence_file"] = str(Path(output) / "action24_wheel_joint_state.json")
        write_json(Path(output) / "action24_wheel_joint_state.json", _strict_json_value(report))
        return report
    action23 = base.get("action23", {})
    action23_exec = action23.get("production_telemetry", {}).get("execution_evidence", {})
    action23_raw = action23_exec.get("execution_evidence", {})
    phase_rows = action23_raw.get("phase_evidence", [])
    action23_acquire = next((row for row in phase_rows
        if row.get("phase") == "ACQUIRE_LINEAR"), {})
    action23_start = action23_acquire.get("start_sim_time")
    action23_end = action23_acquire.get("end_sim_time")
    brake = base.get("action24_production_macro_evidence", {}).get("braking_phase", {})
    acq = base.get("action24_production_macro_evidence", {}).get("acquisition_phase_evidence", {})
    intervals = {
        "action23_acquire_down": (action23_start, action23_end),
        "action23_final": (action23_end, action23_end),
        "action24_pre_brake": (brake.get("start_sim_time"), brake.get("start_sim_time")),
        "action24_brake": (brake.get("start_sim_time"), brake.get("end_sim_time")),
        "action24_acquire_up": (acq.get("start_sim_time"), acq.get("end_sim_time")),
    }
    joint_windows = {}
    for name, (start, end) in intervals.items():
        joint_windows[name] = _series_in_window(capture.samples, start, end) \
            if start is not None and end is not None else []
    by_joint = {name: _joint_state_rows(rows) for name, rows in joint_windows.items()}

    model = ET.parse(sdf_info["diagnostic_sdf"]).getroot().find(".//model[@name='simple_agent']")
    joint_axes = {}
    for joint in model.findall("joint"):
        if joint.get("name") in JOINTS:
            joint_axes[joint.get("name")] = {
                "axis_xyz_model": (joint.findtext("axis/xyz") or "").strip(),
                "child_link": (joint.findtext("child") or "").strip(),
                "expected_raw_forward_rotation_sign": "positive; model source config documents both wheel rates positive about +Y for body +X"}
    radius = float(sdf_info["diffdrive_configuration"]["wheel_radius"])
    acq_odometry = base.get("action24_production_macro_evidence", {}).get(
        "production_validator", {}).get("odometry_after", {})
    body_velocity = base.get("command_delivery_levels", {}).get("E_rigid_body_translation", {})
    body_velocity = body_velocity.get("validator", {}).get("world_pose_history_summary", {}).get(
        "world_end_forward_velocity")
    acq_rows = by_joint["action24_acquire_up"]
    latest = {name: (rows[-1] if rows else None) for name, rows in acq_rows.items()}
    derived = None
    if all(latest[name] is not None for name in JOINTS):
        wl = latest["left_joint"]["velocity_rad_s_native"] * radius
        wr = latest["right_joint"]["velocity_rad_s_native"] * radius
        derived = {"status": "DERIVED_FROM_NATIVE_JOINT_VELOCITY",
            "left_surface_speed_m_s": wl, "right_surface_speed_m_s": wr,
            "mean_forward_speed_m_s": (wl + wr) / 2,
            "formula": "mean(axis1 angular velocity * configured wheel radius); axes both model +Y",
            "wheel_radius_m": radius,
            "authority": "diagnostic only; World Pose_V remains physical authority"}
    classifier_rows = {name: by_joint["action24_acquire_up"][name] for name in JOINTS}
    flat = {name: values for name, values in classifier_rows.items()}
    if not capture.samples:
        classification = "JOINT_TELEMETRY_UNAVAILABLE"
    elif not acq_rows["left_joint"] or not acq_rows["right_joint"]:
        classification = ("INSUFFICIENT_EVIDENCE" if any(
            row.get("simulation_timestamp") is None for row in capture.samples)
            else "JOINT_TELEMETRY_INVALID")
    elif acq_odometry.get("linear_x") is None or body_velocity is None:
        classification = "INSUFFICIENT_EVIDENCE"
    else:
        classification = classify_joint_odometry_body(flat,
            float(acq_odometry["linear_x"]), float(body_velocity))
    report = {
        "schema_version": "0.7.1",
        "verifier": "diagnostic-only action24 native wheel-joint state; production replay",
        "status": base.get("status"), "verdict": "ACTION24_WHEEL_JOINT_DIAGNOSTIC_CAPTURED",
        "production_behavior_modified": False, "production_python_changed": False,
        "dqn_used": False, "training_used": False,
        "source": base.get("source"), "target": base.get("target"),
        "actions_1_to_23_used_production_adapter": base.get("actions_1_to_23_used_production_adapter"),
        "target_used_production_adapter": base.get("target_used_production_adapter"),
        "target_production_step_call_started": base.get("target_production_step_call_started"),
        "target_production_step_returned": base.get("target_production_step_returned"),
        "target_exception": base.get("target_exception"),
        "production_command_delivery_evidence": base.get("command_delivery_levels"),
        "model_and_joint_configuration": sdf_info,
        "telemetry_contract": {"source": "Gazebo Sim JointStatePublisher system",
            "topic": sdf_info["joint_state_topic"], "message_type": "gz.msgs.Model",
            "position": "native Joint.axis1.position radians",
            "velocity": "native Joint.axis1.velocity radians/second",
            "message_simulation_timestamp": "Model.header.stamp when provided; otherwise null",
            "receive_sequence": "diagnostic callback-local monotonically increasing sequence",
            "wall_receive_time": "monotonic diagnostic timestamp; not physical authority",
            "publication_rate": "publisher configured for every simulation iteration; observed sample rate reported from captured messages"},
        "action23_sanity_check": {"production_telemetry": action23.get("production_telemetry"),
            "acquire_down_window": by_joint["action23_acquire_down"],
            "final_state_window": by_joint["action23_final"],
            "interpretation": "Compare native joint response against action23 World Pose_V backward motion and DiffDrive odometry; do not coerce missing samples."},
        "action23_to_action24_handoff": base.get("action23_to_action24_handoff"),
        "action24_pre_brake_joint_state": by_joint["action24_pre_brake"],
        "action24_brake": {"production_braking_evidence": base.get(
                "action24_production_macro_evidence", {}).get("braking_phase"),
            "joint_states_by_name": by_joint["action24_brake"]},
        "action24_acquire_up": {"production_acquisition_evidence": acq,
            "joint_states_by_name": by_joint["action24_acquire_up"],
            "diffdrive_odometry_after": acq_odometry,
            "world_pose_body_velocity_m_s": body_velocity,
            "derived_wheel_surface_speed": derived},
        "all_joint_samples": capture.samples,
        "joint_telemetry_availability": {"native_position": bool(capture.samples),
            "native_velocity": bool(capture.samples),
            "sample_count": len(capture.samples),
            "left_joint_sample_count": len(_joint_state_rows(capture.samples)["left_joint"]),
            "right_joint_sample_count": len(_joint_state_rows(capture.samples)["right_joint"]),
            "message_timestamps_present": bool(capture.samples) and all(
                row["simulation_timestamp"] is not None for row in capture.samples),
            "observed_samples_per_sim_second": _observed_rate(capture.samples)},
        "link_pose_secondary": {"action_window_links_observed": base.get(
                "action24_telemetry_window", {}).get("world_pose_frames", {}).get(
                    "wheel_link_names_observed", []),
            "meaning": "Raw wheel-link Pose_V is secondary only and is not reported as joint velocity."},
        "simulation_advancement": base.get("simulation_advancement"),
        "action24_raw_topic_timeline": base.get("action24_telemetry_window"),
        "sensor_and_contact": {"action24_contact_and_collision": base.get(
                "action24_production_macro_evidence", {}).get("contact_and_collision"),
            "action24_sensor": base.get("action24_production_macro_evidence", {}).get("sensor"),
            "action23_sensor_before_after": {key: action23.get("production_telemetry", {}).get(key)
                for key in ("sensor_before", "sensor_after")}},
        "process_start": base.get("process_start"),
        "process_end": base.get("final_process_status"),
        "reset_provenance": base.get("reset_provenance"),
        "shutdown": base.get("shutdown"),
        "physical_consistency_classification": classification,
        "classification_limits": "Only native axis1 joint values can prove joint rotation. No samples, invalid fields, or inadequate synchronization must remain unavailable/insufficient; odometry cannot substitute.",
        "strict_json_audit": {"status": "PENDING"},
    }
    paths = find_nonfinite_paths(report)
    report["strict_json_audit"] = {"status": "PASS" if not paths else "FAIL",
        "nonfinite_field_paths": paths}
    report["nonfinite_field_paths"] = paths
    report["evidence_file"] = str(Path(output) / "action24_wheel_joint_state.json")
    if paths:
        report["verdict"] = "ACTION24_WHEEL_JOINT_DIAGNOSTIC_INVALID_EVIDENCE"
    write_json(Path(output) / "action24_wheel_joint_state.json", _strict_json_value(report))
    return report


def _observed_rate(samples):
    stamps = [row.get("simulation_timestamp") for row in samples]
    stamps = [float(value) for value in stamps if value is not None]
    if len(stamps) < 2 or stamps[-1] <= stamps[0]:
        return None
    return (len(stamps) - 1) / (stamps[-1] - stamps[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prior-failure", type=Path, default=None)
    parser.add_argument("--successful-down-up", type=Path, default=None)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    kwargs = {key: value for key, value in {
        "prior_failure": args.prior_failure,
        "successful_down_up": args.successful_down_up,
        "gui": args.gui}.items() if value is not None}
    report = _run_with_instrumented_factory(args.artifact_dir, args.output, **kwargs)
    print("Gazebo action-24 wheel joint-state diagnostic: " + report["verdict"])
    print("joint samples: " + str(report["joint_telemetry_availability"]["sample_count"]))
    print("evidence: " + report["evidence_file"])
    return 0 if report.get("strict_json_audit", {}).get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
