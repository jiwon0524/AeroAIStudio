"""Experimental Gazebo executor for the evidence-backed R2L transition only."""
from __future__ import annotations

from dataclasses import replace
import math

from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.gazebo.physics_feedback import (
    BODY_STOPPED_EPSILON,
    QUIESCENCE_CHUNK_ITERATIONS,
    QUIESCENCE_MAX_CHUNKS,
    body_stopped_contract,
)
from aero_ai_studio.simulation.action_mapping import (
    classify_physics_command_transition,
    gazebo_physics_twist,
)
from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.simulation.control_execution import (
    ControlPhaseKind,
    ControlExecutionPlan,
    ControlExecutionRequest,
    ControlExecutionResult,
    ControlExecutionStatus,
    FeedbackCondition,
    plan_control_execution,
)


class GazeboControlExecutor:
    """Run an exact-pair R2L macro using world feedback.

    Defaults preserve the production RIGHT-to-DOWN pair. Experimental exact
    pair wrappers can reuse the same direction-neutral physical procedure.
    """

    def __init__(self, training_environment, *, pre_braking_history: dict,
                 previous_action="right", requested_action="down"):
        self.training_environment = training_environment
        self.env = training_environment.env
        self.pre_braking_history = pre_braking_history
        self.previous_action = str(previous_action)
        self.requested_action = str(requested_action)
        self.dt = float(self.env.stepper.dt)

    def plan(self, request: ControlExecutionRequest) -> ControlExecutionPlan:
        return plan_control_execution(request)

    def execute_plan(self, plan: ControlExecutionPlan, *, on_braking_chunk=None) -> ControlExecutionResult:
        request = plan.request
        if request.transition_type != "ROTATION_TO_LINEAR":
            raise NotImplementedError("Gazebo Phase 3A executor supports ROTATION_TO_LINEAR only")
        if [phase.kind.value for phase in plan.phases] != ["BRAKE_ANGULAR", "ACQUIRE_LINEAR"]:
            raise ValueError("R2L plan must be BRAKE_ANGULAR followed by ACQUIRE_LINEAR")

        bounded_phases = tuple(replace(
            phase,
            max_control_ticks=QUIESCENCE_MAX_CHUNKS,
            completion_conditions=(
                (FeedbackCondition.ANGULAR_VELOCITY_WITHIN_DEADBAND,
                 FeedbackCondition.LINEAR_VELOCITY_WITHIN_DEADBAND)
                if phase.kind is ControlPhaseKind.BRAKE_ANGULAR
                else phase.completion_conditions))
            for phase in plan.phases)
        bounded_plan = replace(plan, phases=bounded_phases)
        start_sim = float(self.env.stepper.time)
        before_pose = dict(self.env.pose)
        previous_angular = _finite_float(
            self.pre_braking_history.get("world_end_angular_velocity"))
        previous_forward = _finite_float(
            self.pre_braking_history.get("world_end_forward_velocity"))
        requested_linear = _finite_float(request.requested_command.get("linear", {}).get("x"))
        requested_angular = _finite_float(request.requested_command.get("angular", {}).get("z"))
        previous_command_angular = _finite_float(
            request.previous_command.get("angular", {}).get("z"))
        expected_request = gazebo_physics_twist(request.agent_intent)
        actual_transition = classify_physics_command_transition(
            request.previous_command, request.requested_command)
        if (request.agent_intent != self.requested_action or
                request.previous_command != gazebo_physics_twist(self.previous_action) or
                actual_transition != "ROTATION_TO_LINEAR" or
                request.requested_command != expected_request):
            return self._result(bounded_plan, ControlExecutionStatus.INCONCLUSIVE,
                start_sim, "request command/intent does not match the configured exact R2L pair",
                failure_category="request_not_supported",
                evidence={"classified_transition": actual_transition,
                    "previous_action": self.previous_action,
                    "requested_action": self.requested_action,
                    "expected_previous_command": gazebo_physics_twist(self.previous_action),
                    "expected_command": expected_request})
        if not _history_is_sufficient(self.pre_braking_history) or None in (
                previous_angular, previous_forward, requested_linear, previous_command_angular):
            return self._result(bounded_plan, ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                start_sim, "pre_braking_world_pose_history_missing_stale_sparse_or_nonfinite",
                failure_category="physical_control_failure",
                evidence={"pre_braking_history": self.pre_braking_history})
        if (abs(previous_angular) <= BODY_STOPPED_EPSILON or
                abs(previous_command_angular) <= BODY_STOPPED_EPSILON or
                previous_angular * previous_command_angular <= 0.):
            return self._result(bounded_plan, ControlExecutionStatus.INCONCLUSIVE,
                start_sim, "replay_did_not_reach_requested_previous_rotation_state",
                failure_category="precondition_not_met",
                evidence={"previous_body_angular_velocity": previous_angular,
                          "previous_command_angular_z": previous_command_angular})
        if requested_linear == 0. or requested_angular is None or abs(requested_angular) > BODY_STOPPED_EPSILON:
            return self._result(bounded_plan, ControlExecutionStatus.INCONCLUSIVE,
                start_sim, "request is not a nonzero linear-only target command",
                failure_category="request_not_supported",
                evidence={"requested_linear_x": requested_linear,
                          "requested_angular_z": requested_angular})

        executed_commands = []
        phases = []
        braking_chunks = []
        controller = self.env.controller
        process = self.env.process
        if process is None or process.poll() is not None:
            return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, "Gazebo process is not alive before angular braking",
                failure_category="process_death")

        # BRAKE_ANGULAR: one neutral Twist, then bounded fixed-physics chunks.
        brake_start = float(self.env.stepper.time)
        brake_start_pose = dict(self.env.pose)
        try:
            controller.stop_agent()
        except Exception as error:
            return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, str(error), failure_category="command_publish_failure")
        zero_command = dict(controller.last_published_command or {})
        executed_commands.append(zero_command)
        if (zero_command.get("linear", {}).get("x") != 0. or
                zero_command.get("angular", {}).get("z") != 0.):
            return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, "neutral Twist was not published", failure_category="command_publish_failure",
                executed_commands=executed_commands)

        brake_completed = False
        early_terminal = None
        for index in range(QUIESCENCE_MAX_CHUNKS):
            if self.env.process is None or self.env.process.poll() is not None:
                return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, "Gazebo process died during angular braking",
                    failure_category="process_death", executed_commands=executed_commands,
                    phases=phases, evidence={"braking_chunks": braking_chunks})
            chunk_start = float(self.env.stepper.time)
            chunk_pose_before = dict(self.env.pose)
            cursor = self.env.transport.cursor(self.env.controller.pose_topic)
            odometry_cursor = self.env.transport.cursor(self.env.odometry_topic)
            try:
                self.env.stepper.step_simulation()
                self.env._refresh()
                chunk_end = float(self.env.stepper.time)
                raw_history = self.env.controller.pose_history_after(
                    cursor, chunk_start, chunk_end)
                history = summarize_world_pose_history(raw_history, chunk_start, chunk_end)
                history_contract = _history_contract(raw_history, history, chunk_start, chunk_end)
                stopped = body_stopped_contract(history)
                step_evidence = dict(getattr(self.env.stepper, "last_verification", {}))
                iterations = step_evidence.get("iteration_delta")
                expected_iterations = step_evidence.get("expected_iteration_delta")
                iteration_pass = (iterations == QUIESCENCE_CHUNK_ITERATIONS and
                                  expected_iterations == QUIESCENCE_CHUNK_ITERATIONS)
                odometry = None
                odometry_error = None
                try:
                    odometry = self.env.read_odometry_after_sequence(
                        odometry_cursor, chunk_end - .02, chunk_end + .002, timeout=.5)
                except Exception as error:
                    # Odometry is recorded as corroboration. It cannot establish
                    # angular braking in place of world-body pose history.
                    odometry_error = {"type": type(error).__name__, "message": str(error)}
                collision_events = (self.env.contacts.poll(chunk_end)
                                    if hasattr(self.env, "contacts") else [])
            except Exception as error:
                return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, str(error), failure_category="physics_progression_or_telemetry",
                    executed_commands=executed_commands, phases=phases,
                    evidence={"braking_chunks": braking_chunks})

            row = {
                "index": index + 1,
                "simulation_start": chunk_start,
                "simulation_end": chunk_end,
                "elapsed_simulation_time": chunk_end - chunk_start,
                "iterations": iterations,
                "expected_iterations": expected_iterations,
                "iterations_contract_pass": iteration_pass,
                "pose_before": chunk_pose_before,
                "pose_after": dict(self.env.pose),
                "world_pose_history": history,
                "world_pose_history_raw": raw_history,
                "world_pose_history_contract": history_contract,
                "body_stopped_contract": stopped,
                "odometry": odometry,
                "odometry_error": odometry_error,
                "collision_events": collision_events,
                "step_evidence": step_evidence,
            }
            braking_chunks.append(row)
            if on_braking_chunk is not None:
                # The training adapter evaluates this completed physical chunk
                # using its fresh sensor/contact state and returns the existing
                # task outcome. The executor itself does not invent task reward.
                row["task_outcome"] = on_braking_chunk(row)
            if collision_events and on_braking_chunk is None:
                row["task_outcome"] = {
                    "reason": "collision", "terminated": True, "truncated": False,
                    "collision": True, "collision_events": collision_events,
                }
            if chunk_end - brake_start > QUIESCENCE_MAX_CHUNKS * self.dt + 1e-9:
                return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, "braking progression exceeded its configured simulation-time bound",
                    failure_category="step_duration_contract",
                    executed_commands=executed_commands, phases=phases,
                    evidence={"braking_chunks": braking_chunks})
            if not iteration_pass:
                return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, "fixed physics chunk did not advance the required iterations",
                    failure_category="step_progression_contract",
                    executed_commands=executed_commands, phases=phases,
                    evidence={"braking_chunks": braking_chunks})
            outcome = row.get("task_outcome") or {}
            if collision_events or outcome.get("terminated") or outcome.get("truncated"):
                early_terminal = outcome or {
                    "reason": "collision", "terminated": True, "truncated": False,
                    "collision": True, "collision_events": collision_events,
                }
                break
            if not history_contract["pass"]:
                return self._result(bounded_plan, ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                    start_sim, "world Pose_V feedback did not satisfy the braking completion contract",
                    failure_category="physical_control_failure",
                    executed_commands=executed_commands, phases=phases,
                    evidence={"braking_chunks": braking_chunks})
            if stopped["pass"]:
                brake_completed = True
                break

        brake_end = float(self.env.stepper.time)
        last_history = braking_chunks[-1]["world_pose_history"] if braking_chunks else {}
        brake_phase = {
            "phase": "BRAKE_ANGULAR",
            "start_sim_time": brake_start,
            "end_sim_time": brake_end,
            "elapsed_simulation_time": brake_end - brake_start,
            "command": zero_command,
            "start_body_forward_velocity": previous_forward,
            "start_body_angular_velocity": previous_angular,
            "end_body_forward_velocity": last_history.get("world_end_forward_velocity"),
            "end_body_angular_velocity": last_history.get("world_end_angular_velocity"),
            "completion_condition": "abs(world body forward/angular velocity samples) <= 0.02",
            "completion_result": brake_completed,
            "chunks": braking_chunks,
            "max_control_ticks": QUIESCENCE_MAX_CHUNKS,
            "chunk_iterations": QUIESCENCE_CHUNK_ITERATIONS,
            "maximum_simulation_duration": QUIESCENCE_MAX_CHUNKS * self.dt,
        }
        phases.append(brake_phase)
        if early_terminal is not None:
            collision = bool(early_terminal.get("collision") or
                             "collision" in str(early_terminal.get("reason", "")))
            status = ControlExecutionStatus.COLLISION if collision else ControlExecutionStatus.TASK_TERMINAL
            return self._result(bounded_plan, status, start_sim,
                str(early_terminal.get("reason") or "task_terminal_during_braking"),
                failure_category="collision" if collision else None,
                executed_commands=executed_commands, phases=phases,
                evidence={"braking_chunks": braking_chunks,
                          "braking_phase": brake_phase,
                          "task_terminal_during_braking": early_terminal,
                          "collision_events": early_terminal.get("collision_events", [])})
        if not brake_completed:
            failure = PhysicalControlFailure(
                "Angular braking did not reach the actual world-body stop contract within the bounded window",
                evidence={"agent_intent": request.agent_intent,
                          "requested_command": dict(request.requested_command),
                          "transition_type": request.transition_type,
                          "phase": brake_phase})
            return self._result(bounded_plan, ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                start_sim, failure.reason, failure_category=failure.failure_category,
                executed_commands=executed_commands, phases=phases,
                evidence={"physical_control_failure": failure.to_dict()})

        # ACQUIRE_LINEAR executes through the unchanged production env.step()
        # and validator. Capture passive Pose_V history independently for evidence.
        acquisition_start = float(self.env.stepper.time)
        acquisition_pose_before = dict(self.env.pose)
        pose_cursor = self.env.transport.cursor(self.env.controller.pose_topic)
        command_sequence_before = getattr(self.env.controller, "publish_sequence", None)
        action = request.agent_intent
        try:
            result = self.training_environment.step(action)
        except PhysicalControlFailure as error:
            phases.append({"phase": "ACQUIRE_LINEAR", "start_sim_time": acquisition_start,
                           "end_sim_time": float(self.env.stepper.time),
                           "completion_result": False, "failure": error.to_dict()})
            if (command_sequence_before is not None and
                    getattr(self.env.controller, "publish_sequence", command_sequence_before) >
                    command_sequence_before):
                executed_commands.append(dict(self.env.controller.last_published_command or {}))
            return self._result(bounded_plan, ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                start_sim, str(error), failure_category=error.failure_category,
                executed_commands=executed_commands, phases=phases,
                evidence={"validator_evidence": error.evidence,
                          "braking_phase": brake_phase})
        except Exception as error:
            phases.append({"phase": "ACQUIRE_LINEAR", "start_sim_time": acquisition_start,
                           "end_sim_time": float(self.env.stepper.time),
                           "completion_result": False,
                           "failure": {"type": type(error).__name__, "reason": str(error)}})
            if (command_sequence_before is not None and
                    getattr(self.env.controller, "publish_sequence", command_sequence_before) >
                    command_sequence_before):
                executed_commands.append(dict(self.env.controller.last_published_command or {}))
            return self._result(bounded_plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, str(error), failure_category=getattr(error, "category", "service_or_sensor_failure"),
                executed_commands=executed_commands, phases=phases,
                evidence={"braking_phase": brake_phase})

        acquisition_end = float(self.env.stepper.time)
        acquisition_raw = self.env.controller.pose_history_after(
            pose_cursor, acquisition_start, acquisition_end)
        acquisition_history = summarize_world_pose_history(
            acquisition_raw, acquisition_start, acquisition_end)
        acquisition_history_contract = _history_contract(
            acquisition_raw, acquisition_history, acquisition_start, acquisition_end)
        validation = dict(self.env.telemetry.get("pose_validation") or {})
        transition = dict(self.env.telemetry.get("action_transition") or {})
        requested_sign = 1 if requested_linear > 0. else -1
        end_forward = _finite_float(acquisition_history.get("world_end_forward_velocity"))
        end_angular = _finite_float(acquisition_history.get("world_end_angular_velocity"))
        forward_displacement = (self.env.pose["x"] - acquisition_pose_before["x"])
        forward_displacement = (forward_displacement * math.cos(acquisition_pose_before["yaw"]) +
                                (self.env.pose["y"] - acquisition_pose_before["y"]) *
                                math.sin(acquisition_pose_before["yaw"]))
        yaw_delta = math.atan2(
            math.sin(self.env.pose["yaw"] - acquisition_pose_before["yaw"]),
            math.cos(self.env.pose["yaw"] - acquisition_pose_before["yaw"]))
        linear_samples = acquisition_history.get("world_forward_velocity_samples", [])
        first_requested_velocity = next((sample for sample in linear_samples
            if _finite_float(sample.get("forward_velocity")) is not None and
            float(sample["forward_velocity"]) * requested_sign > BODY_STOPPED_EPSILON), None)
        collision = ("collision" in result.reason or
                     self.env.collision_event is not None or
                     bool((self.env.telemetry.get("contacts") or {}).get("new_contact_event")))
        acquired = bool(
            acquisition_history_contract["pass"] and validation.get("valid") is True and
            end_forward is not None and end_forward * requested_sign > BODY_STOPPED_EPSILON and
            end_angular is not None and abs(end_angular) <= BODY_STOPPED_EPSILON and
            forward_displacement * requested_sign > 0. and not collision)
        acquisition_phase = {
            "phase": "ACQUIRE_LINEAR",
            "start_sim_time": acquisition_start,
            "end_sim_time": acquisition_end,
            "elapsed_simulation_time": acquisition_end - acquisition_start,
            "command": dict(request.requested_command),
            "pose_before": acquisition_pose_before,
            "pose_after": dict(self.env.pose),
            "world_forward_displacement": forward_displacement,
            "world_yaw_delta": yaw_delta,
            "world_pose_history": acquisition_history,
            "world_pose_history_raw": acquisition_raw,
            "world_pose_history_contract": acquisition_history_contract,
            "end_body_forward_velocity": end_forward,
            "end_body_angular_velocity": end_angular,
            "start_body_forward_velocity": acquisition_history.get("world_start_forward_velocity"),
            "start_body_angular_velocity": acquisition_history.get("world_start_angular_velocity"),
            "first_requested_direction_velocity": first_requested_velocity,
            "requested_direction_established": bool(end_forward is not None and
                end_forward * requested_sign > BODY_STOPPED_EPSILON),
            "production_pose_validation": validation,
            "wheel_odometry_corroboration": transition.get("odometry_history"),
            "collision": collision,
            "completion_result": acquired,
        }
        phases.append(acquisition_phase)
        executed_commands.append(dict(request.requested_command))
        if collision:
            status = ControlExecutionStatus.COLLISION
            category = "collision"
            reason = "contact/collision occurred during linear acquisition"
        elif acquired:
            status = ControlExecutionStatus.EXECUTED
            category = None
            reason = None
        else:
            status = ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
            category = "linear_acquisition_failed"
            reason = "requested backward body motion did not satisfy actual world-body and production validation"
        evidence = {
            "agent_intent": request.agent_intent,
            "previous_command": dict(request.previous_command),
            "requested_command": dict(request.requested_command),
            "transition_type": request.transition_type,
            "plan": bounded_plan.to_dict(),
            "pre_braking_world_body_history": self.pre_braking_history,
            "braking_chunks": braking_chunks,
            "braking_phase": brake_phase,
            "acquisition_phase": acquisition_phase,
            "before_pose": before_pose,
            "body_stopped_epsilon": BODY_STOPPED_EPSILON,
        }
        return self._result(bounded_plan, status, start_sim, reason,
            failure_category=category, executed_commands=executed_commands,
            phases=phases, evidence={**evidence,
                                     "validator_evidence": validation},
            step_result=result)

    def _result(self, plan, status, start_sim, reason, *, failure_category=None,
                executed_commands=(), phases=(), evidence=None, step_result=None):
        return ControlExecutionResult(
            agent_intent=plan.request.agent_intent,
            status=status,
            requested_command=plan.request.requested_command,
            transition_type=plan.request.transition_type,
            executed_commands=tuple(executed_commands),
            phases=plan.phases,
            elapsed_simulation_time=float(self.env.stepper.time) - start_sim,
            failure_category=failure_category,
            reason=reason,
            validator_evidence=(evidence or {}).get("validator_evidence"),
            execution_evidence={**(evidence or {}), "phase_evidence": phases},
            step_result=step_result,
        )


