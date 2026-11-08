"""Read bytes/ELF metadata only. Never load or execute a target."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / 'validation/gazebo-instrumented-prestep-v1/reports/input_audit.json'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

checks = []
def check(path, expected, role):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    actual = digest(p) if p.is_file() else None
    checks.append(dict(path=str(p), role=role, expected=expected,
                       actual=actual, match=actual == expected))

prior = ROOT / 'validation/gazebo-source-materials-v1/reports'
for row in json.loads((prior / 'source_files.json').read_text()):
    check(row['path'], row['sha256'], 'source_or_fixture')
for row in json.loads((prior / 'download_hashes.json').read_text()):
    check(row['file'], row['sha256'], 'download')
inv = json.loads((ROOT / 'validation/gazebo-source-observation-review-v1/reports/material_inventory.json').read_text())
elfs = []
for role, row in inv['installed'].items():
    check(row['path'], row['sha256'], role)
    notes = subprocess.check_output(['readelf', '-n', row['path']], text=True)
    ids = [s.split('Build ID:')[1].strip() for s in notes.splitlines() if 'Build ID:' in s]
    elfs.append(dict(role=role, path=row['path'], build_ids=ids,
                     expected_build_id=row['build_id'], match=ids == [row['build_id']]))
for row in inv['input_hashes']:
    check(row['path'], row['sha256'], 'existing_evidence_or_marker')
main = Path('/home/jiwon/Projects/AeroAIStudio')
head = subprocess.check_output(['git', '-C', str(main), 'rev-parse', 'HEAD'], text=True).strip()
status = subprocess.check_output(['git', '-C', str(main), 'status', '--short'], text=True)
result = dict(checks=checks, installed_elf_build_ids=elfs,
              main_head_matches=head == inv['main_head'], main_status_matches=status == inv['main_status'],
              scope='selected prior manifests only; not whole tree; no target loading',
              build='BLOCKED_BEFORE_CONFIGURE', target_execution='NOT_PERFORMED')
REPORT.write_text(json.dumps(result, indent=2) + '\n')
assert all(r['match'] for r in checks), 'changed or missing input'
assert all(r['match'] for r in elfs), 'ELF Build ID mismatch'
assert result['main_head_matches'] and result['main_status_matches'], 'main changed'
print(f'PASS: {len(checks)} file hashes, {len(elfs)} ELF Build IDs, main HEAD/status unchanged')
