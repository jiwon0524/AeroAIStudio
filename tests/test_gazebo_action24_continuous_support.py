import json
import math
from pathlib import Path
import pytest

from tools.analyze_v07_gazebo_action24_continuous_support import (
    SUPPORTS, analyze_rows, classify_action24_support_case,
    classify_support_state, project_force, strict_load_jsonl)


def _support(state="VALID_EMPTY_CONTACT_SET", contacts=None, entity=10):
    count = 0 if contacts is None else len(contacts)
    if contacts is not None and count:
        state = "VALID_CONTACTS"
    return {"state": state, "component_available": state != "UNAVAILABLE",
            "contact_count": count, "contacts": contacts or [],
            "collision": {"entity_id": entity}}


def _row(iteration, supports=None, paused=False):
    supports = supports or {name: _support(entity=i+10) for i, name in enumerate(SUPPORTS)}
    return {"kind": "support_iteration", "iteration": iteration,
            "sim_time_ns": iteration * 1_000_000, "paused": paused,
            "supports": supports}


def _contact(force=(0, 0, 1), other=99, idx=0, depth=1e-6):
    return {"contact_index": idx,
            "collision1": {"entity_id": 10, "name": "simple_agent::left_wheel::left_collision"},
            "collision2": {"entity_id": other, "name": "ground::body::collision"},
            "pair_classification": "SUPPORT_GROUND",
            "points": [{"point_index": 0, "normal_world": [0, 0, 2],
                        "body_1_force_world_n": list(force), "depth_m": depth}]}


def test_three_state_contract_and_unavailable_does_not_become_zero():
    assert classify_support_state(_support()) == "VALID_EMPTY_CONTACT_SET"
    assert classify_support_state(_support("VALID_CONTACTS", [_contact()])) == "VALID_CONTACTS"
    assert classify_support_state(_support("UNAVAILABLE")) == "UNAVAILABLE"
    assert classify_support_state({"state":"UNAVAILABLE","component_available":True}) == "UNAVAILABLE"


def test_force_projection_normalizes_normal_and_separates_tangent():
    assert project_force([3, 4, 5], [0, 0, 2]) == {"Fn_N": 5.0, "Ft_N": 5.0}
    assert project_force([1, 2, 3], [0, 0, 0]) is None
    assert project_force([math.nan, 0, 0], [0, 0, 1]) is None


def test_multiple_points_sum_and_unexpected_pair_excluded():
    left_contacts = [_contact((0, 0, 2), idx=0), _contact((0, 0, 3), idx=1)]
    left_contacts.append({**_contact((0, 0, 100), idx=2), "pair_classification": "OTHER"})
    supports = {name: _support(entity=i+10) for i, name in enumerate(SUPPORTS)}
    supports["left_wheel"] = _support("VALID_CONTACTS", left_contacts, 10)
    out = analyze_rows([_row(1, supports)], {"one": [0.001, 0.001]})
    phase = out["phases"]["one"]
    assert phase["total_ground_support_fn_N"]["median"] == 5.0
    assert phase["per_support"]["left_wheel"]["ground_contact_point_count"] == 2


def test_empty_is_zero_but_unavailable_makes_total_null():
    empty = analyze_rows([_row(1)], {"one": [0.001, 0.001]})["phases"]["one"]
    assert empty["total_ground_support_fn_N"]["median"] == 0.0
    supports = {name: _support(entity=i+10) for i, name in enumerate(SUPPORTS)}
    supports["left_wheel"] = _support("UNAVAILABLE", entity=10)
    unknown = analyze_rows([_row(1, supports)], {"one": [0.001, 0.001]})["phases"]["one"]
    assert unknown["complete_four_support_iteration_count"] == 0
    assert unknown["total_ground_support_fn_N"]["median"] is None
    assert unknown["per_support"]["left_wheel"]["UNAVAILABLE"] == 1


def test_present_ground_contact_without_force_does_not_fabricate_zero_load():
    supports={name:_support(entity=i+10) for i,name in enumerate(SUPPORTS)}
    supports["left_wheel"]=_support("VALID_CONTACTS",[_contact(force=(math.nan,0,0))],10)
    phase=analyze_rows([_row(1,supports)],{"one":[.001,.001]})["phases"]["one"]
    assert phase["per_support"]["left_wheel"]["Fn_N"]["count"] == 0
    assert phase["per_support"]["left_wheel"]["force_invalid_iteration_count"] == 1
    assert phase["complete_four_support_iteration_count"] == 0
    assert phase["total_ground_support_fn_N"]["median"] is None


def test_paused_and_duplicate_iterations_rejected():
    with pytest.raises(ValueError, match="paused=false"):
        analyze_rows([_row(1, paused=True)], {"one": [0.001, 0.001]})
    with pytest.raises(ValueError, match="duplicate iteration"):
        analyze_rows([_row(1), _row(1)], {"one": [0.001, 0.001]})


def test_exact_four_support_keys_required():
    supports = {name: _support(entity=i+1) for i, name in enumerate(SUPPORTS[:-1])}
    with pytest.raises(ValueError, match="exactly four"):
        analyze_rows([_row(1, supports)], {"one": [0.001, 0.001]})


