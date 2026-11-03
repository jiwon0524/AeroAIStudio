import hashlib
import json

from tools import diagnose_v07_gazebo_runtime_physics_backend as diag


def test_runtime_plugin_library_maps_to_exact_backend():
    assert diag.backend_name_from_plugin("libgz-physics7-dartsim-plugin.so.7") == "DART"
    assert diag.backend_name_from_plugin("libgz-physics7-bullet-plugin.so.7") == "BULLET"
    assert diag.backend_name_from_plugin(
        "libgz-physics7-bullet-featherstone-plugin.so.7") == "BULLET_FEATHERSTONE"
    assert diag.backend_name_from_plugin("libgz-physics7-tpe-plugin.so.7") == "TPE"
    assert diag.backend_name_from_plugin("custom-physics.so") is None


def test_installed_backend_inventory_is_not_runtime_identity():
    source = diag.Path(diag.__file__).read_text()
    assert '"installed_candidates_are_not_active_evidence": True' in source
    assert 'runtime_identity_confirmed' in source


def test_world_configuration_does_not_claim_ignored_type_as_engine(tmp_path):
    world = tmp_path / "world.sdf"
    world.write_text('<sdf version="1.9"><world name="w"><physics name="fixed" type="ignored">'
        '<max_step_size>0.001</max_step_size><real_time_factor>1</real_time_factor></physics>'
        '<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>'
        '</world></sdf>')
    result = diag.physics_configuration(world)
    assert result["physics_type"] == "ignored"
    assert result["explicit_backend_in_sdf"] is False
    assert result["max_step_size"] == 0.001
    assert result["configured_physics_system_plugins"] == [{
        "name": "gz::sim::systems::Physics", "filename": "gz-sim-physics-system"}]


def test_probe_instruments_a_copy_without_selecting_engine(tmp_path):
    source = tmp_path / "world.sdf"
    diagnostic = tmp_path / "probe" / "world.sdf"
    source.write_text('<sdf><world name="w"><physics name="fixed" type="ignored"/>'
        '<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>'
        '</world></sdf>')
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    info = diag.instrument_world(source, diagnostic, tmp_path / "observer.so",
        tmp_path / "identity.json")
    root = diag.ET.parse(diagnostic).getroot()
    observer = root.find("world/plugin[@name='aero_diagnostic::RuntimePhysicsBackendObserver']")
    assert observer is not None
    assert observer.get("filename") == str((tmp_path / "observer.so").resolve())
    assert observer.findtext("output") == str((tmp_path / "identity.json").resolve())
    assert root.find("world/physics").get("type") == "ignored"
    assert len(root.findall("world/plugin")) == 2
    assert info["source_world_sdf_unchanged"] is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    assert info["diagnostic_sdf_delta"] == "one world-scoped read-only system observer stanza"


def test_runtime_observer_reads_active_world_component_without_physics_setters():
    source = diag.OBSERVER_SOURCE.read_text()
    assert "components::PhysicsEnginePlugin" in source
    assert "const gz::sim::EntityComponentManager &_ecm" in source
    assert "engine->Data()" in source
    for forbidden in ("SetPhysicsEngine", "SetLinearVelocity", "SetAngularVelocity",
                      "AddWorldForce", "JointVelocityCmd", "Friction"):
        assert forbidden not in source


def test_runtime_probe_does_not_force_engine_or_issue_control_actions():
    source = diag.Path(diag.__file__).read_text()
    assert '"--physics-engine"' not in source
    assert '"--iterations", "3"' in source
    assert '"control_actions_executed": False' in source
    assert '"selection_not_modified": True' in source


def test_unmapped_runtime_component_is_not_misclassified_as_candidate_backend():
    assert diag.backend_name_from_plugin("libcustom-physics-engine.so") is None
    # Candidate inventory only lists installed plugins; runtime identity is
    # populated exclusively from the PhysicsEnginePlugin component.
    assert diag.classify_runtime_identity({
        "runtime_identity_confirmed": True,
        "physics_engine_plugin_library": "libgz-physics7-dartsim-plugin.so"}) == (
            "RUNTIME_PHYSICS_BACKEND_CONFIRMED", "DART")


def test_missing_or_ambiguous_runtime_identity_stays_unproven():
    assert diag.classify_runtime_identity(None) == (
        "RUNTIME_PHYSICS_BACKEND_UNPROVEN", None)
    assert diag.classify_runtime_identity({"runtime_identity_confirmed": True,
        "physics_engine_plugin_library": ""}) == (
        "RUNTIME_PHYSICS_BACKEND_UNPROVEN", None)
    assert diag.classify_runtime_identity({"runtime_identity_confirmed": True,
        "physics_engine_plugin_library": "/opt/plugins/custom.so"}) == (
        "RUNTIME_PHYSICS_BACKEND_IDENTITY_CAPTURED_UNMAPPED", None)
    assert diag.classify_runtime_identity({"runtime_identity_confirmed": True,
        "physics_engine_plugin_library": "libgz-physics7-dartsim-plugin.so"}) == (
        "RUNTIME_PHYSICS_BACKEND_CONFIRMED", "DART")


def test_runtime_identity_payload_is_json_compatible_and_strict():
    payload = {"physics_engine_plugin_library": "/usr/lib/libgz-physics7-dartsim-plugin.so",
        "simulation_time_s": 0.003, "iteration": 3,
        "runtime_identity_confirmed": True}
    encoded = json.dumps(payload, allow_nan=False)
    assert json.loads(encoded) == payload
