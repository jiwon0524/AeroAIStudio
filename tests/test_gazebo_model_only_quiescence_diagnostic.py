import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import json


TOOL = Path(__file__).parents[1] / "tools" / "diagnose_v07_gazebo_model_only_quiescence.py"
SPEC = importlib.util.spec_from_file_location("model_only_quiescence_diagnostic", TOOL)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def summary(*, fresh=True, dense=True, forward=(0.0, 0.0), angular=(0.0, 0.0), available=True):
    return {
        "world_pose_history_available": available,
        "world_pose_history_fresh": fresh,
        "world_pose_history_dense_enough": dense,
        "world_pose_history_max_gap": .01,
        "world_forward_velocity_samples": [
            {"forward_velocity": value} for value in forward],
        "world_angular_velocity_samples": [
            {"angular_velocity": value} for value in angular],
        "world_end_forward_velocity": forward[-1] if forward else None,
        "world_end_angular_velocity": angular[-1] if angular else None,
    }


@pytest.mark.parametrize("data", [
    summary(fresh=False), summary(dense=False), summary(available=False),
    summary(forward=()), summary(angular=()),
])
def test_quiescence_requires_available_fresh_dense_body_pose_history_and_velocity_samples(data):
    assert diagnostic.body_stopped_contract(data)["pass"] is False


def test_world_body_velocity_is_primary_and_odometry_cannot_substitute_for_it():
    contract = diagnostic.body_stopped_contract(summary(forward=(.5, .5)))
    assert contract["world_body_is_authority"] is True
    assert contract["odometry_is_supporting_evidence_only"] is True
    assert contract["pass"] is False


def test_body_velocity_must_be_stopped_through_the_observed_chunk():
    assert not diagnostic.body_stopped_contract(summary(forward=(.5, .01))) ["pass"]
    assert not diagnostic.body_stopped_contract(summary(angular=(0., .03))) ["pass"]
    assert diagnostic.body_stopped_contract(summary(forward=(.019, -.018), angular=(0., .019)))["pass"]


def test_quiescence_verdict_blocks_model_only_when_bounded_settle_does_not_stop_body():
    evidence = {"precondition_motion": {"confirmed": True},
        "pre_reset_quiescence": {"pass": False},
        "model_only": {"rpc_accepted": True, "stats_contract": {"pass": True}},
        "post_reset": {"contact_contract_pass": True, "body_contract_pass": True,
                       "odometry_contract_pass": True, "sensor_fresh": True,
                       "process_alive": True}}
    assert diagnostic.diagnostic_verdict(evidence) == "PRE_RESET_QUIESCENCE_FAILED"


@pytest.mark.parametrize("condition, expected", [
    ("reset", "MODEL_ONLY_RESET_FAILED"),
    ("contact", "CONTACT_FAILED"),
    ("body", "MODEL_ONLY_POST_RESET_BODY_FAILED"),
    ("odometry", "MODEL_ONLY_POST_RESET_CONTRACT_FAILED"),
    ("sensor", "MODEL_ONLY_POST_RESET_CONTRACT_FAILED"),
    ("process", "MODEL_ONLY_POST_RESET_CONTRACT_FAILED"),
])
def test_final_verdict_requires_each_reset_subsystem(condition, expected):
    evidence = {"precondition_motion": {"confirmed": True},
        "pre_reset_quiescence": {"pass": True},
        "model_only": {"rpc_accepted": True, "stats_contract": {"pass": True}},
        "post_reset": {"contact_contract_pass": True, "body_contract_pass": True,
                       "odometry_contract_pass": True, "sensor_fresh": True,
                       "process_alive": True}}
    if condition == "reset": evidence["model_only"]["rpc_accepted"] = False
    else:
        key = {"contact": "contact_contract_pass", "body": "body_contract_pass",
               "odometry": "odometry_contract_pass", "sensor": "sensor_fresh",
               "process": "process_alive"}[condition]
        evidence["post_reset"][key] = False
    assert diagnostic.diagnostic_verdict(evidence) == expected


def test_success_verdict_requires_motion_quiescence_model_stats_and_all_post_contracts():
    evidence = {"precondition_motion": {"confirmed": True},
        "pre_reset_quiescence": {"pass": True},
        "model_only": {"rpc_accepted": True, "stats_contract": {"pass": True}},
        "post_reset": {"contact_contract_pass": True, "body_contract_pass": True,
                       "odometry_contract_pass": True, "sensor_fresh": True,
                       "process_alive": True}}
    assert diagnostic.diagnostic_verdict(evidence) == "SAFE_MODEL_ONLY_WITH_PRE_RESET_QUIESCENCE"


