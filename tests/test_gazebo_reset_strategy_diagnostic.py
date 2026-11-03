import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOL = Path(__file__).parents[1] / "tools" / "diagnose_v07_gazebo_reset_strategies.py"
SPEC = importlib.util.spec_from_file_location("diagnose_v07_gazebo_reset_strategies", TOOL)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


class Field:
    TYPE_BOOL = 8
    def __init__(self, name, type=8, default=False, presence=False):
        self.name, self.type, self.default_value = name, type, default
        self.has_presence = presence


class Descriptor:
    def __init__(self, fields): self.fields = fields


def supported():
    return diagnostic.supported_reset_modes(Descriptor([
        Field("all"), Field("time_only"), Field("model_only"), Field("header", 11)]))


def test_installed_schema_modes_are_boolean_scalar_defaults_and_only_supported_modes_are_executable():
    modes = supported()
    assert set(modes) == {"all", "time_only", "model_only"}
    assert all(value == {"supported": True, "protobuf_type": "bool",
                         "has_presence": False, "default": False}
               for value in modes.values())
    assert diagnostic.reset_mode_payload("model_only", modes) == {
        "pause": True, "reset": {"model_only": True}}
    with pytest.raises(ValueError, match="Unsupported"):
        diagnostic.reset_mode_payload("future_mode", modes)
    with pytest.raises(ValueError, match="Unsupported"):
        diagnostic.reset_mode_payload("model_only", {"model_only": {"supported": False}})


def test_clock_contracts_keep_all_model_and_time_semantics_distinct():
    before = {"sim_time": {"sec": 4}, "iterations": 400, "paused": True}
    zero = {"sim_time": {"sec": 0}, "iterations": 0, "paused": True,
            "sim_time_raw_present": True, "iterations_raw_present": True}
    same = {"sim_time": {"sec": 4}, "iterations": 400, "paused": True}
    assert diagnostic.strategy_stats_contract("all", before, zero, 5, 6)["pass"]
    assert diagnostic.strategy_stats_contract("time_only", before, zero, 5, 6)["pass"]
    assert diagnostic.strategy_stats_contract("model_only", before, same, 5, 6)["pass"]
    assert not diagnostic.strategy_stats_contract("model_only", before, zero, 5, 6)["pass"]
    assert not diagnostic.strategy_stats_contract("all", before, same, 5, 6)["pass"]


def _base_verdict(**updates):
    evidence = {"pre_reset_motion": {"confirmed": True},
        "reset_rpc": {"accepted": True}, "stats_reset_contract": {"pass": True},
        "process_alive": True, "body_velocity_cleared": True,
        "body_pose_stable": True, "odometry_stopped": True,
        "sensor_fresh": True, "contact_publisher_healthy": True}
    evidence.update(updates)
    return evidence


def test_safe_verdict_requires_every_physical_and_contact_contract():
    assert diagnostic.strategy_verdict(_base_verdict()) == "SAFE_FOR_PERSISTENT_EPISODE_RESET"
    for key in ("body_velocity_cleared", "body_pose_stable", "odometry_stopped",
                "sensor_fresh", "contact_publisher_healthy", "process_alive"):
        assert diagnostic.strategy_verdict(_base_verdict(**{key: False})) == "UNSAFE"


def test_no_pre_reset_motion_is_inconclusive_and_reset_rejection_is_unsafe():
    assert diagnostic.strategy_verdict(_base_verdict(pre_reset_motion={"confirmed": False})) == "INCONCLUSIVE"
    assert diagnostic.strategy_verdict(_base_verdict(reset_rpc={"accepted": False})) == "UNSAFE"


def test_contact_event_silence_is_not_used_as_publisher_health():
    class Node:
        def topic_info(self, _): return ([SimpleNamespace(msg_type_name="gz.msgs.Contacts")], [])
    env = SimpleNamespace(contact_topic="/contacts", transport=SimpleNamespace(node=Node()))
    ready = diagnostic.readiness_snapshot(env)
    assert ready["publisher_visible"] and ready["schema_visible"]
    assert "message" not in ready


def test_wrong_contact_schema_is_unhealthy():
    class Node:
        def topic_info(self, _): return ([SimpleNamespace(msg_type_name="gz.msgs.Pose_V")], [])
    ready = diagnostic.readiness_snapshot(SimpleNamespace(
        contact_topic="/contacts", transport=SimpleNamespace(node=Node())))
    assert ready["publisher_visible"] and not ready["schema_visible"]


