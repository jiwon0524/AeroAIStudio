import json
from pathlib import Path
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from aero_ai_studio.agents.dqn import DQNAgent
from aero_ai_studio.agents.base import Transition
from aero_ai_studio.gazebo.dqn_runtime import DQNCheckpointError, checkpoint_contract, load_compatible_dqn
from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
from aero_ai_studio.observation.encoder import observation_vector
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping, grid_world_action_mapping
from aero_ai_studio.simulation.base import ACTIONS, PhysicalControlFailure
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.training.gazebo_dqn import estimate_training_cost
from aero_ai_studio.training.gazebo_physics import (
    GazeboPhysicsTrainingEnvironment,
    GazeboTrainingInfrastructureError,
    gazebo_dqn_reward,
)
from aero_ai_studio.training.trainer import Trainer, TrainingConfig, _training_failure_metadata
from tools.train_v07_gazebo_dqn import _copy_export, _evaluation_key, _training_failure_summary


def _observation(sequence=1, timestamp=.1):
    return Observation("sensor", (1, 1), (5, 2), sensor_state={
        "front_distance": 5., "back_distance": 5., "left_distance": 5., "right_distance": 5.,
        "goal_distance": 4., "goal_direction": "E", "goal_delta": [4., 1.],
        "moving_obstacle_distance": None, "moving_obstacle_relative_motion": "UNKNOWN",
        "source": "gazebo_lidar", "sensor_timestamp": timestamp, "sequence": sequence,
    })


def _config(kind="full"):
    return TrainingConfig(episodes=5, algorithm="dqn", observation_mode="sensor", state_encoder="canonical",
        simulator="gazebo", gazebo_control_mode="PHYSICS", training_kind=kind, safety_enabled=False,
        batch_size=1, warmup_steps=1, target_interval=1, buffer_size=100, reward_clip=10.)


def test_gazebo_sensor_encoder_contract_is_22_dimensions():
    vector = observation_vector(_observation())
    assert len(vector) == 22
    assert all(-1 <= value <= 1 for value in vector)


def test_physics_mapping_is_indexed_and_matches_controller_twists():
    expected = [
        ("up", .5, 0.), ("down", -.5, 0.), ("left", 0., .8), ("right", 0., -.8),
    ]
    assert [item["action"] for item in gazebo_physics_action_mapping()] == list(ACTIONS)
    for name, linear, angular in expected:
        transport = SimpleNamespace(publish=lambda *_: None, subscribe=lambda *_: None)
        controller = PhysicsEntityController(transport, "fixture")
        controller.apply_action(name)
        assert controller.last_published_command == {"linear": {"x": linear}, "angular": {"z": angular}}
    controller.stop_agent()
    assert controller.last_published_command == {"linear": {"x": 0.}, "angular": {"z": 0.}}


@pytest.mark.parametrize("before,after,reason,expected", [
    (4., 3., "moving", {"progress": 2., "time": -.1, "total": 1.9}),
    (3., 4., "moving", {"progress": -2., "time": -.1, "total": -2.1}),
    (4., 0., "goal", {"goal": 100., "total": 100.}),
    (2., 1., "collision", {"collision": -100., "total": -100.}),
    (2., 2., "timeout", {"progress": 0., "time": -.1, "total": -.1}),
])
def test_gazebo_reward_components(before, after, reason, expected):
    components = gazebo_dqn_reward(before, after, reason)
    for key, value in expected.items():
        assert components[key] == pytest.approx(value)


