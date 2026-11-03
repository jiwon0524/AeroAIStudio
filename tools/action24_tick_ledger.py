"""Diagnostic JSON and incremental-ledger contracts; no Gazebo dependencies."""
import json
import math
import os
import tempfile
from pathlib import Path


def json_value(value):
    """Losslessly normalize JSON sequences; reject unsupported values/keys."""
    if value is None or type(value) in (str,bool,int):return value
    if type(value) is float and math.isfinite(value):return value
    if isinstance(value,(list,tuple)):return [json_value(v) for v in value]
    if isinstance(value,dict) and all(type(k) is str for k in value):
        return {k:json_value(v) for k,v in value.items()}
    raise ValueError('unsupported/nonfinite JSON value or non-string key')


def atomic_json(path,value,validator=None):
    """Validate before replacement, fsync data and directory, check disk content."""
    path=Path(path);normalized=json_value(value)
    if validator:validator(normalized)
    encoded=json.dumps(normalized,indent=2,allow_nan=False)+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        actual=json.loads(Path(name).read_text())
        if actual!=normalized:raise ValueError('incomplete result serialization: '+str(path))
        if validator:validator(actual)
        os.replace(name,path)
        directory_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
        if json.loads(path.read_text())!=normalized:
            raise ValueError('incomplete result serialization: '+str(path))
    finally:
        if Path(name).exists():Path(name).unlink()


def new_ledger(schedule,schedule_digest,protocol_digest):
    return {'schema_version':2,'frozen_schedule_digest':schedule_digest,
        'protocol_digest':protocol_digest,'block_state':'IN_PROGRESS',
        'slots':[{**slot,'state':'SCHEDULED','transitions':['SCHEDULED']} for slot in schedule]}


def validate_ledger(value,schedule,schedule_digest,protocol_digest):
    if (value.get('schema_version')!=2 or value.get('frozen_schedule_digest')!=schedule_digest or
        value.get('protocol_digest')!=protocol_digest or len(value.get('slots',[]))!=25):
        raise ValueError('ledger frozen structure mismatch')
    for expected,slot in zip(schedule,value['slots']):
        if any(slot.get(k)!=v for k,v in expected.items()):raise ValueError('ledger slot/order mismatch')
        state=slot.get('state');transitions=slot.get('transitions')
        if not isinstance(transitions,list) or not transitions or transitions[0]!='SCHEDULED' or transitions[-1]!=state:
            raise ValueError('ledger lifecycle mismatch')
        allowed={'SCHEDULED':('STARTED',),'STARTED':('CAPTURED','CAPTURE_INVALID'),
                 'CAPTURED':('SHUTDOWN_PROVEN','FINALIZED'),
                 'CAPTURE_INVALID':('SHUTDOWN_PROVEN','FINALIZED'),
                 'SHUTDOWN_PROVEN':('FINALIZED',),'FINALIZED':()}
        if state not in allowed or any(b not in allowed.get(a,()) for a,b in zip(transitions,transitions[1:])):
            raise ValueError('ledger invalid transition')
        if state=='SCHEDULED':
            if set(slot)!=set(expected)|{'state','transitions'}:raise ValueError('future slot contains runtime fields')
            continue
        if type(slot.get('started_wall_monotonic_s')) not in (int,float):raise ValueError('started timestamp missing')
        if state=='STARTED':continue
        outcome=slot.get('capture_outcome')
        if outcome not in ('CAPTURED','CAPTURE_INVALID'):raise ValueError('capture outcome missing')
        if not isinstance(slot.get('artifact_paths'),dict):raise ValueError('artifact paths missing')
        if outcome=='CAPTURED' and not slot['artifact_paths'].get('case_result'):
            raise ValueError('captured result path missing')
        if outcome=='CAPTURE_INVALID' and not slot.get('invalid_reasons'):raise ValueError('capture reason missing')
        if 'SHUTDOWN_PROVEN' in transitions and slot.get('shutdown_proven') is not True:
            raise ValueError('shutdown evidence missing')
        if state=='FINALIZED':
            result=slot.get('result')
            if not isinstance(result,dict) or type(result.get('case_valid')) is not bool:
                raise ValueError('incomplete FINALIZED result')
            if result.get('case_id')!=expected['case_id'] or not isinstance(slot.get('process_lifecycle'),dict):
                raise ValueError('incomplete FINALIZED identity/lifecycle')
            if result['case_valid']:
                analysis=result.get('analysis')
                required=('case_id','tick_count','classification','native_displacement_m','Pose_V_displacement_m',
                    'final_forward_velocity_m_s','support_recovery_ms','events','T0','S0','S1',
                    'S1_minus_S0','event_relative_trajectory')
                if result.get('status')!='VALID' or not isinstance(analysis,dict) or any(k not in analysis for k in required):
                    raise ValueError('incomplete FINALIZED case analysis')
                if analysis['case_id']!=expected['case_id'] or analysis['tick_count']!=expected['tick_count'] or not analysis['event_relative_trajectory']:
                    raise ValueError('incomplete FINALIZED trajectory/identity')
                if slot.get('shutdown_proven') is not True:raise ValueError('valid case shutdown missing')
            elif result.get('status')!='CAPTURE_INVALID' or not result.get('invalid_reasons'):
                raise ValueError('incomplete FINALIZED invalid result')
    block=value.get('block_state')
    if block not in ('IN_PROGRESS','FINISHED','STOPPED_SHUTDOWN_UNPROVEN'):raise ValueError('block state invalid')
    if block=='FINISHED' and any(s['state']!='FINALIZED' for s in value['slots']):
        raise ValueError('unfinished slots in finished block')
