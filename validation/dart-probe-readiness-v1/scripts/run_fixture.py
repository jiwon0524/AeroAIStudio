"""Only runs the fixed owned Python fixture. This is not a runtime probe launcher."""
import json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
CHILD=BASE/'tests/fixture_child.py'
def run(case):
    if case not in ('normal','exit','signal','timeout','cpu','memory','file'): raise ValueError(case)
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='fixture-',dir=BASE/'work') as folder:
        env={'PATH':'/usr/bin:/bin','LC_ALL':'C','HOME':folder,'TMPDIR':folder,'PYTHONDONTWRITEBYTECODE':'1'}
        with open(Path(folder)/'stdout','wb') as out,open(Path(folder)/'stderr','wb') as err:
            proc=subprocess.Popen(['/usr/bin/python3','-I','-B',str(CHILD),case],cwd=folder,env=env,stdout=out,stderr=err,start_new_session=True)
            timed_out=False
            try: rc=proc.wait(timeout=0.5 if case=='timeout' else 5)
            except subprocess.TimeoutExpired:
                timed_out=True
                os.killpg(proc.pid,signal.SIGKILL) # exclusively our new session
                rc=proc.wait(timeout=2)
        record={'case':case,'pid':proc.pid,'parent_pid':os.getpid(),'returncode':rc,'signal':-rc if rc<0 else None,'timeout':timed_out,'seconds':round(time.monotonic()-started,3),'stdout':(Path(folder)/'stdout').read_text(),'stderr':(Path(folder)/'stderr').read_text(),'max_file_bytes':max(p.stat().st_size for p in Path(folder).iterdir()),'run_directory':folder}
    record['temporary_cleanup']=not Path(folder).exists()
    return record
if __name__=='__main__':
    results=[]
    def check(name,ok): results.append({'test':name,'status':'PASS' if ok else 'FAIL'})
    records=[run(c) for c in ('normal','exit','signal','timeout','cpu','memory','file','normal')]
    n=records[0]; detail=json.loads(n['stdout'].splitlines()[-1])
    check('separate_process',n['pid']!=n['parent_pid']==os.getpid())
    check('normal_exit',n['returncode']==0)
    check('exit_code',records[1]['returncode']==7)
    check('signal',records[2]['signal']==signal.SIGTERM)
    check('wall_timeout',records[3]['timeout'] and records[3]['seconds']<3)
    check('cpu_limit',records[4]['signal']==signal.SIGKILL and not records[4]['timeout'])
    check('memory_limit',records[5]['returncode']==23)
    check('file_limit',records[6]['returncode'] in (24,-signal.SIGXFSZ) and records[6]['max_file_bytes']<=65536)
    check('limits_applied',detail['limits']=={'RLIMIT_CPU':[1,1],'RLIMIT_AS':[134217728]*2,'RLIMIT_FSIZE':[65536]*2,'RLIMIT_NOFILE':[32]*2,'RLIMIT_NPROC':[16]*2,'RLIMIT_CORE':[0,0]})
    check('logs_captured',all('fixture-start' in r['stdout'] and 'fixture-stderr' in r['stderr'] for r in records))
    check('temporary_cleanup',all(r['temporary_cleanup'] for r in records))
    check('restart_after_abort',records[-1]['returncode']==0 and records[-1]['pid']!=records[3]['pid'])
    check('no_dart_gazebo_mapping',detail['maps_clean'])
    check('environment_allowlist',set(detail['environment_keys'])<= {'PATH','LC_ALL','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE','LC_CTYPE'})
    result={'tests':results,'PASS':sum(r['status']=='PASS' for r in results),'FAIL':sum(r['status']=='FAIL' for r in results),'SKIP':0,'records':records,'scope':'independent Python fixture only; no filesystem/network sandbox claim; RLIMIT_NPROC is per UID, not proof of process containment'}
    (BASE/'reports/fixture_test_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('PASS','FAIL','SKIP')}))
    sys.exit(bool(result['FAIL']))