def test_dqn_replay_learning_target_updates_and_resume(tmp_path):
    agent = DQNAgent(seed=9, batch_size=1, buffer_size=20, target_interval=1,
                     observation_mode="sensor", warmup_steps=1, reward_clip=10.)
    obs = _observation()
    for _ in range(4):
        agent.learn(Transition(obs, "up", 1., obs, False))
    assert len(agent.buffer) == agent.global_step == agent.learn_steps == 4
    assert all(len(item) == 6 and item[-1] == 1.0 for item in agent.buffer.items)
    assert agent.optimizer_updates == 1
    assert agent.target_updates == 4
    path = tmp_path / "model.pt"
    agent.save(path)
    restored = DQNAgent.load(path)
    assert restored.global_step == agent.global_step
    assert restored.learn_steps == agent.learn_steps
    assert restored.optimizer_updates == agent.optimizer_updates
    assert restored.target_updates == agent.target_updates
    assert len(restored.buffer) == len(agent.buffer)
    assert restored.optimizer.state_dict()["state"].keys() == agent.optimizer.state_dict()["state"].keys()


def test_export_schema_verifier_accepts_full_and_rejects_smoke(tmp_path):
    scenario = ScenarioSpec(width=10, height=10, start=(1, 1), goal=(5, 2))
    agent = DQNAgent(seed=3, observation_mode="sensor", action_mapping=gazebo_physics_action_mapping())
    summary = {"episodes_completed": 5, "total_steps": 50, "success_rate": .4,
               "collision_rate": .2, "timeout_rate": .4}
    full = tmp_path / "full"
    metadata = _copy_export(agent, _config("full"), scenario, full, summary)
    assert metadata["compatible_with_verify_v07_dqn"] is True
    contract = checkpoint_contract(full)
    assert contract["agent_metadata"]["action_mapping"] == gazebo_physics_action_mapping()
    assert contract["config"]["simulator"] == "gazebo"
    assert contract["config"]["gazebo_control_mode"] == "PHYSICS"
    assert json.loads((full / "scenario.json").read_text())["goal"] == [5, 2]
    assert not load_compatible_dqn(full)["agent"].network.training
    smoke = tmp_path / "smoke"
    smoke_metadata = _copy_export(agent, _config("smoke"), scenario, smoke, summary)
    assert smoke_metadata["compatible_with_verify_v07_dqn"] is False
    with pytest.raises(DQNCheckpointError, match="Only a full"):
        checkpoint_contract(smoke)


def test_gridworld_training_metadata_cannot_claim_physics_checkpoint(tmp_path):
    scenario = ScenarioSpec(width=10, height=10, start=(1, 1), goal=(5, 2))
    cfg = _config("full")
    cfg.simulator = "grid"
    # Grid metadata remains valid for its own trainer but must not export as verifier compatible.
    agent = DQNAgent(seed=1, observation_mode="sensor", action_mapping=grid_world_action_mapping())
    export = tmp_path / "grid"
    metadata = _copy_export(agent, cfg, scenario, export, {})
    assert metadata["compatible_with_verify_v07_dqn"] is False
    with pytest.raises(DQNCheckpointError, match="Incompatible"):
        checkpoint_contract(export)


def test_cost_estimate_does_not_charge_evaluation_without_evaluation_episodes():
    estimate = estimate_training_cost(5, 20, 25, 0, {
        "actions_per_episode": 154, "mean_action_seconds": .72, "source": "fixture"})
    assert estimate["evaluation_rounds"] == 0
    assert estimate["evaluation_physics_action_upper_bound"] == 0
    assert estimate["estimated_training_physics_actions"] == 100


def test_best_checkpoint_ranking_prefers_goal_rate_then_safer_episodes():
    safe = {"success_rate": .7, "collision_rate": .1, "timeout_rate": .2, "mean_reward": 30.}
    risky = {"success_rate": .7, "collision_rate": .2, "timeout_rate": 0., "mean_reward": 50.}
    more_success = {"success_rate": .8, "collision_rate": .9, "timeout_rate": .9, "mean_reward": -20.}
    assert _evaluation_key(safe) > _evaluation_key(risky)
    assert _evaluation_key(more_success) > _evaluation_key(safe)