def test_unconfirmed_actual_motion_is_inconclusive():
    assert diagnostic.diagnostic_verdict({"precondition_motion": {"confirmed": False}}) == "INCONCLUSIVE"


def test_settle_budget_is_bounded_and_uses_physics_chunks_not_wall_clock_sleep():
    assert diagnostic.MAX_QUIESCENCE_CHUNKS == 20
    assert diagnostic.SETTLE_CHUNK_ITERATIONS == 100
    assert diagnostic.MAX_QUIESCENCE_CHUNKS * diagnostic.SETTLE_CHUNK_SECONDS == pytest.approx(2.)
    source = TOOL.read_text()
    assert '"wall_clock_sleep_used_for_settling": False' in source
    assert "env.stepper.step_simulation()" in source
    with pytest.raises(ValueError, match="max_chunks"):
        diagnostic.run_diagnostic(Path("unused"), max_chunks=diagnostic.MAX_QUIESCENCE_CHUNKS + 1)


class QuiescenceFixture:
    def __init__(self, *, stopped_on_chunk=2):
        self.events = []
        self.chunk = 0
        self.stopped_on_chunk = stopped_on_chunk
        self.timeout = 1.0
        self.odometry_topic = "/model/simple_agent/odometry"
        self.stepper = type("Stepper", (), {"time": 1.0})()
        self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.0}
        self.controller = type("Controller", (), {})()
        self.controller.pose_topic = "/world/test/pose/info"
        self.controller.publish_sequence = 0
        self.controller.last_published_command = None
        def stop():
            self.events.append("zero_twist")
            self.controller.publish_sequence += 1
            self.controller.last_published_command = {
                "linear": {"x": 0.0}, "angular": {"z": 0.0}}
        self.controller.stop_agent = stop
        self.controller.get_pose = lambda *_: dict(self.pose)
        self.transport = type("Transport", (), {})()
        self.transport.cursor = lambda topic: 100 if "pose" in topic else 50
        self.controller.pose_history_after = self.pose_history_after
        def step():
            self.events.append("physics_step")
            self.chunk += 1
            self.stepper.time += .1
            if self.chunk == 1:
                self.pose["x"] += .02
        self.stepper.step_simulation = step
        self._refresh = lambda: None

    def pose_history_after(self, _cursor, start, end):
        moving = self.chunk < self.stopped_on_chunk
        speed = .2 if moving else 0.
        # Timestamped real-pose-shaped fixture. Motion occurs in the first
        # chunk; later stationary chunks provide the stop proof.
        x0 = 1.5 + .02 * max(0, self.chunk - 1)
        return [
            {"simulation_timestamp": start, "world_x": x0,
             "world_y": 1.5, "world_yaw": 0.0},
            {"simulation_timestamp": start + .05, "world_x": x0 + speed * .05,
             "world_y": 1.5, "world_yaw": 0.0},
            {"simulation_timestamp": end, "world_x": x0 + speed * .1,
             "world_y": 1.5, "world_yaw": 0.0},
        ]

    def read_odometry_after_sequence(self, sequence, min_time, max_time, timeout=.5):
        self.events.append("odometry_read")
        return {"timestamp": max_time - .01, "receive_sequence": sequence + 2,
                "linear_x": 0.0, "angular_z": 0.0}


def test_zero_twist_precedes_bounded_physics_quiescence_and_displacement_is_not_failure():
    env = QuiescenceFixture(stopped_on_chunk=2)
    result = diagnostic._quiesce(env, max_chunks=3)
    assert env.events[0] == "zero_twist"
    assert env.events.count("physics_step") == 2
    assert result["total_iterations"] == 200
    assert result["simulation_time_spent"] == pytest.approx(.2)
    assert result["pass"] is True
    assert result["displacement_during_quiescence"]["translation"] > 0.
    assert result["wall_clock_sleep_used_for_settling"] is False


