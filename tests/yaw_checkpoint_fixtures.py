"""Synthetic atomic-checkpoint fixtures, never Host runtime evidence."""
import copy
from tools import gazebo_yaw_checkpoints as cp


def atomic_checkpoint(state,stage='PRE_RPC',marker=None,phase=1000):
    state=copy.deepcopy(state)
    marker=marker or {'iteration':3600,'sim_time_ns':3_600_000_000,'paused':True}
    i,ns=marker['iteration'],marker['sim_time_ns'];identifier=1 if stage=='PRE_RPC' else 2
    links=[]
    for name in ('body','left_wheel','right_wheel'):
        data=state if name=='body' else state['native_wheel_links'][name.removesuffix('_wheel')]
        links.append({'expected_scoped_name':'simple_agent::'+name,'name':'simple_agent::'+name,
            **{key:copy.deepcopy(data[key]) for key in ('position_world_m','orientation_world_xyzw','linear_velocity_world_m_s','angular_velocity_world_rad_s')}})
    native={'iteration':i,'simulation_time_s':ns/1e9,'paused':True,'postupdate_count':phase,'world_entity_id':1,
            'all_link_native_velocities_available':True,'links':links}
    supports={}
    for name,s in state['supports'].items():
        depths=s.get('depths_m',[.000001]);n=len(depths)
        points=[{'depth_m':d,'normal_world':[0.,0.,1.],'position_world_m':[0.,0.,0.],
                 'body_1_force_world_n':[0.,0.,s['Fn_N']/n],'body_2_force_world_n':[0.,0.,-s['Fn_N']/n]} for d in depths]
        supports[name]={'component_available':True,'component_producer_stamp_ns':ns,'state':s['state'],
                        'contacts':[{'pair_classification':'SUPPORT_GROUND','points':points}] if n else []}
    joints={side:{**copy.deepcopy(state['joint_transmitted_wrench'][side]),'state':'VALID_WRENCH','actual_velocity_available':True} for side in ('left','right')}
    raw={'message_kind':cp.KIND,'checkpoint_id':identifier,'world_entity_id':1,'iteration':i,'sim_time_ns':ns,'paused':True,
         'postupdate_count':phase,'update_phase':cp.PHASE,'last_advancing_iteration':i,'last_advancing_time_ns':ns,
         'model_entity_id':2,'model_name':'simple_agent','model_pose':{key:state[key] for key in ('position_world_m','orientation_world_xyzw')},
         'field_sources':{name:'synthetic same-callback current component '+name for name in ('model_pose','native','wheels','support','wrench')},
         'measurement_age_limitation':'Atomic ECM observation, contact/wrench held from last solve, not a new paused solve.',
         'native':native,'support':{'iteration':i,'sim_time_ns':ns,'paused':True,'read_phase_id':phase,'supports':supports},
         'wrench':{'iteration':i,'sim_time_ns':ns,'paused':True,'read_phase_id':phase,**joints},'capture_topic':'/native/test'}
    norm,model=cp.normalize(raw,marker)
    pose={'x':model['position_world_m'][0],'y':model['position_world_m'][1],'z':model['position_world_m'][2],
          'orientation':dict(zip(('x','y','z','w'),model['orientation_world_xyzw'])),'yaw':model['yaw_rad']}
    frame={'header':{'stamp':{'sec':ns//1_000_000_000,'nsec':ns%1_000_000_000}},
           'pose':[{'name':'simple_agent','position':{k:pose[k] for k in ('x','y','z')},'orientation':pose['orientation']}]}
    return {'classification':stage+'_CHECKPOINT_COHERENT','stage':stage,'marker':copy.deepcopy(marker),'raw':raw,
            'state':norm,'model_state':model,'production_Pose_V':{'pose':pose,'frame':frame,'receive_sequence':2,'sim_time_ns':ns},
            'Pose_V_cursor_before_request':1,'latest_native_corroboration':copy.deepcopy(native),
            'request_RPC_history':[{'payload':{},'attempts':[{'response':{'data':True}}],'service':'/native/test/checkpoint'}],
            'request_id':identifier}
