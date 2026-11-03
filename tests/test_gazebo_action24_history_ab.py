import json

from tools import diagnose_v07_gazebo_action24_history_ab as ab


def test_relative_analysis_joins_by_exact_iteration_and_keeps_empty_support():
    case = {
        "events": [{"action": "up", "start_sim_time": 0.999, "up_command_sim_time": 0.999}],
        "support_rows": [{"kind": "support_iteration", "epoch": 2, "iteration": i,
            "sim_time_ns": (1_000_000_000 + (i - 10) * 1_000_000), "paused": False,
            "supports": {"left_wheel": {"state": "VALID_EMPTY_CONTACT_SET", "contact_count": 0}}}
            for i in range(5, 27)],
        "wrench_rows": [{"kind": "joint_wrench_sample", "epoch": 2, "iteration": i,
            "sim_time_ns": 1_000_000_000 + (i - 10) * 1_000_000, "paused": False,
            "left": {"state": "VALID_WRENCH"}, "right": {"state": "VALID_WRENCH"}}
            for i in range(5, 27)],
    }
    report = ab._relative_analysis(case)
    assert report["status"] == "ANALYZED"
    assert report["join_key"] == "(epoch, UpdateInfo.iterations)"
    row = next(r for r in report["relative_rows"] if r["delta_iteration"] == 0)
    assert row["iteration"] == 10
    assert row["exact_support_wrench_same_iteration"] is True
    assert row["support"]["left_wheel"]["state"] == "VALID_EMPTY_CONTACT_SET"


def test_relative_analysis_refuses_nonfinite_ndjson(tmp_path):
    p = tmp_path / "bad.ndjson"
    p.write_text('{"x":NaN}\n', encoding="utf-8")
    try:
        ab._finite_json_rows(p)
    except ValueError as exc:
        assert "nonfinite token" in str(exc)
    else:
        raise AssertionError("nonfinite JSON must fail loudly")


def test_preflight_case_plan_has_same_up_path():
    assert "same GazeboPhysicsTrainingEnvironment.step('up')" in open(
        ab.__file__, encoding="utf-8").read()
    assert ab.PRODUCTION_HASH == "92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55"


def test_pre_up_comparison_reports_numeric_residual_state():
    a = {"pre_up_state": {"available": True, "iteration": 10,
        "support": {"left_wheel": {"Fn_N": 7.0}}, "velocity": [0.0, 0.0, 0.0]}}
    b = {"pre_up_state": {"available": True, "iteration": 20,
        "support": {"left_wheel": {"Fn_N": 0.0}}, "velocity": [0.0, 0.0, 0.0]}}
    report = ab._preup_comparison(a, b)
    assert report["verdict"] == "PRE_UP_STATE_DIFFERENT"
    assert report["numeric_delta_case_b_minus_case_a"]["support.left_wheel.Fn_N"] == -7.0

from types import SimpleNamespace
import pytest


def valid_case(tmp_path, name):
    sdf = tmp_path / (name + '.sdf')
    sdf.write_text('<sdf/>')
    case = {'gazebo_launched': True, 'sdf_path': str(sdf),
        'observer_sdf': {'observation_only': True}, 'reset_completed': True,
        'runtime_sdf_passed_to_gazebo': str(sdf),
        'reset_evidence': {'normal_reset_pass': True,
            'body_residual_velocity_stopped': True, 'odometry_fresh_and_stopped': True},
        'events': [{'action': 'up', 'up_reached': True, 'up_command_sim_time': 1.}],
        'case_result_written': True, 'shutdown_completed': True,
        'runtime_identity': {'partition': name, 'topic': '/native/' + name}}
    for key, kind, stamp, scale in [('support_rows', 'support_iteration', 'sim_time_ns', 1e9),
                                  ('wrench_rows', 'joint_wrench_sample', 'sim_time_ns', 1e9),
                                  ('native_samples', None, 'simulation_time_s', 1.)]:
        case[key] = [{'kind': kind, 'iteration': i, stamp: t * scale, 'paused': False}
                     for i, t in [(1, .999), (2, 1.), (3, 1.001)]]
    return case