def test_quiescence_has_hard_iteration_bound_and_does_not_trust_stopped_odometry():
    env = QuiescenceFixture(stopped_on_chunk=99)
    result = diagnostic._quiesce(env, max_chunks=2)
    assert result["pass"] is False
    assert result["world_body_stopped"] is False
    assert result["total_iterations"] == 200
    assert env.events.count("physics_step") == 2
    assert all(chunk["odometry_contract"]["pass"] for chunk in result["settle_chunks"])


def test_model_only_clock_contract_is_reused_without_all_reset_zero_clock_semantics():
    import sys
    sys.path.insert(0, str(TOOL.parent))
    import diagnose_v07_gazebo_reset_strategies as reset_diagnostic
    before = {"sim_time": {"sec": 4}, "iterations": 400, "paused": True}
    after = {"sim_time": {"sec": 4}, "iterations": 400, "paused": True}
    contract = reset_diagnostic.strategy_stats_contract("model_only", before, after, 3, 4)
    assert contract["pass"] is True
    assert contract["clock_semantics"] == "preserve_simulation_time_epoch"


def test_contact_event_silence_does_not_define_publisher_health_and_epoch_is_reset_after_mode():
    source = TOOL.read_text()
    assert "event_silence_is_not_publisher_health" in source
    assert "env.contacts.reset(reset_time)" in source
    assert "contact_sequence_epoch = env.transport.cursor(env.contact_topic)" in source
    assert '"after_100_iterations"' in source and '"after_settle"' in source


def test_production_reset_and_physics_validator_files_are_not_modified_by_this_diagnostic_scope():
    # This CLI calls the existing environment and provider contracts; it contains no
    # production reset implementation or modified thresholds.
    source = TOOL.read_text()
    assert "reset_mode_payload(\"model_only\"" in source
    assert "POSITION_TOLERANCE = 0.02" in source
    assert "YAW_TOLERANCE = 0.02" in source
    assert diagnostic.BODY_STOPPED_EPSILON == 0.02
    assert "reset_world()" not in source


def test_report_writer_uses_path_for_storage_and_string_for_json_and_creates_parent(tmp_path, monkeypatch):
    from aero_ai_studio.core import storage
    output = tmp_path / "missing" / "nested" / "diagnostic"
    observed = []
    real_write = storage.write_json

    def checked_write(path, payload):
        observed.append(path)
        assert isinstance(path, Path)
        assert isinstance(payload["evidence_file"], str)
        return real_write(path, payload)

    monkeypatch.setattr(diagnostic, "write_json", checked_write)
    report = {"verdict": "PRE_RESET_QUIESCENCE_FAILED", "reason": "fixture",
              "precondition_motion": {"confirmed": True},
              "quiescence": {"pass": False}, "model_only": {},
              "set_pose": {}, "post_reset": {}, "baseline_comparison": {}}
    result = diagnostic._write_report(output, report)
    path = output / "model_only_quiescence_diagnostic.json"
    assert observed == [path]
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["verdict"] == result["verdict"] == "PRE_RESET_QUIESCENCE_FAILED"
    assert loaded["reason"] == result["reason"] == "fixture"
    assert loaded["evidence_file"] == str(path)
    assert not isinstance(loaded["evidence_file"], Path)


def test_failure_report_is_json_serializable_and_preserves_diagnostic_evidence(tmp_path):
    report = {"verdict": "INCONCLUSIVE", "reason": "fixture failure",
              "precondition_motion": {"confirmed": False},
              "quiescence": {"pass": False, "total_iterations": 0},
              "model_only": {"rpc_accepted": False}, "set_pose": None,
              "post_reset": {}, "baseline_comparison": {"current_run": "pending"}}
    result = diagnostic._write_report(tmp_path / "new-parent", report)
    loaded = json.loads((tmp_path / "new-parent" / "model_only_quiescence_diagnostic.json").read_text())
    assert loaded["verdict"] == "INCONCLUSIVE"
    assert loaded["reason"] == "fixture failure"
    assert loaded["precondition_motion"] == {"confirmed": False}
    assert loaded["quiescence"]["total_iterations"] == 0
    assert loaded["model_only"]["rpc_accepted"] is False
    assert loaded["baseline_comparison"] == {"current_run": "pending"}
    assert result["evidence_file"] == loaded["evidence_file"]


