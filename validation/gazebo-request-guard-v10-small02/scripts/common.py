"""Source loading/hash helpers only; no native import or manager operations."""
from pathlib import Path
import importlib.util,hashlib,json,sys,os
R=Path(__file__).resolve().parents[1];B=R.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def need(ok,reason):
    if not ok:raise ValueError(reason)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def json_read(path):return json.loads(Path(path).read_text())