def test_physical_control_failure_stays_typed_through_adapter_and_cli_summary():
    evidence = {
        "requested_action": "down",
        "previous_command": {"linear": {"x": 0.0}, "angular": {"z": -0.8}},
        "requested_command": {"linear": {"x": -0.5}, "angular": {"z": 0.0}},
        "transition_type": "ROTATION_TO_LINEAR",
        "validator_evidence": {"valid": False, "world_direction_ok": False},
        "collision": False,
        "contact_state": {"blocked": False},
    }
    failure = PhysicalControlFailure(
        "Physics movement outside validated tolerance", evidence=evidence)
    adapter = GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.env = SimpleNamespace(
        pose={"x": 1.5, "y": 1.5}, goal=(5.5, 2.5),
        get_agent_observation=lambda *_: _observation(),
        step=lambda _action: (_ for _ in ()).throw(failure),
    )
    adapter._require_actual_sensor = lambda *_args: {"sequence": 2}

    with pytest.raises(PhysicalControlFailure) as caught:
        adapter.step("down")
    assert caught.value is failure
    assert caught.value.evidence["transition_type"] == "ROTATION_TO_LINEAR"

    cli = _training_failure_summary(caught.value, "full")
    run = _training_failure_metadata(caught.value)
    assert cli["status"] == "physical_control_failure"
    assert cli["category"] == "physical_control_failure"
    assert cli["failure"]["evidence"] == evidence
    assert run["status"] == "physical_control_failure"
    assert run["failure_category"] == "physical_control_failure"
    assert run["failure"]["reason"] == "Physics movement outside validated tolerance"
    assert cli["status"] != "infrastructure_failure"


def test_trainer_run_artifact_records_physical_control_failure_status(tmp_path):
    scenario = ScenarioSpec(width=10, height=10, start=(1, 1), goal=(5, 2))
    evidence = {"transition_type": "ROTATION_TO_LINEAR", "validator_evidence": {"valid": False}}

    class RejectedActionEnvironment(GridWorld):
        def step(self, _action):
            raise PhysicalControlFailure("Physics movement outside validated tolerance", evidence=evidence)

    def factory(spec, max_steps):
        return RejectedActionEnvironment(spec, max_steps)

    trainer = Trainer(scenario, TrainingConfig(episodes=1, max_steps=1), factory)
    with pytest.raises(PhysicalControlFailure):
        trainer.run(tmp_path / "runs")
    run_file = next((tmp_path / "runs").glob("*/run.json"))
    artifact = json.loads(run_file.read_text())
    assert artifact["status"] == "physical_control_failure"
    assert artifact["failure_category"] == "physical_control_failure"
    assert artifact["failure"]["evidence"] == evidence


@pytest.mark.parametrize("error,category", [
    (GazeboTrainingInfrastructureError("service_failure", "step service unavailable"), "service_failure"),
    (GazeboTrainingInfrastructureError("ambiguous_timeout", "step progress ambiguous"), "ambiguous_timeout"),
])
def test_infrastructure_failures_keep_infrastructure_classification(error, category):
    cli = _training_failure_summary(error, "full")
    run = _training_failure_metadata(error)
    assert cli["status"] == "infrastructure_failure"
    assert cli["category"] == category
    assert run["status"] == "infrastructure_failure"
    assert run["failure_category"] == category


def test_collision_remains_a_task_outcome_not_a_control_failure():
    components = gazebo_dqn_reward(2., 1., "collision")
    assert components["collision"] == -100.
    assert not isinstance(RuntimeError("collision"), PhysicalControlFailure)


class _Frame:
    source = "gazebo_lidar"
    age_ms = 0.
    sensor_timestamp = .1
    sequence = 2


