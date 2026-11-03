import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOL = Path(__file__).parents[1] / "tools" / "diagnose_v07_gazebo_contact_reset.py"
SPEC = importlib.util.spec_from_file_location("diagnose_v07_gazebo_contact_reset", TOOL)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def sample(ready, elapsed=0.0, phase="phase_A_paused_wall_clock"):
    return {"phase": phase, "wall_elapsed_since_reset": elapsed,
            "publisher_visible": ready, "schema_visible": ready,
            "contact_topic_visible": ready, "discovery_error": None}


def decide(rows, *, stats=True, initial=True, **kwargs):
    return diagnostic.classify_verdict(
        {"schema_visible": initial}, {"pass": stats}, [rows], rows, **kwargs)


def complete_rows(ready_by_phase):
    phases = ["phase_A_paused_wall_clock", "phase_B_after_100_iterations", "phase_C_after_settle"]
    return [sample(ready_by_phase[index], index * 2.0, phase)
            for index, phase in enumerate(phases)]


def test_unavailable_then_available_is_transient_with_first_recovery_time():
    rows = [sample(False, 0.0), sample(False, .1), sample(True, .2),
            sample(True, 2.0, "phase_B_after_100_iterations"),
            sample(True, 4.0, "phase_C_after_settle")]
    verdict, recovery, _ = decide(rows)
    assert verdict == "TRANSIENT_READINESS_GAP"
    assert recovery == .2


def test_unavailable_through_all_phases_is_persistent_loss():
    rows = complete_rows([False, False, False])
    assert decide(rows)[0] == "PERSISTENT_PUBLISHER_LOSS"


def test_initially_visible_then_lost_without_recovery_is_not_misreported_as_transient():
    rows = [sample(True, 0.0), sample(False, .1),
            sample(False, 2.0, "phase_B_after_100_iterations"),
            sample(False, 7.6, "phase_C_after_settle")]
    verdict, recovery, reason = decide(rows)
    assert verdict == "PERSISTENT_PUBLISHER_LOSS"
    assert recovery is None
    assert "did not recover" in reason


def test_continuously_available_is_no_publisher_loss():
    rows = complete_rows([True, True, True])
    verdict, recovery, _ = decide(rows)
    assert (verdict, recovery) == ("NO_PUBLISHER_LOSS", 0.0)


@pytest.mark.parametrize("publishers,subscribers,visible,schema,message_type", [
    ([SimpleNamespace(msg_type_name="gz.msgs.Contacts")], [], True, True, "gz.msgs.Contacts"),
    ([SimpleNamespace(msg_type_name="gz.msgs.Pose")], [], True, False, "gz.msgs.Pose"),
    ([SimpleNamespace()], [], True, False, None),
    ([], [SimpleNamespace(msg_type_name="gz.msgs.Contacts")], True, False, None),
    ([], [], False, False, None),
])
def test_topic_schema_readiness_is_separate_from_visibility(publishers, subscribers,
                                                             visible, schema, message_type):
    result = diagnostic.evaluate_topic_info(publishers, subscribers)
    assert result["contact_topic_visible"] is visible
    assert result["schema_visible"] is schema
    assert result["message_type"] == message_type
    assert result["contact_message_observed"] is None
    assert result["message_silence_means_publisher_absence"] is False


def test_contact_event_silence_is_not_publisher_absence():
    result = diagnostic.evaluate_topic_info(
        [SimpleNamespace(msg_type_name="gz.msgs.Contacts")], [])
    assert result["publisher_visible"] and result["schema_visible"]
    assert result["contact_message_observed"] is None


def test_discovery_exception_is_recorded_and_makes_verdict_inconclusive():
    class Node:
        def topic_info(self, topic):
            raise RuntimeError("discovery unavailable")

    env = SimpleNamespace(contact_topic="/contacts", transport=SimpleNamespace(node=Node()))
    row = diagnostic._probe(env, "phase_A_paused_wall_clock", 10.0, .1, 1)
    assert row["discovery_error"] == {"type": "RuntimeError", "message": "discovery unavailable"}
    rows = [row, sample(False, 2.0, "phase_B_after_100_iterations"),
            sample(False, 4.0, "phase_C_after_settle")]
    assert decide(rows)[0] == "INCONCLUSIVE"


