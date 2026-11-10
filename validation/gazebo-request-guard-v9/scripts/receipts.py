"""Source/policy snapshots shared by build and tests. Never executes artifacts."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1];B=R.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def source_files():
    selected=[p for d in ('inputs','scripts','tests') for p in sorted((R/d).iterdir()) if p.is_file() and p.suffix in {'.c','.cc','.h','.hh','.inc','.py'}]
    selected.extend([R/'reports/policy.json',R/'reports/candidate_contract.json'])
    return {str(p.relative_to(B)):sha(p) for p in sorted(selected)}
def external_python():
    paths=set()
    for version in range(1,9):
        paths.update((R.parent/f'gazebo-request-guard-v{version}'/'scripts').glob('*.py'))
    paths.update((R.parent/'gazebo-joint-execution-contract-v1'/'scripts').glob('*.py'))
    paths.update([R.parent/'gazebo-request-guard-v6/tests/check.py',R.parent/'gazebo-joint-execution-contract-v1/tests/test_contract.py'])
    original=json.loads((R.parent/'gazebo-joint-execution-contract-v1/reports/manifest.json').read_text())
    paths.update(Path(p) for p in original['code'] if p.endswith('.py'))
    return {str(p.relative_to(B)):sha(p) for p in sorted(paths)}
def snapshot():
    value=dict(schema=1,files=source_files(),external_python=external_python(),compiled_policy_paths=468,
        object_cap=543979760,preparation_cap=2159132672,owner_memory_max=5368709120,runtime_executed=False)
    value['sha256']=hashlib.sha256(canonical(value)).hexdigest()
    return value

def verify(value):
    expected=dict(value);digest=expected.pop('sha256')
    if hashlib.sha256(canonical(expected)).hexdigest()!=digest or value!=snapshot():raise ValueError('source/policy snapshot changed since build')
    return True

def refresh_build_snapshot():
    """Python/test-only edits do not rebuild unchanged native inputs. Rebind the
    current verified ELF receipt to the exact snapshot used by the next test.
    Retain previous receipts locally; fail on any C dependency/output change.
    """
    path=R/'reports/build_receipt.json';record=json.loads(path.read_text())
    for p,h in record['inputs'].items():
        if sha(p)!=h:raise ValueError('native input changed; rebuild required: '+p)
    for p,h in record['outputs'].items():
        if sha(p)!=h:raise ValueError('native output changed: '+p)
    current=snapshot();history=Path(next(iter(record['outputs']))).parent
    (history/('build_receipt.'+sha(path)+'.json')).write_bytes(path.read_bytes())
    old=R/'reports/source_manifest.json'
    if old.exists():(history/('source_manifest.'+sha(old)+'.json')).write_bytes(old.read_bytes())
    record.update(source_manifest_sha256=current['sha256'],source_hashes=current['files'],external_python_hashes=current['external_python'],
        source_snapshot_refresh='PYTHON_TEST_METADATA_ONLY; native input/output hashes rechecked; no native compilation/link repeated')
    old.write_text(json.dumps(current,indent=2)+'\n');path.write_text(json.dumps(record,indent=2)+'\n')
    return current['sha256']
if __name__=='__main__':print(refresh_build_snapshot())
