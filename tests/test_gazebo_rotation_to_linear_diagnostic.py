from types import SimpleNamespace
import math

import pytest

from aero_ai_studio.core.storage import read_json
from tools import diagnose_v07_gazebo_rotation_to_linear as diagnostic


class _FakeRotationToLinearEnvironment:
    def __init__(self,scenario,**kwargs):
        self.injected=False;self.control_mode=kwargs['control_mode'];self.world_name='fixture_world'
        self.manager=SimpleNamespace(partition='fixture_partition',status=lambda:{'status':'Running','available':True})
        self.initialization_checks={'reset_applied':'PASS'}
        self.stepper=SimpleNamespace(time=0.,last_verification={})
        self.pose={'x':1.5,'y':1.5,'z':.11,'yaw':0.}
        self.telemetry={};self.collision_event=None;self.actions=[];self.events=[]
        self.frames=[];self.mode='fresh';self.target_validator_failure=True
        self.controller=SimpleNamespace(pose_topic='/world/fixture_world/pose/info')
        self.transport=SimpleNamespace(cursor=self._cursor)
        self.controller.pose_history_after=self._history_after

    def launch(self):return {'available':True}
    def reset(self,seed=None):self.stepper.time=.1
    def _cursor(self,topic):
        self.events.append(('cursor',self.stepper.time,topic))
        return len(self.frames)

    def _history_after(self,cursor,start,end):
        return [dict(row) for row in self.frames[cursor:]
            if start-.002<=row['simulation_timestamp']<=end+.002]

    def step(self,action):
        index=len(self.actions);start=self.stepper.time;end=start+.1
        before=dict(self.pose);self.actions.append(action);self.events.append(('action',action,start))
        if action=='right':
            forward_displacement=0.;yaw_delta=-.08
            linear=0.;angular=-.8
            command={'linear':{'x':0.},'angular':{'z':-.8}}
            prior={'linear':{'x':0.},'angular':{'z':-.8}} if index else {'linear':{'x':0.},'angular':{'z':0.}}
        else:
            yaw_delta=(-.085 if index==3 else (-.03 if index==4 else -.01 if index==5 else 0.))
            forward_displacement=(-.001363 if index==3 else -.025 if index==4 else -.04 if index==5 else -.05)
            linear=-.5;angular=0.
            command={'linear':{'x':-.5},'angular':{'z':0.}}
            prior={'linear':{'x':0.},'angular':{'z':-.8}} if index==3 else {'linear':{'x':-.5},'angular':{'z':0.}}
        for sample_index in range(6):
            fraction=sample_index/5
            timestamp=start+.1*fraction
            yaw=before['yaw']+yaw_delta*fraction
            forward=forward_displacement*fraction
            x=before['x']+forward*math.cos(before['yaw'])
            y=before['y']+forward*math.sin(before['yaw'])
            self.frames.append({'simulation_timestamp':timestamp,'world_x':x,'world_y':y,
                'world_yaw':yaw,'receive_sequence':len(self.frames)+1})
        self.pose={'x':self.frames[-1]['world_x'],'y':self.frames[-1]['world_y'],
            'z':.11,'yaw':self.frames[-1]['world_yaw']}
        local=diagnostic.summarize_world_pose_history(self.frames[-6:],start,end)
        odom_before={'timestamp':start,'linear_x':0. if action=='right' else -.5,
                     'angular_z':-.8 if action=='right' or index>=3 else 0.}
        odom_after={'timestamp':end,'linear_x':linear,'angular_z':angular}
        odom_history=[{'timestamp':start+i*.01,'linear_x':linear if i else odom_before['linear_x'],
            'angular_z':angular if i else odom_before['angular_z']} for i in range(1,10)]
        transition={'action':action,'command_mode_transition':(
                diagnostic.classify_physics_command_transition(prior,command)),
            'previous_action_twist':prior,'commanded_twist':command,
            'action_command_sim_time':start,'simulation_duration':.1,
            'before_pose':before,'after_pose':dict(self.pose),
            'world_pose_history':[dict(row) for row in self.frames[-6:]],
            'world_pose_history_summary':local,
            'odometry_before':odom_before,'odometry_after':odom_after,
            'odometry_history':odom_history}
        self.telemetry={'action_transition':transition,
            'pose_validation':{'valid':not (index==3 and self.target_validator_failure),
                               'collision_may_block_motion':False}}
        if self.mode=='collision' and index==3:
            self.collision_event=SimpleNamespace(to_dict=lambda:{'contact':True})
        self.stepper.time=end;self.stepper.last_verification={'iteration_delta':100,
            'expected_iteration_delta':100,'observed_delta':.1}
        if index==3 and self.target_validator_failure:
            raise RuntimeError('Physics movement outside validated tolerance')
        reason='collision' if self.mode=='collision' and index==3 else 'moving'
        if reason=='collision':self.collision_event=SimpleNamespace(to_dict=lambda:{'contact':True})
        return SimpleNamespace(reward=0.,terminated=reason=='collision',truncated=False,reason=reason)

    def close(self):pass