class FakeEnv:
    def __init__(self, pid, *, body_residual=False, contact_recovery=True, sensor_fresh=True,
                 odometry_stopped=True):
        self.injected = False
        self.control_mode = "PHYSICS"
        self.timeout = 1.
        self.world_name = f"world_{pid}"
        self.odometry_topic = f"/model/simple_agent/odometry"
        self.scenario = SimpleNamespace(start=(1, 1))
        self.manager = SimpleNamespace(partition=f"part_{pid}", status=lambda: {
            "pid": pid, "status": "Stopped" if self.closed else "Running"})
        self.closed = False
        self.body_residual = body_residual
        self.contact_recovery = contact_recovery
        self.sensor_fresh = sensor_fresh
        self.odom_stopped = odometry_stopped
        self.reset_mode = None
        self.stats = {"sim_time": {"sec": 0, "nsec": 100000000},
                      "iterations": 100, "paused": True,
                      "sim_time_raw_present": True, "iterations_raw_present": True}
        self.stats_sequence = 10
        self.pose = {"x": 1.5, "y": 1.5, "z": .16, "yaw": 0.}
        self.odom_sequence = 20
        self.pose_sequence = 100
        self.sensors = SimpleNamespace(sequence=0, frame=None, reset_epoch=lambda: None)
        self.env_ref = self
        self.transport = SimpleNamespace()
        self.transport.node = SimpleNamespace(topic_info=self.topic_info)
        self.transport.snapshot = lambda _: {"data": self.stats, "sequence": self.stats_sequence}
        self.transport.cursor = self.cursor
        self.stepper = SimpleNamespace(time=.1, topic=f"/world/{self.world_name}/stats",
            control=self.control, pause=lambda: None, step_simulation=self.step_simulation)
        self.controller = SimpleNamespace(
            pose_topic=f"/world/{self.world_name}/pose/info",
            last_published_command=None, last_pose_request={},
            get_pose=self.get_pose, apply_action=self.apply_action,
            stop_agent=self.stop_agent, reset_agent_pose=self.reset_pose,
            pose_history_after=self.pose_history_after)
        self.contact_topic="/contacts"
        self.contacts=SimpleNamespace(reset=lambda _: None)
        self.pose_cursor_at_reset=None

    def topic_info(self, topic):
        if topic == self.contact_topic:
            if self.reset_mode and not self.contact_recovery and self.reset_mode == "all": return ([], [])
            return ([SimpleNamespace(msg_type_name="gz.msgs.Contacts")], [])
        return ([], [])

    def cursor(self, topic):
        if "odometry" in topic: return self.odom_sequence
        if "pose/info" in topic: return self.pose_sequence
        return 0

    def launch(self): return {"available": True}
    def prepare(self): pass
    def prepare_contacts(self): pass
    def reset(self, seed):
        self.stats_sequence += 1
        self.sensors.sequence = 1
        self.sensors.frame = SimpleNamespace(sequence=1, age_ms=0., source="gazebo_lidar", sensor_timestamp=.1)
    def get_pose(self, *args): return dict(self.pose)
    def apply_action(self, action): self.controller.last_published_command={"action": action}
    def stop_agent(self): self.controller.last_published_command={"linear": {"x": 0.}, "angular": {"z": 0.}}
    def reset_pose(self, x, y, z, yaw):
        self.pose={"x": x, "y": y, "z": z, "yaw": yaw}
        self.controller.last_pose_request={"accepted": True, "payload": {"x": x, "y": y, "z": z, "yaw": yaw}}
    def control(self, payload):
        mode = next(iter(payload["reset"]))
        self.reset_mode = mode
        self.pose_cursor_at_reset = self.pose_sequence
        if mode in ("all", "time_only"):
            self.stats={"sim_time": {"sec": 0}, "iterations": 0 if mode == "all" else 400,
                        "paused": True, "sim_time_raw_present": True, "iterations_raw_present": True}
            self.stepper.time=0.
        self.stats_sequence += 1
        self.odom_sequence += 1
        return {"data": True}
    def step_simulation(self, n_steps=1):
        start=self.stepper.time
        self.stepper.time += .1*n_steps
        self.stats={"sim_time": {"sec": int(self.stepper.time),
                    "nsec": int(round((self.stepper.time % 1)*1e9))},
                    "iterations": int(round(self.stepper.time*1000)), "paused": True,
                    "sim_time_raw_present": True, "iterations_raw_present": True}
        self.stats_sequence += 1
        self.odom_sequence += n_steps*10
        self.pose_sequence += n_steps*10
        if self.reset_mode is None:
            self.pose["x"] += .05*n_steps
        elif self.body_residual:
            self.pose["x"] += .05*n_steps

    def _refresh(self):
        self.sensors.sequence += 1
        self.sensors.frame=SimpleNamespace(sequence=self.sensors.sequence, age_ms=0.,
            source="gazebo_lidar", sensor_timestamp=self.stepper.time)
        self.pose=self.get_pose()
        if not self.sensor_fresh:
            self.sensors.frame.age_ms=100.
    def read_odometry_after_sequence(self, sequence, min_time, max_time, timeout=.5):
        if self.reset_mode is None:
            return {"timestamp": self.stepper.time, "linear_x": .5, "angular_z": 0.,
                    "receive_sequence": self.odom_sequence}
        return {"timestamp": self.stepper.time,
                "linear_x": .01 if self.odom_stopped else .2,
                "angular_z": 0., "receive_sequence": self.odom_sequence}
    def pose_history_after(self, sequence, start, end):
        count=max(3, int(round((end-start)/.01))+1)
        return [{"simulation_timestamp": start+(end-start)*i/(count-1),
                 "world_x": (1.5 + .5*((start+(end-start)*i/(count-1))-.1)
                             if self.reset_mode is None else
                             (1.5 + .5*(end-start)*i/(count-1) if self.body_residual else 1.5)),
                 "world_y": 1.5, "world_yaw": 0.}
                for i in range(count)]
    def close(self): self.closed=True