@pytest.mark.parametrize('a_valid,b_valid', [(False, False), (True, False), (False, True), (True, True)])
def test_capture_requires_both_cases(tmp_path, a_valid, b_valid):
    a, b = valid_case(tmp_path, 'A'), valid_case(tmp_path, 'B')
    for case, valid in [(a, a_valid), (b, b_valid)]:
        if not valid:
            for key in ('support_rows', 'wrench_rows', 'native_samples'):
                case[key] = []
    assert ab.capture_integrity({'A_clean_up': a, 'B_history_up': b})['both_cases_valid'] is (a_valid and b_valid)


@pytest.mark.parametrize('field', ['partition', 'topic'])
def test_no_stale_runtime_identity(tmp_path, field):
    a, b = valid_case(tmp_path, 'A'), valid_case(tmp_path, 'B')
    b['runtime_identity'][field] = a['runtime_identity'][field]
    assert not ab.capture_integrity({'A_clean_up': a, 'B_history_up': b})['both_cases_valid']


def test_preflight_cannot_count_as_runtime():
    report = {'status': 'PREFLIGHT_PASS', 'gazebo_launched': False,
              'runtime_evidence_created': False}
    assert not ab.validate_case(report)['case_valid']


@pytest.mark.parametrize('stream', ['support_rows', 'wrench_rows', 'native_samples'])
def test_each_stream_must_advance_and_cover_up(tmp_path, stream):
    case = valid_case(tmp_path, 'A')
    case[stream] = [case[stream][0]] * 3
    assert not ab.validate_case(case)['case_valid']


def test_native_topic_timeout_is_explicit_failure(monkeypatch, tmp_path, capsys):
    from aero_ai_studio.gazebo import discovery, diagnostics
    monkeypatch.setattr(discovery, 'discover', lambda *a: {'topics': ['/stale/native']})
    monkeypatch.setattr(diagnostics, 'gazebo_status', lambda **k: {'executable': 'gz'})
    env = SimpleNamespace(env=SimpleNamespace(timeout=0, manager=SimpleNamespace(partition='current')))
    def fail(*args):
        ab._wait_native_topic(env, '/current/native')
    monkeypatch.setattr(ab, 'run', fail)
    assert ab.main(['--output', str(tmp_path)]) == 1
    assert 'CAPTURE_FAILED: TimeoutError: native observer topic timeout: /current/native' in capsys.readouterr().out


def test_case_lifecycle_prepares_before_topic_and_subscribes_before_reset(monkeypatch, tmp_path):
    from aero_ai_studio.training import gazebo_physics
    calls = []
    class FakeEnv:
        def __init__(self, *args, **kwargs):
            self.env = SimpleNamespace(manager=SimpleNamespace(partition='fresh'), process=None,
                prepare=lambda: calls.append('prepare'))
        def close(self):
            calls.append('close')
    monkeypatch.setattr(gazebo_physics, 'GazeboPhysicsTrainingEnvironment', FakeEnv)
    record = ab._run_case('A', False, None, tmp_path / 'world', tmp_path, {}, 1)
    assert calls == ['prepare', 'close']
    assert record['infrastructure_failure']['message'] == 'native observer topic unavailable'
    assert not ab.validate_case(record)['case_valid']


@pytest.mark.parametrize('a_valid,b_valid', [(False, False), (True, False), (False, True), (True, True)])
def test_cli_runtime_status_and_exit_are_gated(monkeypatch, tmp_path, capsys, a_valid, b_valid):
    monkeypatch.setattr(ab, '_build_all', lambda *a: ({}, {}))
    def fake_case(name, history, scenario, root, output, libraries, seed):
        case = valid_case(tmp_path, name)
        if not (b_valid if history else a_valid):
            case['native_samples'] = []
            case['infrastructure_failure'] = {'message': 'native observer topic timeout'}
        return case
    monkeypatch.setattr(ab, '_run_case', fake_case)
    output = tmp_path / 'capture'
    code = ab.main(['--output', str(output)])
    lines = capsys.readouterr().out.splitlines()
    assert code == (0 if a_valid and b_valid else 1)
    assert ('CAPTURED' in lines) is (a_valid and b_valid)
    assert ('CAPTURE_FAILED' in lines) is not (a_valid and b_valid)
    integrity = json.loads((output / 'capture_integrity.json').read_text())
    assert integrity['both_cases_valid'] is (a_valid and b_valid)
    assert not (output / 'history_ab_transition_analysis.json').exists()