class GazeboLeftToUpControlExecutor(GazeboControlExecutor):
    """Experimental feedback executor for exact LEFT→UP ROTATION_TO_LINEAR.

    It shares the verified R2L braking/acquisition implementation but remains
    outside production training routing until this exact pair passes host
    validation. Precondition and feedback classification stay evidence based.
    """

    def __init__(self, training_environment, *, pre_braking_history: dict):
        super().__init__(training_environment, pre_braking_history=pre_braking_history,
            previous_action="left", requested_action="up")

    def execute_plan(self, plan: ControlExecutionPlan, *, on_braking_chunk=None):
        request = plan.request
        if (request.agent_intent != "up" or
                request.previous_command != gazebo_physics_twist("left") or
                request.requested_command != gazebo_physics_twist("up") or
                classify_physics_command_transition(request.previous_command,
                    request.requested_command) != "ROTATION_TO_LINEAR"):
            start = float(self.env.stepper.time)
            return self._result(plan, ControlExecutionStatus.INCONCLUSIVE, start,
                "request does not match exact LEFT→UP ROTATION_TO_LINEAR",
                failure_category="request_not_supported",
                evidence={"classified_transition": classify_physics_command_transition(
                    request.previous_command, request.requested_command)})
        history = self.pre_braking_history or {}
        if not _history_is_sufficient(history):
            start = float(self.env.stepper.time)
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start, "pre-braking world Pose_V history is missing, stale, or sparse",
                failure_category="world_pose_feedback_unavailable",
                evidence={"pre_braking_world_body_history": history})
        angular_samples = history.get("world_angular_velocity_samples") or []
        forward_samples = history.get("world_forward_velocity_samples") or []
        samples = []
        for row in angular_samples:
            timestamp = _finite_float(row.get("simulation_timestamp"))
            velocity = _finite_float(row.get("angular_velocity"))
            if timestamp is None or velocity is None:
                samples = []
                break
            samples.append((timestamp, velocity))
        ordered_dense = bool(len(samples) >= 3 and all(
            right[0] > left[0] for left, right in zip(samples, samples[1:])))
        end_angular = _finite_float(history.get("world_end_angular_velocity"))
        end_forward = _finite_float(history.get("world_end_forward_velocity"))
        forward_finite = bool(len(forward_samples) >= 2 and all(
            _finite_float(row.get("simulation_timestamp")) is not None and
            _finite_float(row.get("forward_velocity")) is not None
            for row in forward_samples))
        left_rotation = bool(ordered_dense and end_angular is not None and
            end_angular > BODY_STOPPED_EPSILON and
            any(value > BODY_STOPPED_EPSILON for _, value in samples))
        if not ordered_dense or not forward_finite or end_forward is None:
            start = float(self.env.stepper.time)
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start, "pre-braking world Pose_V history is non-finite, unordered, or sparse",
                failure_category="world_pose_feedback_unavailable",
                evidence={"pre_braking_world_body_history": history,
                    "ordered_dense_finite_angular_samples": ordered_dense,
                    "finite_forward_samples": forward_finite})
        if not left_rotation:
            start = float(self.env.stepper.time)
            return self._result(plan, ControlExecutionStatus.INCONCLUSIVE, start,
                "actual LEFT angular body motion was not established before braking",
                failure_category="precondition_not_met",
                evidence={"pre_braking_world_body_history": history,
                    "left_rotation_precondition_pass": False})

        result = super().execute_plan(plan, on_braking_chunk=on_braking_chunk)
        evidence = dict(result.execution_evidence or {})
        phases = list(evidence.get("phase_evidence") or [])
        brake = next((row for row in phases if row.get("phase") == "BRAKE_ANGULAR"), {})
        acquire = next((row for row in phases if row.get("phase") == "ACQUIRE_LINEAR"), {})
        transition = dict(self.env.telemetry.get("action_transition") or {})
        brake_publish_sequence = _finite_int(transition.get("command_publish_sequence_before"))
        acquire_publish_sequence = _finite_int(transition.get("action_publish_sequence"))
        command_ordered = bool(transition.get("action") == "up" and
            transition.get("commanded_twist") == gazebo_physics_twist("up") and
            brake_publish_sequence is not None and acquire_publish_sequence is not None and
            acquire_publish_sequence > brake_publish_sequence)
        if acquire:
            acquire["command_published_after_braking"] = command_ordered
            acquire["brake_completion_publish_sequence"] = brake_publish_sequence
            acquire["acquire_command_publish_sequence"] = acquire_publish_sequence
            acquire["ordering_proof_source"] = "production_action_transition_publish_sequence"
        body_samples = ((acquire.get("world_pose_history") or {}).get(
            "world_forward_velocity_samples") or [])
        body_values = []
        for row in body_samples:
            stamp = _finite_float(row.get("simulation_timestamp"))
            velocity = _finite_float(row.get("forward_velocity"))
            if stamp is None or velocity is None:
                body_values = []
                break
            body_values.append((stamp, velocity))
        body_ordered = bool(body_values and all(b[0] > a[0]
            for a, b in zip(body_values, body_values[1:])))
        first_forward = next((i for i, (_, velocity) in enumerate(body_values)
            if velocity > BODY_STOPPED_EPSILON), None)
        no_reverse_after_forward = bool(first_forward is not None and all(
            velocity >= -BODY_STOPPED_EPSILON
            for _, velocity in body_values[first_forward:]))
        if acquire:
            acquire["requested_direction_established"] = first_forward is not None
            acquire["first_requested_direction_velocity"] = (None if first_forward is None
                else {"simulation_timestamp": body_values[first_forward][0],
                      "forward_velocity": body_values[first_forward][1]})
            acquire["no_opposite_forward_response_after_established"] = no_reverse_after_forward
        evidence["left_rotation_precondition"] = {
            "pass": True, "world_pose_is_authority": True,
            "end_body_angular_velocity": end_angular,
            "world_angular_velocity_samples": angular_samples,
            "wheel_odometry_is_corroboration_only": True}
        evidence["process_healthy_after_execution"] = bool(
            self.env.process is not None and self.env.process.poll() is None)
        sensor = dict((self.env.telemetry.get("gazebo_dqn_training") or {}).get(
            "sensor_after") or {})
        sensor_pass = _sensor_contract_pass(sensor,
            getattr(self.training_environment, "max_sensor_age_ms", 20.))
        evidence["acquisition_sensor_evidence"] = sensor
        evidence["acquisition_sensor_contract_pass"] = sensor_pass
        contact_state = dict(self.env.telemetry.get("contacts") or
            getattr(getattr(self.env, "contacts", None), "state", {}) or {})
        contact_schema = getattr(getattr(self.env, "contacts", None), "schema", None)
        contact_pass = _contact_contract_pass(self.env, contact_state, contact_schema)
        evidence["acquisition_contact_evidence"] = {
            "state": contact_state, "schema": contact_schema,
            "expected_topic": getattr(self.env, "contact_topic", None),
            "contract_pass": contact_pass, "collision": acquire.get("collision")}

        braking_chunks = evidence.get("braking_chunks") or []
        braking_feedback_invalid = any(
            (row.get("world_pose_history_contract") or {}).get("pass") is not True
            for row in braking_chunks)
        feedback_unavailable = (result.status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE and
            (braking_feedback_invalid or
             "world Pose_V feedback did not satisfy" in str(result.reason) or
             not (acquire.get("world_pose_history_contract") or {}).get("pass", True)))
        if feedback_unavailable:
            return replace(result, status=ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                failure_category="world_pose_feedback_unavailable",
                reason="LEFT→UP execution lacks valid fresh/dense world Pose_V feedback",
                execution_evidence=evidence)
        if result.status is ControlExecutionStatus.EXECUTED and (
                not command_ordered or not body_ordered):
            return replace(result, status=ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                failure_category="execution_evidence_contract",
                reason="LEFT→UP command ordering or world Pose_V sample ordering is unavailable",
                execution_evidence=evidence, step_result=None)
        if result.status is ControlExecutionStatus.EXECUTED and (
                not sensor_pass or not contact_pass):
            return replace(result, status=ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                failure_category="sensor_or_contact_contract",
                reason="LEFT→UP acquisition sensor or Contact evidence contract failed",
                execution_evidence=evidence, step_result=None)
        if result.status is ControlExecutionStatus.EXECUTED and (
                first_forward is None or not no_reverse_after_forward):
            return replace(result, status=ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                failure_category="linear_acquisition_failed",
                reason="UP acquisition did not preserve ordered requested-direction world-body response",
                execution_evidence=evidence, step_result=None)
        return replace(result, execution_evidence=evidence)


