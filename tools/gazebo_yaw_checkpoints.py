"""Atomic paused diagnostic component checkpoints; never advancing telemetry."""
from __future__ import annotations
import copy
import json
import math
import threading
import time
import xml.etree.ElementTree as ET
from tools import diagnose_v07_gazebo_action24_duration_matched as dm
from aero_ai_studio.gazebo.entity_controller import GazeboEntityController

InvalidCapture = dm.history.InvalidCapture
KIND = 'paused_physical_checkpoint'
PHASE = 'PostUpdate/const_ECM/single_callback'


def invalid(message):
    raise InvalidCapture(message)


def rpy(q):
    x,y,z,w=dm.vector(q,4,'checkpoint quaternion')
    return (math.atan2(2*(w*x+y*z),1-2*(x*x+y*y)),
            math.asin(max(-1.,min(1.,2*(w*y-z*x)))),
            math.atan2(2*(w*z+x*y),1-2*(y*y+z*z)))


def precision(value=1.):
    return 64*math.ulp(max(1.,abs(value)))


def same_pose(a,b):
    av=dm.vector(a.get('position_world_m'),3,'checkpoint model XYZ')
    bv=dm.vector(b.get('position_world_m'),3,'observed current XYZ')
    aq=dm.vector(a.get('orientation_world_xyzw'),4,'checkpoint model quaternion')
    bq=dm.vector(b.get('orientation_world_xyzw'),4,'observed current quaternion')
    sign=1 if sum(x*y for x,y in zip(aq,bq))>=0 else -1
    return (all(abs(x-y)<=precision(max(abs(x),abs(y))) for x,y in zip(av,bv)) and
            all(abs(x-sign*y)<=precision() for x,y in zip(aq,bq)))


def instrument(diagnostic, info):
    tree=ET.parse(diagnostic)
    plugin=tree.find("world/plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']")
    if plugin is None:invalid('checkpoint requires existing native observer')
    service=info['native']['topic']+'/checkpoint'
    ET.SubElement(plugin,'checkpoint_service').text=service
    tree.write(diagnostic,encoding='utf-8',xml_declaration=True)
    info['diagnostic_sdf_sha256']=dm.ab._sha(diagnostic)
    info['native']['diagnostic_sdf_sha256']=info['diagnostic_sdf_sha256']
    info['paused_checkpoint']={'service':service,'request_type':'Empty','response_type':'Boolean',
        'publication_topic':info['native']['topic'],'message_kind':KIND,'observation_only':True,
        'scope':'single native observer PostUpdate const-ECM callback; held contact/wrench semantics explicit'}
    return diagnostic,info


class CaptureMixin:
    def __init__(self,*args,**kwargs):
        self.checkpoints=[]
        self.checkpoint_condition=threading.Condition()
        self.checkpoint_request_id=0
        self.checkpoint_output=None
        super().__init__(*args,**kwargs)

    def receive(self,message,receive_sequence,wall_receive):
        try:row=json.loads(message.get('data',''))
        except (TypeError,ValueError):return super().receive(message,receive_sequence,wall_receive)
        if not isinstance(row,dict) or row.get('message_kind')!=KIND:
            return super().receive(message,receive_sequence,wall_receive)
        row.update(receive_sequence=receive_sequence,wall_receive_monotonic_seconds=wall_receive,
                   capture_topic=self.topic)
        with self.checkpoint_condition:
            if self.checkpoint_output is not None:
                with self.checkpoint_output.open('a') as stream:
                    stream.write(json.dumps(row,allow_nan=False)+'\n')
            self.checkpoints.append(row)
            self.checkpoint_condition.notify_all()
        # Never forward checkpoint records to native_samples / heartbeat physics selection.