def test_instrument_launch_subscribe_discover_reset_shutdown_order(monkeypatch, tmp_path):
    from aero_ai_studio.training import gazebo_physics
    calls = []
    production = tmp_path / 'world.sdf'
    diagnostic = tmp_path / 'diagnostic.sdf'
    monkeypatch.setattr(ab.GazeboWorldGenerator, 'generate', lambda *a, **k: production)
    original = ab.GazeboWorldGenerator.generate
    def instrument(*args):
        calls.append('instrument')
        return diagnostic, {'native': {'topic': '/current/native'}}
    monkeypatch.setattr(ab, '_instrument_world', instrument)
    class Capture:
        subscribed = False
        samples = []
        def __init__(self, *a): pass
        def subscribe(self, env, topic):
            assert env.env.world == diagnostic
            assert topic == '/current/native'
            self.topic = topic
            self.subscribed = True
            calls.append('subscribe')
    monkeypatch.setattr(ab.native, 'NativeVelocityCapture', Capture)
    monkeypatch.setattr(ab, '_wait_native_topic', lambda *a: calls.append('discover'))
    class FakeEnv:
        def __init__(self, *args, **kwargs):
            calls.append('construct')
            self.env = SimpleNamespace(manager=SimpleNamespace(partition='fresh'), process=None,
                                       prepare=self.prepare, transport=SimpleNamespace(node=SimpleNamespace(
                                           unsubscribe=lambda topic: calls.append('unsubscribe'))))
        def prepare(self):
            self.env.world = ab.GazeboWorldGenerator().generate(None, tmp_path, closed_loop=True, control_mode='PHYSICS')
            calls.append('launch_connect')
        def reset(self, seed):
            calls.append('reset_settle')
            raise RuntimeError('test stops after proving subscription precedes reset')
        def close(self): calls.append('shutdown')
    monkeypatch.setattr(gazebo_physics, 'GazeboPhysicsTrainingEnvironment', FakeEnv)
    ab._run_case('A', False, None, tmp_path / 'world', tmp_path, {}, 1)
    assert calls == ['construct', 'instrument', 'launch_connect', 'subscribe', 'discover', 'reset_settle', 'unsubscribe', 'shutdown']
    assert ab.GazeboWorldGenerator.generate is original


def test_braking_publications_cannot_claim_up_acquisition():
    controller = SimpleNamespace(publish_sequence=0, last_published_command={})
    env = SimpleNamespace(env=SimpleNamespace(controller=controller,
        stepper=SimpleNamespace(time=1.), telemetry={}))
    def step(action):
        controller.publish_sequence += 1
        controller.last_published_command = {'linear': {'x': 0.}}
        return SimpleNamespace(execution_evidence={'execution_phases': [
            {'phase': 'ACQUIRE_LINEAR', 'start_sim_time': 1.}]})
    env.step = step
    assert not ab._execute_captured(env, 'up', 'BRAKE_LINEAR_THEN_UP')['up_reached']


def test_diagnostic_exception_cannot_claim_capture(tmp_path):
    case = valid_case(tmp_path, 'A')
    case['events'][0]['exception'] = {'type': 'RuntimeError', 'message': 'setup failed'}
    assert not ab.validate_case(case)['case_valid']


def test_production_zero_after_step_preserves_actual_up_publication():
    controller = SimpleNamespace(publish_sequence=0, last_published_command={})
    env = SimpleNamespace(env=SimpleNamespace(controller=controller,
        stepper=SimpleNamespace(time=1.), telemetry={}))
    def step(action):
        controller.publish_sequence = 2
        controller.last_published_command = {'linear': {'x': 0.}}
        env.env.telemetry['action_transition'] = {'action_publish_sequence': 1,
            'commanded_twist': {'linear': {'x': .5}}, 'action_command_sim_time': 1.}
        env.env.stepper.time = 1.1
        return SimpleNamespace(execution_evidence={})
    env.step = step
    event = ab._execute_captured(env, 'up', 'CLEAN_UP')
    assert event['up_reached']
    assert event['up_command_sim_time'] == 1.