class MotionPreconditionFixture:
    def __init__(self, *, moving=True):
        self.events = []
        self.moving = moving
        self.pose = {"x": 1.5, "y": 1.5, "yaw": 0.0}
        self.stepper = SimpleNamespace(time=.1)
        self.timeout = 1.0
        self.odometry_topic = "/model/simple_agent/odometry"
        self.controller = SimpleNamespace(pose_topic="/world/test/pose/info",
            last_published_command=None)
        self.controller.get_pose = lambda *_: dict(self.pose)
        def apply_action(action):
            self.events.append(("action", action, self.stepper.time))
            self.controller.last_published_command = {
                "linear": {"x": .5}, "angular": {"z": 0.}}
        self.controller.apply_action = apply_action
        def pose_history_after(cursor, start, end):
            self.events.append(("history", cursor, start, end, self.stepper.time))
            x0 = 1.5
            speed = .5 if self.moving else 0.
            return [{"simulation_timestamp": start, "world_x": x0,
                     "world_y": 1.5, "world_yaw": 0.},
                    {"simulation_timestamp": (start + end) / 2,
                     "world_x": x0 + speed * (end - start) / 2,
                     "world_y": 1.5, "world_yaw": 0.},
                    {"simulation_timestamp": end,
                     "world_x": x0 + speed * (end - start),
                     "world_y": 1.5, "world_yaw": 0.}]
        self.controller.pose_history_after = pose_history_after
        self.transport = SimpleNamespace()
        def cursor(topic):
            value = 41 if "pose/info" in topic else 17
            self.events.append(("cursor", topic, value, self.stepper.time))
            return value
        self.transport.cursor = cursor
        self.sensors = SimpleNamespace(sequence=0, frame=None)
        self.pose = dict(self.pose)
        self.env_pose = self.pose
        def step():
            self.events.append(("physics_step", self.stepper.time))
            self.stepper.time += .1
            if moving:
                self.pose["x"] += .05
        self.stepper.step_simulation = step
        def refresh():
            self.sensors.sequence += 1
            self.sensors.frame = SimpleNamespace(sequence=self.sensors.sequence,
                source="gazebo_lidar", age_ms=0., sensor_timestamp=self.stepper.time)
        self._refresh = refresh
        def read_odom(_sequence, _min_time, max_time, timeout=.5):
            self.events.append(("odom", max_time, self.stepper.time))
            return {"timestamp": max_time - .002, "linear_x": .5 if moving else 0.,
                    "angular_z": 0., "receive_sequence": 51}
        self.read_odometry_after_sequence = read_odom
        self.controller.stop_agent = lambda: self.events.append(("zero_twist", self.stepper.time))


def test_motion_precondition_captures_pose_cursor_before_first_up_and_passes_it_to_history():
    env = MotionPreconditionFixture(moving=True)
    evidence = diagnostic._motion_precondition(env)
    pose_cursor_index = next(i for i, item in enumerate(env.events)
                             if item[0] == "cursor" and "pose/info" in item[1])
    first_up_index = next(i for i, item in enumerate(env.events) if item[:2] == ("action", "up"))
    history_index = next(i for i, item in enumerate(env.events) if item[0] == "history")
    history_call = env.events[history_index]
    assert pose_cursor_index < first_up_index < history_index
    assert history_call[1] == 41
    assert history_call[2] == pytest.approx(.1)
    assert history_call[3] == pytest.approx(.4)
    assert evidence["confirmed"] is True
    assert evidence["world_pose_history"]["world_pose_sample_count"] == 3
    assert evidence["world_pose_history"]["world_pose_history_fresh"] is True
    assert evidence["world_pose_history"]["world_pose_history_dense_enough"] is True
    assert len([item for item in env.events if item[:2] == ("action", "up")]) == 3
    assert not any(item[0] == "zero_twist" for item in env.events)


def test_insufficient_motion_remains_failed_and_zero_twist_is_not_sent():
    env = MotionPreconditionFixture(moving=False)
    evidence = diagnostic._motion_precondition(env)
    assert evidence["confirmed"] is False
    assert evidence["translation"] == pytest.approx(0.)
    assert len([item for item in env.events if item[:2] == ("action", "up")]) == 3
    assert not any(item[0] == "zero_twist" for item in env.events)


def test_diagnostic_gates_zero_twist_quiescence_after_motion_confirmation():
    source = TOOL.read_text()
    assert source.index("motion = _motion_precondition(env)") < source.index(
        'if not motion["confirmed"]:') < source.index("quiescence = _quiesce(env")
