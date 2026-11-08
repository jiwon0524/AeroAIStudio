"""Hash/identity/XML/readelf checks only. Never load subject shared libraries."""
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
PRIOR = ROOT / 'validation/gazebo-joint-resolution-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    plan = json.loads((PRIOR / 'reports/actual_plan.json').read_text())
    resources = json.loads((PRIOR / 'reports/resources.json').read_text())
    old = json.loads((ROOT / 'validation/gazebo-joint-harness-fix-v1/reports/final_manifest.json').read_text())
    # Reuse the existing pure read-only preservation checker. It checks original
    # main dirty files, old failure evidence, every mount and all 13 receipts.
    sys.path.insert(0, str(PRIOR / 'scripts'))
    from integrity import capture
    preserved = capture(plan)
    for dest, row in plan['mounts'].items():
        require(not Path(row['source']).is_symlink(), 'noncanonical source ' + dest)
        st = os.stat(row['source'])
        require((st.st_dev, st.st_ino) == (row['device'], row['inode']), 'inode ' + dest)
    for path, row in old['ELFs'].items():
        require(sha(path) == row['sha256'], 'old ELF ' + path)
    files = resources['protocol_extension']['files']
    require(len(files) == 129, 'schema file count')
    paths = {r['path'] for r in files}
    edges = []
    for row in files:
        p = Path(row['path']); require(sha(p) == row['sha256'], 'schema SHA ' + str(p))
        for element in ET.parse(p).getroot().iter('include'):
            if 'filename' in element.attrib:
                target = str(p.parent / element.attrib['filename'])
                require(target in paths, 'schema include outside manifest ' + target)
                edges.append({'from': str(p), 'filename': element.attrib['filename']})
    require(edges == resources['protocol_extension']['schema_include_edges'] and len(edges) == 135,
            'schema closure changed')
    template = (ROOT / 'validation/gazebo-joint-codegen-fix-v1/inputs/fixture.hh').read_text()
    xml = template.split('R"AERO(', 1)[1].split(')AERO"', 1)[0]
    rendered = xml.replace('@SYSTEM@', plan['payload'][2]).replace('@ENGINE@', plan['payload'][3])
    require(rendered.encode() == Path(old['world']['path']).read_bytes(), 'embedded/rendered world mismatch')
    world = ET.fromstring(rendered)
    require(not any(list(world.iter(t)) for t in ('include', 'uri', 'mesh', 'heightmap')),
            'unexpected external world resource')
    require(sha(plan['payload'][1]) == '23f5cfb408c12eff76e560101888f5c8437acf5b584b677f82235383c4c5c88b',
            'ACK harness changed')
    require(sha(old['executable']) == 'bd7ce6480b15debab915a69cd9e9a429b92c066063cd31882666617c0a0b3d5a',
            'old harness changed')
    elf_meta = {}
    for path in plan['payload']:
        text = subprocess.check_output(['/usr/bin/readelf', '-n', '-dW', path], text=True)
        elf_meta[path] = {'sha256': sha(path), 'build_id': re.findall(r'Build ID: (\w+)', text),
                          'needed': re.findall(r'Shared library: \[(.*?)\]', text),
                          'runpath': re.findall(r'\(RUNPATH\).*?\[(.*?)\]', text),
                          'rpath': re.findall(r'\(RPATH\).*?\[(.*?)\]', text)}
    summary = json.loads((PRIOR / 'reports/harmless_summary.json').read_text())
    require(summary['status'] == 'PASS_ISOLATION_PATH_ONLY' and summary['physical_steps'] == 0
            and summary['cleanup'] and summary['original_integrity'], 'historical fixture summary')
    require(all(not os.path.lexists(PRIOR / p) for p in plan['outputs'] + plan['one_shot']),
            'actual output/marker exists')
    report = {'status': 'PASS_READ_ONLY_REUSE', 'original_main': preserved['main_head'],
              'original_main_status_hex': preserved['main_status'], 'dangling_symlink': preserved['symlink'],
              'receipt_pairs': len(preserved['receipt']), 'old_ELFs': len(old['ELFs']),
              'mounts': len(plan['mounts']), 'backing_files': len({r['source'] for r in plan['mounts'].values()}),
              'protocol_1_11_files': len(files), 'include_edges': len(edges),
              'embedded_rendered_world_identical': True, 'ELFs': elf_meta,
              'historical_harmless_summary_sha256': sha(PRIOR / 'reports/harmless_summary.json'),
              'historical_harmless_rerun': False, 'new_binary': False, 'subject_execution': False,
              'preserved_hashes': preserved['hashes']}
    (BASE / 'reports/reuse.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS read-only reuse:', report['receipt_pairs'], 'receipt pairs;', report['old_ELFs'],
          'ELFs; 129 schemas/135 edges; world template identical; actual paths absent')


if __name__ == '__main__':
    main()