def fake_factory_factory(instances, **options):
    def factory(*args, **kwargs):
        env=FakeEnv(len(instances)+1, **options)
        instances.append(env)
        return env
    return factory


def test_strategy_runs_use_distinct_fresh_processes_and_can_recommend_only_strict_safe_mode(tmp_path, monkeypatch):
    instances=[]
    monkeypatch.setattr(diagnostic, "gazebo_status", lambda probe=True: {"detail": "Gazebo Harmonic fixture"})
    report=diagnostic.run_diagnostic(tmp_path, env_factory=fake_factory_factory(instances),
        contact_timeout=0., contact_poll_interval=.01)
    assert set(report["strategies"]) == {"all", "model_only", "time_only"}
    assert len({env.manager.partition for env in instances}) == 3
    assert all(env.closed for env in instances)
    assert all(result["process_exited"] for result in report["strategies"].values())
    assert report["recommended_strategy"] is not None


@pytest.mark.parametrize("options", [
    {"contact_recovery": False}, {"body_residual": True},
    {"sensor_fresh": False}, {"odometry_stopped": False},
])
def test_failed_contact_body_sensor_or_odometry_contract_never_returns_safe(tmp_path, monkeypatch, options):
    monkeypatch.setattr(diagnostic, "gazebo_status", lambda probe=True: {"detail": "fixture"})
    instances=[]
    report=diagnostic.run_diagnostic(tmp_path, env_factory=fake_factory_factory(instances, **options),
                                     contact_timeout=0.)
    if options.get("contact_recovery") is False:
        assert report["strategies"]["all"]["verdict"] == "UNSAFE"
    else:
        assert all(result["verdict"] != "SAFE_FOR_PERSISTENT_EPISODE_RESET"
                   for result in report["strategies"].values())


def test_five_centimeter_settle_drift_is_reported_and_makes_strategy_unsafe(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostic, "gazebo_status", lambda probe=True: {"detail": "fixture"})
    instances=[]
    report=diagnostic.run_diagnostic(tmp_path,
        env_factory=fake_factory_factory(instances, body_residual=True), contact_timeout=0.)
    result=report["strategies"]["model_only"]
    assert result["body"]["settle_motion"]["translation"] == pytest.approx(.05)
    assert result["body_pose_stable"] is False
    assert result["verdict"] == "UNSAFE"


def test_process_death_cannot_satisfy_safe_verdict():
    assert diagnostic.strategy_verdict(_base_verdict(process_alive=False)) == "UNSAFE"
