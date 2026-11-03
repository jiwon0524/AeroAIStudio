#!/usr/bin/env python3
"""Diagnostic-only wheel/ground contact capture for production action 24.

The tool reuses the native joint-state diagnostic and adds two Gazebo Contact
sensors to a diagnostic SDF copy. Production SDF and training code are untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
import tools.diagnose_v07_gazebo_action24_wheel_joint_state as joint_diag
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)

WHEEL_LINKS = {"left": "left_wheel", "right": "right_wheel"}
WHEEL_COLLISIONS = {"left": "left_collision", "right": "right_collision"}
GROUND_COLLISION = ("ground", "body", "collision")
DEFAULT_OUTPUT = Path(
    "validation/v071-host/gazebo-action24-wheel-ground-contact-phase3hf")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _stamp_seconds(header):
    stamp = (header or {}).get("stamp")
    if not isinstance(stamp, dict) or not ("sec" in stamp or "nsec" in stamp):
        return None
    value = float(stamp.get("sec", 0)) + float(stamp.get("nsec", 0)) * 1e-9
    return value if math.isfinite(value) else None


def _entity_name(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name")
    return None


def classify_contact_pair(first, second, collision_map):
    """Classify only exact SDF collision identities; unresolved pairs stay OTHER."""
    a, b = _entity_name(first), _entity_name(second)
    if not a or not b:
        return "OTHER"

    def resolves(name, key):
        return name == key or name.endswith("::" + key)

    ground = collision_map["ground"]
    body = collision_map["body"]
    left = collision_map["left_wheel"]
    right = collision_map["right_wheel"]
    if (resolves(a, left) and resolves(b, ground)) or (resolves(b, left) and resolves(a, ground)):
        return "LEFT_WHEEL_GROUND"
    if (resolves(a, right) and resolves(b, ground)) or (resolves(b, right) and resolves(a, ground)):
        return "RIGHT_WHEEL_GROUND"
    if (resolves(a, body) and resolves(b, ground)) or (resolves(b, body) and resolves(a, ground)):
        return "CHASSIS_GROUND"
    if ((resolves(a, left) or resolves(a, right)) and resolves(b, body)) or \
            ((resolves(b, left) or resolves(b, right)) and resolves(a, body)):
        return "WHEEL_CHASSIS"
    if "obstacle" in a.lower() or "obstacle" in b.lower() or "wall_" in a.lower() or "wall_" in b.lower():
        return "OBSTACLE"
    return "OTHER"


def parse_contacts_message(data, topic, receive_sequence, wall_receive_monotonic_seconds,
                           collision_map):
    """Keep protobuf contact fields native and classify collision pairs."""
    rows = []
    for contact in data.get("contact", []):
        first, second = contact.get("collision1"), contact.get("collision2")
        rows.append({
            "contact_header": contact.get("header"),
            "collision1": first,
            "collision2": second,
            "collision1_name": _entity_name(first),
            "collision2_name": _entity_name(second),
            "pair_classification": classify_contact_pair(first, second, collision_map),
            "position_native": contact.get("position", []),
            "normal_native": contact.get("normal", []),
            "depth_m_native": contact.get("depth", []),
            "wrench_native": contact.get("wrench", []),
            "world": contact.get("world"),
        })
    timestamp = _stamp_seconds(data.get("header"))
    if timestamp is None and rows:
        timestamp = _stamp_seconds(rows[0].get("contact_header"))
    return {"topic": topic, "receive_sequence": int(receive_sequence),
        "wall_receive_monotonic_seconds": float(wall_receive_monotonic_seconds),
        "simulation_timestamp": timestamp,
        "contact_count": len(rows), "contacts": rows}


def _collision_map_from_sdf(production_sdf):
    root = ET.parse(production_sdf).getroot()
    model = root.find(".//model[@name='simple_agent']")
    ground = root.find(".//model[@name='ground']")
    if model is None or ground is None:
        raise ValueError("Expected simple_agent and ground models in production SDF")
    expected = {
        "ground": (ground, "body", "collision"),
        "body": (model, "body", "body_collision"),
        "left_wheel": (model, "left_wheel", "left_collision"),
        "right_wheel": (model, "right_wheel", "right_collision"),
    }
    result = {}
    for key, (owner, link_name, collision_name) in expected.items():
        link = owner.find(f"link[@name='{link_name}']")
        collision = link.find(f"collision[@name='{collision_name}']") if link is not None else None
        if collision is None:
            raise ValueError(f"Missing configured collision for {key}: {link_name}/{collision_name}")
        result[key] = f"{owner.get('name')}::{link_name}::{collision_name}"
    return result


def _static_sdf_audit(production_sdf):
    root = ET.parse(production_sdf).getroot()
    world = root.find("world")
    model = root.find(".//model[@name='simple_agent']")
    ground = root.find(".//model[@name='ground']")
    if world is None or model is None or ground is None:
        raise ValueError("SDF missing world, simple_agent, or ground")

    def link_data(owner, name):
        link = owner.find(f"link[@name='{name}']")
        if link is None:
            raise ValueError(f"Missing link {name}")
        collision = link.find("collision")
        inertial = link.find("inertial")
        return {
            "pose": link.findtext("pose"),
            "mass": inertial.findtext("mass") if inertial is not None else None,
            "inertia": ({child.tag: child.text for child in inertial.find("inertia")}
                        if inertial is not None and inertial.find("inertia") is not None else None),
            "collision_name": collision.get("name") if collision is not None else None,
            "collision_pose": collision.findtext("pose") if collision is not None else None,
            "geometry": ET.tostring(collision.find("geometry"), encoding="unicode")
                        if collision is not None and collision.find("geometry") is not None else None,
            "surface": ET.tostring(collision.find("surface"), encoding="unicode")
                       if collision is not None and collision.find("surface") is not None else None,
        }

    joints = {}
    for name in ("left_joint", "right_joint", "front_fixed", "rear_fixed"):
        joint = model.find(f"joint[@name='{name}']")
        if joint is None:
            continue
        joints[name] = {"type": joint.get("type"), "parent": joint.findtext("parent"),
            "child": joint.findtext("child"),
            "axis_xyz": joint.findtext("axis/xyz"),
            "lower": joint.findtext("axis/limit/lower"),
            "upper": joint.findtext("axis/limit/upper")}
    diffdrive = model.find("plugin[@name='gz::sim::systems::DiffDrive']")
    return {
        "world": world.get("name"), "gravity": world.findtext("gravity"),
        "physics": ET.tostring(world.find("physics"), encoding="unicode"),
        "simple_agent_static": model.findtext("static"),
        "self_collision": model.findtext("self_collide"),
        "links": {name: link_data(model, name) for name in
                  ("body", "left_wheel", "right_wheel", "front_caster", "rear_caster")},
        "ground": {"pose": ground.findtext("pose"),
            "static": ground.findtext("static"),
            "link_body_collision": ground.find("link[@name='body']/collision").get("name"),
            "collision_geometry": ET.tostring(
                ground.find("link[@name='body']/collision/geometry"), encoding="unicode"),
            "surface": ET.tostring(ground.find("link[@name='body']/collision/surface"), encoding="unicode")
                       if ground.find("link[@name='body']/collision/surface") is not None else None},
        "joints": joints,
        "diffdrive": {key: diffdrive.findtext(key) for key in
                      ("left_joint", "right_joint", "wheel_radius", "wheel_separation", "topic",
                       "odom_publish_frequency")} if diffdrive is not None else None,
        "direction_asymmetry_in_drive_wheels": False,
        "direction_asymmetry_basis": (
            "left/right drive wheel cylinders, poses, friction mu/mu2, joint axes and unbounded "
            "revolute limits are symmetric in the production SDF; no fdir1 or anisotropic setting."),
        "potentially_relevant_configuration": (
            "front/rear caster collisions use mu=mu2=0.001 while drive wheels use 1; this is not "
            "left/right or forward/backward asymmetry and does not establish a cause."),
    }


def instrument_contact_sensors(diagnostic_sdf: Path, production_sdf: Path):
    """Add read-only contact sensors only to the already diagnostic SDF copy."""
    diagnostic_sdf, production_sdf = Path(diagnostic_sdf), Path(production_sdf)
    production_bytes = production_sdf.read_bytes()
    tree = ET.parse(diagnostic_sdf)
    root = tree.getroot()
    world = root.find("world")
    model = root.find(".//model[@name='simple_agent']")
    if world is None or model is None:
        raise ValueError("Diagnostic SDF missing world or simple_agent")
    world_name = world.get("name")
    collision_map = _collision_map_from_sdf(production_sdf)
    topics, sensor_defs = {}, {}
    for side, link_name in WHEEL_LINKS.items():
        link = model.find(f"link[@name='{link_name}']")
        collision_name = WHEEL_COLLISIONS[side]
        if link is None or link.find(f"collision[@name='{collision_name}']") is None:
            raise ValueError(f"Diagnostic SDF missing {side} wheel collision")
        sensor_name = f"{side}_wheel_ground_contact_diagnostic"
        topic = f"/aero/{world_name}/{side}_wheel_ground_contacts_diagnostic"
        sensor = ET.SubElement(link, "sensor", name=sensor_name, type="contact")
        ET.SubElement(sensor, "always_on").text = "true"
        ET.SubElement(sensor, "update_rate").text = "1000"
        contact = ET.SubElement(sensor, "contact")
        ET.SubElement(contact, "collision").text = collision_name
        ET.SubElement(contact, "topic").text = topic
        topics[side] = topic
        sensor_defs[side] = {"sensor_name": sensor_name, "link_name": link_name,
            "collision_name": collision_name, "topic": topic,
            "message_type": "gz.msgs.Contacts", "update_rate_hz": 1000}
    ET.indent(tree)
    tree.write(diagnostic_sdf, encoding="utf-8", xml_declaration=True)
    if production_sdf.read_bytes() != production_bytes:
        raise RuntimeError("Contact instrumentation changed production SDF")
    return {"production_sdf_sha256_before": hashlib.sha256(production_bytes).hexdigest(),
        "production_sdf_sha256_after": _sha256(production_sdf),
        "production_sdf_unchanged": True,
        "diagnostic_sdf": str(diagnostic_sdf),
        "diagnostic_sdf_sha256": _sha256(diagnostic_sdf),
        "contact_topics": topics, "wheel_contact_sensors": sensor_defs,
        "collision_entity_map": collision_map,
        "body_contact_topic": f"/aero/{world_name}/contacts",
        "instrumentation_semantics": (
            "Adds only SDF contact-sensor declarations to left/right wheel links in diagnostic copy. "
            "The installed Gazebo Contact sensor publishes gz.msgs.Contacts from collision state; "
            "no actuation, collision, friction, mass, inertia, joint, DiffDrive or physics settings are changed."),
        "native_contacts_fields": ["collision1", "collision2", "position", "normal", "depth", "wrench"],
        "native_force_fields": ["JointWrench.body_1_wrench.force/torque",
            "JointWrench.body_2_wrench.force/torque"],
        "native_normal_tangential_force_fields": False,
        "normal_tangential_force_note": (
            "The protobuf has raw contact normals and body wrench vectors, but no separately named "
            "normal/tangential force components; no decomposition is fabricated."),
        "observation_only_api_basis": {
            "sensor_type": "SDF contact sensor configured for a collision and output topic",
            "output_message": "gz.msgs.Contacts",
            "message_schema": "contact pair, positions, normals, depths and joint wrenches",
            "actuation_interface_added": False,
            "physical_parameter_edits": [],
        }}


class ContactCapture:
    def __init__(self, collision_map):
        self.collision_map = collision_map
        self.samples = []
        self.callbacks = []
        self._json = None

    def subscribe(self, adapter, topics):
        from gz.msgs10 import contacts_pb2
        transport = adapter.env.transport
        self._json = transport.json
        for label, topic in topics.items():
            def callback(message, label=label, topic=topic):
                data = self._json.MessageToDict(message, preserving_proto_field_name=True)
                row = parse_contacts_message(data, topic, len(self.samples) + 1,
                    time.monotonic(), self.collision_map)
                row["sensor_label"] = label
                self.samples.append(row)
            self.callbacks.append(callback)
            if not transport.node.subscribe(contacts_pb2.Contacts, topic, callback):
                raise RuntimeError("Gazebo Contact sensor subscription failed: " + topic)


def _extract_action_windows(base):
    action23 = base.get("action23", {})
    action23_exec = action23.get("production_telemetry", {}).get("execution_evidence", {})
    raw = action23_exec.get("execution_evidence", {})
    acquire23 = next((row for row in raw.get("phase_evidence", [])
        if row.get("phase") == "ACQUIRE_LINEAR"), {})
    macro24 = base.get("action24_production_macro_evidence", {})
    brake = macro24.get("braking_phase", {})
    acquire = macro24.get("acquisition_phase_evidence", {})
    return {
        "action23_down_acquisition": (acquire23.get("start_sim_time"), acquire23.get("end_sim_time")),
        "action24_brake": (brake.get("start_sim_time"), brake.get("end_sim_time")),
        "action24_up_acquisition": (acquire.get("start_sim_time"), acquire.get("end_sim_time")),
    }


def _in_window(row, interval):
    stamp = row.get("simulation_timestamp")
    start, end = interval
    return stamp is not None and start is not None and end is not None and \
        float(start) - 1e-9 <= stamp <= float(end) + 1e-9


def _window_summary(rows, interval):
    selected = [r for r in rows if _in_window(r, interval)]
    contacts = [c for row in selected for c in row["contacts"]]
    classes = {name: [] for name in ("LEFT_WHEEL_GROUND", "RIGHT_WHEEL_GROUND",
        "CHASSIS_GROUND", "WHEEL_CHASSIS", "OBSTACLE", "OTHER")}
    for item in contacts:
        classes[item["pair_classification"]].append(item)
    by_sensor = {}
    for label in ("left", "right", "chassis"):
        sensor_rows = [r for r in selected if r.get("sensor_label") == label]
        sensor_contacts = [c for row in sensor_rows for c in row["contacts"]]
        by_sensor[label] = {"message_count": len(sensor_rows),
            "contact_count": len(sensor_contacts),
            "pair_counts": {name: sum(c["pair_classification"] == name
                for c in sensor_contacts) for name in classes},
            "availability": "AVAILABLE" if sensor_rows else "NO_SAMPLES_IN_WINDOW"}
    return {"simulation_interval": list(interval), "message_count": len(selected),
        "contact_event_count": len(contacts), "pair_counts": {k: len(v) for k, v in classes.items()},
        "pair_evidence": classes,
        "by_sensor": by_sensor,
        "topic_timestamp_count": sum(r.get("simulation_timestamp") is not None for r in selected),
        "contact_present": bool(contacts) if selected else None,
        "availability": "AVAILABLE" if selected else "NO_SAMPLES_IN_WINDOW"}


def classify_contact_observations(action23, action24):
    """Avoid inferring traction from contact presence or absent wrench fields."""
    for window in (action23, action24):
        if any(window["by_sensor"][side]["availability"] != "AVAILABLE"
               for side in ("left", "right")):
            return "CONTACT_TELEMETRY_UNAVAILABLE"
    baseline = action23["by_sensor"]
    target = action24["by_sensor"]
    missing = [side for side in ("left", "right")
        if baseline[side]["pair_counts"][f"{side.upper()}_WHEEL_GROUND"] > 0 and
           target[side]["pair_counts"][f"{side.upper()}_WHEEL_GROUND"] == 0]
    if missing:
        return "WHEEL_GROUND_CONTACT_MISSING"
    if any(target[side]["pair_counts"][f"{side.upper()}_WHEEL_GROUND"] > 0
           for side in ("left", "right")):
        return "CONTACT_TELEMETRY_AVAILABLE_CAUSE_UNRESOLVED"
    return "INSUFFICIENT_CONTACT_EVIDENCE"


def resolve_model_and_joint_configuration(base_report, generated_configuration=None):
    """Resolve the successful joint-diagnostic schema or fail explicitly.

    The success schema carries this field at the top level. Early failure
    reports intentionally contain only base_replay_evidence and must not be
    treated as if diagnostic instrumentation/configuration had succeeded.
    """
    if not isinstance(base_report, dict):
        raise TypeError("Joint-state diagnostic report must be a JSON object")
    if base_report.get("verdict") == "ACTION24_JOINT_TELEMETRY_INSTRUMENTATION_FAILED":
        replay = base_report.get("base_replay_evidence")
        error = replay.get("error") if isinstance(replay, dict) else None
        detail = (f"{error.get('type')}: {error.get('message')}" if isinstance(error, dict)
                  else "upstream production replay report has no structured error")
        raise RuntimeError("Joint-state instrumentation failed before model_and_joint_configuration "
                           f"was produced ({detail})")
    configuration = base_report.get("model_and_joint_configuration")
    if configuration is None and isinstance(generated_configuration, dict):
        # Canonical fallback: output of instrument_diagnostic_sdf for the exact
        # production SDF used by this replay. It contains no guessed defaults.
        configuration = generated_configuration
    if isinstance(configuration, dict):
        required = ("production_sdf", "diagnostic_sdf", "joint_state_topic",
                    "wheel_geometry", "diffdrive_configuration", "production_sdf_unchanged")
        missing = [key for key in required if key not in configuration]
        if missing:
            raise ValueError("Joint-state diagnostic configuration is incomplete; missing " +
                             ", ".join(missing))
        return configuration
    raise ValueError("Unsupported joint-state diagnostic schema: expected successful top-level "
                     "model_and_joint_configuration; got verdict=" +
                     repr(base_report.get("verdict")))


def _run_contact_diagnostic(artifact_dir, output, **kwargs):
    original_instrument = joint_diag.instrument_diagnostic_sdf
    original_capture_class = joint_diag.JointStateCapture
    contact_capture = {"instance": None, "info": None, "model_configuration": None}

    def instrument_and_add_contact(production_sdf):
        diagnostic_sdf, info = original_instrument(production_sdf)
        contact_info = instrument_contact_sensors(diagnostic_sdf, production_sdf)
        info["contact_instrumentation"] = contact_info
        contact_capture["info"] = contact_info
        contact_capture["model_configuration"] = info
        return diagnostic_sdf, info

    class CombinedCapture(original_capture_class):
        def subscribe(self, adapter, topic):
            super().subscribe(adapter, topic)
            info = contact_capture["info"]
            topics = dict(info["contact_topics"])
            topics["chassis"] = info["body_contact_topic"]
            self.contact_capture = ContactCapture(info["collision_entity_map"])
            self.contact_capture.subscribe(adapter, topics)
            contact_capture["instance"] = self.contact_capture

    joint_diag.instrument_diagnostic_sdf = instrument_and_add_contact
    joint_diag.JointStateCapture = CombinedCapture
    try:
        base = joint_diag._run_with_instrumented_factory(artifact_dir, output, **kwargs)
    finally:
        joint_diag.instrument_diagnostic_sdf = original_instrument
        joint_diag.JointStateCapture = original_capture_class
    raw_path = Path(base["evidence_file"])
    base = json.loads(raw_path.read_text(encoding="utf-8"))
    info = resolve_model_and_joint_configuration(
        base, generated_configuration=contact_capture["model_configuration"])
    contact_info = info["contact_instrumentation"]
    capture = contact_capture["instance"]
    if capture is None:
        raise RuntimeError("Contact capture was not initialized")
    intervals = _extract_action_windows(base)
    windows = {name: _window_summary(capture.samples, interval)
        for name, interval in intervals.items()}
    contact_classification = classify_contact_observations(
        windows["action23_down_acquisition"], windows["action24_up_acquisition"])
    report = {
        "schema_version": "0.7.1",
        "verifier": "diagnostic-only wheel-ground contact, native joints and production action24",
        "status": base.get("status"),
        "verdict": "ACTION24_WHEEL_GROUND_CONTACT_CAPTURED",
        "provenance": base.get("source"), "target": base.get("target"),
        "actions_1_to_23_used_production_adapter": base.get("actions_1_to_23_used_production_adapter"),
        "target_used_production_adapter": base.get("target_used_production_adapter"),
        "target_production_step_call_started": base.get("target_production_step_call_started"),
        "target_production_step_returned": base.get("target_production_step_returned"),
        "target_exception": base.get("target_exception"),
        "static_sdf_audit": _static_sdf_audit(info["production_sdf"]),
        "telemetry_source": {"system": "Gazebo Harmonic Contact sensor / Contact system",
            "message_type": "gz.msgs.Contacts", "topics": contact_info["contact_topics"],
            "body_topic": contact_info["body_contact_topic"],
            "native_fields": contact_info["native_contacts_fields"],
            "native_force_fields": contact_info["native_force_fields"],
            "normal_tangential_components_native": False},
        "instrumentation": contact_info,
        "production_sdf_unchanged": info["production_sdf_unchanged"],
        "production_sdf_sha256_before": info["production_sdf_sha256_before"],
        "production_sdf_sha256_after": info["production_sdf_sha256_after"],
        "collision_entity_map": contact_info["collision_entity_map"],
        "joint_telemetry": {"action23": base.get("action23_sanity_check"),
            "action24_brake": base.get("action24_brake"),
            "action24_acquisition": base.get("action24_acquire_up")},
        "world_pose_body_evidence": base.get("action24_raw_topic_timeline"),
        "action23_working_contact_window": windows["action23_down_acquisition"],
        "action24_brake_contact_window": windows["action24_brake"],
        "action24_up_acquisition_contact_window": windows["action24_up_acquisition"],
        "contact_samples": capture.samples,
        "comparison": {"action23": windows["action23_down_acquisition"],
            "action24_brake": windows["action24_brake"],
            "action24_acquisition": windows["action24_up_acquisition"],
            "earliest_difference": "DERIVED_FROM_ACTION23_AND_ACTION24_CONTACT_TIMELINES",
            "classification": contact_classification,
            "interpretation_limit": (
                "Contact presence and raw wrench values are reported; contact presence alone does not "
                "prove traction or exclude wheel slip/constraint." )},
        "sensor_collision_process_reset": {
            "sensor_and_contact": base.get("sensor_and_contact"),
            "process_start": base.get("process_start"), "process_end": base.get("process_end"),
            "reset_provenance": base.get("reset_provenance"), "shutdown": base.get("shutdown")},
        "strict_json_audit": {"status": "PENDING"},
    }
    nonfinite = find_nonfinite_paths(report)
    report["strict_json_audit"] = {"status": "PASS" if not nonfinite else "FAIL",
        "nonfinite_field_paths": nonfinite}
    report["nonfinite_field_paths"] = nonfinite
    report["evidence_file"] = str(Path(output) / "action24_wheel_ground_contact.json")
    if nonfinite:
        report["verdict"] = "ACTION24_WHEEL_GROUND_CONTACT_INVALID_EVIDENCE"
    write_json(Path(output) / "action24_wheel_ground_contact.json", _strict_json_value(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prior-failure", type=Path, default=None)
    parser.add_argument("--successful-down-up", type=Path, default=None)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    kwargs = {key: value for key, value in {"prior_failure": args.prior_failure,
        "successful_down_up": args.successful_down_up, "gui": args.gui}.items()
        if value is not None}
    report = _run_contact_diagnostic(args.artifact_dir, args.output, **kwargs)
    print("Gazebo action-24 wheel-ground contact diagnostic: " + report["verdict"])
    print("contact messages: " + str(len(report["contact_samples"])))
    print("evidence: " + report["evidence_file"])
    return 0 if report["strict_json_audit"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