class GazeboLinearReversalControlExecutor:
    """Experimental, DQN-free exact-pair linear reversal executor.

    This class is intentionally not wired into ``GazeboPhysicsTrainingEnvironment``.
    It shares the strict world-pose quiescence contract and leaves acquisition
    to the existing production ``env.step`` validator. The default pair remains
    the previously verified DOWN-to-UP case; an isolated verifier may select
    another exact pair.
    """

    def __init__(self, training_environment, *, pre_braking_history: dict,
                 previous_action="down", requested_action="up"):
        self.training_environment = training_environment
        self.env = training_environment.env
        self.pre_braking_history = pre_braking_history
        self.previous_action = str(previous_action)
        self.requested_action = str(requested_action)
        self.dt = float(self.env.stepper.dt)

    def plan(self, request: ControlExecutionRequest) -> ControlExecutionPlan:
        return plan_control_execution(request)

    def execute_plan(self, plan: ControlExecutionPlan, *, on_braking_chunk=None) -> ControlExecutionResult:
        request = plan.request
        start_sim = float(self.env.stepper.time)
        expected = gazebo_physics_twist(self.requested_action)
        actual_transition = classify_physics_command_transition(
            request.previous_command, request.requested_command)
        if (request.agent_intent != self.requested_action or
                actual_transition != "LINEAR_REVERSAL" or
                request.transition_type != "LINEAR_REVERSAL" or
                request.previous_command != gazebo_physics_twist(self.previous_action) or
                request.requested_command != expected):
            return self._result(plan, ControlExecutionStatus.INCONCLUSIVE, start_sim,
                "request does not match the configured exact LINEAR_REVERSAL pair",
                failure_category="request_not_supported",
                evidence={"classified_transition": actual_transition,
                          "previous_action": self.previous_action,
                          "requested_action": self.requested_action,
                          "expected_previous_command": gazebo_physics_twist(self.previous_action),
                          "expected_requested_command": expected})
        if [phase.kind.value for phase in plan.phases] != ["BRAKE_LINEAR", "ACQUIRE_LINEAR"]:
            raise ValueError("LINEAR_REVERSAL plan must be BRAKE_LINEAR then ACQUIRE_LINEAR")
        plan = replace(plan, phases=tuple(replace(phase,
            max_control_ticks=(QUIESCENCE_MAX_CHUNKS if phase.kind is ControlPhaseKind.BRAKE_LINEAR
                               else 1)) for phase in plan.phases))
        if not _history_is_sufficient(self.pre_braking_history):
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "pre-braking world Pose_V history is missing, stale, or sparse",
                failure_category="world_pose_feedback_unavailable",
                evidence={"pre_braking_history": self.pre_braking_history})
        previous_forward = _finite_float(
            self.pre_braking_history.get("world_end_forward_velocity"))
        if previous_forward is None:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "pre-braking world Pose_V velocity is missing or non-finite",
                failure_category="world_pose_feedback_unavailable",
                evidence={"pre_braking_history": self.pre_braking_history})
        previous_direction = 1. if float(
            gazebo_physics_twist(self.previous_action)["linear"]["x"]) > 0. else -1.
        if previous_forward * previous_direction <= BODY_STOPPED_EPSILON:
            return self._result(plan, ControlExecutionStatus.INCONCLUSIVE, start_sim,
                "pre-reversal world body motion was not established in the previous direction",
                failure_category="precondition_not_met",
                evidence={"previous_action": self.previous_action,
                          "pre_braking_world_forward_velocity": previous_forward,
                          "expected_previous_direction": previous_direction})

        controller = self.env.controller
        process = self.env.process
        if process is None or process.poll() is not None:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "Gazebo process is not alive before linear braking",
                failure_category="process_death")
        executed_commands = []
        try:
            controller.stop_agent()
        except Exception as error:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                str(error), failure_category="command_publish_failure")
        zero_command = dict(controller.last_published_command or {})
        executed_commands.append(zero_command)
        if (zero_command.get("linear", {}).get("x") != 0. or
                zero_command.get("angular", {}).get("z") != 0.):
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "neutral Twist was not published before the requested reversal action",
                failure_category="command_publish_failure",
                executed_commands=executed_commands)

        brake_start = float(self.env.stepper.time)
        chunks = []
        brake_completed = False
        terminal_outcome = None
        for index in range(QUIESCENCE_MAX_CHUNKS):
            if self.env.process is None or self.env.process.poll() is not None:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                    "Gazebo process died during linear braking", failure_category="process_death",
                    executed_commands=executed_commands,
                    evidence={"braking_chunks": chunks})
            chunk_start = float(self.env.stepper.time)
            pose_before = dict(self.env.pose)
            pose_cursor = self.env.transport.cursor(controller.pose_topic)
            odometry_cursor = self.env.transport.cursor(self.env.odometry_topic)
            try:
                self.env.stepper.step_simulation()
                self.env._refresh()
                chunk_end = float(self.env.stepper.time)
                raw = controller.pose_history_after(pose_cursor, chunk_start, chunk_end)
                history = summarize_world_pose_history(raw, chunk_start, chunk_end)
                contract = _history_contract(raw, history, chunk_start, chunk_end)
                step_evidence = dict(getattr(self.env.stepper, "last_verification", {}))
                iterations = step_evidence.get("iteration_delta")
                expected_iterations = step_evidence.get("expected_iteration_delta")
                iteration_pass = (iterations == QUIESCENCE_CHUNK_ITERATIONS and
                                  expected_iterations == QUIESCENCE_CHUNK_ITERATIONS)
                odometry = None
                odometry_error = None
                try:
                    odometry = self.env.read_odometry_after_sequence(
                        odometry_cursor, chunk_end - .02, chunk_end + .002, timeout=.5)
                except Exception as error:
                    # Supporting telemetry only; it cannot replace body feedback.
                    odometry_error = {"type": type(error).__name__, "message": str(error)}
                contacts = self.env.contacts.poll(chunk_end) if hasattr(self.env, "contacts") else []
            except Exception as error:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                    str(error), failure_category="physics_progression_or_telemetry",
                    executed_commands=executed_commands,
                    evidence={"braking_chunks": chunks})
            stopped = body_stopped_contract(history)
            row = {
                "index": index + 1,
                "phase": "BRAKE_LINEAR",
                "simulation_start": chunk_start,
                "simulation_end": chunk_end,
                "elapsed_simulation_time": chunk_end - chunk_start,
                "iterations": iterations,
                "expected_iterations": expected_iterations,
                "iterations_contract_pass": iteration_pass,
                "command": zero_command,
                "pose_before": pose_before,
                "pose_after": dict(self.env.pose),
                "displacement_during_chunk": math.hypot(
                    self.env.pose["x"] - pose_before["x"],
                    self.env.pose["y"] - pose_before["y"]),
                "world_pose_history": history,
                "world_pose_history_raw": raw,
                "world_pose_history_contract": contract,
                "body_stopped_contract": stopped,
                "odometry": odometry,
                "odometry_error": odometry_error,
                "collision_events": contacts,
                "step_evidence": step_evidence,
            }
            chunks.append(row)
            if not iteration_pass:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                    "fixed physics chunk did not advance the required iterations",
                    failure_category="step_progression_contract",
                    executed_commands=executed_commands,
                    evidence={"braking_chunks": chunks})
            if not contract["pass"]:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                    "world Pose_V braking feedback is missing, stale, sparse, unordered, or non-finite",
                    failure_category="world_pose_feedback_unavailable",
                    executed_commands=executed_commands,
                    evidence={"braking_chunks": chunks})
            if chunk_end - brake_start > QUIESCENCE_MAX_CHUNKS * self.dt + 1e-9:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                    "linear braking exceeded the configured simulation-time bound",
                    failure_category="step_duration_contract",
                    executed_commands=executed_commands,
                    evidence={"braking_chunks": chunks})
            if contacts:
                terminal_outcome = {"reason": "collision", "collision": True,
                    "terminated": True, "truncated": False,
                    "collision_events": contacts}
                break
            if on_braking_chunk is not None:
                try:
                    row["task_outcome"] = on_braking_chunk(row)
                except Exception as error:
                    return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                        str(error), failure_category=getattr(error, "category", "sensor_or_task_telemetry"),
                        executed_commands=executed_commands,
                        evidence={"braking_chunks": chunks})
            outcome = row.get("task_outcome") or {}
            if outcome.get("collision") or outcome.get("terminated") or outcome.get("truncated"):
                terminal_outcome = outcome or {
                    "reason": "collision", "collision": True,
                    "terminated": True, "truncated": False,
                    "collision_events": contacts,
                }
                break
            if stopped["pass"]:
                brake_completed = True
                break

        last_history = chunks[-1]["world_pose_history"] if chunks else {}
        brake_phase = {
            "phase": "BRAKE_LINEAR",
            "start_sim_time": brake_start,
            "end_sim_time": float(self.env.stepper.time),
            "elapsed_simulation_time": float(self.env.stepper.time) - brake_start,
            "command": zero_command,
            "start_body_forward_velocity": previous_forward,
            "end_body_forward_velocity": last_history.get("world_end_forward_velocity"),
            "end_body_angular_velocity": last_history.get("world_end_angular_velocity"),
            "completion_condition": "body_stopped_contract(world Pose_V, epsilon=0.02)",
            "completion_result": brake_completed,
            "chunks": chunks,
            "max_control_ticks": QUIESCENCE_MAX_CHUNKS,
            "chunk_iterations": QUIESCENCE_CHUNK_ITERATIONS,
            "maximum_simulation_duration": QUIESCENCE_MAX_CHUNKS * self.dt,
        }
        phase_evidence = [brake_phase]
        if terminal_outcome is not None:
            collision = bool(terminal_outcome.get("collision") or
                             "collision" in str(terminal_outcome.get("reason", "")))
            status = (ControlExecutionStatus.COLLISION if collision else
                      ControlExecutionStatus.TASK_TERMINAL)
            return self._result(plan, status, start_sim,
                str(terminal_outcome.get("reason") or "task_terminal_during_braking"),
                failure_category="collision" if collision else None,
                executed_commands=executed_commands,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase,
                          "task_terminal_during_braking": terminal_outcome},
                phase_evidence=[brake_phase])
        if not brake_completed:
            error = PhysicalControlFailure(
                "Linear braking did not reach the actual world-body stop contract within the bounded window",
                evidence={"transition_type": "LINEAR_REVERSAL", "phase": brake_phase})
            return self._result(plan, ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE, start_sim,
                error.reason, failure_category=error.failure_category,
                executed_commands=executed_commands, evidence={
                    "braking_chunks": chunks, "braking_phase": brake_phase,
                    "physical_control_failure": error.to_dict()},
                phase_evidence=[brake_phase])

        # Simulation time is paused while commands are published, so the
        # completion and acquisition publish events can share a sim timestamp.
        # Keep an explicit executor event order and retain the controller's
        # monotonic publish sequence at the completion boundary.
        brake_completion_event_sequence = 1
        brake_completion_publish_sequence = getattr(controller, "publish_sequence", None)
        acquisition_start = float(self.env.stepper.time)
        acquisition_pose_before = dict(self.env.pose)
        pose_cursor = self.env.transport.cursor(controller.pose_topic)
        publish_sequence_before = brake_completion_publish_sequence
        if (controller.last_command.get("linear", {}).get("x") != 0. or
                controller.last_command.get("angular", {}).get("z") != 0.):
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "controller command is not neutral after successful body braking",
                failure_category="braking_command_contract",
                executed_commands=executed_commands,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase})
        try:
            step_result = self.training_environment.step(self.requested_action)
        except PhysicalControlFailure as error:
            phase_evidence.append({"phase": "ACQUIRE_LINEAR",
                "start_sim_time": acquisition_start,
                "end_sim_time": float(self.env.stepper.time),
                "completion_result": False, "failure": error.to_dict()})
            if (publish_sequence_before is not None and
                    getattr(controller, "publish_sequence", publish_sequence_before) > publish_sequence_before):
                executed_commands.append(dict(controller.last_published_command or {}))
            return self._result(plan, ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE, start_sim,
                str(error), failure_category=error.failure_category,
                executed_commands=executed_commands,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase,
                          "validator_evidence": error.evidence,
                          "production_validator": error.evidence.get("validator_evidence")},
                phase_evidence=phase_evidence)
        except Exception as error:
            phase_evidence.append({"phase": "ACQUIRE_LINEAR",
                "start_sim_time": acquisition_start,
                "end_sim_time": float(self.env.stepper.time),
                "completion_result": False,
                "failure": {"type": type(error).__name__, "reason": str(error)}})
            if (publish_sequence_before is not None and
                    getattr(controller, "publish_sequence", publish_sequence_before) > publish_sequence_before):
                executed_commands.append(dict(controller.last_published_command or {}))
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                str(error), failure_category=getattr(error, "category", "service_or_sensor_failure"),
                executed_commands=executed_commands,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase},
                phase_evidence=phase_evidence)

        acquisition_end = float(self.env.stepper.time)
        if self.env.process is None or self.env.process.poll() is not None:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "Gazebo process died during linear acquisition", failure_category="process_death",
                executed_commands=executed_commands,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase,
                          "production_validator": self.env.telemetry.get("pose_validation")})
        transition = dict(self.env.telemetry.get("action_transition") or {})
        acquire_publish_sequence = _finite_int(transition.get("action_publish_sequence"))
        acquire_event_ordered = _acquisition_publish_ordered(
            brake_completion_publish_sequence, transition, expected,
            expected_action=self.requested_action)
        acquire_command_publish_event_sequence = (
            brake_completion_event_sequence + 1 if acquire_event_ordered else None)
        command_published = bool(
            brake_completed and acquire_event_ordered and
            acquire_command_publish_event_sequence > brake_completion_event_sequence)
        acquire_publish_sim_time = _finite_float(
            transition.get("action_command_sim_time"))
        simulation_time_equal_at_publish = bool(
            acquire_publish_sim_time is not None and
            math.isclose(acquire_publish_sim_time, brake_phase["end_sim_time"],
                         rel_tol=0., abs_tol=1e-12))
        raw = controller.pose_history_after(pose_cursor, acquisition_start, acquisition_end)
        history = summarize_world_pose_history(raw, acquisition_start, acquisition_end)
        contract = _history_contract(raw, history, acquisition_start, acquisition_end)
        validation = dict(self.env.telemetry.get("pose_validation") or {})
        requested_direction = 1 if float(expected["linear"]["x"]) > 0. else -1
        end_forward = _finite_float(history.get("world_end_forward_velocity"))
        end_angular = _finite_float(history.get("world_end_angular_velocity"))
        dx = float(self.env.pose["x"]) - acquisition_pose_before["x"]
        dy = float(self.env.pose["y"]) - acquisition_pose_before["y"]
        projected = dx * math.cos(acquisition_pose_before["yaw"]) + dy * math.sin(
            acquisition_pose_before["yaw"])
        direction_established = bool(end_forward is not None and
                                     end_forward * requested_direction > BODY_STOPPED_EPSILON)
        collision = ("collision" in step_result.reason or self.env.collision_event is not None or
                     bool((self.env.telemetry.get("contacts") or {}).get("new_contact_event")))
        training_telemetry = self.env.telemetry.get("gazebo_dqn_training") or {}
        sensor_validation = training_telemetry.get("sensor_after")
        contact_state = dict(self.env.telemetry.get("contacts") or {})
        contact_schema = getattr(getattr(self.env, "contacts", None), "schema", None)
        sensor_pass = _sensor_contract_pass(sensor_validation,
            getattr(self.training_environment, "max_sensor_age_ms", 20.))
        contact_pass = _contact_contract_pass(self.env, contact_state, contact_schema)
        acquisition_valid = bool(contract["pass"] and validation.get("valid") is True and
            direction_established and projected * requested_direction > 0. and
            end_angular is not None and abs(end_angular) <= BODY_STOPPED_EPSILON and
            sensor_pass and contact_pass and command_published and not collision)
        acquisition = {
            "phase": "ACQUIRE_LINEAR",
            "start_sim_time": acquisition_start,
            "end_sim_time": acquisition_end,
            "elapsed_simulation_time": acquisition_end - acquisition_start,
            "command": dict(request.requested_command),
            "pose_before": acquisition_pose_before,
            "pose_after": dict(self.env.pose),
            "world_forward_displacement": projected,
            "world_pose_history": history,
            "world_pose_history_raw": raw,
            "world_pose_history_contract": contract,
            "end_body_forward_velocity": end_forward,
            "end_body_angular_velocity": end_angular,
            "requested_direction_established": direction_established,
            "production_pose_validation": validation,
            "wheel_odometry_corroboration": transition.get("odometry_history"),
            "command_published_after_braking": command_published,
            "brake_completion_event_sequence": brake_completion_event_sequence,
            "acquire_command_publish_event_sequence": acquire_command_publish_event_sequence,
            "brake_completion_publish_sequence": brake_completion_publish_sequence,
            "acquire_command_publish_sequence": acquire_publish_sequence,
            "brake_end_sim_time": brake_phase["end_sim_time"],
            "acquire_publish_sim_time": acquire_publish_sim_time,
            "simulation_time_equal_at_publish": simulation_time_equal_at_publish,
            "ordering_proof_source": "executor_control_flow_and_action_transition_publish_sequence",
            "sensor_validation": sensor_validation,
            "sensor_contract_pass": sensor_pass,
            "contact_schema": contact_schema,
            "contact_state": contact_state,
            "contact_contract_pass": contact_pass,
            "collision": collision,
            "completion_result": acquisition_valid,
        }
        phase_evidence.append(acquisition)
        executed_commands.append(dict(request.requested_command))
        if not contract["pass"]:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "world Pose_V acquisition feedback is missing, stale, sparse, or non-finite",
                failure_category="world_pose_feedback_unavailable",
                executed_commands=executed_commands,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase,
                          "acquisition_phase": acquisition,
                          "validator_evidence": validation},
                step_result=step_result, phase_evidence=phase_evidence)
        if not sensor_pass or not contact_pass or not command_published:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE, start_sim,
                "acquisition did not preserve command, fresh sensor, or Contact schema contract",
                failure_category="sensor_contact_or_command_contract",
                executed_commands=executed_commands,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase,
                          "acquisition_phase": acquisition,
                          "validator_evidence": validation},
                step_result=step_result, phase_evidence=phase_evidence)
        if collision:
            status, category, reason = (ControlExecutionStatus.COLLISION, "collision",
                "contact/collision occurred during linear acquisition")
        elif acquisition_valid:
            status, category, reason = ControlExecutionStatus.EXECUTED, None, None
        else:
            status, category, reason = (ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                "linear_acquisition_failed",
                f"requested {self.requested_action.upper()} motion did not satisfy world-body feedback and production validation")
        evidence = {"agent_intent": self.requested_action,
            "previous_action": self.previous_action,
            "requested_action": self.requested_action,
            "previous_command": dict(request.previous_command),
            "requested_command": dict(request.requested_command),
            "transition_type": "LINEAR_REVERSAL", "plan": plan.to_dict(),
            "pre_braking_world_body_history": self.pre_braking_history,
            "braking_chunks": chunks, "braking_phase": brake_phase,
            "acquisition_phase": acquisition,
            "body_stopped_epsilon": BODY_STOPPED_EPSILON,
            "odometry_is_supporting_evidence_only": True,
            "validator_evidence": validation}
        return self._result(plan, status, start_sim, reason, failure_category=category,
            executed_commands=executed_commands, evidence=evidence, step_result=step_result,
            phase_evidence=phase_evidence)

    def _result(self, plan, status, start_sim, reason, *, failure_category=None,
                executed_commands=(), evidence=None, step_result=None, phase_evidence=()):
        return ControlExecutionResult(
            agent_intent=plan.request.agent_intent,
            status=status,
            requested_command=plan.request.requested_command,
            transition_type=plan.request.transition_type,
            executed_commands=tuple(executed_commands),
            phases=plan.phases,
            elapsed_simulation_time=float(self.env.stepper.time) - start_sim,
            failure_category=failure_category,
            reason=reason,
            validator_evidence=(evidence or {}).get("validator_evidence"),
            execution_evidence={**(evidence or {}), "phase_evidence": list(phase_evidence)},
            step_result=step_result)