class _FakeTrainingEnv:
    def __init__(self, scenario):
        self.scenario = scenario
        self.control_mode = "PHYSICS"
        self.timeout = 5.
        self.injected = False
        self.process = SimpleNamespace(poll=lambda: None)
        self.pose = {"x": .5, "y": .5, "z": .16, "yaw": 0.}
        self.pose_start=(.5,.5)
        self.goal = (5.5, 2.5)
        self.stepper = SimpleNamespace(time=0., step_simulation=self._step,
            pause=lambda:self.reset_order.append('pause'), reset_world=self._reset_world,
            reset_model_only=self._reset_model_only, last_verification={})
        self.controller = SimpleNamespace(last_command={}, last_published_command=None,
            stop_agent=self._stop)
        self.controller.get_pose=lambda *_:dict(self.pose)
        self.sensors = SimpleNamespace(sequence=0, frame=None, reset_epoch=self._reset_sensor_epoch)
        self.contacts = SimpleNamespace(poll=lambda *_: [], reset=self._reset_contact)
        self.reset_count = 0
        self.reset_order=[]
        self.drift_on_refresh=0.
        self.world_reset_error=None
        self.model_only_error=None
        self.quiescence_failure=False
        self.body_linear_velocity=.0
        self.body_angular_velocity=.0
        self.wheel_velocity=.0
        self.odometry_topic='/model/simple_agent/odometry'
        self.odometry_sequence_at_subscription=0
        self.odometry_epoch_source='fresh_process_initialization'
        self.contact_topic='/aero/test/contacts'
        self.sensors.topic='/aero/test/scan'
        self.transport=SimpleNamespace(cursor=lambda _topic:1,
            wait_for_topic=self._wait_for_topic)
        self.controller.pose_topic='/world/test/pose/info'
        self.controller.pose_history_after=self._pose_history_after

    def _reset_world(self):
        self.reset_order.append('world_physics_reset')
        if self.world_reset_error:raise RuntimeError(self.world_reset_error)
        self.body_linear_velocity=0.
        self.body_angular_velocity=0.
        self.wheel_velocity=0.
        self.stepper.time=0.
        return {'method':'world_control_reset_all','before_sim_time':.1,'after_sim_time':0.,
                'after_iterations':0,'paused_after':True,'valid':True}

    def _reset_model_only(self):
        self.reset_order.append('model_only_reset')
        if self.model_only_error:raise RuntimeError(self.model_only_error)
        return {'method':'world_control_reset_model_only','before_sim_time':self.stepper.time,
                'after_sim_time':self.stepper.time,'before_iterations':int(round(self.stepper.time*1000)),
                'after_iterations':int(round(self.stepper.time*1000)),
                'stats_reset_contract':{'pass':True,'clock_semantics':'preserve_simulation_time_and_iterations'},
                'valid':True}

    def _reset_contact(self,*_):
        self.reset_order.append('contact_epoch_reset')

    def _wait_for_topic(self,topic,message_type,timeout=None):
        self.reset_order.append('contact_readiness:'+topic)
        assert message_type=='Contacts'
        return {'topic':topic,'message_type':'gz.msgs.Contacts'}

    def _pose_history_after(self,_sequence,start,end):
        x=float(self.pose['x'])
        x0,y0=self.pose_start
        if self.quiescence_failure and self.controller.last_command.get('linear',{}).get('x')==0.:
            x=x0+.01
        return [{'simulation_timestamp':start+(end-start)*fraction,
                 'world_x':x0+(x-x0)*fraction,'world_y':y0,'world_yaw':0.}
                for fraction in (0.,1/3,2/3,1.)]

    def _reset_sensor_epoch(self):self.reset_order.append('sensor_epoch_reset')

    def _stop(self):
        self.reset_order.append('zero_command')
        self.controller.last_command = {"linear": {"x": 0.}, "angular": {"z": 0.}}
        self.controller.last_published_command = self.controller.last_command

    def _step(self):
        self.reset_order.append('physics_step')
        self.stepper.time += .1
        self.stepper.last_verification={'iteration_delta':100,'expected_iteration_delta':100}
        self.sensors.sequence += 1
        self.sensors.frame = SimpleNamespace(source="gazebo_lidar", age_ms=0.,
            sequence=self.sensors.sequence, sensor_timestamp=self.stepper.time)

    def reset(self, seed=None):
        self.reset_order.append('environment_pose_reset')
        self.reset_count += 1
        self._stop()
        self._step()

    def restart(self,seed=None):
        fresh=_FakeTrainingEnv(self.scenario)
        fresh.reset(seed)
        return fresh

    def _refresh(self):
        # The real Environment._refresh reads topics only; physics was already
        # advanced by step_simulation above.
        self.pose['x']+=self.drift_on_refresh
        return None

    def read_odometry(self, *_):
        return {"timestamp": self.stepper.time, "linear_x": 0., "angular_z": 0.}

    def read_odometry_after_sequence(self,_sequence,min_time,max_time,timeout=.5):
        assert min_time<=self.stepper.time<=max_time
        return {"timestamp":self.stepper.time,"linear_x":0.,"angular_z":0.,"receive_sequence":2}

    def get_agent_observation(self, *_):
        return _observation(self.sensors.sequence, self.stepper.time)

    def get_observation(self):
        return (0, 0)


