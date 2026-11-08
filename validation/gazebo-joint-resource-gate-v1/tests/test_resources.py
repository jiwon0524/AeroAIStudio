"""Synthetic resource and inherited ACK tests; no subject or service execution."""
import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
from resource_gate import ResourceLedger, ResourceSession, ResourceError
sys.path.insert(0, str(ROOT / 'validation/gazebo-joint-resolution-v1/scripts'))
from protocol import AckWindow, HarmlessSession
import supervisor

CASES = []
EXPECTED = {
    'world_parse': {'path': '/input/world.sdf', 'sha256': 'a' * 64, 'inode': 41},
    'schema_closure': {'provider': '/stack/libsdformat.so', 'sha256': 'b' * 64,
                       'version': '1.11', 'include_edges': 135},
    'server_config': {'path': '/input/server.config', 'sha256': 'c' * 64, 'inode': 42},
    'physics_system': {'path': '/stack/physics.so', 'sha256': 'd' * 64, 'inode': 43},
    'dartsim': {'path': '/stack/dartsim.so', 'sha256': 'e' * 64, 'inode': 44},
}


def packet(role):
    return {'kind': 'resource_result', 'role': role, 'selected': copy.deepcopy(EXPECTED[role]),
            'outcome': 'success', 'fallback': False, 'errors': 0, 'closure_complete': True}


def reject(name, operation):
    try:
        operation()
    except (ValueError, OSError) as error:
        CASES.append({'case': name, 'status': 'PASS_REJECTED', 'reason': str(error)})
    else:
        raise AssertionError('accepted ' + name)


def setup(skip=None, change=None):
    writes = []
    window = AckWindow(writes.append,
                       lambda: {'status': 'PASS_FILE_IDENTITY', 'pid': 77, 'start': 's1'},
                       's1', 77)
    session = ResourceSession(EXPECTED, HarmlessSession(window, lambda: True))
    for role in EXPECTED:
        if role == skip:
            continue
        row = packet(role)
        if change and role == change[0]:
            change[1](row)
        session.packet(row)
    return session, window, writes


def ready(s):
    for _ in range(2):
        s.packet({'kind': 'fixture_ready', 'iteration': 0, 'sim_time_ns': 0})


def completion(s, w):
    for i in range(1, 101):
        s.packet({'kind': 'fixture_sample', 'iteration': i, 'sim_time_ns': i * 1000000})
    s.packet({'kind': 'final_wait', 'iteration': 100, 'sim_time_ns': 100000000})
    w.send_ack()


def main():
    s, w, writes = setup(); ready(s); s.authorize(); completion(s, w)
    s.finalize(True, True, 0, True, True, True)
    assert writes == [b'GO\n', b'EXIT_ACK\n']
    CASES.append({'case': 'approved_choices_ACK_EOF_exit', 'status': 'PASS_SYNTHETIC_ONLY'})
    reject('duplicate_GO', s.authorize)
    reject('duplicate_ACK', w.send_ack)
    reject('101st_sample', lambda: s.packet({'kind': 'fixture_sample', 'iteration': 101,
                                           'sim_time_ns': 101000000}))
    reject('failure_cannot_finalize_success', lambda: s.finalize(True, True, 0, True, True, True))
    for name, role, edit in [
        ('required_include_missing', 'schema_closure', lambda r: r.update(closure_complete=False)),
        ('parsing_failure', 'world_parse', lambda r: r.update(errors=1)),
        ('same_basename_other_file', 'world_parse', lambda r: r['selected'].update(path='/other/world.sdf')),
        ('hash_mismatch', 'world_parse', lambda r: r['selected'].update(sha256='f' * 64)),
        ('same_hash_other_inode', 'physics_system', lambda r: r['selected'].update(inode=99)),
        ('plugin_fallback', 'physics_system', lambda r: r.update(fallback=True)),
        ('load_failure', 'dartsim', lambda r: r.update(outcome='failure')),
    ]:
        reject(name, lambda role=role, edit=edit: setup(change=(role, edit)))
    s, w, writes = setup(skip='schema_closure')
    reject('observation_missing', lambda: ready(s)); reject('missing_evidence_GO', s.authorize)
    assert not writes
    s, w, writes = setup(); ready(s)
    reject('late_resource_result', lambda: s.packet(packet('world_parse')))
    reject('latched_resource_failure_GO', s.authorize); assert not writes
    s, w, writes = setup(); ready(s); s.authorize(); completion(s, w)
    reject('EOF_missing', lambda: s.finalize(False, True, 0, True, True, True))
    reject('exit_failed', lambda: s.finalize(True, True, 70, True, True, True))
    s, w, writes = setup(); ready(s); s.authorize()
    for i in range(1, 101):
        s.packet({'kind': 'fixture_sample', 'iteration': i, 'sim_time_ns': i * 1000000})
    s.packet({'kind': 'final_wait', 'iteration': 100, 'sim_time_ns': 100000000})
    reject('ACK_missing', lambda: s.finalize(True, True, 0, True, True, True))
    w.observe = lambda: {'status': 'FAIL', 'pid': 77, 'start': 's1'}
    reject('final_mapping_mismatch', w.send_ack)
    # Existing sealed actual collector still refuses before any side effects.
    with patch.object(supervisor.smoke, 'properties', side_effect=AssertionError('manager queried')), \
         patch.object(supervisor, 'exclusive', side_effect=AssertionError('marker created')), \
         patch.object(supervisor.subprocess, 'Popen', side_effect=AssertionError('service started')):
        reject('existing_actual_launcher_pre_service_refusal', lambda: supervisor.run('actual'))
    # Only execute the refusal-only Python CLI, never a target or service.
    p = subprocess.run([sys.executable, '-I', '-B', str(BASE / 'scripts/preflight.py')],
                       capture_output=True, text=True, check=False)
    row = json.loads(p.stdout)
    assert p.returncode == 78 and row['blockers'] and not any(
        row[k] for k in ['manager_queried', 'service_started', 'marker_created', 'go_sent'])
    CASES.append({'case': 'actual_preflight_exit78', 'status': 'PASS_PRE_SERVICE_REFUSAL'})
    (BASE / 'reports/actual_preflight.json').write_text(p.stdout)
    (BASE / 'reports/tests.json').write_text(json.dumps({'status': 'PASS_STATIC_MOCK_ONLY',
        'cases': CASES, 'native_resource_producer': 'ABSENT', 'subject_execution': False,
        'new_service_starts': 0}, indent=2) + '\n')
    print('PASS', len(CASES), 'synthetic resource/ACK/refusal cases; native producer absent')


if __name__ == '__main__':
    main()