class GazeboDownToLeftControlExecutor:
    """Feedback executor for the exact DOWN→LEFT L2R pair.

    It brakes using shared world-Pose_V feedback, then delegates angular
    acquisition to the existing production environment step and unchanged
    physical validator. The training adapter activates it only for this exact
    verified pair; the host diagnostic may also invoke it directly.
    """

    def __init__(self, training_environment, *, pre_braking_history: dict,
                 previous_action="down", requested_action="left"):
        self.training_environment = training_environment
        self.env = training_environment.env
        self.pre_braking_history = pre_braking_history
        self.previous_action = str(previous_action)
        self.requested_action = str(requested_action)
        self.dt = float(self.env.stepper.dt)

    def plan(self, request: ControlExecutionRequest) -> ControlExecutionPlan:
        return plan_control_execution(request)

    def execute_plan(self, plan: ControlExecutionPlan, *, on_braking_chunk=None):
        request = plan.request
        start_sim = float(self.env.stepper.time)
        expected = gazebo_physics_twist(self.requested_action)
        actual_transition = classify_physics_command_transition(
            request.previous_command, request.requested_command)
        if (request.agent_intent != self.requested_action or request.transition_type != "LINEAR_TO_ROTATION" or
                actual_transition != "LINEAR_TO_ROTATION" or
                request.previous_command != gazebo_physics_twist(self.previous_action) or
                request.requested_command != expected or
                [phase.kind.value for phase in plan.phases] !=
                ["BRAKE_LINEAR", "ACQUIRE_ANGULAR"]):
            return self._result(plan, ControlExecutionStatus.INCONCLUSIVE, start_sim,
                f"request does not match exact {self.previous_action.upper()}→{self.requested_action.upper()} LINEAR_TO_ROTATION",
                failure_category="request_not_supported",
                evidence={"classified_transition": actual_transition,
                    "expected_previous_command": gazebo_physics_twist(self.previous_action),
                    "expected_requested_command": expected})
        plan = replace(plan, phases=tuple(replace(phase,
            max_control_ticks=(QUIESCENCE_MAX_CHUNKS if
                phase.kind is ControlPhaseKind.BRAKE_LINEAR else 1))
            for phase in plan.phases))
        if not _history_is_sufficient(self.pre_braking_history):
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, "pre-braking world Pose_V history is missing, stale, or sparse",
                failure_category="world_pose_feedback_unavailable",
                evidence={"pre_braking_history": self.pre_braking_history})
        initial_forward = _finite_float(
            self.pre_braking_history.get("world_end_forward_velocity"))
        initial_samples = self.pre_braking_history.get("world_forward_velocity_samples", [])
        requested_source_sign = 1. if self.previous_action == "up" else -1.
        source_motion_established = bool(initial_forward is not None and
            initial_forward * requested_source_sign > BODY_STOPPED_EPSILON and any(
                _finite_float(row.get("forward_velocity")) is not None and
                float(row["forward_velocity"]) * requested_source_sign > BODY_STOPPED_EPSILON
                for row in initial_samples if isinstance(row, dict)))
        if not source_motion_established:
            return self._result(plan, ControlExecutionStatus.INCONCLUSIVE, start_sim,
                f"pre-transition world body {self.previous_action} motion was not established",
                failure_category="precondition_not_met",
                evidence={"pre_braking_history": self.pre_braking_history,
                    "initial_source_body_motion_established": False})

        controller = self.env.controller
        if self.env.process is None or self.env.process.poll() is not None:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, "Gazebo process is not alive before linear braking",
                failure_category="process_death")
        executed = []
        phases = []
        chunks = []
        try:
            controller.stop_agent()
        except Exception as error:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, str(error), failure_category="command_publish_failure")
        neutral = dict(controller.last_published_command or {})
        executed.append(neutral)
        if neutral != {"linear": {"x": 0.0}, "angular": {"z": 0.0}}:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, f"neutral Twist was not published before {self.requested_action.upper()}",
                failure_category="command_publish_failure", executed_commands=executed)

        brake_start = float(self.env.stepper.time)
        stopped = False
        terminal = None
        brake_sensor_sequence = None
        for index in range(QUIESCENCE_MAX_CHUNKS):
            if self.env.process is None or self.env.process.poll() is not None:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, "Gazebo process died during linear braking",
                    failure_category="process_death", executed_commands=executed,
                    evidence={"braking_chunks": chunks})
            chunk_start = float(self.env.stepper.time)
            pose_before = dict(self.env.pose)
            pose_cursor = self.env.transport.cursor(controller.pose_topic)
            odometry_cursor = self.env.transport.cursor(self.env.odometry_topic)
            try:
                self.env.stepper.step_simulation()
                self.env._refresh()
                chunk_end = float(self.env.stepper.time)
                raw = controller.pose_history_after(pose_cursor, chunk_start, chunk_end)
                history = summarize_world_pose_history(raw, chunk_start, chunk_end)
                contract = _history_contract(raw, history, chunk_start, chunk_end)
                step_evidence = dict(getattr(self.env.stepper, "last_verification", {}))
                iterations = step_evidence.get("iteration_delta")
                expected_iterations = step_evidence.get("expected_iteration_delta")
                iteration_pass = (iterations == QUIESCENCE_CHUNK_ITERATIONS and
                                  expected_iterations == QUIESCENCE_CHUNK_ITERATIONS)
                contacts = self.env.contacts.poll(chunk_end)
                odometry = None
                odometry_error = None
                try:
                    odometry = self.env.read_odometry_after_sequence(
                        odometry_cursor, chunk_end - .02, chunk_end + .002, timeout=.5)
                except Exception as error:
                    odometry_error = {"type": type(error).__name__, "message": str(error)}
            except Exception as error:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, str(error), failure_category="physics_progression_or_telemetry",
                    executed_commands=executed, evidence={"braking_chunks": chunks})
            stop_contract = body_stopped_contract(history)
            row = {"index": index + 1, "phase": "BRAKE_LINEAR",
                "simulation_start": chunk_start, "simulation_end": chunk_end,
                "elapsed_simulation_time": chunk_end - chunk_start,
                "iterations": iterations, "expected_iterations": expected_iterations,
                "iterations_contract_pass": iteration_pass, "command": neutral,
                "pose_before": pose_before, "pose_after": dict(self.env.pose),
                "world_pose_history": history, "world_pose_history_raw": raw,
                "world_pose_history_contract": contract,
                "body_stopped_contract": stop_contract,
                "odometry_corroboration": odometry, "odometry_error": odometry_error,
                "collision_events": contacts, "step_evidence": step_evidence}
            chunks.append(row)
            if not iteration_pass or chunk_end - chunk_start <= 0.:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, "fixed physics braking chunk progression contract failed",
                    failure_category="step_progression_contract",
                    executed_commands=executed, evidence={"braking_chunks": chunks})
            if not contract["pass"]:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, "braking Pose_V history is stale, sparse, unordered, or non-finite",
                    failure_category="world_pose_feedback_unavailable",
                    executed_commands=executed, evidence={"braking_chunks": chunks})
            if chunk_end - brake_start > QUIESCENCE_MAX_CHUNKS * self.dt + 1e-9:
                return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                    start_sim, "linear braking exceeded its bounded simulation-time window",
                    failure_category="step_duration_contract",
                    executed_commands=executed, evidence={"braking_chunks": chunks})
            if contacts:
                terminal = {"reason": "collision", "collision": True,
                    "collision_events": contacts, "terminated": True, "truncated": False}
                break
            if on_braking_chunk is not None:
                try:
                    row["task_outcome"] = on_braking_chunk(row)
                    sensor_evidence = (row.get("task_outcome") or {}).get("sensor_contract") or {}
                    if isinstance(sensor_evidence.get("sequence"), int):
                        brake_sensor_sequence = sensor_evidence["sequence"]
                except Exception as error:
                    return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                        start_sim, str(error),
                        failure_category=getattr(error, "category", "sensor_or_contact_failure"),
                        executed_commands=executed, evidence={"braking_chunks": chunks})
            outcome = row.get("task_outcome") or {}
            if outcome.get("collision") or outcome.get("terminated") or outcome.get("truncated"):
                terminal = outcome
                break
            if stop_contract["pass"]:
                stopped = True
                break

        brake_end = float(self.env.stepper.time)
        last_history = chunks[-1]["world_pose_history"] if chunks else {}
        brake_phase = {"phase": "BRAKE_LINEAR", "start_sim_time": brake_start,
            "end_sim_time": brake_end, "elapsed_simulation_time": brake_end - brake_start,
            "command": neutral, "start_body_forward_velocity": initial_forward,
            "end_body_forward_velocity": last_history.get("world_end_forward_velocity"),
            "end_body_angular_velocity": last_history.get("world_end_angular_velocity"),
            "completion_condition": "body_stopped_contract(world Pose_V, epsilon=0.02)",
            "completion_result": stopped, "chunks": chunks,
            "max_control_ticks": QUIESCENCE_MAX_CHUNKS,
            "chunk_iterations": QUIESCENCE_CHUNK_ITERATIONS,
            "maximum_simulation_duration": QUIESCENCE_MAX_CHUNKS * self.dt}
        phases.append(brake_phase)
        if terminal is not None:
            status = (ControlExecutionStatus.COLLISION if terminal.get("collision") else
                      ControlExecutionStatus.TASK_TERMINAL)
            return self._result(plan, status, start_sim,
                str(terminal.get("reason") or "terminal_during_braking"),
                failure_category="collision" if status is ControlExecutionStatus.COLLISION else None,
                executed_commands=executed,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase,
                    "task_terminal_during_braking": terminal}, phase_evidence=phases)
        if not stopped:
            return self._result(plan, ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE,
                start_sim, "Linear braking did not reach the world-body stopped contract within 20 chunks",
                failure_category="physical_control_failure", executed_commands=executed,
                evidence={"braking_chunks": chunks, "braking_phase": brake_phase,
                    "source_action": self.previous_action,
                    "requested_action": self.requested_action,
                    "initial_source_body_motion_established": source_motion_established},
                phase_evidence=phases)

        brake_publish_sequence = getattr(controller, "publish_sequence", None)
        acquire_start = float(self.env.stepper.time)
        pose_before = dict(self.env.pose)
        pose_cursor = self.env.transport.cursor(controller.pose_topic)
        try:
            result = self.training_environment.step(self.requested_action)
        except PhysicalControlFailure as error:
            failure = error.to_dict()
            phases.append({"phase": "ACQUIRE_ANGULAR", "start_sim_time": acquire_start,
                "end_sim_time": float(self.env.stepper.time), "completion_result": False,
                "production_validator_evidence": error.evidence,
                "failure": failure})
            collision = bool((error.evidence or {}).get("collision") or
                (error.evidence or {}).get("collision_event"))
            failure_status = (ControlExecutionStatus.COLLISION if collision else
                              ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE)
            return self._result(plan, failure_status,
                start_sim, str(error),
                failure_category="collision" if collision else "physical_control_failure",
                executed_commands=executed, evidence={"braking_chunks": chunks,
                    "braking_phase": brake_phase, "validator_evidence": error.evidence,
                    "collision": collision},
                phase_evidence=phases)
        except Exception as error:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, str(error), failure_category=getattr(error, "category", "step_failure"),
                executed_commands=executed, evidence={"braking_chunks": chunks,
                    "braking_phase": brake_phase}, phase_evidence=phases)

        acquire_end = float(self.env.stepper.time)
        if self.env.process is None or self.env.process.poll() is not None:
            return self._result(plan, ControlExecutionStatus.INFRASTRUCTURE_FAILURE,
                start_sim, "Gazebo process died during angular acquisition",
                failure_category="process_death", executed_commands=executed,
                evidence={"braking_phase": brake_phase})
        transition = dict(self.env.telemetry.get("action_transition") or {})
        publish_ordered = _acquisition_publish_ordered(
            brake_publish_sequence, transition, expected, expected_action=self.requested_action)
        raw = controller.pose_history_after(pose_cursor, acquire_start, acquire_end)
        history = summarize_world_pose_history(raw, acquire_start, acquire_end)
        history_contract = _history_contract(raw, history, acquire_start, acquire_end)
        validation = dict(self.env.telemetry.get("pose_validation") or {})
        angular_samples = history.get("world_angular_velocity_samples", [])
        requested_angular = float(expected["angular"]["z"])
        directed = [(i, _finite_float(row.get("angular_velocity")))
                    for i, row in enumerate(angular_samples)]
        established_index = next((i for i, value in directed
            if value is not None and value * requested_angular > BODY_STOPPED_EPSILON), None)
        no_opposite_after_established = bool(established_index is not None and all(
            value is not None and value * requested_angular >= -BODY_STOPPED_EPSILON
            for i, value in directed if i >= established_index))
        first_requested = (None if established_index is None else
                           angular_samples[established_index])
        end_angular = _finite_float(history.get("world_end_angular_velocity"))
        end_forward = _finite_float(history.get("world_end_forward_velocity"))
        dx = float(self.env.pose["x"]) - pose_before["x"]
        dy = float(self.env.pose["y"]) - pose_before["y"]
        forward_displacement = dx * math.cos(pose_before["yaw"]) + dy * math.sin(pose_before["yaw"])
        yaw_delta = math.atan2(math.sin(float(self.env.pose["yaw"]) - pose_before["yaw"]),
                               math.cos(float(self.env.pose["yaw"]) - pose_before["yaw"]))
        training = self.env.telemetry.get("gazebo_dqn_training") or {}
        sensor = training.get("sensor_after")
        sensor_pass = _sensor_contract_pass(sensor,
            getattr(self.training_environment, "max_sensor_age_ms", 20.)) and (
                brake_sensor_sequence is None or
                isinstance(sensor, dict) and isinstance(sensor.get("sequence"), int) and
                sensor["sequence"] > brake_sensor_sequence)
        contact_state = dict(self.env.telemetry.get("contacts") or {})
        contact_schema = getattr(getattr(self.env, "contacts", None), "schema", None)
        contact_pass = _contact_contract_pass(self.env, contact_state, contact_schema)
        collision = bool("collision" in result.reason or self.env.collision_event is not None or
            contact_state.get("new_contact_event"))
        odometry = transition.get("odometry_history")
        acquire_valid = bool(history_contract["pass"] and validation.get("valid") is True and
            publish_ordered and established_index is not None and
            no_opposite_after_established and end_angular is not None and
            end_angular * requested_angular > BODY_STOPPED_EPSILON and
            end_forward is not None and sensor_pass and contact_pass and not collision)
        acquire = {"phase": "ACQUIRE_ANGULAR", "start_sim_time": acquire_start,
            "end_sim_time": acquire_end, "elapsed_simulation_time": acquire_end-acquire_start,
            "command": expected, "pose_before": pose_before,
            "pose_after": dict(self.env.pose), "world_pose_history": history,
            "world_pose_history_raw": raw, "world_pose_history_contract": history_contract,
            "start_body_forward_velocity": history.get("world_start_forward_velocity"),
            "end_body_forward_velocity": end_forward, "end_body_angular_velocity": end_angular,
            "first_requested_direction_angular_velocity": (None if first_requested is None
                else first_requested.get("angular_velocity")),
            "requested_angular_direction_established": established_index is not None,
            "no_opposite_angular_response_after_established": no_opposite_after_established,
            "world_forward_displacement": forward_displacement, "yaw_delta": yaw_delta,
            "production_pose_validation": validation, "wheel_odometry_corroboration": odometry,
            "command_published_after_braking": publish_ordered,
            "brake_completion_event_sequence": 1,
            "acquire_command_publish_event_sequence": 2 if publish_ordered else None,
            "ordering_proof_source": "executor_control_flow_and_action_transition_publish_sequence",
            "brake_completion_publish_sequence": brake_publish_sequence,
            "acquire_command_publish_sequence": transition.get("action_publish_sequence"),
            "sensor_contract_pass": sensor_pass, "sensor_evidence": sensor,
            "contact_contract_pass": contact_pass, "contact_state": contact_state,
            "contact_schema": contact_schema, "collision": collision,
            "completion_result": acquire_valid}
        phases.append(acquire)
        executed.append(dict(expected))
        if collision:
            status = ControlExecutionStatus.COLLISION
            reason = "collision during angular acquisition"
        elif not history_contract["pass"] or not sensor_pass or not contact_pass or not publish_ordered:
            status = ControlExecutionStatus.INFRASTRUCTURE_FAILURE
            reason = "angular acquisition sensor, Contact, command, or world Pose_V contract failed"
        elif not acquire_valid:
            status = ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
            reason = f"{self.requested_action.upper()} acquisition did not establish validated world-body angular motion"
        elif result.terminated or result.truncated:
            status = ControlExecutionStatus.TASK_TERMINAL
            reason = result.reason
        else:
            status = ControlExecutionStatus.EXECUTED
            reason = result.reason
        return self._result(plan, status, start_sim, reason,
            failure_category=(None if status in (ControlExecutionStatus.EXECUTED,
                ControlExecutionStatus.COLLISION, ControlExecutionStatus.TASK_TERMINAL)
                else "physical_control_failure" if status is ControlExecutionStatus.PHYSICAL_CONTROL_FAILURE
                else "sensor_or_world_feedback"),
            executed_commands=executed, step_result=result,
            evidence={"initial_source_body_motion_established": source_motion_established,
                "initial_backward_body_motion_established": (
                    source_motion_established if self.previous_action == "down" else None),
                "source_action": self.previous_action, "requested_action": self.requested_action,
                "initial_body_forward_velocity": initial_forward,
                "braking_chunks": chunks, "braking_phase": brake_phase,
                "acquisition_phase": acquire, "production_validator": validation,
                "sensor_contract_pass": sensor_pass, "contact_contract_pass": contact_pass,
                "collision": collision}, phase_evidence=phases)

    def _result(self, plan, status, start_sim, reason, *, failure_category=None,
                executed_commands=(), evidence=None, step_result=None, phase_evidence=()):
        return ControlExecutionResult(agent_intent=plan.request.agent_intent,
            status=status, requested_command=plan.request.requested_command,
            transition_type=plan.request.transition_type,
            executed_commands=tuple(executed_commands), phases=plan.phases,
            elapsed_simulation_time=float(self.env.stepper.time)-start_sim,
            failure_category=failure_category, reason=reason,
            validator_evidence=(evidence or {}).get("production_validator"),
            execution_evidence={**(evidence or {}), "phase_evidence": list(phase_evidence)},
            step_result=step_result)