def test_episode_reset_reuses_same_sim_process_and_requires_fresh_sensor():
    scenario = ScenarioSpec(width=10, height=10, start=(0, 0), goal=(5, 2))
    adapter = GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.scenario = scenario
    adapter.max_sensor_age_ms = 20
    adapter.restart_fallbacks = 0
    adapter.reset_evidence = []
    adapter.episodes_started = 0
    adapter._active_reset_attempt = None
    fake = _FakeTrainingEnv(scenario)
    adapter.env = fake
    adapter._reset_once(9)
    adapter._reset_once(10)
    assert fake.reset_count == 2
    assert adapter.restart_fallbacks == 0
    assert len(adapter.reset_evidence) == 2
    assert all(evidence["sensor_fresh"] and evidence["odometry_fresh_and_stopped"]
               for evidence in adapter.reset_evidence)
    assert adapter.reset_evidence[0]['odometry_epoch']=={
        'epoch_type':'fresh_process_initialization','baseline_receive_sequence':0,
        'selected_receive_sequence':2,'receive_sequence_after_epoch':True,
        'baseline_source':'fresh_process_subscription'}
    assert all(evidence["observation_contract"]["dimension"] == 22 for evidence in adapter.reset_evidence)


def test_reused_episode_quiesces_body_then_model_only_before_pose_reset():
    scenario=ScenarioSpec(width=10,height=10,start=(0,0),goal=(5,2))
    adapter=GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.scenario=scenario;adapter.max_sensor_age_ms=20;adapter.restart_fallbacks=0
    adapter.reset_evidence=[];adapter.episodes_started=0;adapter._active_reset_attempt=None
    fake=_FakeTrainingEnv(scenario);adapter.env=fake
    adapter._reset_once(10)
    fake.body_linear_velocity=.5;fake.body_angular_velocity=.8;fake.wheel_velocity=-.5
    fake.reset_order.clear()
    adapter.reset(11)
    zero_index=fake.reset_order.index('zero_command')
    first_progression=fake.reset_order.index('physics_step')
    pause_index=fake.reset_order.index('pause')
    model_only_index=fake.reset_order.index('model_only_reset')
    pose_index=fake.reset_order.index('environment_pose_reset')
    assert zero_index<first_progression<pause_index<model_only_index<pose_index
    evidence=adapter.last_reset_evidence
    assert evidence['reset_method']=='world_control_reset_model_only_after_quiescence'
    assert evidence['reset_rpc']['valid'] is True
    assert evidence['pre_reset_quiescence']['pass'] is True
    assert evidence['pre_reset_quiescence']['max_chunks']==20
    assert evidence['pre_reset_quiescence']['chunk_iterations']==100
    assert evidence['pre_reset_quiescence']['final_body_stopped_contract']['pass'] is True
    assert evidence['contact_readiness']['after_model_only']['pass'] is True
    assert evidence['contact_readiness']['after_progression']['pass'] is True
    assert evidence['contact_readiness']['after_settle']['pass'] is True
    assert evidence['normal_reset_pass'] is True
    assert evidence['restart_fallback_used'] is False
    assert evidence['odometry_fresh_and_stopped'] is True
    assert evidence['odometry_epoch']['baseline_receive_sequence']==1
    assert evidence['odometry_epoch']['selected_receive_sequence']==2
    assert evidence['odometry_epoch']['receive_sequence_after_epoch'] is True
    assert evidence['sensor_fresh'] is True
    assert evidence['world_pose_history_sufficient'] is True
    assert evidence['body_residual_velocity_stopped'] is True
    assert fake.reset_order.count('model_only_reset')==1
    assert fake.reset_order.count('world_physics_reset')==0


