"""Compare same-profile noninstrumented and instrumented native algebra paths.
No World::step or Gazebo. Fixtures reviewed before execution.
"""
import subprocess,json,importlib.util
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]
@pytest.mark.parametrize('mode',['primary_true','primary_false','primary_nan','nan_no_fallback','real_dantzig','real_pgs_fallback'])
def test_same_profile_impulses_and_call_order(mode,tmp_path):
 outputs=[]
 for tag,enabled in [('original','off'),('baseline','off'),('trace','off'),('trace','on')]:
  p=subprocess.run([str(R/f'work/{tag}_boxed'),mode,enabled,str(tmp_path/(tag+enabled+'.json'))],capture_output=True,text=True,check=True,timeout=15)
  outputs.append(p.stdout)
 assert len(set(outputs))==1
@pytest.mark.parametrize('continue_error',[False,True])
def test_same_profile_dantzig_failure_return_and_mapping(continue_error,tmp_path):
 outputs=[]
 for tag in ('original','baseline','trace'):
  p=subprocess.run([str(R/f'work/{tag}_failure'),str(tmp_path/(tag+'.json'))]+(['continue'] if continue_error else []),capture_output=True,text=True,check=True,timeout=15)
  outputs.append(p.stdout)
 assert len(set(outputs))==1