class GazeboUpToRightControlExecutor(GazeboDownToLeftControlExecutor):
    """Feedback executor for the exact actual-verified UP→RIGHT L2R pair."""

    def __init__(self, training_environment, *, pre_braking_history: dict):
        super().__init__(training_environment, pre_braking_history=pre_braking_history,
            previous_action="up", requested_action="right")

def _finite_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _finite_int(value):
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if not isinstance(value, bool) and value == result else None


def _acquisition_publish_ordered(brake_publish_sequence, transition, expected_command,
                                 *, expected_action="up"):
    acquire_publish_sequence = _finite_int(
        transition.get("action_publish_sequence") if isinstance(transition, dict) else None)
    baseline = _finite_int(brake_publish_sequence)
    return bool(
        isinstance(transition, dict) and transition.get("action") == expected_action and
        transition.get("commanded_twist") == expected_command and
        acquire_publish_sequence is not None and baseline is not None and
        acquire_publish_sequence > baseline)


def _history_is_sufficient(summary):
    return bool(summary and summary.get("world_pose_history_available") and
                summary.get("world_pose_history_fresh") and
                summary.get("world_pose_history_dense_enough"))


def _history_contract(raw_samples, summary, start, end):
    timestamps = [_finite_float(sample.get("simulation_timestamp")) for sample in raw_samples]
    ordered = bool(timestamps and all(value is not None for value in timestamps) and
                   all(b >= a for a, b in zip(timestamps, timestamps[1:])))
    unique_times = list(dict.fromkeys(timestamps)) if ordered else []
    covered = bool(ordered and len(unique_times) >= 3 and
                   unique_times[0] >= start - .002 and unique_times[0] <= start + .01 and
                   unique_times[-1] >= end - .01 and unique_times[-1] <= end + .002)
    values_finite = bool(raw_samples and all(
        _finite_float(sample.get(key)) is not None
        for sample in raw_samples for key in ("world_x", "world_y", "world_yaw")))
    return {
        "available": bool(summary.get("world_pose_history_available")),
        "fresh": bool(summary.get("world_pose_history_fresh")),
        "dense": bool(summary.get("world_pose_history_dense_enough")),
        "sample_count": len(raw_samples),
        "first_timestamp": unique_times[0] if unique_times else None,
        "last_timestamp": unique_times[-1] if unique_times else None,
        "timestamps_ordered_finite": ordered,
        "interval_covered": covered,
        "pose_values_finite": values_finite,
        "pass": bool(_history_is_sufficient(summary) and ordered and covered and values_finite),
    }


def _sensor_contract_pass(sensor, max_age_ms):
    if not isinstance(sensor, dict):
        return False
    try:
        age = float(sensor["age_ms"])
        sequence = int(sensor["sequence"])
        dimension = int(sensor["dimension"])
    except (KeyError, TypeError, ValueError):
        return False
    return bool(sensor.get("source") == "gazebo_lidar" and sequence >= 0 and
                math.isfinite(age) and -2. <= age <= float(max_age_ms) and dimension == 22)


def _contact_contract_pass(env, state, schema):
    if not isinstance(state, dict) or not isinstance(schema, dict):
        return False
    schema_type = schema.get("message_type")
    return bool(getattr(env, "contact_topic", None) and
                state.get("topic") == env.contact_topic and
                state.get("semantics") == "event_only" and
                schema_type == "gz.msgs.Contacts" and
                isinstance(state.get("assessment"), str))