def test_quiescence_failure_blocks_model_only_and_uses_existing_restart_fallback():
    scenario=ScenarioSpec(width=10,height=10,start=(0,0),goal=(5,2))
    adapter=GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.scenario=scenario;adapter.max_sensor_age_ms=20;adapter.restart_fallbacks=0
    adapter.reset_evidence=[];adapter.episodes_started=0;adapter._active_reset_attempt=None
    fake=_FakeTrainingEnv(scenario);adapter.env=fake
    adapter._reset_once(10)
    fake.quiescence_failure=True
    fake.reset_order.clear()
    adapter.reset(11)
    evidence=adapter.last_reset_evidence
    attempt=evidence['primary_reset_attempt']
    assert attempt['normal_reset_pass'] is False
    assert 'pre_reset_quiescence_failed' in attempt['normal_reset_failure_reason']
    assert attempt['restart_fallback_used'] is True
    assert adapter.restart_fallbacks==1
    assert 'model_only_reset' not in fake.reset_order
    assert evidence['reset_method']=='fresh_process_restart'


def test_reset_odometry_freshness_uses_settle_end_and_failure_provenance_is_false():
    scenario=ScenarioSpec(width=10,height=10,start=(0,0),goal=(5,2))
    adapter=GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.scenario=scenario;adapter.max_sensor_age_ms=20;adapter.restart_fallbacks=0
    adapter.reset_evidence=[];adapter.episodes_started=0
    adapter._active_reset_attempt={'seed':4,'reset_epoch_sim_time':0.,
        'odometry_sequence_before_reset':9,'odometry_sequence_after_reset':10}
    fake=_FakeTrainingEnv(scenario);adapter.env=fake
    selected_bounds={}
    def stale_odom(_sequence,min_time,max_time,timeout=.5):
        selected_bounds.update(min_time=min_time,max_time=max_time)
        return {'timestamp':.11,'linear_x':1.1e-17,'angular_z':6.6e-19,
                'receive_sequence':11}
    fake.read_odometry_after_sequence=stale_odom
    with pytest.raises(GazeboTrainingInfrastructureError) as caught:
        adapter._reset_once(4)
    settle=fake.stepper.time
    attempt=adapter._active_reset_attempt
    evidence=attempt['settle_evidence']
    assert selected_bounds['min_time']==pytest.approx(settle-.02)
    assert selected_bounds['max_time']==pytest.approx(settle+.002)
    assert evidence['odometry_contract']['receive_sequence_new'] is True
    assert evidence['odometry_contract']['timestamp_after_epoch'] is True
    assert evidence['odometry_contract']['linear_stopped'] is True
    assert evidence['odometry_contract']['angular_stopped'] is True
    assert evidence['odometry_contract']['timestamp_fresh'] is False
    assert evidence['normal_reset_pass'] is False
    assert 'odometry:timestamp_fresh' in evidence['normal_reset_failure_reason']
    assert caught.value.reset_failure_reasons==('odometry:timestamp_fresh',)


def test_reset_failure_keeps_restart_fallback_and_persists_primary_reason():
    scenario=ScenarioSpec(width=10,height=10,start=(0,0),goal=(5,2))
    adapter=GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.scenario=scenario;adapter.max_sensor_age_ms=20;adapter.restart_fallbacks=0
    adapter.reset_evidence=[];adapter.episodes_started=0;adapter._active_reset_attempt=None
    adapter.env=_FakeTrainingEnv(scenario)
    adapter._reset_once(20)
    adapter.env.model_only_error='model reset API unavailable'
    adapter.reset(21)
    evidence=adapter.last_reset_evidence
    assert adapter.restart_fallbacks==1
    assert evidence['restart_fallback_used'] is True
    assert evidence['normal_reset_pass'] is False
    assert 'model reset API unavailable' in evidence['restart_fallback_reason']
    assert evidence['primary_reset_attempt']['restart_fallback_used'] is True