def normalize(raw,marker):
    try:
        phase=raw['postupdate_count']
        if (raw.get('message_kind')!=KIND or raw.get('paused') is not True or raw.get('update_phase')!=PHASE or
            type(phase) is not int or phase<=0 or type(raw.get('world_entity_id')) is not int or raw['world_entity_id']<=0 or raw.get('iteration')!=marker['iteration'] or
            raw.get('sim_time_ns')!=marker['sim_time_ns'] or raw.get('last_advancing_iteration')!=marker['iteration'] or
            raw.get('last_advancing_time_ns')!=marker['sim_time_ns'] or raw.get('model_name')!='simple_agent' or
            type(raw.get('model_entity_id')) is not int or raw['model_entity_id']<=0):
            invalid('checkpoint update phase / iteration / model provenance invalid')
        sources=raw['field_sources']
        if set(sources)!={'model_pose','native','wheels','support','wrench'} or not all(isinstance(v,str) and v for v in sources.values()):
            invalid('checkpoint per-category provenance missing')
        if not raw.get('measurement_age_limitation'):
            invalid('checkpoint held-component age limitation missing')
        support,wrench,native=(raw[k] for k in ('support','wrench','native'))
        if native.get('postupdate_count')!=phase or native.get('world_entity_id')!=raw.get('world_entity_id'):
            invalid('native and checkpoint callbacks/world identities disagree')
        for component in (support,wrench,native):
            ns=round(component['simulation_time_s']*1e9) if component is native else component['sim_time_ns']
            if component.get('paused') is not True or component.get('iteration')!=marker['iteration'] or ns!=marker['sim_time_ns']:
                invalid('mixed paused/advancing or mixed-time checkpoint components')
        if any(component.get('read_phase_id')!=phase for component in (support,wrench)):
            invalid('support/wrench checkpoint callback identity mismatch')
        if set(support['supports'])!={'left_wheel','right_wheel','front_caster','rear_caster'}:
            invalid('checkpoint required support component missing')
        for value in support['supports'].values():
            producer=value.get('component_producer_stamp_ns')
            if producer is not None and (type(producer) is not int or producer<0 or producer>marker['sim_time_ns']):
                invalid('contact component producer time invalid/future')
            for contact in value.get('contacts',[]):
                if contact.get('pair_classification')!='SUPPORT_GROUND':invalid('checkpoint non-ground contact')
                for point in contact['points']:
                    if type(point.get('depth_m')) not in (int,float) or not math.isfinite(point['depth_m']):
                        invalid('checkpoint contact depth missing/nonfinite')
        state=dm.component_state(support,wrench,native)
        model=raw['model_pose']
        if not same_pose(model,state):
            invalid('current model pose and current native chassis pose disagree; no stale substitution')
        roll,pitch,yaw=rpy(model['orientation_world_xyzw'])
        model_state={'position_world_m':list(model['position_world_m']),
            'orientation_world_xyzw':list(model['orientation_world_xyzw']),
            'roll_rad':roll,'pitch_rad':pitch,'yaw_rad':yaw}
        return state,model_state
    except (KeyError,TypeError,ValueError) as exc:
        raise InvalidCapture('incomplete checkpoint: '+str(exc)) from exc


def pose_v_view(pose):
    return {'position_world_m':[pose[k] for k in ('x','y','z')],
            'orientation_world_xyzw':[pose['orientation'].get(k,1. if k=='w' else 0.) for k in ('x','y','z','w')]}


def production_pose_after_request(adapter,cursor,marker,model):
    transport=adapter.env.transport;topic=adapter.env.controller.pose_topic
    deadline=time.monotonic()+adapter.env.timeout
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0:invalid('fresh exact production Pose_V checkpoint corroboration missing')
        frames=transport.messages_after(topic,cursor,timeout=remaining)
        if not frames:invalid('fresh production Pose_V checkpoint frame missing')
        for sequence,frame in frames:
            if sequence<=cursor:invalid('production Pose_V receive cursor did not advance')
            cursor=sequence
            if round(dm.stamp(frame)*1e9)!=marker['sim_time_ns']:
                invalid('production Pose_V checkpoint exact timestamp mismatch')
            candidates=[p for p in frame.get('pose',[]) if p.get('name')=='simple_agent']
            if len(candidates)!=1:continue
            pose=GazeboEntityController.decode_pose(next(iter(candidates)))
            if not same_pose(model,pose_v_view(pose)):
                invalid('production Pose_V and atomic model checkpoint differ at same timestamp')
            return {'pose':pose,'frame':frame,'receive_sequence':sequence,'sim_time_ns':round(dm.stamp(frame)*1e9)}


