#!/usr/bin/env python3
"""DQN-free actual-host verifier for exact UP→RIGHT LINEAR_TO_ROTATION."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.control_executor import (
    _contact_contract_pass, _history_contract, _history_is_sufficient,
    _sensor_contract_pass)
from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.gazebo.physics_feedback import (
    BODY_STOPPED_EPSILON, QUIESCENCE_CHUNK_ITERATIONS, QUIESCENCE_MAX_CHUNKS,
    body_stopped_contract)
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition, gazebo_physics_twist)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.simulation.control_execution import (
    ControlExecutionRequest, ControlExecutionStatus, plan_control_execution)
from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from tools.verify_v07_gazebo_up_to_down_production_integration import (
    _strict_json_value, find_nonfinite_paths)


PREFIX = ["up", "down", "up", "up", "up", "down", "up"]
TARGET = "right"


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _precondition(summary):
    samples = summary.get("world_forward_velocity_samples") or []
    valid_samples = []
    for row in samples:
        stamp = _finite(row.get("simulation_timestamp"))
        velocity = _finite(row.get("forward_velocity"))
        if stamp is None or velocity is None:
            return False
        valid_samples.append((stamp, velocity))
    return bool(_history_is_sufficient(summary) and len(valid_samples) >= 2 and
        all(b[0] > a[0] for a, b in zip(valid_samples, valid_samples[1:])) and
        (_finite(summary.get("world_end_forward_velocity")) or 0.) >
            BODY_STOPPED_EPSILON and
        any(value > BODY_STOPPED_EPSILON for _, value in valid_samples))


def validate_sources(replay, diagnostic, retry, phase3fb):
    actions = replay["completed_episode_actions"][0]
    trial = (diagnostic.get("trials") or [{}])[0]
    transition = ((trial.get("final_runtime") or {}).get("action_transition") or {})
    validation = ((trial.get("final_runtime") or {}).get("pose_validation") or {})
    rows = ((retry.get("episode_replays") or [{}])[0].get("actions") or [])
    failed = trial.get("failure_exception") or {}
    required = {
        "saved_prefix_exact": actions[:8] == PREFIX + [TARGET],
        "diagnostic_failed_at_action_8": trial.get("failure_action") == 8 and
            failed.get("type") == "PhysicalControlFailure",
        "runtime_command_pair_up_to_right": transition.get("action") == "right" and
            transition.get("previous_action_twist") == gazebo_physics_twist("up") and
            transition.get("commanded_twist") == gazebo_physics_twist("right"),
        "runtime_classification_l2r": transition.get("command_mode_transition") ==
            "LINEAR_TO_ROTATION",
        "production_validator_rejected": validation.get("valid") is False,
        "retry4_action_8_returned": len(rows) >= 8 and
            rows[7].get("action") == "right" and rows[7].get("reason") == "moving" and
            rows[7].get("terminated") is False and rows[7].get("truncated") is False,
        "phase3fb_reached_beyond_action_8": int(
            phase3fb.get("prefix_replayed_count", 0)) >= 81,
    }
    if not all(required.values()):
        raise ValueError(f"Evidence does not prove exact UP→RIGHT action-8 failure: {required}")
    return {"target_episode": 1, "target_action_index_in_episode_1_based": 8,
        "target_global_action_index_1_based": 8, "previous_action": "up",
        "requested_action": "right", "transition_type": "LINEAR_TO_ROTATION",
        "checks": required, "retry4_action_8": rows[7],
        "phase3fb_prefix_replayed_count": phase3fb.get("prefix_replayed_count"),
        "diagnostic_failure_action": trial.get("failure_action"),
        "diagnostic_action_transition": transition,
        "diagnostic_pose_validation": validation}


def _task_chunk(adapter, prior_sensor_sequence, row):
    observation = adapter.get_agent_observation("sensor", 2)
    sensor = adapter._require_actual_sensor(observation, prior_sensor_sequence)
    env = adapter.env
    state = dict(getattr(env.contacts, "state", {}))
    schema = getattr(env.contacts, "schema", None)
    if not _contact_contract_pass(env, state, schema):
        raise RuntimeError("Contact schema/readiness failed during BRAKE_LINEAR")
    pose = row["pose_after"]
    goal = math.dist((pose["x"], pose["y"]), env.goal) <= adapter.goal_radius
    danger = any(item.type == "danger_zone" and
        math.hypot(pose["x"] - (item.position[0] + .5),
                   pose["y"] - (item.position[1] + .5)) < .5
        for item in adapter.scenario.objects)
    contacts = row.get("collision_events") or []
    reason = "collision" if contacts else "goal" if goal else "danger_zone" if danger else "moving"
    return {"reason": reason, "terminated": bool(contacts or goal or danger),
        "truncated": False, "collision": bool(contacts),
        "collision_events": contacts, "sensor_contract": sensor,
        "contact_state": state, "contact_schema": schema}


def execute_experimental_up_to_right(adapter, prehistory, *, initial_sensor_sequence):
    """Use shared contracts for one verifier-only UP→RIGHT brake/acquire trial."""
    env = adapter.env
    start = float(env.stepper.time)
    previous_command = dict(env.controller.last_command or {})
    requested = gazebo_physics_twist("right")
    transition = classify_physics_command_transition(previous_command, requested)
    request = ControlExecutionRequest(TARGET, previous_command, requested, transition)
    plan = plan_control_execution(request)
    evidence = {"agent_intent": TARGET, "previous_action": "up",
        "transition_type": transition, "plan": plan.to_dict(),
        "pre_braking_world_pose_history": prehistory,
        "world_pose_is_authority": True,
        "wheel_odometry_is_corroboration_only": True,
        "executed_commands": [], "phases": [], "status": None}
    if (transition != "LINEAR_TO_ROTATION" or
            previous_command != gazebo_physics_twist("up") or
            [item.kind.value for item in plan.phases] !=
                ["BRAKE_LINEAR", "ACQUIRE_ANGULAR"]):
        evidence.update(status="INCONCLUSIVE", failure_stage="TARGET_PRECONDITION",
            failure_reason="target command pair is not exact UP→RIGHT L2R")
        return evidence
    if not _precondition(prehistory):
        evidence.update(status="INCONCLUSIVE", failure_stage="UP_BODY_PRECONDITION",
            failure_reason="actual world-body forward UP motion was not established")
        return evidence
    controller = env.controller
    process = env.process
    if process is None or process.poll() is not None:
        evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="PROCESS_CHECK",
            failure_reason="Gazebo process is not alive before target braking")
        return evidence
    try:
        controller.stop_agent()
    except Exception as error:
        evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="BRAKE_PUBLISH",
            failure_reason=f"{type(error).__name__}: {error}")
        return evidence
    neutral = dict(controller.last_published_command or {})
    evidence["executed_commands"].append(neutral)
    if neutral != {"linear": {"x": 0.0}, "angular": {"z": 0.0}}:
        evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="BRAKE_PUBLISH",
            failure_reason="neutral Twist was not published")
        return evidence

    brake_start = float(env.stepper.time)
    chunks = []
    sensor_sequence = initial_sensor_sequence
    stopped = False
    for index in range(QUIESCENCE_MAX_CHUNKS):
        chunk_start = float(env.stepper.time)
        before = dict(env.pose)
        pose_cursor = env.transport.cursor(controller.pose_topic)
        odom_cursor = env.transport.cursor(env.odometry_topic)
        try:
            env.stepper.step_simulation()
            env._refresh()
            chunk_end = float(env.stepper.time)
            raw = controller.pose_history_after(pose_cursor, chunk_start, chunk_end)
            summary = summarize_world_pose_history(raw, chunk_start, chunk_end)
            contract = _history_contract(raw, summary, chunk_start, chunk_end)
            stopped_contract = body_stopped_contract(summary)
            step_evidence = dict(getattr(env.stepper, "last_verification", {}))
            odometry = None
            odometry_error = None
            try:
                odometry = env.read_odometry_after_sequence(odom_cursor,
                    chunk_end - .02, chunk_end + .002, timeout=.5)
            except Exception as error:
                odometry_error = {"type": type(error).__name__, "message": str(error)}
            collisions = env.contacts.poll(chunk_end) if hasattr(env, "contacts") else []
        except Exception as error:
            evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="BRAKE_PROGRESS",
                failure_reason=f"{type(error).__name__}: {error}", braking_chunks=chunks)
            return evidence
        iterations = step_evidence.get("iteration_delta")
        expected_iterations = step_evidence.get("expected_iteration_delta")
        iteration_ok = (iterations == QUIESCENCE_CHUNK_ITERATIONS and
                        expected_iterations == QUIESCENCE_CHUNK_ITERATIONS)
        row = {"index": index + 1, "phase": "BRAKE_LINEAR",
            "simulation_start": chunk_start, "simulation_end": chunk_end,
            "elapsed_simulation_time": chunk_end - chunk_start,
            "iterations": iterations, "expected_iterations": expected_iterations,
            "iterations_contract_pass": iteration_ok, "command": neutral,
            "pose_before": before, "pose_after": dict(env.pose),
            "world_pose_history": summary, "world_pose_history_raw": raw,
            "world_pose_history_contract": contract,
            "body_stopped_contract": stopped_contract,
            "wheel_odometry_corroboration": odometry,
            "wheel_odometry_error": odometry_error,
            "collision_events": collisions, "step_evidence": step_evidence}
        try:
            row["task_outcome"] = _task_chunk(adapter, sensor_sequence, row)
            sensor_sequence = row["task_outcome"]["sensor_contract"]["sequence"]
        except Exception as error:
            chunks.append(row)
            evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="BRAKE_TASK_CHECK",
                failure_reason=f"{type(error).__name__}: {error}", braking_chunks=chunks)
            return evidence
        chunks.append(row)
        if not iteration_ok or not contract.get("pass"):
            evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="BRAKE_FEEDBACK",
                failure_reason="physics progression or fresh/dense finite Pose_V contract failed",
                braking_chunks=chunks)
            return evidence
        if collisions or row["task_outcome"].get("terminated"):
            evidence.update(status="COLLISION_OR_TERMINAL", failure_stage="BRAKE_TERMINAL",
                collision=bool(collisions), braking_chunks=chunks,
                terminal_outcome=row["task_outcome"])
            break
        if chunk_end - brake_start > QUIESCENCE_MAX_CHUNKS * float(env.stepper.dt) + 1e-9:
            evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="BRAKE_BOUND",
                failure_reason="braking exceeded shared simulation-time bound",
                braking_chunks=chunks)
            return evidence
        if stopped_contract["pass"]:
            stopped = True
            break
    brake_end = float(env.stepper.time)
    last_summary = chunks[-1].get("world_pose_history") if chunks else {}
    brake_phase = {"phase": "BRAKE_LINEAR", "start_sim_time": brake_start,
        "end_sim_time": brake_end, "elapsed_simulation_time": brake_end-brake_start,
        "command": neutral, "completion_condition":
            "body_stopped_contract(world Pose_V, epsilon=0.02)",
        "completion_result": stopped, "chunks": chunks,
        "start_body_forward_velocity": prehistory.get("world_end_forward_velocity"),
        "end_body_forward_velocity": (last_summary or {}).get("world_end_forward_velocity"),
        "end_body_angular_velocity": (last_summary or {}).get("world_end_angular_velocity"),
        "max_control_ticks": QUIESCENCE_MAX_CHUNKS,
        "chunk_iterations": QUIESCENCE_CHUNK_ITERATIONS}
    evidence["phases"].append(brake_phase)
    evidence["braking_chunks"] = chunks
    if evidence.get("status") == "COLLISION_OR_TERMINAL":
        return evidence
    if not stopped:
        evidence.update(status="PHYSICAL_CONTROL_FAILURE", failure_stage="BRAKE_LINEAR",
            failure_reason="body did not satisfy shared stopped contract within bound")
        return evidence

    brake_publish_sequence = getattr(controller, "publish_sequence", None)
    acquire_start = float(env.stepper.time)
    pose_before = dict(env.pose)
    pose_cursor = env.transport.cursor(controller.pose_topic)
    try:
        result = adapter.step(TARGET)
    except PhysicalControlFailure as error:
        transition_evidence = dict(env.telemetry.get("action_transition") or {})
        failure = error.to_dict()
        evidence["phases"].append({"phase": "ACQUIRE_ANGULAR",
            "start_sim_time": acquire_start, "end_sim_time": float(env.stepper.time),
            "elapsed_simulation_time": float(env.stepper.time)-acquire_start,
            "command": TARGET, "completion_result": False,
            "production_validator_evidence": failure.get("evidence"),
            "action_transition": transition_evidence, "failure": failure})
        evidence.update(status="PHYSICAL_CONTROL_FAILURE", failure_stage="ACQUIRE_ANGULAR",
            failure_reason=str(error), production_validator_evidence=failure.get("evidence"),
            action_transition=transition_evidence)
        return evidence
    except Exception as error:
        evidence.update(status="INFRASTRUCTURE_FAILURE", failure_stage="ACQUIRE_ANGULAR",
            failure_reason=f"{type(error).__name__}: {error}")
        return evidence

    acquire_end = float(env.stepper.time)
    raw = controller.pose_history_after(pose_cursor, acquire_start, acquire_end)
    summary = summarize_world_pose_history(raw, acquire_start, acquire_end)
    contract = _history_contract(raw, summary, acquire_start, acquire_end)
    validation = dict(env.telemetry.get("pose_validation") or {})
    transition_evidence = dict(env.telemetry.get("action_transition") or {})
    publish_sequence = transition_evidence.get("action_publish_sequence")
    ordered = bool(transition_evidence.get("action") == TARGET and
        transition_evidence.get("commanded_twist") == requested and
        isinstance(brake_publish_sequence, int) and isinstance(publish_sequence, int) and
        publish_sequence > brake_publish_sequence)
    angular_samples = summary.get("world_angular_velocity_samples") or []
    requested_sign = -1.
    angular_values = [(_finite(row.get("simulation_timestamp")),
                       _finite(row.get("angular_velocity"))) for row in angular_samples]
    angular_ordered = bool(angular_values and all(
        t is not None and v is not None for t, v in angular_values) and
        all(b[0] > a[0] for a, b in zip(angular_values, angular_values[1:])))
    first_index = next((i for i, (_, value) in enumerate(angular_values)
        if value is not None and value * requested_sign > BODY_STOPPED_EPSILON), None)
    no_opposite = bool(first_index is not None and all(value is not None and
        value * requested_sign >= -BODY_STOPPED_EPSILON
        for _, value in angular_values[first_index:]))
    end_angular = _finite(summary.get("world_end_angular_velocity"))
    end_forward = _finite(summary.get("world_end_forward_velocity"))
    dx = float(env.pose["x"]) - pose_before["x"]
    dy = float(env.pose["y"]) - pose_before["y"]
    yaw_delta = math.atan2(math.sin(float(env.pose["yaw"])-pose_before["yaw"]),
        math.cos(float(env.pose["yaw"])-pose_before["yaw"]))
    projected = dx * math.cos(pose_before["yaw"]) + dy * math.sin(pose_before["yaw"])
    training = env.telemetry.get("gazebo_dqn_training") or {}
    sensor = training.get("sensor_after")
    sensor_ok = _sensor_contract_pass(sensor, adapter.max_sensor_age_ms)
    contact_state = dict(env.telemetry.get("contacts") or {})
    contact_schema = getattr(env.contacts, "schema", None)
    contact_ok = _contact_contract_pass(env, contact_state, contact_schema)
    collision = bool("collision" in result.reason or env.collision_event is not None or
        contact_state.get("new_contact_event"))
    process_ok = env.process is not None and env.process.poll() is None
    acquire_ok = bool(contract.get("pass") and validation.get("valid") is True and
        ordered and angular_ordered and first_index is not None and no_opposite and
        end_angular is not None and end_angular < -BODY_STOPPED_EPSILON and
        end_forward is not None and sensor_ok and contact_ok and process_ok and not collision)
    acquire = {"phase": "ACQUIRE_ANGULAR", "start_sim_time": acquire_start,
        "end_sim_time": acquire_end, "elapsed_simulation_time": acquire_end-acquire_start,
        "command": requested, "pose_before": pose_before, "pose_after": dict(env.pose),
        "world_pose_history": summary, "world_pose_history_raw": raw,
        "world_pose_history_contract": contract,
        "first_requested_direction_angular_velocity": (None if first_index is None else
            {"simulation_timestamp": angular_values[first_index][0],
             "angular_velocity": angular_values[first_index][1]}),
        "requested_angular_direction_established": first_index is not None,
        "final_body_forward_velocity": end_forward,
        "final_body_angular_velocity": end_angular,
        "world_forward_displacement": projected, "yaw_delta": yaw_delta,
        "production_pose_validation": validation,
        "wheel_odometry_corroboration": transition_evidence.get("odometry_history"),
        "command_ordered_after_braking": ordered,
        "brake_completion_publish_sequence": brake_publish_sequence,
        "acquire_command_publish_sequence": publish_sequence,
        "sensor_evidence": sensor, "sensor_contract_pass": sensor_ok,
        "contact_state": contact_state, "contact_schema": contact_schema,
        "contact_contract_pass": contact_ok, "collision": collision,
        "process_healthy": process_ok, "completion_result": acquire_ok}
    evidence["phases"].append(acquire)
    evidence["executed_commands"].append(requested)
    infra_failure = not (contract.get("pass") and sensor_ok and contact_ok and
                         process_ok and ordered and end_forward is not None)
    terminal_status = bool(result.terminated or result.truncated)
    evidence.update(status=("COLLISION" if collision else
        "INFRASTRUCTURE_FAILURE" if infra_failure else
        "PHYSICAL_CONTROL_FAILURE" if not acquire_ok else
        "TASK_TERMINAL" if terminal_status else "EXECUTED"),
        failure_stage=None if acquire_ok else "ACQUIRE_ANGULAR",
        failure_reason=None if acquire_ok else
            ("acquisition sensor/Contact/process/Pose_V contract failed"
             if infra_failure else
             "RIGHT angular acquisition failed world-body/validator contracts"),
        production_validator_evidence=validation,
        collision=collision, process_healthy=process_ok)
    evidence["elapsed_execution_time"] = acquire_end - start
    evidence["elapsed_discount_units"] = evidence["elapsed_execution_time"] / \
        NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
    evidence["simulation_start"] = start
    evidence["simulation_end"] = acquire_end
    return evidence


def assess_execution(evidence, *, process_status, shutdown):
    phases = evidence.get("phases") or []
    brake = next((row for row in phases if row.get("phase") == "BRAKE_LINEAR"), {})
    acquire = next((row for row in phases if row.get("phase") == "ACQUIRE_ANGULAR"), {})
    chunks = brake.get("chunks") or []
    total = _finite(evidence.get("elapsed_execution_time"))
    units = _finite(evidence.get("elapsed_discount_units"))
    checks = {
        "exact_up_to_right_l2r": evidence.get("previous_action") == "up" and
            evidence.get("agent_intent") == "right" and
            evidence.get("transition_type") == "LINEAR_TO_ROTATION",
        "plan_brake_linear_then_acquire_angular": [p.get("phase") for p in phases] ==
            ["BRAKE_LINEAR", "ACQUIRE_ANGULAR"],
        "up_body_motion_precondition": _precondition(
            evidence.get("pre_braking_world_pose_history") or {}),
        "neutral_before_right": bool(evidence.get("executed_commands")) and
            evidence["executed_commands"][0] ==
                {"linear": {"x": 0.0}, "angular": {"z": 0.0}} and
            evidence["executed_commands"][-1] == gazebo_physics_twist("right"),
        "bounded_world_body_stop": bool(chunks) and
            brake.get("completion_result") is True and
            chunks[-1].get("body_stopped_contract", {}).get("pass") is True and
            chunks[-1].get("body_stopped_contract", {}).get(
                "world_body_is_authority") is True,
        "requested_negative_world_angular_response":
            acquire.get("requested_angular_direction_established") is True and
            acquire.get("final_body_angular_velocity", 0.) < -BODY_STOPPED_EPSILON and
            acquire.get("world_pose_history_contract", {}).get("pass") is True,
        "production_pose_validator": acquire.get(
            "production_pose_validation", {}).get("valid") is True,
        "sensor_contact_process_healthy": acquire.get("sensor_contract_pass") is True and
            acquire.get("contact_contract_pass") is True and
            acquire.get("process_healthy") is True,
        "collision_explicit_false": acquire.get("collision") is False,
        "measured_time_discount_units": total is not None and total > 0. and
            units is not None and math.isclose(units,
                total / NOMINAL_DISCOUNT_TIME_UNIT_SECONDS, rel_tol=0., abs_tol=1e-10),
        "production_status_executed": evidence.get("status") == "EXECUTED",
        "process_and_shutdown": process_status.get("status") == "Running" and
            process_status.get("available") is True and shutdown == "PASS",
    }
    return {"checks": checks, "all_pass": all(checks.values())}


def run_verifier(artifact_dir, diagnostic_evidence_path, retry_evidence_path,
                 phase3fb_evidence_path, output, *, gui=False, env_factory=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "0.7.1",
        "verifier": "experimental actual-host UP-to-RIGHT L2R executor",
        "status": "ARTIFACT_EXTRACTION", "verdict": "UP_TO_RIGHT_L2R_FAILED",
        "failure_stage": "ARTIFACT_EXTRACTION", "last_completed_stage": None,
        "production_activation": False, "dqn_used": False, "training_used": False,
        "target_episode": 1, "target_action_index_in_episode_1_based": 8,
        "target_global_action_index_1_based": 8, "production_routing_used_for_target": False,
        "prefix_replayed_count": 0, "acceptance": None, "shutdown": "NOT_ATTEMPTED",
        "error": None}
    adapter = None
    try:
        replay = extract_reversal_replay(Path(artifact_dir))
        diagnostic = json.loads(Path(diagnostic_evidence_path).read_text(encoding="utf-8"))
        retry = json.loads(Path(retry_evidence_path).read_text(encoding="utf-8"))
        phase3fb = json.loads(Path(phase3fb_evidence_path).read_text(encoding="utf-8"))
        report["source_reconstruction"] = validate_sources(replay, diagnostic, retry, phase3fb)
        report["saved_run_id"] = replay.get("run_id")
        report["last_completed_stage"] = "ARTIFACT_EXTRACTION"
        report.update(status="ENVIRONMENT_STARTUP", failure_stage="ENVIRONMENT_STARTUP")
        factory = env_factory or GazeboPhysicsTrainingEnvironment
        adapter = factory(ScenarioSpec.from_dict(replay["scenario"]),
            replay["max_steps"], root=output / "worlds", gui=gui,
            max_sensor_age_ms=20)
        report.update(status="INITIAL_RESET", failure_stage="INITIAL_RESET",
            last_completed_stage="ENVIRONMENT_STARTUP")
        adapter.reset(int(replay["training_seed"]) + 1)
        report["reset_evidence"] = dict(adapter.last_reset_evidence)
        if adapter.injected or adapter.control_mode != "PHYSICS":
            raise RuntimeError("Verifier requires actual Gazebo PHYSICS mode")
        if adapter.process is None or adapter.process.poll() is not None:
            raise RuntimeError("Gazebo process is not alive after fresh initialization")
        report["process_start"] = adapter.manager.status()
        report["initial_pid"] = adapter.process.pid
        report["last_completed_stage"] = "INITIAL_RESET"

        rows = []
        report.update(status="REPLAYING_PRODUCTION_PREFIX", failure_stage="REPLAYING_PRODUCTION_PREFIX")
        for index, action in enumerate(PREFIX, 1):
            before_time = float(adapter.env.stepper.time)
            result = adapter.step(action)
            row = {"index": index, "action": action,
                "simulation_start": before_time,
                "simulation_end": float(adapter.env.stepper.time),
                "reason": result.reason, "terminated": result.terminated,
                "truncated": result.truncated}
            rows.append(row)
            report["prefix_replayed_count"] = len(rows)
            if result.terminated or result.truncated:
                raise RuntimeError(f"Production prefix became terminal at action {index}")
        env = adapter.env
        previous_command = dict(env.controller.last_command)
        prehistory = dict((env.telemetry.get("action_transition") or {}).get(
            "world_pose_history_summary") or {})
        start_sensor = dict((env.telemetry.get("gazebo_dqn_training") or {}).get(
            "sensor_after") or {})
        if previous_command != gazebo_physics_twist("up"):
            raise RuntimeError("Action 7 did not leave the exact UP physical command")
        target_start_steps = int(env.steps)
        target_start = float(env.stepper.time)
        report["prefix_replay"] = {"expected_count": 7, "replayed_count": 7,
            "actions": rows}
        report["target_precondition"] = {"previous_action": "up",
            "agent_intent": "right", "previous_command": previous_command,
            "requested_command": gazebo_physics_twist("right"),
            "transition_type": classify_physics_command_transition(
                previous_command, gazebo_physics_twist("right")),
            "pre_braking_world_pose_history": prehistory,
            "decision_count": target_start_steps, "simulation_time": target_start}
        report.update(status="EXECUTING_EXPERIMENTAL_TARGET",
            failure_stage="EXECUTING_EXPERIMENTAL_TARGET",
            last_completed_stage="REPLAYING_PRODUCTION_PREFIX")
        evidence = execute_experimental_up_to_right(adapter, prehistory,
            initial_sensor_sequence=start_sensor.get("sequence"))
        evidence.setdefault("simulation_start", target_start)
        evidence["simulation_end"] = float(env.stepper.time)
        evidence["elapsed_execution_time"] = float(env.stepper.time) - target_start
        evidence["elapsed_discount_units"] = evidence["elapsed_execution_time"] / \
            NOMINAL_DISCOUNT_TIME_UNIT_SECONDS
        evidence.update(target_episode=1, target_action_index_in_episode_1_based=8,
            target_global_action_index_1_based=8,
            agent_decisions_consumed=int(env.steps)-target_start_steps)
        report["execution"] = evidence
        report["process_status"] = adapter.manager.status()
        report["last_completed_stage"] = "TARGET_EXECUTION_RETURNED"
        report["status"] = evidence.get("status")
        report["failure_stage"] = evidence.get("failure_stage")
        report["verdict"] = ("UP_TO_RIGHT_L2R_ACTUAL_PASS"
            if evidence.get("status") == "EXECUTED" else
            "UP_TO_RIGHT_PHYSICAL_CONTROL_FAILURE"
            if evidence.get("status") == "PHYSICAL_CONTROL_FAILURE" else
            "UP_TO_RIGHT_INFRASTRUCTURE_FAILURE")
    except Exception as error:
        report.update(status="FAILED", failure_stage=report.get("failure_stage"),
            verdict="UP_TO_RIGHT_L2R_EXECUTOR_FAILED",
            error={"type": type(error).__name__, "message": str(error)})
    finally:
        if adapter is not None:
            try:
                report["final_process_status"] = adapter.manager.status()
                adapter.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = {"type": type(error).__name__,
                    "message": str(error)}
        if isinstance(report.get("execution"), dict):
            report["acceptance"] = assess_execution(report["execution"],
                process_status=report.get("final_process_status") or {},
                shutdown=report["shutdown"])
            report["verdict"] = ("UP_TO_RIGHT_L2R_ACTUAL_PASS"
                if report["acceptance"]["all_pass"] else "UP_TO_RIGHT_L2R_REJECTED")
        report["evidence_file"] = str(output / "up_to_right_control_executor.json")
        nonfinite = find_nonfinite_paths(report)
        report["nonfinite_field_paths"] = nonfinite
        report["json_evidence_audit"] = {"status": "PASS" if not nonfinite else "FAIL",
            "nonfinite_field_paths": nonfinite}
        if nonfinite and isinstance(report.get("acceptance"), dict):
            report["acceptance"]["checks"]["strict_json_finite"] = False
            report["acceptance"]["all_pass"] = False
            report["verdict"] = "UP_TO_RIGHT_L2R_REJECTED"
        write_json(output / "up_to_right_control_executor.json",
                   _strict_json_value(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--diagnostic-evidence", type=Path, required=True)
    parser.add_argument("--retry-evidence", type=Path, required=True)
    parser.add_argument("--phase3fb-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_verifier(args.artifact_dir, args.diagnostic_evidence,
        args.retry_evidence, args.phase3fb_evidence, args.output, gui=args.gui)
    print("Gazebo experimental UP-to-RIGHT L2R: " + report["verdict"])
    print("evidence: " + report["evidence_file"])
    return 0 if report["verdict"] == "UP_TO_RIGHT_L2R_ACTUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