def test_actual_set_pose_ack_does_not_override_recorded_body_drift():
    fixture=Path(__file__).parent/'fixtures'/'gazebo_reset_residual_velocity_actual.json'
    data=json.loads(fixture.read_text())
    start=data['requested_pose']
    drifts=[((row['x']-start['x'])**2+(row['y']-start['y'])**2)**.5
            for row in data['failures']]
    assert data['set_pose_response']['data'] is True
    assert data['wheel_odometry']['linear_x']==pytest.approx(0.,abs=1e-9)
    assert all(distance>.02 for distance in drifts)
    assert data['failure_reason']=='Gazebo reset pose was not applied'


def test_actual_five_centimeter_reset_drift_fails_even_with_ack_zero_wheels_and_fresh_sensor():
    fixture=Path(__file__).parent/'fixtures'/'gazebo_reset_residual_velocity_actual.json'
    data=json.loads(fixture.read_text());requested=data['requested_pose']
    scenario=ScenarioSpec(width=10,height=10,start=(1,1),goal=(5,2))
    adapter=GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.scenario=scenario;adapter.max_sensor_age_ms=20;adapter.restart_fallbacks=0
    adapter.reset_evidence=[];adapter.episodes_started=0;adapter._active_reset_attempt=None
    fake=_FakeTrainingEnv(scenario);fake.pose.update(x=requested['x'],y=requested['y'])
    fake.pose_start=(requested['x'],requested['y'])
    fake.drift_on_refresh=data['failures'][1]['x']-requested['x']
    fake.controller.last_pose_request={'accepted':True,'response':data['set_pose_response']}
    adapter.env=fake
    with pytest.raises(GazeboTrainingInfrastructureError,match='pose_or_body_settle_outside_existing_tolerance') as error:
        adapter._reset_once(13)
    message=str(error.value)
    assert "'data': True" in message
    assert 'zero_command_displacement' in message
    assert fake.read_odometry()['linear_x']==pytest.approx(0.)
    assert fake.sensors.frame.age_ms==0.


def test_fresh_sensor_and_zero_wheel_odom_do_not_hide_world_body_residual_velocity():
    scenario=ScenarioSpec(width=10,height=10,start=(0,0),goal=(5,2))
    adapter=GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.scenario=scenario;adapter.max_sensor_age_ms=20;adapter.restart_fallbacks=0
    adapter.reset_evidence=[];adapter.episodes_started=0;adapter._active_reset_attempt=None
    fake=_FakeTrainingEnv(scenario);fake.drift_on_refresh=.003;adapter.env=fake
    with pytest.raises(GazeboTrainingInfrastructureError,match='actual_world_body_residual_velocity_unavailable_or_moving') as error:
        adapter._reset_once(12)
    evidence=error.value.args[0]
    assert 'body_residual_velocity_stopped' in evidence
    assert fake.sensors.frame.age_ms==0.
    assert fake.read_odometry()['linear_x']==0.


def test_stale_actual_sensor_is_infrastructure_failure():
    scenario = ScenarioSpec(width=10, height=10, start=(0, 0), goal=(5, 2))
    adapter = GazeboPhysicsTrainingEnvironment.__new__(GazeboPhysicsTrainingEnvironment)
    adapter.max_sensor_age_ms = 20
    adapter.env = SimpleNamespace(stepper=SimpleNamespace(time=1.), sensors=SimpleNamespace(
        frame=SimpleNamespace(source="gazebo_lidar")))
    stale = _observation(sequence=1, timestamp=.5)
    with pytest.raises(GazeboTrainingInfrastructureError, match="fresh") as error:
        adapter._require_actual_sensor(stale)
    assert error.value.category == "stale_sensor"