def acquire(adapter,capture,marker,label):
    if label not in ('PRE_RPC','POST_RPC'):invalid('unknown checkpoint stage')
    pose_cursor=adapter.env.transport.cursor(adapter.env.controller.pose_topic)
    if type(pose_cursor) is not int:invalid('Pose_V checkpoint receive cursor missing')
    capture.checkpoint_request_id+=1;requested_id=capture.checkpoint_request_id
    transport=adapter.env.transport
    rpc_cursor=len(transport.request_history)
    response=transport.request(capture.topic+'/checkpoint','Empty','Boolean',{},max_attempts=1)
    rpc_history=copy.deepcopy(transport.request_history[rpc_cursor:])
    if response.get('data') is not True:invalid('paused checkpoint request rejected')
    deadline=time.monotonic()+adapter.env.timeout
    with capture.checkpoint_condition:
        while not any(r.get('checkpoint_id')==requested_id for r in capture.checkpoints):
            remaining=deadline-time.monotonic()
            if remaining<=0:invalid('paused checkpoint response missing; no advancing fallback')
            capture.checkpoint_condition.wait(remaining)
        matches=[r for r in capture.checkpoints if r.get('checkpoint_id')==requested_id]
        if len(matches)!=1:invalid('duplicate checkpoint identity')
        raw=copy.deepcopy(next(iter(matches)))
    if raw.get('capture_topic')!=capture.topic:invalid('stale checkpoint transport identity')
    state,model=normalize(raw,marker)
    pose_v=production_pose_after_request(adapter,pose_cursor,marker,model)
    latest=not_superseded(capture,{'raw':raw,'model_state':model,'marker':marker})
    return {'classification':label+'_CHECKPOINT_COHERENT','stage':label,'marker':copy.deepcopy(marker),
        'raw':raw,'state':state,'model_state':model,'production_Pose_V':pose_v,'Pose_V_cursor_before_request':pose_cursor,
        'latest_native_corroboration':copy.deepcopy(latest),'request_RPC_history':rpc_history,
        'request_id':requested_id,'scope':'one current const-ECM PostUpdate observation; held component ages explicit; not a fresh paused physics solve'}


def not_superseded(capture,checkpoint):
    marker=checkpoint['marker'];raw=checkpoint['raw'];model=checkpoint['model_state']
    if not capture.samples:invalid('current native checkpoint corroboration missing')
    latest=next(reversed(capture.samples))
    if (latest.get('paused') is not True or latest.get('iteration')!=marker['iteration'] or
        round(latest['simulation_time_s']*1e9)!=marker['sim_time_ns'] or
        latest.get('postupdate_count',-1)<raw['postupdate_count'] or latest.get('world_entity_id')!=raw['world_entity_id']):
        invalid('current native observation does not corroborate checkpoint phase')
    for original in raw['native']['links']:
        name=original['expected_scoped_name']
        current=dm.unique_match(latest.get('links'),lambda link:link.get('expected_scoped_name')==name,'current checkpoint native link')
        if not same_pose(original,current) or any(original[k]!=current[k] for k in ('linear_velocity_world_m_s','angular_velocity_world_rad_s')):
            invalid('checkpoint superseded by newer/current native state; no stale request origin')
    return copy.deepcopy(latest)


def validate(checkpoint,marker,label):
    if checkpoint.get('classification')!=label+'_CHECKPOINT_COHERENT' or checkpoint.get('stage')!=label:
        invalid(label+' coherent checkpoint missing')
    state,model=normalize(checkpoint['raw'],marker)
    if state!=checkpoint.get('state') or model!=checkpoint.get('model_state'):
        invalid('checkpoint normalized state/model changed')
    pv=checkpoint['production_Pose_V']
    if (pv['receive_sequence']<=checkpoint['Pose_V_cursor_before_request'] or pv['sim_time_ns']!=marker['sim_time_ns'] or
        not same_pose(model,pose_v_view(pv['pose'])) or round(dm.stamp(pv['frame'])*1e9)!=marker['sim_time_ns']):
        invalid('fresh checkpoint Pose_V corroboration invalid')
    latest=checkpoint['latest_native_corroboration']
    not_superseded(type('CaptureEvidence',(),{'samples':[latest]})(),checkpoint)
    rpc=checkpoint.get('request_RPC_history')
    if (not isinstance(rpc,list) or len(rpc)!=1 or rpc[0].get('payload')!={} or len(rpc[0].get('attempts',[]))!=1 or
        checkpoint['raw'].get('checkpoint_id')!=checkpoint.get('request_id') or rpc[0].get('service')!=checkpoint['raw'].get('capture_topic','')+'/checkpoint'):
        invalid('checkpoint RPC/identity proof invalid')
    return state,model