def test_timeline_is_ordered_and_first_recovery_uses_wall_elapsed():
    class Clock:
        now = 0.0
        def monotonic(self):
            return self.now
        def sleep(self, amount):
            self.now += amount

    clock = Clock()
    env = SimpleNamespace(
        contact_topic="/contacts",
        transport=SimpleNamespace(
            node=SimpleNamespace(topic_info=lambda _: (
                [] if clock.now < .2 else [SimpleNamespace(msg_type_name="gz.msgs.Contacts")], [])),
            snapshot=lambda _: {"data": {"sim_time": {"sec": 0}, "paused": True}, "sequence": 7},
            cursor=lambda _: 0),
        stepper=SimpleNamespace(topic="/world/w/stats"))
    rows = []
    diagnostic.observe_phase(env, "phase_A_paused_wall_clock", 0.0, .3, .1,
                             monotonic=clock.monotonic, sleep=clock.sleep, timeline=rows)
    assert [row["discovery_attempt"] for row in rows] == [1, 2, 3, 4]
    assert [row["wall_elapsed_since_reset"] for row in rows] == pytest.approx([0, .1, .2, .3])
    assert rows[-1]["stats_receive_sequence"] == 7
    rows.extend([sample(True, 2.0, "phase_B_after_100_iterations"),
                 sample(True, 4.0, "phase_C_after_settle")])
    assert decide(rows)[1] == pytest.approx(.2)


def test_reset_stats_contract_failure_is_inconclusive():
    rows = complete_rows([False, False, False])
    assert decide(rows, stats=False)[0] == "INCONCLUSIVE"


def test_diagnostic_keeps_one_process_and_never_calls_restart(tmp_path, monkeypatch):
    events = []

    class FakeTransport:
        node = SimpleNamespace(topic_info=lambda _: ([SimpleNamespace(msg_type_name="gz.msgs.Contacts")], []))
        def snapshot(self, _):
            return {"data": {"sim_time": {"sec": 0}, "paused": True, "iterations": 0}, "sequence": 2}
        def cursor(self, _):
            return 0

    class FakeEnv:
        def __init__(self, *args, **kwargs):
            self.injected = False
            self.control_mode = "PHYSICS"
            self.world_name = "world_test"
            self.contact_topic = "/contacts"
            self.scenario = SimpleNamespace(start=(1, 1))
            self.transport = FakeTransport()
            self.manager = SimpleNamespace(partition="partition_test", status=lambda: {"pid": 123, "status": "Running"})
            self.controller = SimpleNamespace(
                stop_agent=lambda: events.append("zero"),
                reset_agent_pose=lambda *args: events.append("set_pose"),
                last_pose_request={"payload": {"name": "simple_agent"}})
            self.stepper = SimpleNamespace(
                topic="/world/world_test/stats", time=.1,
                last_verification={"valid": True},
                pause=lambda: events.append("pause"),
                reset_world=lambda: {"stats_reset_contract": {"pass": True}},
                step_simulation=lambda: events.append("step"))
        def launch(self): return {"available": True}
        def prepare(self): pass
        def prepare_contacts(self): pass
        def reset(self, seed): events.append("normal_progression")
        def restart(self, *args): raise AssertionError("diagnostic must not restart Gazebo")
        def close(self): events.append("close")

    monkeypatch.setattr(diagnostic, "GazeboEnvironment", FakeEnv)
    monkeypatch.setattr(diagnostic, "gazebo_status", lambda probe=True: {"detail": "Harmonic test"})
    report = diagnostic.run_diagnostic(tmp_path, phase_seconds=0, poll_interval=.01)
    assert report["status"] == "NO_PUBLISHER_LOSS"
    assert report["process_restart_during_diagnostic"] is False
    assert events.count("step") == 2
    assert events[:4] == ["normal_progression", "zero", "pause", "set_pose"]
    assert events[-1] == "close"
    assert (tmp_path / "contact_reset_diagnostic.json").exists()
    assert (tmp_path / "contact_reset_timeline.json").exists()


def test_existing_contact_provider_publisher_readiness_is_unchanged():
    from aero_ai_studio.gazebo.contact_provider import ContactProvider

    class ProviderTransport:
        def __init__(self): self.waits = []
        def wait_for_topic(self, topic, kind, timeout=None):
            self.waits.append((topic, kind, timeout))
            if timeout == 0: raise TimeoutError("publisher gap")
            return {"message_type": "gz.msgs.Contacts"}
        def subscribe(self, *_): pass
        def cursor(self, _): return 0

    transport = ProviderTransport()
    provider = ContactProvider(transport, "/contacts", "simple_agent")
    with pytest.raises(TimeoutError, match="publisher gap"):
        provider.poll(.1)
    assert transport.waits == [("/contacts", "Contacts", 5), ("/contacts", "Contacts", 0)]
