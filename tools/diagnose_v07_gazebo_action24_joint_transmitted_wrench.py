#!/usr/bin/env python3
"""Diagnostic-only same-replay joint transmitted-wrench capture for Action24."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from tools import diagnose_v07_gazebo_action24_continuous_support as support
from tools import diagnose_v07_gazebo_action24_wheel_joint_state as joint_diag
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.scenario.models import ScenarioSpec

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "validation/v071-host/gazebo-dqn-full-stage1-post-r2l"
DEFAULT_OUTPUT = ROOT / "validation/v071-host/gazebo-action24-joint-wrench-phase3hag-host1"
SOURCE = ROOT / "tools/gazebo_joint_transmitted_wrench_observer.cc"
PLUGIN = "aero_diagnostic::JointTransmittedWrenchObserver"
JOINTS = ("left_joint", "right_joint")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_observer(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "libaero_joint_transmitted_wrench_observer.so"
    pkg = subprocess.run(["pkg-config", "--cflags", "--libs", "gz-sim8", "gz-physics7", "gz-msgs10"],
                         check=True, text=True, capture_output=True)
    command = ["c++", "-std=c++17", "-shared", "-fPIC", str(SOURCE), "-o", str(library), *shlex.split(pkg.stdout)]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("joint transmitted-wrench observer build failed:\n" + result.stderr[-8000:])
    info = {"command": command, "source_sha256": sha(SOURCE), "library_sha256": sha(library),
            "plugin_library": str(library.resolve()), "compile_stdout": result.stdout, "compile_stderr": result.stderr}
    gz = shutil.which("gz")
    if gz:
        p = subprocess.run([gz, "plugin", "--info", "--plugin", str(library)], text=True, capture_output=True)
        info.update(plugin_info_exit_code=p.returncode, plugin_info_stdout=p.stdout, plugin_info_stderr=p.stderr)
        if p.returncode or PLUGIN not in p.stdout or "ISystemPostUpdate" not in p.stdout:
            raise RuntimeError("plugin registration inspection failed: " + p.stdout + p.stderr)
    ldd = shutil.which("ldd")
    if ldd:
        p = subprocess.run([ldd, "-r", str(library)], text=True, capture_output=True)
        unresolved = [line.strip() for line in (p.stdout + p.stderr).splitlines()
                      if "not found" in line or "undefined symbol" in line]
        info.update(ldd_exit_code=p.returncode, unresolved_dependencies=unresolved)
        if p.returncode or unresolved:
            raise RuntimeError("plugin dependency inspection failed: " + repr(unresolved))
    return library, info


def resolve_joints(root: ET.Element):
    model = root.find(".//model[@name='simple_agent']")
    if model is None:
        raise ValueError("production SDF has no simple_agent model")
    resolved = {}
    for name in JOINTS:
        matches = model.findall(f"joint[@name='{name}']")
        if len(matches) != 1:
            raise ValueError(f"expected exactly one {name}, found {len(matches)}")
        joint = matches[0]
        if joint.get("type") != "revolute":
            raise ValueError(f"{name} is not revolute")
        axis = joint.find("axis/xyz")
        if axis is None or not (axis.text or "").strip():
            raise ValueError(f"{name} has no canonical SDF axis")
        vals = [float(v) for v in (axis.text or "").split()]
        norm = math.sqrt(sum(v*v for v in vals))
        if len(vals) != 3 or not math.isfinite(norm) or norm <= 0:
            raise ValueError(f"{name} axis is invalid")
        resolved[name] = {"parent": joint.findtext("parent"), "child": joint.findtext("child"),
                          "type": joint.get("type"), "axis_xyz": [v/norm for v in vals],
                          "axis_frame": axis.get("expressed_in") or "joint", "axis_unit_length": norm}
    return resolved


def insert_observer(path: Path, library: Path, output: Path, joints: dict):
    root = ET.parse(path).getroot()
    world = root.find("world")
    if world is None:
        raise ValueError("diagnostic SDF has no world")
    if world.find(f"plugin[@name='{PLUGIN}']") is not None:
        raise ValueError("joint transmitted-wrench observer already inserted")
    plugin = ET.SubElement(world, "plugin", {"name": PLUGIN, "filename": str(library.resolve())})
    ET.SubElement(plugin, "model_name").text = "simple_agent"
    ET.SubElement(plugin, "output").text = str(output.resolve())
    for side, name in (("left", "left_joint"), ("right", "right_joint")):
        axis = joints[name]["axis_xyz"]
        ET.SubElement(plugin, f"{side}_axis_xyz").text = ",".join(format(v, ".17g") for v in axis)
        frame = joints[name]["axis_frame"]
        ET.SubElement(plugin, f"{side}_axis_frame").text = frame.replace('"', '')
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return {"plugin_class_name": PLUGIN, "plugin_library": str(library.resolve()),
            "output_ndjson": str(output.resolve()), "world_scoped": True, "joint_axes": joints}


def _make_diagnostic_sdf(artifact_dir: Path, output: Path, library: Path):
    replay = extract_reversal_replay(artifact_dir)
    actions = replay["completed_episode_actions"][0]
    if len(actions) < 24 or actions[22:24] != ["down", "up"]:
        raise ValueError("source evidence lacks deterministic Action23 DOWN → Action24 UP")
    if replay.get("target_action") != "up" or replay.get("previous_action") != "down":
        raise ValueError("source reversal contract mismatch")
    scenario = ScenarioSpec.from_dict(replay["scenario"])
    temp = tempfile.TemporaryDirectory(prefix="phase3hag-preflight-")
    temporary = Path(temp.name)
    production = GazeboWorldGenerator().generate(scenario, temporary, closed_loop=True, control_mode="PHYSICS")
    before_hash = sha(production)
    joints = resolve_joints(ET.parse(production).getroot())
    diagnostic, joint_info = joint_diag.instrument_diagnostic_sdf(production)
    contact_info = __import__("tools.diagnose_v07_gazebo_action24_wheel_ground_contact", fromlist=["instrument_contact_sensors"]).instrument_contact_sensors(diagnostic, production)
    support.support_diag.add_caster_contact_sensors(diagnostic, production, contact_info)
    support.support_diag._validate_observation_sdf(diagnostic, production, joint_info, contact_info)
    plugin_info = insert_observer(diagnostic, library, output / "joint_transmitted_wrench.ndjson", joints)
    prod_root, diag_root = ET.parse(production).getroot(), ET.parse(diagnostic).getroot()
    if support._semantic(prod_root) != support._semantic(diag_root):
        temp.cleanup()
        raise ValueError("diagnostic SDF contains non-observation differences")
    if sha(production) != before_hash:
        temp.cleanup()
        raise ValueError("production SDF changed during diagnostic instrumentation")
    info = {"production_sdf_sha256_before": before_hash, "production_sdf_sha256_after": sha(production),
            "diagnostic_sdf_sha256": sha(diagnostic), "only_observation_additions": True,
            "resolved_joints": joints, "wrench_observer": plugin_info,
            "existing_support_observer_composition": "continuous ContactSensorData observer inserted by H-AC runner"}
    temp.cleanup()
    return info


def preflight(artifact_dir: Path, output: Path):
    artifact_dir, output = artifact_dir.resolve(), output.resolve()
    if not artifact_dir.is_dir():
        raise FileNotFoundError(f"H-AC source artifact directory missing: {artifact_dir}")
    replay = extract_reversal_replay(artifact_dir)
    if not replay.get("scenario"):
        raise ValueError("deterministic production replay evidence missing")
    h_ac_evidence = artifact_dir.parent / "gazebo-action24-continuous-support-phase3hac-retry1"
    if not (h_ac_evidence / "action24_continuous_support.json").is_file():
        raise FileNotFoundError(f"accepted H-AC runtime evidence missing: {h_ac_evidence}")
    output.mkdir(parents=True, exist_ok=True)
    probe = output / ".write-probe"
    probe.write_text("ok", encoding="ascii")
    probe.unlink()
    header = Path("/usr/include/gz/sim8/gz/sim/Joint.hh")
    if not header.is_file() or "EnableTransmittedWrenchCheck" not in header.read_text(encoding="utf-8"):
        raise RuntimeError("installed public Joint transmitted-wrench API unavailable")
    library, build = build_observer(output / "observer_build")
    sdf = _make_diagnostic_sdf(artifact_dir, output, library)
    if not sdf["only_observation_additions"] or sdf["production_sdf_sha256_before"] != sdf["production_sdf_sha256_after"]:
        raise RuntimeError("observation-only SDF integrity check failed")
    report = {"status": "PREFLIGHT_PASS", "gazebo_launched": False, "runtime_evidence_created": False,
              "artifact_dir": str(artifact_dir), "output_dir": str(output),
              "action_sequence": replay["completed_episode_actions"][0][22:24],
              "public_api_header": str(header), "observer_build": build, "sdf_integrity": sdf}
    (output / "joint_wrench_preflight.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def _load_samples(path: Path):
    samples, health = [], []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"nonfinite JSON {value}")))
        (samples if row.get("kind") == "joint_wrench_sample" else health).append(row)
    iterations = [(row["epoch"], row["iteration"]) for row in samples]
    if len(iterations) != len(set(iterations)):
        raise ValueError("duplicate epoch/iteration in joint wrench stream")
    return samples, health


def run(artifact_dir: Path, output: Path):
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty runtime output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    library, build = build_observer(output / "observer_build")
    ndjson = output / "joint_transmitted_wrench.ndjson"
    old = joint_diag.instrument_diagnostic_sdf
    captured = {}
    def instrument(production_sdf):
        diagnostic, info = old(production_sdf)
        root = ET.parse(diagnostic).getroot()
        joints = resolve_joints(root)
        captured["observer"] = insert_observer(diagnostic, library, ndjson, joints)
        return diagnostic, info
    joint_diag.instrument_diagnostic_sdf = instrument
    try:
        result = support.run_diagnostic(artifact_dir, output / "same_replay")
    finally:
        joint_diag.instrument_diagnostic_sdf = old
    if not ndjson.is_file():
        raise RuntimeError("joint transmitted-wrench observer produced no stream")
    samples, health = _load_samples(ndjson)
    report = {"schema_version": "0.7.1", "status": "CAPTURED", "observer_build": build,
              "observer_sdf": captured.get("observer"), "wrench_ndjson": str(ndjson),
              "wrench_sample_count": len(samples), "health_record_count": len(health),
              "samples": samples, "health_records": health,
              "same_run_support_diagnostic": str(output / "same_replay" / "action24_continuous_support.json"),
              "action24_failure_reproduced": result.get("action24_failure_reproduced"),
              "wrench_semantics": "composite joint-transmitted wrench; not motor torque",
              "production_behavior_modified": False, "production_sdf_changed": False, "physics_changed": False}
    (output / "action24_joint_transmitted_wrench.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    report = preflight(args.artifact_dir, args.output) if args.preflight_only else run(args.artifact_dir, args.output)
    print("PREFLIGHT_PASS" if report.get("status") == "PREFLIGHT_PASS" else "Gazebo joint transmitted-wrench diagnostic: " + report["status"])
    print("evidence: " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
