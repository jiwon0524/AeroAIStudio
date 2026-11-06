"""Offline recorder tests. Fake contexts only, no DART World/Gazebo stepping."""
import json,struct,subprocess
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]
S=R/'work/trace-source'

def decode(r):return [struct.unpack('>d',bytes.fromhex(v))[0] for v in r['data_bits']]
@pytest.fixture(scope='session')
def fixture(tmp_path_factory):
 p=tmp_path_factory.mktemp('recorder')/'fixture'
 cmd=['g++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-I'+str(S),str(R/'tests/recorder_fixture.cpp'),str(S/'dart/external/odelcpsolver/internal_trace.cpp'),'-o',str(p)]
 subprocess.run(cmd,check=True,capture_output=True,text=True)
 return p

def run(fixture,tmp_path,mode):
 p=tmp_path/(mode+'.json');res=subprocess.run([str(fixture),mode,str(p)],capture_output=True,text=True,check=True)
 return p,res

def test_default_off(fixture,tmp_path):
 p,_=run(fixture,tmp_path,'disabled');assert not p.exists()
def test_bad_config_rejected(fixture,tmp_path):
 p,_=run(fixture,tmp_path,'bad_config');assert not p.exists()
def test_snapshot_stride_and_copy(fixture,tmp_path):
 p,_=run(fixture,tmp_path,'normal');d=json.loads(p.read_text());assert d['window_complete'] and d['steps']==5
 assert d['time_alignment']=='UNVERIFIED_DART_FRAME_ONLY'
 for row in d['records']:
  if row['kind']=='A0':assert decode(row) in [[2.,.25],[.25,3.]]
  if row['kind']=='b0':assert decode(row)==[1.,2.]
  if row['kind']=='findex0':assert decode(row)==[-1,0]
 assert {r['step'] for r in d['records']}==set(range(10,15))
 assert all(r['source'] for r in d['records'])
 assert len({r['assembly'] for r in d['records'] if r['kind']=='assembly_begin'})==5
 assert all(999 not in decode(r) for r in d['records'])
def test_ieee_bits(fixture,tmp_path):
 p,_=run(fixture,tmp_path,'normal');d=json.loads(p.read_text());v=next(r for r in d['records'] if r['kind']=='special_bits')['data_bits']
 assert v[0]=='8000000000000000' and v[2]=='7ff0000000000000'
 assert decode({'data_bits':[v[1]]})[0]!=decode({'data_bits':[v[1]]})[0]
@pytest.mark.parametrize('mode,bit',[('overflow',1),('thread',2),('interrupted',8),('bad_stride',16),('nested',64),('gap',128)])
def test_faults_never_complete(fixture,tmp_path,mode,bit):
 p,_=run(fixture,tmp_path,mode);d=json.loads(p.read_text());assert d['fault_bits']&bit;assert not d['window_complete']
def test_wrong_world_no_capture(fixture,tmp_path):
 p,_=run(fixture,tmp_path,'wrong_world');d=json.loads(p.read_text());assert not d['window_complete'];assert not d['records']
def test_exclusive_no_overwrite(fixture,tmp_path):
 p=tmp_path/'existing';p.write_text('KEEP');res=subprocess.run([str(fixture),'normal',str(p)],check=True,capture_output=True,text=True);assert res.stdout.startswith('0 ');assert p.read_text()=='KEEP'
def test_deterministic(fixture,tmp_path):
 p,_=run(fixture,tmp_path,'normal');old=p.read_bytes();p.unlink();p,_=run(fixture,tmp_path,'normal');assert p.read_bytes()==old
