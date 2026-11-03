from types import SimpleNamespace

import pytest

from aero_ai_studio.gazebo.entity_controller import summarize_world_pose_history
from aero_ai_studio.gazebo.physics_controller import PhysicsEntityController
from aero_ai_studio.simulation.action_mapping import physics_transition_requires_world_pose_history
from test_v06 import FakeTransport


def _case(*, mutate_history=None, collision=False, odometry=True, start=.4, end=.5):
    transport=FakeTransport();transport.publish=lambda *args:None
    controller=PhysicsEntityController(transport,'rotation_to_linear_fixture')
    controller.apply_action('right');previous=dict(controller.last_published_command)
    controller.apply_action('down')
    poses=[];yaw=0.;x=1.5
    for index in range(21):
        t=start+index*.005
        poses.append({'simulation_timestamp':t,'world_x':x,'world_y':1.5,
            'world_yaw':yaw})
        if index<20:
            # Residual rightward angular velocity decays across the interval.
            omega=-.8*max(0.,(15-index)/15)
            yaw+=omega*.005
            # Translation is below the ordinary minimum; requested backward
            # body velocity is established in the final actual pose interval.
            if index==19:x-=.0013631948645405328
    history=summarize_world_pose_history(poses,start,end)
    if mutate_history:mutate_history(history)
    before={'x':1.5,'y':1.5,'yaw':0.}
    after={'x':x,'y':1.5,'yaw':yaw}
    odo_before={'timestamp':start,'linear_x':0.,'angular_z':-.8}
    odo_after={'timestamp':end,'linear_x':-.5,'angular_z':0.}
    odo_history=[{'timestamp':start+i*.01,'linear_x':-.5*min(i/2,1.),
        'angular_z':-.8*max(0.,1-i/2)} for i in range(1,10)]
    result=controller.validate_pose(before,after,end-start,collision,odo_before if odometry else None,
        odo_after if odometry else None,odo_history if odometry else [],
        simulation_start_time=start,simulation_end_time=end,previous_command=previous,
        world_pose_history=history)
    return controller,history,result


def test_actual_like_rotation_to_backward_linear_transition_passes_only_body_evidence():
    _,history,result=_case()
    assert history['world_pose_history_fresh'] and history['world_pose_history_dense_enough']
    assert result['command_mode_transition']=='ROTATION_TO_LINEAR'
    assert result['rotation_to_linear_start_angular_velocity']==pytest.approx(-.8)
    assert result['rotation_to_linear_end_angular_velocity']==pytest.approx(0.)
    assert result['rotation_to_linear_angular_decay_valid']
    assert result['rotation_to_linear_angular_stopped']
    assert result['rotation_to_linear_requested_direction_established']
    assert result['rotation_to_linear_final_direction_ok']
    assert result['rotation_to_linear_wheel_response_valid']
    assert result['rotation_to_linear_transient_valid']
    assert result['valid']
    assert result['discrepancy_classification']=='validated_rotation_to_linear_transient'
    assert result['world_direction_raw_ok'] is False


@pytest.mark.parametrize('mutation',[
    lambda h:h.update(world_pose_history_fresh=False),
    lambda h:h.update(world_pose_history_dense_enough=False),
    lambda h:h.update(world_pose_sample_timestamps=[h['world_pose_sample_timestamps'][0],
        h['world_pose_sample_timestamps'][-1]],world_pose_sample_count=2),
    lambda h:h.update(world_pose_sample_timestamps=list(reversed(h['world_pose_sample_timestamps']))),
    lambda h:h.update(world_forward_velocity_samples=[dict(s,forward_velocity=float('nan'))
        for s in h['world_forward_velocity_samples']]),
    lambda h:h.update(world_pose_yaw=[float('inf') for _ in h['world_pose_yaw']]),
])
def test_rotation_to_linear_rejects_stale_sparse_unordered_or_nonfinite_history(mutation):
    _,_,result=_case(mutate_history=mutation)
    assert not result['rotation_to_linear_transient_valid'] and not result['valid']


def test_rotation_to_linear_rejects_wrong_previous_angular_direction():
    def mutate(h):
        for row in h['world_angular_velocity_samples']:
            row['angular_velocity']=row['body_angular_velocity']=abs(row['angular_velocity'])
    _,_,result=_case(mutate_history=mutate)
    assert not result['rotation_to_linear_angular_decay_valid']
    assert not result['rotation_to_linear_transient_valid']


