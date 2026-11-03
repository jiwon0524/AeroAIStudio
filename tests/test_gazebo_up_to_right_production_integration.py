import json
from types import SimpleNamespace

from aero_ai_studio.simulation.base import PhysicalControlFailure
from aero_ai_studio.simulation.action_mapping import gazebo_physics_twist
from tools import verify_v07_gazebo_up_to_right_production_integration as verifier
from tools.verify_v07_gazebo_up_to_down_production_integration import _recompute_macro_reward


def _replay():
    actions = ["up", "down", "up", "up", "up", "down", "up", "right"]
    return {"completed_episode_actions": [actions], "run_id": "fixture-run",
        "artifact_dir": "fixture", "scenario": {}, "max_steps": 250,
        "training_seed": 42}


def test_phase3ga_proof_and_saved_target_are_exact_up_to_right():
    actual = {"verdict": "UP_TO_RIGHT_L2R_ACTUAL_PASS",
        "status": "EXECUTED", "acceptance": {"all_pass": True},
        "execution": {"status": "EXECUTED"}, "evidence_file": "fixture.json"}
    result = verifier._validate_sources(_replay(), actual)
    assert result["expected_prefix_count"] == 7
    assert result["target_global_action_index_1_based"] == 8
    assert result["actual_executor_verdict"] == "UP_TO_RIGHT_L2R_ACTUAL_PASS"


def test_target_step_is_production_step_and_failure_evidence_is_written(tmp_path, monkeypatch):
    import tools.verify_v07_gazebo_up_to_right_production_integration as module

    class Adapter:
        def __init__(self, *_args, **_kwargs):
            self.injected = False
            self.control_mode = "PHYSICS"
            self.last_reset_evidence = {"normal_reset_pass": True}
            self.process = SimpleNamespace(poll=lambda: None, pid=123)
            self.manager = SimpleNamespace(status=lambda: {
                "status": "Running", "available": True, "pid": 123})
            self.env = SimpleNamespace(stepper=SimpleNamespace(time=0.),
                controller=SimpleNamespace(last_command={}), telemetry={}, steps=0)
            self.calls = []
            self.closed = False

        def reset(self, _seed):
            return None

        def step(self, action):
            self.calls.append(action)
            self.env.stepper.time += .1
            self.env.steps += 1
            self.env.controller.last_command = gazebo_physics_twist(action)
            if action == "right":
                raise PhysicalControlFailure("fixture target failure", evidence={"valid": False})
            return SimpleNamespace(reason="moving", terminated=False, truncated=False)

        def get_agent_observation(self, *_args):
            return SimpleNamespace(sensor_state={})

        def close(self):
            self.closed = True

    adapter = Adapter()
    monkeypatch.setattr(module, "extract_reversal_replay", lambda _path: _replay())
    monkeypatch.setattr(module.ScenarioSpec, "from_dict", lambda value: value)
    monkeypatch.setattr(module, "GazeboPhysicsTrainingEnvironment", lambda *_a, **_k: adapter)
    evidence_path = tmp_path / "phase3ga.json"
    evidence_path.write_text(json.dumps({"verdict": "UP_TO_RIGHT_L2R_ACTUAL_PASS",
        "status": "EXECUTED", "acceptance": {"all_pass": True},
        "execution": {"status": "EXECUTED"},
        "evidence_file": "phase3ga.json"}))

    report = module.run_verifier("unused", evidence_path, tmp_path / "out")

    assert adapter.calls == ["up", "down", "up", "up", "up", "down", "up", "right"]
    assert report["production_environment_step_used_for_target"] is True
    assert report["target_production_step_call_started"] is True
    assert report.get("target_physical_result_returned") is not True
    assert report["acceptance"] is None
    assert report["target_failure"]["reason"] == "fixture target failure"
    assert report["shutdown"] == "PASS" and adapter.closed
    on_disk = json.loads((tmp_path / "out" /
        "up_to_right_production_integration.json").read_text())
    assert on_disk["production_environment_step_used_for_target"] is True


def test_acceptance_checks_one_macro_transition_reward_and_smdp_duration():
    chunks = [
        {"phase": "BRAKE_LINEAR", "reward": -.1,
            "elapsed_execution_time": .1, "terminated": False},
        {"phase": "BRAKE_LINEAR", "reward": -.1,
            "elapsed_execution_time": .1, "terminated": False},
        {"phase": "ACQUIRE_ANGULAR", "reward": -.15,
            "elapsed_execution_time": .1, "terminated": False},
    ]
    macro = _recompute_macro_reward(.95, chunks)
    acquire = {"phase": "ACQUIRE_ANGULAR",
        "command": gazebo_physics_twist("right"),
        "command_published_after_braking": True,
        "brake_completion_publish_sequence": 11,
        "acquire_command_publish_sequence": 12,
        "world_pose_history_contract": {"pass": True},
        "world_pose_history": {"world_angular_velocity_samples": [
            {"simulation_timestamp": 1.91, "angular_velocity": -.3},
            {"simulation_timestamp": 1.96, "angular_velocity": -.7}]},
        "end_body_angular_velocity": -.7,
        "production_pose_validation": {"valid": True},
        "sensor_contract_pass": True, "contact_contract_pass": True,
        "collision": False}
    brake_chunks = [{"body_stopped_contract": {"pass": True,
        "world_body_is_authority": True}, "collision_events": []} for _ in range(2)]
    execution = {"execution_evidence": {"initial_source_body_motion_established": True,
            "source_action": "up"},
        "execution_phases": [{"phase": "BRAKE_LINEAR", "command": {
            "linear": {"x": 0.}, "angular": {"z": 0.}}, "chunks": brake_chunks}, acquire],
        "reward_chunks": chunks, "control_chunk_count": 3,
        "elapsed_execution_time": .3, "elapsed_discount_units": 3.,
        "macro_reward": macro, "physical_status": "EXECUTED", "collision": False}
    training = {"agent_intent": "right", "previous_action": "up",
        "transition_type": "LINEAR_TO_ROTATION", "production_macro": True,
        "activation_pair": "UP_TO_RIGHT",
        "control_executor_activation": {"active": True,
            "verified_action_pair": ["up", "right"]}, "execution_evidence": execution}
    result = SimpleNamespace(reward=macro, elapsed_execution_time=.3,
        elapsed_discount_units=3., terminated=False, truncated=False)
    payload = ([0.] * 22, 3, macro, [0.] * 22, False, 3.)
    acceptance = verifier.assess_production_up_to_right(result, training,
        gazebo_physics_twist("up"), 7, 8, payload, True, macro)
    assert acceptance["all_pass"] is True
    assert acceptance["right_action_index"] == 3
    assert acceptance["macro_reward_recomputed"] == macro
