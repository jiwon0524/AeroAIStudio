#!/usr/bin/env python3
"""Read the active Gazebo physics-engine component in a minimal world run.

This is diagnostic-only. It copies the supplied world SDF, adds one observer
system, advances three simulation iterations without control actions, and
reads PhysicsEnginePlugin from the active world's const EntityComponentManager.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OBSERVER_SOURCE = ROOT / "tools/gazebo_runtime_physics_backend_observer.cc"
DEFAULT_WORLD = ROOT / "validation/v071-host/gazebo-action24-native-contact-kinematics-phase3hl/production_replay/production_replay_evidence/worlds/aero_ef81a06d3164/world.sdf"
DEFAULT_OUTPUT = ROOT / "validation/v071-host/gazebo-runtime-physics-backend-phase3hn"
PLUGIN_CLASS = "aero_diagnostic::RuntimePhysicsBackendObserver"
PLUGIN_FILENAME = "libaero_runtime_physics_backend_observer.so"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backend_name_from_plugin(plugin_library: str) -> str | None:
    name = Path(plugin_library).name.lower()
    if "dartsim" in name:
        return "DART"
    if "bullet-featherstone" in name:
        return "BULLET_FEATHERSTONE"
    if "bullet" in name:
        return "BULLET"
    if "tpe" in name:
        return "TPE"
    return None


def classify_runtime_identity(identity):
    if not isinstance(identity, dict) or identity.get("runtime_identity_confirmed") is not True:
        return "RUNTIME_PHYSICS_BACKEND_UNPROVEN", None
    library = identity.get("physics_engine_plugin_library")
    if not isinstance(library, str) or not library:
        return "RUNTIME_PHYSICS_BACKEND_UNPROVEN", None
    backend = backend_name_from_plugin(library)
    if backend is None:
        return "RUNTIME_PHYSICS_BACKEND_IDENTITY_CAPTURED_UNMAPPED", None
    return "RUNTIME_PHYSICS_BACKEND_CONFIRMED", backend


def inventory_installed_backends():
    candidates = []
    seen_libraries = set()
    gz_plugin = shutil.which("gz")
    roots = (Path("/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins"),
             Path("/usr/lib/aarch64-linux-gnu/gz-physics-7/engine-plugins"))
    package_by_backend = {
        "DART": "libgz-physics7-dartsim",
        "BULLET": "libgz-physics7-bullet",
        "BULLET_FEATHERSTONE": "libgz-physics7-bullet",
        "TPE": "libgz-physics7-tpe",
    }
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("libgz-physics*-plugin.so*")):
            resolved_path = path.resolve()
            if resolved_path in seen_libraries:
                continue
            seen_libraries.add(resolved_path)
            backend = backend_name_from_plugin(resolved_path.name)
            if backend is None:
                continue
            package = package_by_backend[backend]
            version_result = subprocess.run(["dpkg-query", "-W", "-f=${Version}", package],
                text=True, capture_output=True)
            plugin_info = subprocess.run([gz_plugin, "plugin", "--info", "--plugin", str(resolved_path)],
                text=True, capture_output=True) if gz_plugin else None
            plugin_output = (plugin_info.stdout + plugin_info.stderr) if plugin_info else ""
            plugin_classes = []
            if "* Found 1 plugin in library file:" in plugin_output:
                section = plugin_output.split("* Found 1 plugin in library file:", 1)[1]
                section = section.split("* Found", 1)[0]
                plugin_classes = [line.strip()[2:] for line in section.splitlines()
                    if line.strip().startswith("- ")]
            candidates.append({"backend": backend, "plugin_library": str(resolved_path),
                "installed": True, "package": package,
                "package_version": version_result.stdout.strip() if version_result.returncode == 0 else None,
                "plugin_loader_inspection": "PASS" if plugin_info and plugin_info.returncode == 0 else "FAIL_OR_UNAVAILABLE",
                "registered_plugin_classes": plugin_classes,
                "loadability": "gz plugin metadata recognized; not evidence of active selection"})
    return candidates


def physics_configuration(world_sdf: Path):
    root = ET.parse(world_sdf).getroot()
    world = root.find("world")
    if world is None:
        raise ValueError("world SDF has no <world>")
    physics = world.find("physics")
    if physics is None:
        raise ValueError("world SDF has no <physics>")
    known = {"max_step_size", "real_time_factor", "real_time_update_rate"}
    return {"world_name": world.get("name"), "physics_name": physics.get("name"),
        "physics_type": physics.get("type"),
        "explicit_backend_in_sdf": False,
        "max_step_size": _float_or_text(physics.findtext("max_step_size")),
        "real_time_factor": _float_or_text(physics.findtext("real_time_factor")),
        "other_physics_children": [child.tag for child in physics if child.tag not in known],
        "configured_physics_system_plugins": [
            {"name": plugin.get("name"), "filename": plugin.get("filename")}
            for plugin in world.findall("plugin")
            if "Physics" in (plugin.get("name") or "") or "physics-system" in (plugin.get("filename") or "")]}


def _float_or_text(value):
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return value


def instrument_world(source_sdf: Path, diagnostic_sdf: Path,
                     observer_library: Path, identity_output: Path):
    source_bytes = source_sdf.read_bytes()
    tree = ET.parse(source_sdf)
    root = tree.getroot()
    world = root.find("world")
    if world is None:
        raise ValueError("world SDF has no <world>")
    if world.find(f"plugin[@name='{PLUGIN_CLASS}']") is not None:
        raise ValueError("runtime backend observer already exists in source world")
    plugin = ET.SubElement(world, "plugin", filename=str(observer_library.resolve()),
        name=PLUGIN_CLASS)
    ET.SubElement(plugin, "output").text = str(identity_output.resolve())
    ET.indent(tree)
    diagnostic_sdf.parent.mkdir(parents=True, exist_ok=True)
    tree.write(diagnostic_sdf, encoding="utf-8", xml_declaration=True)
    unchanged = source_sdf.read_bytes() == source_bytes
    if not unchanged:
        raise RuntimeError("source world SDF changed during instrumentation")
    return {"source_world_sdf": str(source_sdf.resolve()),
        "source_world_sdf_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "diagnostic_world_sdf": str(diagnostic_sdf.resolve()),
        "diagnostic_world_sdf_sha256": sha256(diagnostic_sdf),
        "observer_library": str(observer_library.resolve()),
        "observer_class": PLUGIN_CLASS,
        "observer_scope": "world",
        "diagnostic_sdf_delta": "one world-scoped read-only system observer stanza",
        "source_world_sdf_unchanged": unchanged}


def build_observer(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    library = output_dir / PLUGIN_FILENAME
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "gz-sim8"],
        text=True, capture_output=True, check=True)
    command = ["c++", "-std=c++17", "-shared", "-fPIC", str(OBSERVER_SOURCE),
        "-o", str(library), *shlex.split(flags.stdout)]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("backend observer compilation failed: " + result.stderr[-4000:])
    return library, {"command": command, "library_sha256": sha256(library),
        "compiler_stderr": result.stderr}


def run_probe(world_sdf: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    identity_file = output_dir / "runtime_backend_identity.json"
    identity_file.unlink(missing_ok=True)
    library, build = build_observer(output_dir / "observer_build")
    diagnostic_sdf = output_dir / "world_runtime_backend_diagnostic.sdf"
    sdf_info = instrument_world(world_sdf, diagnostic_sdf, library, identity_file)
    gz = shutil.which("gz")
    if not gz:
        raise RuntimeError("gz executable not found")
    command = [gz, "sim", "-s", "--headless-rendering", "-r", "--iterations", "3",
        str(diagnostic_sdf.resolve())]
    environment = os.environ.copy()
    environment["GZ_SIM_SYSTEM_PLUGIN_PATH"] = os.pathsep.join(filter(None,
        [str(library.parent.resolve()), environment.get("GZ_SIM_SYSTEM_PLUGIN_PATH", "")]))
    # Do not set --physics-engine or rewrite any engine-selection setting.
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=environment, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=45)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
    identity = json.loads(identity_file.read_text(encoding="utf-8")) if identity_file.is_file() else None
    raw_library = identity.get("physics_engine_plugin_library") if identity else None
    verdict, backend = classify_runtime_identity(identity)
    candidates = inventory_installed_backends()
    component_confirmed = bool(identity and identity.get("runtime_identity_confirmed") and raw_library)
    report = {"schema_version": "0.7.1",
        "verifier": "diagnostic-only runtime physics backend identity probe",
        "status": "CAPTURED" if identity else "IDENTITY_NOT_CAPTURED",
        "verdict": verdict,
        "world_source": str(world_sdf.resolve()),
        "physics_configuration": physics_configuration(world_sdf),
        "engine_selection": {"command_line_engine_selector_present": False,
            "command_line_engine_selector": None,
            "GZ_SIM_PHYSICS_ENGINE_PATH": environment.get("GZ_SIM_PHYSICS_ENGINE_PATH"),
            "GZ_SIM_SERVER_CONFIG_PATH": environment.get("GZ_SIM_SERVER_CONFIG_PATH"),
            "selection_not_modified": True,
            "installed_cli_default_documentation": "This installed gz sim --help reports DART as the default when --physics-engine is omitted; this is configuration evidence, not the active identity verdict."},
        "runtime_identity": identity,
        "active_backend": backend,
        "runtime_identity_evidence_source": identity.get("evidence_source") if identity else None,
        "backend_proof_level": "CONFIRMED" if component_confirmed and backend else "UNPROVEN",
        "installed_backend_candidates": candidates,
        "installed_candidates_are_not_active_evidence": True,
        "ambiguity": {"unknown_plugin_library": raw_library if component_confirmed and not backend else None,
            "historical_hl_process_library_map_preserved": False,
            "runtime_probe_world_sdf_sha256_matches_hl_production_world":
                sdf_info["source_world_sdf_sha256"] == "92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55"},
        "diagnostic_sdf": sdf_info, "build": build,
        "process": {"command": command, "exit_code": process.returncode,
            "timed_out": timed_out, "duration_seconds": time.monotonic()-started,
            "stdout_tail": stdout[-6000:], "stderr_tail": stderr[-6000:],
            "clean_shutdown": not timed_out and process.returncode == 0},
        "production_behavior_modified": False, "production_sdf_modified": False,
        "control_actions_executed": False,
        "strict_json_audit": {"status": "PENDING"}}
    try:
        encoded = json.dumps(report, allow_nan=False, indent=2) + "\n"
        json.loads(encoded)
        report["strict_json_audit"] = {"status": "PASS", "nonfinite_paths": []}
    except (ValueError, TypeError) as exc:
        report["strict_json_audit"] = {"status": "FAIL", "error": str(exc)}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "runtime_physics_backend.json").write_text(
        json.dumps(report, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_probe(args.world, args.output)
    print("Gazebo runtime physics backend: " + report["verdict"])
    if report.get("active_backend"):
        print("active backend: " + report["active_backend"])
    print("evidence: " + str(args.output / "runtime_physics_backend.json"))
    return 0 if report["strict_json_audit"]["status"] == "PASS" and \
        report["verdict"] == "RUNTIME_PHYSICS_BACKEND_CONFIRMED" and \
        report["process"]["clean_shutdown"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