def test_rotation_to_linear_rejects_angular_velocity_that_does_not_decay_or_stop():
    def mutate(h):
        for row in h['world_angular_velocity_samples']:
            row['angular_velocity']=row['body_angular_velocity']=-.8
    _,_,result=_case(mutate_history=mutate)
    assert not result['rotation_to_linear_angular_decay_valid']
    assert not result['rotation_to_linear_transient_valid']


def test_rotation_to_linear_requires_entire_represented_tail_inside_velocity_deadband():
    def mutate(h):
        for row in h['world_angular_velocity_samples']:
            if row['interval_end']>.48 and row['interval_start']<.5 and row['interval_start']>=.48:
                row['angular_velocity']=row['body_angular_velocity']=.03
    _,_,result=_case(mutate_history=mutate)
    assert result['rotation_to_linear_angular_tail_coverage_valid']
    assert not result['rotation_to_linear_angular_decay_valid']
    assert not result['rotation_to_linear_transient_valid']


def test_rotation_to_linear_requires_full_twenty_millisecond_interval_union_coverage():
    _,history,result=_case()
    tail=[row for row in history['world_angular_velocity_samples']
        if row['interval_end']>.48 and row['interval_start']<.5]
    midpoint_only=tail[-1]['simulation_timestamp']-tail[0]['simulation_timestamp']
    assert midpoint_only<.02
    assert result['rotation_to_linear_angular_tail_coverage_valid']
    assert result['rotation_to_linear_angular_tail_coverage_seconds']==pytest.approx(.02)
    assert result['rotation_to_linear_angular_decay_valid']


def test_rotation_to_linear_rejects_actual_interval_union_shorter_than_twenty_ms():
    def mutate(history):
        first=next(row for row in history['world_angular_velocity_samples']
            if row['interval_start']>=.48)
        first['interval_start']+=.001
        first['sample_interval']-=.001
        first['simulation_timestamp']=(first['interval_start']+first['interval_end'])/2
    _,_,result=_case(mutate_history=mutate)
    assert not result['rotation_to_linear_angular_tail_coverage_valid']
    assert not result['rotation_to_linear_angular_decay_valid']
    assert not result['rotation_to_linear_transient_valid']


def test_rotation_to_linear_rejects_missing_requested_body_velocity():
    def mutate(h):
        for row in h['world_forward_velocity_samples']:
            row['forward_velocity']=row['body_forward_velocity']=0.
    _,_,result=_case(mutate_history=mutate)
    assert not result['rotation_to_linear_requested_direction_established']
    assert not result['rotation_to_linear_final_direction_ok']
    assert not result['rotation_to_linear_transient_valid']


def test_rotation_to_linear_rejects_body_ending_in_opposite_direction():
    def mutate(h):
        row=h['world_forward_velocity_samples'][-1]
        row['forward_velocity']=row['body_forward_velocity']=.5
    _,_,result=_case(mutate_history=mutate)
    assert not result['rotation_to_linear_final_direction_ok']
    assert not result['rotation_to_linear_transient_valid']


def test_rotation_to_linear_rejects_wheel_only_evidence_and_collision():
    _,_,without_odom=_case(odometry=False)
    _,_,contact=_case(collision=True)
    assert not without_odom['rotation_to_linear_transient_valid']
    assert not contact['rotation_to_linear_transient_valid']


def test_rotation_to_linear_rejects_excessive_distance_or_yaw():
    # Exercise the same predicate through strict endpoint physical bounds.
    _,_,base=_case()
    assert base['rotation_to_linear_transient_valid']
    transport=FakeTransport();transport.publish=lambda *args:None
    controller=PhysicsEntityController(transport,'rotation_to_linear_fixture')
    controller.apply_action('right');previous=dict(controller.last_published_command)
    controller.apply_action('down')
    poses=[{'simulation_timestamp':.4+i*.005,'world_x':1.5,'world_y':1.5,
        'world_yaw':-.8*i*.005} for i in range(21)]
    history=summarize_world_pose_history(poses,.4,.5)
    # Add requested body motion evidence so only the endpoint bound is decisive.
    for row in history['world_forward_velocity_samples']:
        row['forward_velocity']=row['body_forward_velocity']=-.5
    history['world_start_forward_velocity']=-.5;history['world_end_forward_velocity']=-.5
    odo0={'timestamp':.4,'linear_x':0.,'angular_z':-.8};odo1={'timestamp':.5,'linear_x':-.5,'angular_z':0.}
    odoh=[{'timestamp':.4+i*.01,'linear_x':-.5*min(i/2,1.),
        'angular_z':-.8*max(0.,1-i/2)} for i in range(1,10)]
    far=controller.validate_pose({'x':1.5,'y':1.5,'yaw':0.},{'x':1.8,'y':1.5,'yaw':-.04},.1,
        odometry_before=odo0,odometry_after=odo1,odometry_history=odoh,
        simulation_start_time=.4,simulation_end_time=.5,previous_command=previous,
        world_pose_history=history)
    too_yaw=controller.validate_pose({'x':1.5,'y':1.5,'yaw':0.},{'x':1.5,'y':1.5,'yaw':-.2},.1,
        odometry_before=odo0,odometry_after=odo1,odometry_history=odoh,
        simulation_start_time=.4,simulation_end_time=.5,previous_command=previous,
        world_pose_history=history)
    assert not far['valid'] and not too_yaw['valid']