def test_strict_ndjson_rejects_nonfinite(tmp_path):
    path = tmp_path / "bad.ndjson"
    path.write_text('{"value":NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="nonfinite"):
        strict_load_jsonl(path)


def test_observer_sdf_insertion_is_world_scoped_and_observation_only(tmp_path):
    from tools.diagnose_v07_gazebo_action24_continuous_support import insert_observer
    sdf = tmp_path / "world.sdf"
    sdf.write_text('<sdf version="1.9"><world name="w"><model name="m"/></world></sdf>')
    info = insert_observer(sdf, tmp_path / "observer.so", tmp_path / "samples.ndjson")
    root = __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).parse(sdf).getroot()
    assert root.find("world/plugin[@name='aero_diagnostic::ContinuousSupportObserver']") is not None
    assert info["plugin_scope"] == "world"
    text = sdf.read_text()
    assert "<collision" not in text and "<joint" not in text and "<physics" not in text


def test_all_support_collision_names_resolve_and_missing_fails_loudly():
    from xml.etree import ElementTree as ET
    from tools.diagnose_v07_gazebo_action24_continuous_support import resolve_support_collisions
    links = "".join(f'<link name="{link}"><collision name="{collision}"/></link>'
                    for link, collision in (("left_wheel","left_collision"),
                        ("right_wheel","right_collision"),("front_caster","front_collision"),
                        ("rear_caster","rear_collision")))
    root=ET.fromstring(f'<sdf><world><model name="simple_agent">{links}</model></world></sdf>')
    assert {x["label"] for x in resolve_support_collisions(root)} == set(SUPPORTS)
    rear=root.find(".//link[@name='rear_caster']")
    rear.remove(rear.find("collision"))
    with pytest.raises(ValueError, match="unresolved support collision"):
        resolve_support_collisions(root)


def test_observer_source_uses_only_contact_component_creation_and_postupdate_read():
    source=Path("tools/gazebo_continuous_support_observer.cc").read_text(encoding="utf-8")
    assert "CreateComponent(s.collision, gz::sim::components::ContactSensorData())" in source
    assert source.index("void PreUpdate") < source.index("void PostUpdate")
    assert "Component<gz::sim::components::ContactSensorData>(s.collision)" in source
    assert "SetFriction" not in source and "SetPose" not in source and "SetLinearVelocity" not in source
    # The emit loop is independent of protobuf equality metadata.
    assert "component_content_changed_since_previous_iteration" in source
    assert "for (std::size_t i = 0; i < this->supports.size(); ++i)" in source


def test_reset_epochs_allow_iteration_counter_restart_without_cross_epoch_dedup():
    rows=[_row(5),_row(1)]
    rows[0]["epoch"]=0; rows[1]["epoch"]=1
    out=analyze_rows(rows,{"window":[0.001,0.005]})
    assert out["sample_count"] == 2


def test_phase_windows_are_taken_from_actual_replay_evidence():
    from tools.diagnose_v07_gazebo_action24_native_contact_kinematics import _phase_intervals_from_replay_evidence
    replay={"action23":{"production_telemetry":{"execution_evidence":{"execution_phases":[
        {"phase":"ACQUIRE_LINEAR","start_sim_time":1.25,"end_sim_time":1.35}]}}},
        "action24_production_macro_evidence":{"braking_phase":{"start_sim_time":2.0,"end_sim_time":2.2},
            "acquisition_phase_evidence":{"start_sim_time":2.21,"end_sim_time":2.41}}}
    assert _phase_intervals_from_replay_evidence(replay)=={
        "action23_down_acquisition":(1.25,1.35),"action24_brake":(2.0,2.2),
        "action24_up_acquisition":(2.21,2.41)}


def test_action24_decision_requires_reproduction_and_full_iteration_coverage():
    assert classify_action24_support_case({},False)["verdict"] == "ACTION24_FAILURE_NOT_REPRODUCED"
    assert classify_action24_support_case({},True)["verdict"] == "CONTINUOUS_SUPPORT_RUNTIME_OBSERVATION_INCOMPLETE"


def test_action24_decision_uses_action23_empirical_range_for_redistribution():
    def phase(total, right, caster):
        return {"iteration_count":10,"complete_four_support_iteration_count":10,
            "total_ground_support_fn_N":{"count":10,"p05":total[0],"p95":total[1],"median":total[2]},
            "per_support":{"right_wheel":{"Fn_N":{"exact_zero_count":10 if right==0 else 0}},
                "left_wheel":{"Fn_N":{"p95":5.0,"median":3.0}},
                "front_caster":{"Fn_N":{"p95":5.0,"median":caster}},
                "rear_caster":{"Fn_N":{"p95":5.0,"median":caster}}}}
    data={"phases":{"action23_down_acquisition":phase((23,25,24),2,4.0),
        "action24_up_acquisition":phase((23.5,24.5,24),0,12.0)}}
    assert classify_action24_support_case(data,True)["verdict"] == "ACTION24_RIGHT_LOAD_REDISTRIBUTION_CONFIRMED"


def test_diagnostic_semantic_diff_removes_only_observation_plugins():
    from xml.etree import ElementTree as ET
    from tools.diagnose_v07_gazebo_action24_continuous_support import _semantic
    production=ET.fromstring('<sdf><world name="w"><physics name="p"/><model name="m"><link name="l"><collision name="c"/></link></model></world></sdf>')
    diagnostic=ET.fromstring('<sdf><world name="w"><physics name="p"/><plugin name="aero_diagnostic::ContinuousSupportObserver" filename="observer.so"/><model name="m"><link name="l"><collision name="c"/></link></model></world></sdf>')
    assert _semantic(production)==_semantic(diagnostic)


def test_reset_epoch_records_not_interpolated_and_valid_empty_is_zero():
    rows = [_row(10), _row(11)]
    out = analyze_rows(rows, {"window": [0.01, 0.011]})["phases"]["window"]
    assert out["iteration_count"] == 2
    assert out["complete_four_support_iteration_count"] == 2
    assert out["total_ground_support_fn_N"]["median"] == 0.0
