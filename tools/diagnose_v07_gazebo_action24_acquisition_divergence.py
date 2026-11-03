#!/usr/bin/env python3
"""Host-only telemetry capture for the production action-23/24 handoff."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from tools.diagnose_v07_gazebo_macro_composition_action24 import (
    validate_sources,
)
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value,
    find_nonfinite_paths,
)

DEFAULT_PRIOR_FAILURE = Path(
    "validation/v071-host/gazebo-left-to-up-production-integration-phase3fb-retry2/"
    "left_to_up_production_integration.json")
DEFAULT_SUCCESSFUL_DOWN_UP = Path(
    "validation/v071-host/gazebo-control-executor-linear-reversal-phase3ca-reset-provenance/"
    "linear_reversal_control_executor.json")


def _stats_sample(adapter):
    env = adapter.env
    try:
        sample = env.transport.sample(env.stepper.topic,
            float(env.stepper.time) - .002, timeout=.15)
        return {"available": True, "simulation_time": _stamp(sample),
            "iterations": sample.get("iterations_normalized", sample.get("iterations")),
            "paused": sample.get("paused"),
            "iterations_raw_present": sample.get("iterations_raw_present", "iterations" in sample),
            "receive_sequence": env.transport.cursor(env.stepper.topic)}
    except Exception as error:
        return {"available": False, "error": type(error).__name__ + ": " + str(error)}


def _stamp(sample):
    from aero_ai_studio.gazebo.transport import stamp
    return stamp(sample)


def _topic_cursor(adapter, topic):
    try:
        return int(adapter.env.transport.cursor(topic))
    except Exception:
        return None


def _all_messages_after(adapter, topic, sequence):
    if sequence is None:
        return {"status": "UNAVAILABLE", "reason": "topic cursor unavailable", "samples": []}
    try:
        rows = adapter.env.transport.messages_after(topic, sequence, timeout=0)
    except Exception as error:
        return {"status": "UNAVAILABLE", "reason": type(error).__name__ + ": " + str(error),
                "samples": []}
    return {"status": "AVAILABLE", "samples": rows}


def _pose_frame_samples(adapter, sequence):
    topic = adapter.env.controller.pose_topic
    messages = _all_messages_after(adapter, topic, sequence)
    if messages["status"] != "AVAILABLE":
        return messages
    body_name = adapter.env.agent_entity
    result = []
    wheel_names = set()
    for receive_sequence, frame in messages["samples"]:
        timestamp = _stamp(frame)
        selected = []
        for pose in frame.get("pose", []):
            name = pose.get("name", "")
            if name == body_name or ("wheel" in name.lower() and
                    (body_name in name or "simple_agent" in name)):
                decoded = adapter.env.controller.decode_pose(pose)
                selected.append({"name": name, **decoded})
                if "wheel" in name.lower():
                    wheel_names.add(name)
        if selected:
            result.append({"receive_sequence": receive_sequence,
                "simulation_timestamp": timestamp, "entities": selected})
    return {"status": "AVAILABLE", "sample_count": len(result),
        "agent_entity": body_name, "wheel_link_names_observed": sorted(wheel_names),
        "samples": result}


def _sensor_samples(adapter, sequence):
    topic = adapter.env.sensors.topic
    messages = _all_messages_after(adapter, topic, sequence)
    if messages["status"] != "AVAILABLE":
        return messages
    rows = []
    for receive_sequence, sample in messages["samples"]:
        ranges = sample.get("ranges", [])
        rows.append({"receive_sequence": receive_sequence,
            "simulation_timestamp": _stamp(sample), "range_count": len(ranges),
            "finite_range_count": sum(1 for value in ranges
                if _is_finite_number(value)),
            "range_max": sample.get("range_max")})
    return {"status": "AVAILABLE", "sample_count": len(rows), "samples": rows}


def _is_finite_number(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _contact_samples(adapter, sequence):
    contacts = getattr(adapter.env, "contacts", None)
    if contacts is None:
        return {"status": "UNAVAILABLE", "reason": "Contact provider not initialized", "samples": []}
    messages = _all_messages_after(adapter, contacts.topic, sequence)
    if messages["status"] != "AVAILABLE":
        return messages
    samples = []
    for receive_sequence, data in messages["samples"]:
        stamp_data = data.get("header", {}).get("stamp", {})
        timestamp = float(stamp_data.get("sec", 0)) + float(stamp_data.get("nsec", 0)) * 1e-9
        samples.append({"receive_sequence": receive_sequence,
            "simulation_timestamp": timestamp,
            "contact_pair_count": len(data.get("contact", [])),
            "contact_names": [row.get("collision1", "") + " | " + row.get("collision2", "")
                for row in data.get("contact", [])]})
    return {"status": "AVAILABLE", "sample_count": len(samples), "samples": samples}


def _topic_history(adapter, start_sequences, start_time, end_time):
    env = adapter.env
    pose = _pose_frame_samples(adapter, start_sequences.get(env.controller.pose_topic))
    stats = _all_messages_after(adapter, env.stepper.topic,
        start_sequences.get(env.stepper.topic))
    if stats.get("status") == "AVAILABLE":
        stats_rows = []
        for receive_sequence, sample in stats.pop("samples"):
            timestamp = _stamp(sample)
            if start_time - .002 <= timestamp <= end_time + .002:
                stats_rows.append({"receive_sequence": receive_sequence,
                    "simulation_timestamp": timestamp,
                    "iterations": sample.get("iterations_normalized", sample.get("iterations")),
                    "paused": sample.get("paused")})
        stats.update(sample_count=len(stats_rows), samples=stats_rows)
    sensor = _sensor_samples(adapter, start_sequences.get(env.sensors.topic))
    contact_topic = getattr(env, "contact_topic", None)
    contact = (_contact_samples(adapter, start_sequences.get(contact_topic))
        if contact_topic else {"status": "UNAVAILABLE", "reason": "no contact topic", "samples": []})
    odometry = []
    if hasattr(env, "read_odometry_interval"):
        try:
            odometry = env.read_odometry_interval(start_time, end_time)
        except Exception:
            odometry = []
    return {"world_pose_frames": pose, "world_statistics": stats,
        "sensor_frames": sensor, "contact_frames": contact,
        "diffdrive_odometry_samples": odometry,
        "window": {"simulation_start": start_time, "simulation_end": end_time}}


def _snapshot(adapter):
    env = adapter.env
    pose = dict(getattr(env, "pose", {}) or {})
    command = dict(getattr(env.controller, "last_command", {}) or {})
    published = dict(getattr(env.controller, "last_published_command", {}) or {})
    stats = _stats_sample(adapter)
    odometry = None
    try:
        odometry = env.read_odometry(min_time=float(env.stepper.time) - .02, timeout=.05)
    except Exception:
        pass
    provider = getattr(env, "contacts", None)
    sensor_frame = getattr(getattr(env, "sensors", None), "frame", None)
    pose_names = sorted(getattr(env.controller, "poses", {}).keys())
    return {"simulation_time": float(env.stepper.time), "simulation_stats": stats,
        "simulation_step_verification": dict(getattr(env.stepper, "last_verification", {}) or {}),
        "environment_step_count": getattr(env, "steps", None), "model_pose": pose,
        "world_pose_entity_names": pose_names,
        "world_pose_source": "Gazebo Pose_V model pose; finite-difference body velocity when history exists",
        "last_action_transition": _transition_summary(env.telemetry.get("action_transition") or {}),
        "last_physics_validation": dict(env.telemetry.get("pose_validation") or {}),
        "last_command_controller_state": command,
        "last_published_command_controller_state": published,
        "command_publish_sequence": getattr(env.controller, "publish_sequence", None),
        "diffdrive_odometry_latest": odometry,
        "sensor_frame": sensor_frame.to_dict() if sensor_frame else None,
        "contact_schema": getattr(provider, "schema", None),
        "contact_state": dict(getattr(provider, "state", {}) or {}),
        "collision_event": (None if getattr(env, "collision_event", None) is None
            else env.collision_event.to_dict()),
        "process": adapter.manager.status(),
        "partition": adapter.manager.partition,
        "pid": getattr(getattr(adapter, "process", None), "pid", None)}


def _transition_summary(transition):
    keys = ("action", "commanded_twist", "previous_action_twist", "zero_twist_after_step",
        "command_publish_sequence_before", "action_publish_sequence", "zero_publish_sequence",
        "action_command_sim_time", "zero_command_sim_time", "simulation_duration",
        "pose_topic_sequence_before", "pose_topic_sequence_after",
        "world_pose_history_summary", "world_pose_history", "odometry_before",
        "odometry_after", "odometry_history")
    return {key: transition[key] for key in keys if key in transition}


def _signal_inventory(adapter):
    env = adapter.env
    discovery = getattr(env, "discovery", {}) or {}
    topics = discovery.get("topics", [])
    sdf = ""
    world_path = getattr(env, "world", None)
    if world_path is not None:
        try:
            sdf = Path(world_path).read_text(encoding="utf-8")
        except (OSError, TypeError):
            pass
    relevant = [topic for topic in topics if any(token in topic.lower()
        for token in ("odometry", "pose/info", "stats", "contact", "joint", "cmd_vel"))]
    return {
        "world_model_pose": "AVAILABLE: Pose_V /world/<world>/pose/info; model pose selected by entity name",
        "model_linear_angular_velocity_direct": "UNAVAILABLE: finite-differenced from timestamped Pose_V model pose",
        "individual_link_pose": {"status": "CONDITIONAL",
            "observed_entity_names": sorted(name for name in env.controller.poses
                if "simple_agent" in name or "wheel" in name.lower())},
        "wheel_joint_position_velocity": "UNAVAILABLE: no JointState/joint topic subscription or parser in adapter",
        "diffdrive_odometry": "AVAILABLE: Gazebo DiffDrive Odometry topic; source semantics are wheel-joint dead-reckoning",
        "commanded_twist": "AVAILABLE: Python requested command and controller publish sequence; no per-message consumer acknowledgement",
        "simulation_iterations_time_paused": "AVAILABLE: /world/<world>/stats WorldStatistics",
        "contact": {"status": "AVAILABLE_EVENT_STREAM" if getattr(env, "contact_topic", None) else "UNAVAILABLE",
            "scope": "SDF body_contacts sensor on body_collision; does not report wheel-ground traction/contact"},
        "obstacle_contact": "Observable only when the body Contact sensor emits a collision event; silence is not proof of contact health",
        "wheel_ground_contact": "UNAVAILABLE from the configured body-only Contact sensor",
        "entity_existence": "AVAILABLE through Pose_V entity names",
        "static_configuration": {"status": "CONFIGURED_NONSTATIC" if "<static>false</static>" in sdf else "UNKNOWN",
            "runtime_static_or_frozen_state": "UNAVAILABLE"},
        "joint_controller_state": "UNAVAILABLE",
        "discovered_relevant_topics": relevant}


def _successful_reference(path):
    if not path.is_file():
        return {"status": "UNAVAILABLE", "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    execution = data.get("execution_result", {})
    raw = execution.get("execution_evidence", {})
    brake, acquire = raw.get("braking_phase", {}), raw.get("acquisition_phase", {})
    validator = data.get("production_validator", {})
    acquire_evidence = raw.get("acquisition_phase", {})
    process = data.get("final_process", data.get("process", {}))
    return {"status": "AVAILABLE", "path": str(path), "verdict": data.get("verdict"),
        "target_request": data.get("target_request"),
        "brake": {key: brake.get(key) for key in
            ("start_sim_time", "end_sim_time", "elapsed_simulation_time",
             "start_body_forward_velocity", "end_body_forward_velocity",
             "end_body_angular_velocity", "completion_result")},
        "acquire": {key: acquire.get(key) for key in
            ("start_sim_time", "end_sim_time", "elapsed_simulation_time",
             "end_body_forward_velocity", "end_body_angular_velocity",
             "requested_direction_established", "completion_result", "collision")},
        "acquire_command": acquire.get("command"),
        "acquire_pose_before": acquire.get("pose_before"),
        "acquire_pose_after": acquire.get("pose_after"),
        "world_pose_history": acquire.get("world_pose_history"),
        "world_pose_sample_count_raw": len(acquire.get("world_pose_history_raw") or []),
        "production_validator": {key: validator.get(key) for key in
            ("valid", "distance", "expected_distance", "body_forward_displacement",
             "yaw_delta", "world_direction_ok")},
        "world_pose_history_summary": acquire_evidence.get("world_pose_history_summary"),
        "wheel_odometry_corroboration": acquire_evidence.get("wheel_odometry_corroboration"),
        "sensor_contract_pass": acquire_evidence.get("sensor_contract_pass"),
        "contact_contract_pass": acquire_evidence.get("contact_contract_pass"),
        "collision": acquire_evidence.get("collision"),
        "process": process, "shutdown": data.get("shutdown")}


def run_diagnostic(artifact_dir, output, *, prior_failure=DEFAULT_PRIOR_FAILURE,
                   successful_down_up=DEFAULT_SUCCESSFUL_DOWN_UP, gui=False,
                   env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "0.7.1",
        "verifier": "diagnostic-only action24 acquisition divergence; production path",
        "status": "ARTIFACT_EXTRACTION", "verdict": "ACTION24_ACQUISITION_DIVERGENCE_DIAGNOSTIC_FAILED",
        "production_behavior_modified": False, "dqn_used": False, "training_used": False,
        "target": {"episode": 1, "episode_action_index": 24,
            "global_action_index": 24, "previous_action": "down", "requested_action": "up"},
        "actions_1_to_23_used_production_adapter": True,
        "target_used_production_adapter": True,
        "target_production_step_call_started": False,
        "target_production_step_returned": False,
        "shutdown": "NOT_ATTEMPTED", "error": None}
    adapter = None
    stage = "ARTIFACT_EXTRACTION"
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        actions = replay["completed_episode_actions"][0]
        if len(actions) < 24 or actions[22:24] != ["down", "up"]:
            raise ValueError("Saved Stage1 source does not establish action23 DOWN, action24 UP")
        prior = json.loads(Path(prior_failure).read_text(encoding="utf-8")) if Path(prior_failure).is_file() else {}
        report["source"] = {"run_id": replay.get("run_id"),
            "artifact_dir": replay.get("artifact_dir"), "episode_action_count": len(actions),
            "source_actions_19_to_29": [
                {"global_action_index": idx, "action": actions[idx - 1]}
                for idx in range(19, min(29, len(actions)) + 1)],
            "prior_failure_path": str(prior_failure),
            "prior_failure_reconstruction": (validate_sources(replay, prior)
                if prior else {"status": "UNAVAILABLE", "reason": "prior failure artifact absent"})}
        report["successful_down_to_up_reference"] = _successful_reference(Path(successful_down_up))
        stage = "ENVIRONMENT_STARTUP"
        report.update(status=stage, failure_stage=stage, last_completed_stage="ARTIFACT_EXTRACTION")
        adapter = (env_factory or GazeboPhysicsTrainingEnvironment)(
            ScenarioSpec.from_dict(replay["scenario"]), replay["max_steps"],
            root=output / "worlds", gui=gui, max_sensor_age_ms=20)
        stage = "INITIAL_RESET"
        report.update(status=stage, failure_stage=stage, last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Diagnostic requires native Gazebo PHYSICS mode")
        report["reset_provenance"] = dict(adapter.last_reset_evidence)
        report["process_start"] = adapter.manager.status()
        report["available_signal_inventory"] = _signal_inventory(adapter)
        report["last_completed_stage"] = stage

        env = adapter.env
        action23_before = None
        source_sequences_23 = None
        for index, action in enumerate(actions[:23], 1):
            if index == 23:
                action23_before = _snapshot(adapter)
                source_sequences_23 = {topic: _topic_cursor(adapter, topic)
                    for topic in [env.controller.pose_topic, env.stepper.topic, env.sensors.topic,
                        getattr(env, "contact_topic", ""), getattr(env, "odometry_topic", "")]
                    if topic}
            try:
                result = adapter.step(action)
            except Exception as error:
                raise RuntimeError(f"Production prefix action {index} {action} failed: "
                    f"{type(error).__name__}: {error}") from error
            if result.terminated or result.truncated:
                raise RuntimeError(f"Production prefix terminated at action {index}")
        action23_after = _snapshot(adapter)
        action23_telemetry = dict(env.telemetry.get("gazebo_dqn_training") or {})
        action23_topic_window = _topic_history(adapter, source_sequences_23,
            action23_before["simulation_time"], action23_after["simulation_time"])
        action23 = {"global_action_index": 23, "requested_action": "down",
            "production_telemetry": action23_telemetry,
            "before": action23_before, "after": action23_after,
            "physical_topic_window": action23_topic_window}
        report["action23"] = action23
        report["prefix_replayed_count"] = 23
        report["action23_to_action24_handoff"] = {
            "action23_final_command": action23_after["last_command_controller_state"],
            "action24_previous_command": dict(env.controller.last_command or {}),
            "action23_final_pose": action23_after["model_pose"],
            "action24_initial_pose": dict(env.pose or {}),
            "action23_final_odometry": action23_after["diffdrive_odometry_latest"],
            "action24_initial_odometry": _snapshot(adapter)["diffdrive_odometry_latest"],
            "same_simulation_time": action23_after["simulation_time"] == float(env.stepper.time)}

        report["action24_pre_state"] = _snapshot(adapter)
        pre_action24 = float(env.stepper.time)
        stats_before = _stats_sample(adapter)
        action24_sequences = {topic: _topic_cursor(adapter, topic)
            for topic in [env.controller.pose_topic, env.stepper.topic, env.sensors.topic,
                getattr(env, "contact_topic", ""), getattr(env, "odometry_topic", "")]
            if topic}
        if dict(env.controller.last_command or {}) != gazebo_physics_twist("down"):
            raise RuntimeError("Action23 did not leave exact DOWN command for target action24")
        report.update(status="EXECUTING_PRODUCTION_ACTION_24",
            failure_stage="EXECUTING_PRODUCTION_ACTION_24",
            last_completed_stage="REPLAYING_ACTIONS_1_TO_23",
            target_production_step_call_started=True)
        try:
            # The target stays on GazeboPhysicsTrainingEnvironment.step('up').
            result = adapter.step("up")
        except Exception as error:
            report["target_production_step_returned"] = False
            report["target_exception"] = {"type": type(error).__name__, "message": str(error),
                "failure_category": "physical_control_failure" if isinstance(
                    error, PhysicalControlFailure) else "infrastructure_or_unknown",
                "physical_failure": error.to_dict() if isinstance(error, PhysicalControlFailure) else None}
            report["target_runtime_after_failure"] = _snapshot(adapter)
        else:
            report["target_production_step_returned"] = True
            report["target_result"] = {"reason": result.reason, "reward": result.reward,
                "terminated": result.terminated, "truncated": result.truncated,
                "elapsed_execution_time": result.elapsed_execution_time,
                "elapsed_discount_units": result.elapsed_discount_units,
                "execution_evidence": result.execution_evidence}
            report["target_runtime_after_step"] = _snapshot(adapter)
        post_state = report.get("target_runtime_after_failure") or report.get("target_runtime_after_step") or _snapshot(adapter)
        end_time = float(env.stepper.time)
        report["action24_telemetry_window"] = _topic_history(
            adapter, action24_sequences, pre_action24, end_time)
        report["action24_production_macro_evidence"] = _action24_macro_evidence(report)
        report["simulation_advancement"] = {"before": stats_before,
            "after": _stats_sample(adapter),
            "step_verification": dict(getattr(env.stepper, "last_verification", {}) or {}),
            "start_simulation_time": pre_action24, "end_simulation_time": end_time,
            "observed_time_delta": end_time - pre_action24,
            "iterations_delta": (None if stats_before.get("iterations") is None or
                post_state.get("simulation_stats", {}).get("iterations") is None else
                post_state["simulation_stats"]["iterations"] - stats_before["iterations"])}
        report["command_delivery_levels"] = _command_delivery_report(report)
        report["joint_telemetry"] = _joint_availability(adapter)
        report["comparison_earliest_divergence"] = _compare_success(report)
        report["status"] = "FAILED" if not report["target_production_step_returned"] else "TARGET_STEP_RETURNED"
        report["failure_stage"] = ("EXECUTING_PRODUCTION_ACTION_24" if not
            report["target_production_step_returned"] else None)
        report["last_completed_stage"] = ("REPLAYING_ACTIONS_1_TO_23" if not
            report["target_production_step_returned"] else "TARGET_STEP_RETURNED")
        report["diagnostic_classification"] = _classify_observed_divergence(report)
        if not report["target_production_step_returned"]:
            report["classification_scope"] = (
                "Observed signal divergence only; this tool does not claim actual wheel rotation "
                "without joint telemetry and cannot infer the physical mechanism.")
    except Exception as error:
        report.update(status="FAILED", failure_stage=stage,
            error={"type": type(error).__name__, "message": str(error)})
    finally:
        if adapter is not None:
            try:
                report["final_process_status"] = adapter.manager.status()
                adapter.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = {"type": type(error).__name__, "message": str(error)}
        report["evidence_file"] = str(output / "action24_acquisition_divergence.json")
        paths = find_nonfinite_paths(report)
        report["nonfinite_field_paths"] = paths
        report["json_evidence_audit"] = {"status": "PASS" if not paths else "FAIL",
            "nonfinite_field_paths": paths}
        write_json(output / "action24_acquisition_divergence.json", _strict_json_value(report))
    return report


def _command_delivery_report(report):
    failure = report.get("target_exception", {}).get("physical_failure") or {}
    outer = failure.get("evidence", {}).get("execution_evidence", {})
    raw = outer.get("execution_evidence", {})
    validator = raw.get("production_validator", {})
    transition = ((outer.get("validator_evidence") or {}).get("action_transition") or
        validator.get("action_transition") or {})
    return {
        "A_python_requested_twist": outer.get("requested_command"),
        "B_controller_command_state_after_failure": (report.get(
            "target_runtime_after_failure", {}).get("last_command_controller_state")),
        "B_last_published_command_after_cleanup": (report.get(
            "target_runtime_after_failure", {}).get("last_published_command_controller_state")),
        "publish_sequence_evidence": {key: transition.get(key) for key in
            ("command_publish_sequence_before", "action_publish_sequence",
             "zero_publish_sequence", "action_command_sim_time", "zero_command_sim_time",
             "commanded_twist", "zero_twist_after_step")},
        "C_diffdrive_consumption_ack": {"status": "NOT_DIRECTLY_OBSERVED",
            "post_command_odometry_output_observed": validator.get("odometry_after"),
            "reason": "Gazebo Transport publish succeeds with a connected subscriber and later DiffDrive Odometry is observed, but the subscriber provides no per-command acknowledgement."},
        "D_physical_wheel_joint_motion": {"status": "UNAVAILABLE",
            "reason": "The adapter subscribes to DiffDrive Odometry, not JointState/joint velocity."},
        "E_rigid_body_translation": {"status": "WORLD_POSE_V_PRIMARY",
            "validator": {key: validator.get(key) for key in
                ("world_pose_forward", "body_forward_displacement", "world_direction_ok",
                 "world_pose_history_summary")}},
        "diffdrive_odometry_response": {key: validator.get(key) for key in
            ("odometry_before", "odometry_after", "odometry_integrated_forward",
             "odometry_sample_count", "odometry_sample_timestamps",
             "odometry_sample_linear_x", "discrepancy_classification")}}


def _joint_availability(adapter):
    discovery = getattr(adapter.env, "discovery", {}) or {}
    topics = discovery.get("topics", [])
    candidates = [topic for topic in topics if any(token in topic.lower()
        for token in ("joint_state", "jointstate", "joint_states"))]
    pose_names = sorted(name for name in getattr(adapter.env.controller, "poses", {})
        if "wheel" in name.lower())
    return {"joint_state_topics_discovered": candidates,
        "direct_joint_position_velocity_telemetry_available": False,
        "wheel_link_pose_entities_currently_in_pose_frame": pose_names,
        "wheel_link_pose_samples_are_joint_velocity": False,
        "reason": "Current adapter exposes Pose_V and DiffDrive Odometry; no JointState subscription or joint-state parser exists."}


def _action24_macro_evidence(report):
    physical = (report.get("target_exception", {}).get("physical_failure") or {})
    outer = physical.get("evidence", {}).get("execution_evidence", {})
    raw = outer.get("execution_evidence", {})
    validator = raw.get("production_validator", {})
    validator_wrapper = outer.get("validator_evidence", {})
    return {"selected_executor_evidence": {
            "agent_intent": outer.get("agent_intent"), "status": outer.get("status"),
            "transition_type": outer.get("transition_type"),
            "activation_pair": outer.get("activation_pair"),
            "requested_command": outer.get("requested_command"),
            "executed_commands": outer.get("executed_commands"),
            "phase_plan": outer.get("phases"),
            "execution_phases": outer.get("execution_phases"),
            "elapsed_simulation_time": outer.get("elapsed_simulation_time"),
            "failure_category": outer.get("failure_category"), "reason": outer.get("reason")},
        "braking_phase": raw.get("braking_phase"),
        "braking_chunks": raw.get("braking_chunks"),
        "acquisition_phase": raw.get("acquisition_phase"),
        "acquisition_phase_evidence": next((row for row in raw.get("phase_evidence", [])
            if row.get("phase") == "ACQUIRE_LINEAR"), None),
        "production_validator": validator,
        "validator_action_transition": (validator_wrapper.get("action_transition") or
            validator.get("action_transition")),
        "contact_and_collision": {"collision": validator_wrapper.get("collision"),
            "collision_event": validator_wrapper.get("collision_event"),
            "contact_state": validator_wrapper.get("contact_state")},
        "sensor": report.get("target_runtime_after_failure", {}).get("sensor_frame"),
        "process": report.get("target_runtime_after_failure", {}).get("process")}


def _classify_observed_divergence(report):
    if report.get("target_production_step_returned"):
        return "TARGET_STEP_RETURNED_REQUIRES_REVIEW"
    physical = (report.get("target_exception", {}).get("physical_failure") or {})
    outer = physical.get("evidence", {}).get("execution_evidence", {})
    raw = outer.get("execution_evidence", {})
    validator = raw.get("production_validator", {})
    if outer.get("status") != "PHYSICAL_CONTROL_FAILURE":
        return "INSUFFICIENT_PHYSICAL_TELEMETRY"
    history = validator.get("world_pose_history_summary", {})
    window = report.get("action24_telemetry_window", {})
    stats = window.get("world_statistics", {})
    stepping = (report.get("simulation_advancement", {}).get("step_verification") or {})
    world_history_available = (history.get("world_pose_history_available") is True and
        history.get("world_pose_history_fresh") is True and
        history.get("world_pose_history_dense_enough") is True)
    odometry_response = validator.get("odometry_after")
    world_stationary = (validator.get("world_direction_ok") is False and
        abs(float(validator.get("body_forward_displacement") or 0.)) < 1e-4)
    stats_progressed = ((stats.get("status") == "AVAILABLE" and stats.get("sample_count", 0) > 1) or
        (stepping.get("valid") is True and
         (stepping.get("iteration_delta") or 0) > 0 and
         (stepping.get("observed_delta") or 0.) > 0.))
    if (validator.get("discrepancy_classification") ==
            "wheel_odometry_without_world_translation" and odometry_response and
            world_stationary and world_history_available and stats_progressed):
        return "DIFFDRIVE_STATE_DIVERGENCE"
    if not stats_progressed:
        return "PHYSICS_NOT_ADVANCING_OR_STATS_EVIDENCE_INSUFFICIENT"
    return "INSUFFICIENT_PHYSICAL_TELEMETRY"


def _compare_success(report):
    reference = report.get("successful_down_to_up_reference", {})
    target = report.get("target_exception", {}).get("physical_failure", {})
    outer = target.get("evidence", {}).get("execution_evidence", {})
    raw = outer.get("execution_evidence", {})
    validator = raw.get("production_validator", {})
    acquire = next((row for row in raw.get("phase_evidence", [])
        if row.get("phase") == "ACQUIRE_LINEAR"), {})
    brake = raw.get("braking_phase", {})
    reference_acquire = reference.get("acquire", {})
    success_history = reference.get("world_pose_history") or {}
    failure_history = validator.get("world_pose_history_summary") or {}
    success_velocity = success_history.get("body_forward_velocity_samples") or []
    failure_velocity = failure_history.get("body_forward_velocity_samples") or []
    success_first = success_velocity[0] if success_velocity else None
    failure_first = failure_velocity[0] if failure_velocity else None
    failed_brake = {key: brake.get(key) for key in
        ("start_sim_time", "end_sim_time", "elapsed_simulation_time",
         "start_body_forward_velocity", "end_body_forward_velocity",
         "end_body_angular_velocity", "completion_result")}
    successful_brake = reference.get("brake", {})
    failed_acquire_start = acquire.get("start_sim_time")
    successful_acquire_start = reference_acquire.get("start_sim_time")
    return {"reference": reference,
        "failed_run": {"pre_state": report.get("action24_pre_state"),
            "brake": failed_brake,
            "acquire": {key: acquire.get(key) for key in
                ("phase", "start_sim_time", "end_sim_time", "completion_result", "failure",
                 "command")},
            "validator": {key: validator.get(key) for key in
                ("valid", "distance", "expected_distance", "body_forward_displacement",
                 "world_pose_forward", "world_direction_ok", "odometry_before",
                 "odometry_after", "odometry_integrated_forward", "discrepancy_classification")}},
        "phase_comparison": {
            "initial_forward_velocity": {"successful": successful_brake.get("start_body_forward_velocity"),
                "failed": failed_brake.get("start_body_forward_velocity")},
            "braking_completion": {"successful": successful_brake.get("completion_result"),
                "failed": failed_brake.get("completion_result")},
            "braking_duration": {"successful": successful_brake.get("elapsed_simulation_time"),
                "failed": failed_brake.get("elapsed_simulation_time")},
            "acquisition_command": {"successful": reference.get("acquire_command"),
                "failed": outer.get("requested_command")},
            "acquisition_duration": {"successful": reference_acquire.get("elapsed_simulation_time"),
                "failed": acquire.get("end_sim_time", 0.) - (failed_acquire_start or 0.)},
            "first_world_body_forward_velocity_sample": {
                "successful": success_first, "failed": failure_first}},
        "earliest_observed_divergence": (
            "At the first available post-command World Pose_V finite-difference sample: "
            f"successful body response={success_first}, failed body response={failure_first}; "
            "the failed run's DiffDrive odometry reports forward response but World Pose_V does not. "
            "The differing initial speed is a state difference, not proof of the mechanism. "
            "Why the plugin odometry and rigid-body pose diverged remains unresolved.")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior-failure", type=Path, default=DEFAULT_PRIOR_FAILURE)
    parser.add_argument("--successful-down-up", type=Path, default=DEFAULT_SUCCESSFUL_DOWN_UP)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_diagnostic(args.artifact_dir, args.output,
        prior_failure=args.prior_failure, successful_down_up=args.successful_down_up,
        gui=args.gui)
    print("Gazebo action-24 acquisition divergence diagnostic: " + report["status"])
    print("evidence: " + report["evidence_file"])
    return 0 if report.get("target_production_step_returned") else 1


if __name__ == "__main__":
    raise SystemExit(main())