def test_environment_captures_rotation_to_linear_history_and_keeps_existing_modes():
    rotation={'linear':{'x':0.},'angular':{'z':-.8}}
    backward={'linear':{'x':-.5},'angular':{'z':0.}}
    forward={'linear':{'x':.5},'angular':{'z':0.}}
    assert physics_transition_requires_world_pose_history(rotation,backward)
    assert physics_transition_requires_world_pose_history(forward,backward)
    assert physics_transition_requires_world_pose_history(forward,rotation)
    assert not physics_transition_requires_world_pose_history(rotation,rotation)


@pytest.mark.parametrize('classification,expected_path',[
    ('wheel_odometry_exceeds_world_pose','NORMAL'),
    ('validated_rotation_to_linear_transient','ROTATION_TO_LINEAR_TRANSIENT'),
])
def test_rotation_to_linear_verifier_accepts_normal_or_transient_production_path(
        tmp_path,monkeypatch,classification,expected_path):
    from tools import verify_v07_gazebo_rotation_to_linear as verifier
    from aero_ai_studio.core.storage import read_json

    class FakeEnv:
        def __init__(self,*args,**kwargs):
            self.injected=False;self.control_mode='PHYSICS';self.world_name='fixture'
            self.manager=SimpleNamespace(partition='p',status=lambda:{'status':'Running'})
            self.initialization_checks={'reset_applied':'PASS'};self.pose={'x':1.5,'y':1.5,'yaw':0.}
            self.stepper=SimpleNamespace(time=0.,last_verification={'iteration_delta':100})
            self.sensors=SimpleNamespace(frame=SimpleNamespace(age_ms=0.))
            self.telemetry={};self.contact_topic='/contacts';self.index=0
        def launch(self):return {'available':True}
        def reset(self,seed=None):self.stepper.time=.1
        def step(self,action):
            sequence=['right','right','right','down']
            index=self.index
            assert action==sequence[index];self.index+=1;self.stepper.time+=.1
            validation={'valid':True,'discrepancy_classification':classification}
            mode='OTHER' if index==0 else 'STEADY_ROTATION' if index<3 else 'ROTATION_TO_LINEAR'
            transition={'command_mode_transition':mode,'world_pose_history_summary':{
                'world_pose_history_available':True,'world_pose_history_fresh':True,
                'world_pose_history_dense_enough':True,'world_pose_sample_count':21}}
            self.telemetry={'pose_validation':validation,'action_transition':transition,
                'sensor_age_ms':0.,'contacts':{'new_contact_event':False}}
            self.pose={'x':1.5,'y':1.5,'yaw':0.}
            return SimpleNamespace(terminated=False,truncated=False,reason='moving',reward=0.)
        def close(self):pass
    monkeypatch.setattr(verifier,'GazeboEnvironment',FakeEnv)
    report=verifier.run_verifier(tmp_path,trials=3)
    saved=read_json(tmp_path/'rotation_to_linear_production_verifier.json')
    expected_status=('NORMAL_ACTUAL_VERIFIED_R2L_TRANSIENT_NOT_REPRODUCED'
        if expected_path=='NORMAL' else 'PRODUCTION_VALIDATOR_ACCEPTED_R2L_TRANSIENT')
    assert report['status']==expected_status
    assert saved['uses_production_environment_step'] and saved['uses_production_pose_validator']
    assert saved['action_sequence']==['right','right','right','down']
    assert len(saved['trials'])==3
    assert all(trial['acceptance_path']==expected_path for trial in saved['trials'])
    assert all(trial['production_pose_validation_pass'] for trial in saved['trials'])
    assert all(trial['world_pose_evidence_pass'] for trial in saved['trials'])

