"""Approved boundary and initial owner-to-terminal chain mocks; no native calls."""
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch,Mock
import copy,json,time
import configuration as Q,coordinator as K,owner as O
C=K._collector

def run(checks):
    def ok(name,value=True):
        assert value,name
        checks.append(dict(case='v9_'+name,status='PASS_STATIC_MOCK'))
    def reject(name,fn):
        try:fn()
        except (ValueError,OSError,KeyError,TypeError):ok(name)
        else:raise AssertionError(name)
    R=Path(__file__).resolve().parents[1]
    import importlib.util
    spec=importlib.util.spec_from_file_location('v9_contract_checks',R/'scripts/candidate_contract.py');F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
    saved=json.loads((R/'reports/candidate_contract.json').read_text())
    c,m,seal=C.channel.S.catalog.load_contract()
    import importlib.util
    spec=importlib.util.spec_from_file_location('mock_classify',R.parent/'gazebo-request-guard-v4/scripts/inputs.py');v4=importlib.util.module_from_spec(spec);spec.loader.exec_module(v4)
    records=v4.classify(m,json.loads((R.parent/'gazebo-request-guard-v3/reports/copy_contract.json').read_text()))
    policy=json.loads((R/'reports/policy.json').read_text())
    groups,total=F.verify(policy,m,records,False)
    ok('all468_contract_paths_not_actual_delivery',len(groups)==303 and saved['actual_delivered_paths_this_phase']==saved['actual_prepared_objects_this_phase']==0)
    ok('known_admission_within_approved_budget',total==2158694400 and Q.ADMISSION_CAP-total==438272)
    ok('exact_largest_object_boundary',Q.admission([Q.OBJECT_CAP])==543981568+131072)
    reject('object_cap_plus_one',lambda:Q.admission([Q.OBJECT_CAP+1]))
    reject('negative_object_size',lambda:Q.admission([-1]))
    reject('higher_object_ceiling',lambda:Q.admission([1],object_cap=Q.OBJECT_CAP+1))
    reject('admission_ceiling_plus_one',lambda:Q.admission([1],budget=Q.ADMISSION_CAP+1))
    sizes=[g['bytes'] for g in groups]
    ok('exact_required_minimum_budget',Q.admission(sizes,budget=total)==total)
    reject('required_budget_minus_one',lambda:Q.admission(sizes,budget=total-1))
    reject('six_large_exceed_budget',lambda:Q.admission([Q.OBJECT_CAP]*6))
    # Every row is checked, including five original groups and all16 aliases.
    for i,row in enumerate(policy['paths']):
        altered=copy.deepcopy(policy);altered['paths'][i]['original']['sha256']='0'*64
        reject('wrong_hash_alias_'+str(i),lambda:F.verify(altered,m,records,False))
    for i,g in enumerate(saved['large_objects']):
        altered=copy.deepcopy(policy);altered['paths']=[r for r in altered['paths'] if r['path'] not in g['aliases']]
        reject('missing_large_object_'+str(i),lambda:F.verify(altered,m,records,False))
        for alias in g['aliases']:
            altered=copy.deepcopy(policy);altered['paths']=[r for r in altered['paths'] if r['path']!=alias]
            reject('missing_large_alias_'+alias,lambda:F.verify(altered,m,records,False))
    for field,value in [('source','/dev/null'),('size',1),('executable',False)]:
        altered=copy.deepcopy(policy)
        # Select shared executable group so alias disagreement always rejects.
        alias=saved['large_objects'][0]['aliases'][0]
        next(r for r in altered['paths'] if r['path']==alias)[field]=value
        reject('alias_'+field+'_substitution',lambda:F.verify(altered,m,records,False))
    compiled=[]
    for row in policy['paths']:
        o=row['original']
        compiled.append('{'+','.join([json.dumps(row['path']),str(o['device'])+'ULL',str(o['inode'])+'ULL',json.dumps(o['sha256']),str(int(row['executable'])),json.dumps(row['source'])])+'},')
    ok('all468_compiled_C_rows_equal_verified_contract',(R/'inputs/allowlist.inc').read_text()=='\n'.join(compiled)+'\n')
    prior=R.parent/'gazebo-request-guard-v8'
    for source in (R/'inputs').iterdir():
        if source.name in ('catalog.c','launch.c','preparation_limits.h'):continue
        ok('unchanged_native_input_'+source.name,source.read_bytes()==(prior/'inputs'/source.name).read_bytes())
    target={k:v for k,t,v in C.placement.target_properties('/proc/10/fd/11')}
    ok('owner_property_exact',Q.owner_properties()=={'MemoryMax':5368709120})
    ok('target_MemoryMax_separate',target['MemoryMax']==['536870912'])
    ok('target_rlimits_exact',target['LimitAS']==['2147483648'] and target['LimitFSIZE']==['1048576'] and target['LimitNOFILE']==['256'])
    def observed(pid):return dict(pid=pid,start=str(pid),cgroup='/owner')
    ok('domain_valid_sibling',Q.domain(10,11,'/target',lambda *a:'5368709120',observed)=='/owner')
    for bound in ('max','536870912','5368709121','0'):
        reject('domain_wrong_bound_'+bound,lambda:Q.domain(10,11,'/target',lambda *a:bound,observed))
    for target_group in ('/owner','/owner/target','/','/owner/sub/target'):
        reject('overlapping_domain_'+target_group,lambda:Q.domain(10,11,target_group,lambda *a:'5368709120',observed))
    reject('collector_outside_bounded_domain',lambda:Q.domain(10,11,'/target',lambda *a:'5368709120',lambda pid:dict(observed(pid),cgroup='/different' if pid==11 else '/owner')))
    reads=[]
    def migrating(pid):
        reads.append(pid);return dict(observed(pid),start='changed' if len(reads)>2 else str(pid))
    reject('domain_PID_reuse',lambda:Q.domain(10,11,'/target',lambda *a:'5368709120',migrating))
    # The initial owner handshake feeds the real Coordinator. OS boundaries and
    # final controller are mocks; real controller/protocol audited in check.py.
    def chain(fault=None):
        events=[]
        cat=S(packet=Mock(side_effect=[True]),closed=False)
        def close():cat.closed=True;events.append('pins_closed')
        cat.close=close
        owner=S(pid=100,start='held',executable_sha256='e'*64,run='test',policy='p'*64)
        unit=S(cgroup='/target')
        ep=S()
        root=S(root=200,root_start='child',pidfd=99,run='test',policy='p'*64)
        class Controller:
            def __init__(self,*args):self.terminal=args[-1];self.collection_s=25
            def run(self):
                if fault=='audit_disconnect':raise ValueError('independent audit disconnected')
                self.terminal();events.append('V' if cat.closed else 'UNSAFE_V');return True
        b=K.BootstrapCoordinator(ep,10,'parent','e'*64,'test','p'*64,policy,records,unit,None,{"protocol":S(Lines=object)},m,(1,2),(1,3),lambda b:None,20,21,lambda r:True,lambda r:True,lambda:events.append('terminal'))
        bind=Mock(side_effect=ValueError('bad owner') if fault=='owner' else None,return_value=owner)
        domain=Mock(side_effect=ValueError('wrong domain') if fault=='domain' else None,return_value='/owner')
        with patch.object(Q,'domain',domain),patch.object(O,'bind',bind),patch.object(K.channel,'Catalog',lambda *a,**kw:cat),patch.object(K.placement,'receive',lambda *a:dict(pid=200,start='child')),patch.object(K.N,'receive_audit',lambda *a:(98,root)),patch.object(K,'session',lambda *a:(None,None,None)),patch.object(K.N.old,'AuditGate',lambda *a:None),patch.object(K.N,'NativeJournal',lambda *a:None),patch.object(K.N,'LiveReader',lambda *a:None),patch.object(K.control,'Controller',Controller):
            if fault=='deadline':b.deadline=time.monotonic()-1
            try:
                assert b.readable() is False and b.phase=='CATALOG'
                assert b.coordinator.deadline==b.deadline
                assert b.readable() is False and b.phase=='PLACEMENT'
                assert b.readable() is False and b.phase=='AUDIT'
                assert b.readable() is True and b.phase=='COLLECTING'
                if fault=='terminal_deadline':b.coordinator.deadline=time.monotonic()-1
                result=b.collect()
            except ValueError:
                assert b.failed
                assert 'V' not in events
                if b.coordinator:assert cat.closed
                if fault=='domain':assert not bind.called
                raise
        assert result and events.index('terminal')<events.index('pins_closed')<events.index('V')
    chain();ok('initial_O_catalog_K_placement_P_audit_A_terminal_cleanup_V_chain')
    for fault in ('owner','domain','deadline','audit_disconnect','terminal_deadline'):reject('bootstrap_fail_closed_'+fault,lambda:chain(fault))
    source=(R/'inputs/launch.c').read_text();header=(R/'inputs/preparation_limits.h').read_text()
    ok('native_preparation_domain_gate_before_bootstrap_prepare',source.index('if(preparation_domain(collector)||owner_control_fds')<source.index('catalog_prepare(',source.index('pid_t candidate_owner_bootstrap')))
    ok('native_both_control_peers_same_domain', 'strcmp(own,other)' in source and 'preparation_group(peer.pid,again' in source)
    ok('native_no_setter_in_domain_gate','setrlimit' not in source[source.index('static int preparation_group'):source.index('int candidate_stage')])
    ok('preparation_limits_explicit',all(str(n) in header for n in (Q.OBJECT_CAP,Q.ADMISSION_CAP,Q.OWNER_MEMORY_MAX)))
    ok('native_truncated_cgroup_line_denied','if(end&&strcmp(group' in source)
    ok('native_owner_bound_uses_approved_constant','PREPARATION_OWNER_MEMORY_MAX);' in source)
    ok('original_entry_still_78',(R/'inputs/entry.c').read_text().endswith('int main(void) { return 78; }\n'))