@pytest.fixture
def fake_environment(monkeypatch):
    instances=[]
    class Factory(_FakeRotationToLinearEnvironment):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);instances.append(self)
    monkeypatch.setattr(diagnostic,'GazeboEnvironment',Factory)
    return instances


def test_cursor_precedes_rotation_and_sequence_is_rotation_then_backward_linear(tmp_path,fake_environment):
    report=diagnostic.run_diagnostic(tmp_path)
    env=fake_environment[0]
    assert env.events[0][0]=='cursor'
    assert env.events[0][1]==pytest.approx(.1)
    assert [event[1] for event in env.events if event[0]=='action']==diagnostic.ACTION_SEQUENCE
    assert env.events[0][0]=='cursor' and env.events[1][1]=='right'
    assert report['pose_cursor_sequence_before_rotation']==0
    assert report['target_transition_found']
    target=report['actions'][3]['action_transition']
    assert target['command_mode_transition']=='ROTATION_TO_LINEAR'
    assert target['previous_action_twist']=={'linear':{'x':0.},'angular':{'z':-.8}}
    assert target['commanded_twist']=={'linear':{'x':-.5},'angular':{'z':0.}}


def test_transition_history_contains_actual_body_and_wheel_telemetry(tmp_path,fake_environment):
    report=diagnostic.run_diagnostic(tmp_path);trajectory=report['trajectory']
    assert report['world_pose_history_captured'] and report['world_pose_history_sufficient']
    assert trajectory['timestamps_ordered']
    assert len(trajectory['world_pose_history'])>20
    assert trajectory['body_angular_velocity_history']
    assert trajectory['body_forward_velocity_history']
    assert trajectory['wheel_odometry_history']
    assert trajectory['rotation_before_transition']['body_history_summary']['world_end_angular_velocity']==pytest.approx(-.8)
    assert trajectory['first_significant_requested_backward_body_velocity_time'] is not None
    assert trajectory['world_body_signed_yaw_delta_after_transition']<0
    assert trajectory['world_body_forward_displacement_after_transition']<0
    assert all(row.get('simulation_timestamp') is not None and 'world_x' in row and
               'world_y' in row and 'world_yaw' in row for row in trajectory['world_pose_history'])


def test_validator_failure_is_captured_without_being_converted_to_pass(tmp_path,fake_environment):
    report=diagnostic.run_diagnostic(tmp_path)
    assert report['status']=='CAPTURED_WITH_VALIDATOR_FAILURE'
    assert report['actions'][3]['exception_kind']=='validator_failure'
    assert report['actions'][3]['pose_validation']['valid'] is False


@pytest.mark.parametrize('mode,expected',[
    ('missing','CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY'),
    ('stale','CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY'),
    ('sparse','CAPTURED_WITH_INSUFFICIENT_POSE_HISTORY'),
    ('collision','COLLISION_SAMPLE_REJECTED')])
def test_bad_or_colliding_trajectory_is_not_a_clean_sample(tmp_path,fake_environment,mode,expected):
    env= fake_environment[0] if fake_environment else None
    # The factory instance is created by run_diagnostic; alter its history after
    # the run using a decorator to provide the requested evidence fault.
    original=diagnostic.GazeboEnvironment
    class Altered(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self.mode=mode
        def _history_after(self,cursor,start,end):
            rows=super()._history_after(cursor,start,end)
            if mode=='missing':return []
            if mode=='sparse':return rows[:2]
            if mode=='stale':
                for row in rows:row['simulation_timestamp']-=.1
            return rows
    diagnostic.GazeboEnvironment=Altered
    try:
        report=diagnostic.run_diagnostic(tmp_path)
    finally:
        diagnostic.GazeboEnvironment=original
    assert report['status']==expected
    if mode=='collision':assert report['collision_free_sample'] is False


def test_report_is_saved_with_transition_evidence_and_no_validator_semantic_mutation(tmp_path,fake_environment):
    report=diagnostic.run_diagnostic(tmp_path)
    saved=read_json(tmp_path/'rotation_to_linear_diagnostic.json')
    assert saved['trajectory']['target_transition_classification']=='ROTATION_TO_LINEAR'
    assert saved['production_validator_changed'] is False
    assert saved['dqn_used'] is False and saved['training_used'] is False
    assert report['physics_interval_iterations']==100


def test_nonstandard_physics_interval_is_not_reported_as_valid_trajectory(tmp_path):
    class BadInterval(_FakeRotationToLinearEnvironment):
        def step(self,action):
            try:return super().step(action)
            finally:
                if action=='down':self.stepper.last_verification['iteration_delta']=99
    report=diagnostic.run_diagnostic(tmp_path,env_factory=BadInterval)
    assert report['fixed_physics_intervals_valid'] is False
    assert report['status']=='INVALID_PHYSICS_INTERVAL_EVIDENCE'
