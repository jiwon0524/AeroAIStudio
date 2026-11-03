#!/usr/bin/env python3
"""Same-initial-condition clean-UP vs DOWN/BRAKE/UP diagnostic replay.

The runtime mode is Host-only. ``--preflight-only`` builds and validates the
observation-only composition without launching Gazebo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from tools import diagnose_v07_gazebo_action24_continuous_support as support
from tools import diagnose_v07_gazebo_action24_joint_transmitted_wrench as wrench
from tools import diagnose_v07_gazebo_action24_native_contact_kinematics as native
from tools import diagnose_v07_gazebo_action24_wheel_ground_contact as contact
from tools import diagnose_v07_gazebo_action24_wheel_joint_state as joints
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.scenario.models import ScenarioSpec

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "validation/v071-host/gazebo-dqn-full-stage1-post-r2l"
DEFAULT_OUTPUT = ROOT / "validation/v071-host/gazebo-action24-history-ab-phase3hai-host2"
PRODUCTION_HASH = "92def637ff4da2be1348502d345a30721cc845c34704f0b125d4ff1a26fdcc55"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _semantic(node):
    if node.tag == "sensor" and node.get("name") in support.support_diag.DIAGNOSTIC_SENSOR_NAMES:
        return None
    if node.tag == "plugin" and (node.get("name") == "gz::sim::systems::JointStatePublisher" or
                                   "aero_diagnostic::" in node.get("name", "")):
        return None
    children = tuple(x for x in (_semantic(c) for c in node) if x is not None)
    return node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(), children


def _build_all(output):
    output = Path(output)
    support_lib, support_build = support.build_observer(output / "support_observer_build")
    wrench_lib, wrench_build = wrench.build_observer(output / "wrench_observer_build")
    native_lib, native_build = native.build_observer_library(output / "native_observer_build")
    return {"support": support_lib, "wrench": wrench_lib, "native": native_lib}, {
        "support": support_build, "wrench": wrench_build, "native": native_build}


def _instrument_world(production, output, libraries, topic_identity=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    before_hash = _sha(production)
    root = ET.parse(production).getroot()
    resolved = wrench.resolve_joints(root)
    diagnostic, joint_info = joints.instrument_diagnostic_sdf(production)
    contact_info = contact.instrument_contact_sensors(diagnostic, production)
    support.support_diag.add_caster_contact_sensors(diagnostic, production, contact_info)
    support.support_diag._validate_observation_sdf(diagnostic, production, joint_info, contact_info)
    support_info = support.insert_observer(diagnostic, libraries["support"],
                                           output / "continuous_support_iterations.ndjson")
    wrench_info = wrench.insert_observer(diagnostic, libraries["wrench"],
        output / "joint_transmitted_wrench.ndjson", resolved)
    native_info = native.instrument_native_velocity_plugin(diagnostic, production, libraries["native"])
    tree = ET.parse(diagnostic)
    topic_node = tree.find("world/plugin[@name='aero_diagnostic::NativeLinkVelocityObserver']/topic")
    topic_node.text += "/" + (topic_identity or output.name)
    native_info["topic"] = topic_node.text
    tree.write(diagnostic, encoding="utf-8", xml_declaration=True)
    native_info["diagnostic_sdf_sha256"] = _sha(diagnostic)
    required = {"aero_diagnostic::ContinuousSupportObserver": libraries["support"],
                "aero_diagnostic::JointTransmittedWrenchObserver": libraries["wrench"],
                "aero_diagnostic::NativeLinkVelocityObserver": libraries["native"]}
    for plugin_name, library in required.items():
        plugin = tree.find(f"world/plugin[@name='{plugin_name}']")
        if plugin is None or plugin.get("filename") != str(Path(library).resolve()) or not Path(library).is_file():
            raise RuntimeError("missing runtime observer plugin/library: " + plugin_name)
    prod_root, diag_root = ET.parse(production).getroot(), ET.parse(diagnostic).getroot()
    if _semantic(prod_root) != _semantic(diag_root):
        raise ValueError("A/B diagnostic SDF contains non-observation changes")
    if _sha(production) != before_hash or before_hash != PRODUCTION_HASH:
        raise ValueError(f"production SDF hash mismatch or mutation: {before_hash}")
    return diagnostic, {"production_sdf_sha256_before": before_hash,
        "production_sdf_sha256_after": _sha(production), "diagnostic_sdf_sha256": _sha(diagnostic),
        "observation_only": True, "support": support_info, "wrench": wrench_info,
        "native": native_info, "resolved_joints": resolved,
        "joint_state_observer": joint_info, "support_contact_sensors": contact_info}


def preflight(artifact_dir, output):
    artifact_dir, output = Path(artifact_dir).resolve(), Path(output).resolve()
    if not artifact_dir.is_dir():
        raise FileNotFoundError(f"deterministic Action24 source artifact missing: {artifact_dir}")
    replay = extract_reversal_replay(artifact_dir)
    if not replay.get("scenario"):
        raise ValueError("canonical source scenario missing")
    output.mkdir(parents=True, exist_ok=True)
    probe = output / ".write-probe"
    probe.write_text("ok", encoding="ascii"); probe.unlink()
    libs, builds = _build_all(output / "observer_builds")
    scenario = ScenarioSpec.from_dict(replay["scenario"])
    with tempfile.TemporaryDirectory(prefix="phase3hai-preflight-") as td:
        td = Path(td)
        production = GazeboWorldGenerator().generate(scenario, td, closed_loop=True,
                                                       control_mode="PHYSICS")
        if _sha(production) != PRODUCTION_HASH:
            raise ValueError(f"generated production SDF hash differs from accepted H-AG hash: {_sha(production)}")
        diag, sdf = _instrument_world(production, output / "preflight_A", libs, "A_clean_up")
        if not diag.is_file() or not sdf["observation_only"]:
            raise RuntimeError("diagnostic SDF composition failed")
        preflight_sdf = Path(output / "preflight_A" / "diagnostic.sdf")
        preflight_sdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(diag, preflight_sdf)
        diag_b, sdf_b = _instrument_world(production, output / "preflight_B", libs, "B_history_up")
        shutil.copy2(diag_b, output / "preflight_B/diagnostic.sdf")
        assert sdf["native"]["topic"] != sdf_b["native"]["topic"]
    report = {"status": "PREFLIGHT_PASS", "gazebo_launched": False,
        "runtime_evidence_created": False, "source_artifact_dir": str(artifact_dir),
        "output_dir": str(output), "case_a_actions": ["reset", "settle", "verify_stopped", "up"],
        "case_b_actions": ["reset", "settle", "verify_stopped", "down", "BRAKE_LINEAR", "verify_stopped", "up"],
        "up_implementation": "same GazeboPhysicsTrainingEnvironment.step('up') in both arms",
        "observer_builds": builds, "sdf_integrity": sdf, "case_b_sdf_integrity": sdf_b,
        "runtime_artifacts_claimed": False,
        "runtime_topics": {"A_clean_up": sdf["native"]["topic"], "B_history_up": sdf_b["native"]["topic"]}}
    (output / "history_ab_preflight.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return report


def _finite_json_rows(path):
    rows = []
    if not Path(path).is_file():
        return rows
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            rows.append(json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"nonfinite token {x} at {i}"))))
    return rows


def _run_case(case_name, history, scenario, root, output, libraries, seed):
    from aero_ai_studio.training.gazebo_physics import GazeboPhysicsTrainingEnvironment
    generated = {}
    original_generate = GazeboWorldGenerator.generate

    def generate(generator, selected_scenario, world_root, closed_loop=False, control_mode="KINEMATIC"):
        production = original_generate(generator, selected_scenario, world_root,
            closed_loop=closed_loop, control_mode=control_mode)
        if control_mode == "PHYSICS" and closed_loop:
            diag, meta = _instrument_world(production, output, libraries)
            generated.update(meta=meta, sdf=str(diag))
            return diag
        return production

    GazeboWorldGenerator.generate = generate
    old_plugin_path = os.environ.get("GZ_SIM_SYSTEM_PLUGIN_PATH")
    os.environ["GZ_SIM_SYSTEM_PLUGIN_PATH"] = os.pathsep.join(dict.fromkeys(
        [str(Path(lib).resolve().parent) for lib in libraries.values()] +
        ([old_plugin_path] if old_plugin_path else [])))
    env = None
    native_capture = None
    record = {"case": case_name, "history": history, "seed": seed,
              "events": [], "physical_failure": None, "infrastructure_failure": None}
    try:
        env = GazeboPhysicsTrainingEnvironment(scenario, 100, root=root, gui=False)
        # Use the existing launch/discovery lifecycle; subscribe before the
        # production reset settle so all streams bracket the first UP.
        record["partition"] = env.env.manager.partition
        env.env.prepare()
        topic = generated.get("meta", {}).get("native", {}).get("topic")
        if not topic:
            raise RuntimeError("native observer topic unavailable")
        record["runtime_sdf_passed_to_gazebo"] = str(env.env.world)
        if str(env.env.world) != generated.get("sdf"):
            raise RuntimeError("Gazebo runtime SDF differs from current case diagnostic SDF")
        native_capture = native.NativeVelocityCapture(_NoBaseCapture())
        native_capture.subscribe(env, topic)
        _wait_native_topic(env, topic)
        env.reset(seed)
        record["reset_completed"] = True
        record["reset_evidence"] = dict(env.last_reset_evidence)
        record["reset_sim_time"] = float(env.env.stepper.time)
        record["initial_pose"] = dict(env.env.pose)
        record["pre_up_sim_time"] = float(env.env.stepper.time)
        record["pre_up_command"] = dict(env.env.controller.last_command)
        if not history:
            record["pre_up_state"] = _state_snapshot(output, native_capture, env)
            event = _execute_captured(env, "up", "CLEAN_UP")
            record["events"].append(event)
            if event.get("exception"):
                record["physical_failure"] = event["exception"]
        else:
            record["pre_down_state"] = _state_snapshot(output, native_capture, env)
            down_event = _execute_captured(env, "down", "DOWN")
            record["events"].append(down_event)
            if down_event.get("exception"):
                record["physical_failure"] = down_event["exception"]
                raise RuntimeError("DOWN acquisition failed; cannot run history-UP comparison")
            record["pre_brake_state"] = _state_snapshot(output, native_capture, env)
            up_event = _execute_captured(env, "up", "BRAKE_LINEAR_THEN_UP")
            record["events"].append(up_event)
            up_time = up_event.get("up_command_sim_time")
            record["pre_up_sim_time"] = up_time
            record["pre_up_command"] = {"linear": {"x": 0.0}, "source": "BRAKE_LINEAR stop contract immediately before ACQUIRE_LINEAR"}
            record["pre_up_state"] = (_state_snapshot_at(output, native_capture, up_time)
                                      if up_time is not None else None)
            if up_event.get("exception"):
                record["physical_failure"] = up_event["exception"]
        record["final_pose"] = dict(env.env.pose)
        record["final_sim_time"] = float(env.env.stepper.time)
        record["process_alive"] = bool(env.env.process and env.env.process.poll() is None)
        record["native_samples"] = native_capture.samples
        record["native_heartbeats"] = native_capture.heartbeat_messages
        record["native_parse_failures"] = native_capture.parse_failures
        record["observer_sdf"] = generated.get("meta")
        record["sdf_path"] = generated.get("sdf")
    except Exception as exc:
        record["infrastructure_failure"] = _failure(exc)
    finally:
        record["observer_sdf"] = generated.get("meta")
        record["sdf_path"] = generated.get("sdf")
        if native_capture is not None:
            if native_capture.subscribed:
                try:
                    env.env.transport.node.unsubscribe(native_capture.topic)
                    native_capture.subscribed = False
                except Exception as exc:
                    record["close_error"] = _failure(exc)
            record["native_samples"] = list(native_capture.samples)
        if env is not None:
            record["gazebo_launched"] = env.env.process is not None
            record["runtime_identity"] = {"partition": env.env.manager.partition,
                "topic": generated.get("meta", {}).get("native", {}).get("topic")}
        if env is not None:
            try: env.close()
            except Exception as exc: record.setdefault("close_error", _failure(exc))
            record["shutdown_completed"] = not env.env.process or env.env.process.poll() is not None
        GazeboWorldGenerator.generate = original_generate
        if old_plugin_path is None:
            os.environ.pop("GZ_SIM_SYSTEM_PLUGIN_PATH", None)
        else:
            os.environ["GZ_SIM_SYSTEM_PLUGIN_PATH"] = old_plugin_path
    try:
        record["support_rows"] = _finite_json_rows(output / "continuous_support_iterations.ndjson")
        record["wrench_rows"] = _finite_json_rows(output / "joint_transmitted_wrench.ndjson")
    except Exception as exc:
        record["infrastructure_failure"] = _failure(exc)
    record["case_result_written"] = True
    result_path = output / "case_result.json"
    result_path.write_text(json.dumps(record, indent=2, allow_nan=False)+"\n")
    # Read back the complete JSON before permitting capture validity.
    if json.loads(result_path.read_text()) != record:
        raise RuntimeError("case result readback mismatch")
    return record


def _wait_native_topic(env, topic):
    from aero_ai_studio.gazebo.discovery import discover
    from aero_ai_studio.gazebo.diagnostics import gazebo_status
    deadline = time.monotonic() + env.env.timeout
    while True:
        discovered = discover(gazebo_status(probe=False)["executable"], env.env.manager.partition)
        if topic in discovered["topics"]:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("native observer topic timeout: " + topic)
        time.sleep(.1)


class _NoBaseCapture:
    """NativeVelocityCapture only uses this field as retained context."""
    pass


def _failure(exc):
    evidence = getattr(exc, "evidence", None)
    return {"type": type(exc).__name__, "message": str(exc),
            "evidence": evidence if isinstance(evidence, (dict, list, str, int, float, bool, type(None))) else None}


def _state_snapshot(output, native_capture, env):
    support_rows = _finite_json_rows(Path(output) / "continuous_support_iterations.ndjson")
    wrench_rows = _finite_json_rows(Path(output) / "joint_transmitted_wrench.ndjson")
    candidates = [r for r in support_rows if r.get("kind") == "support_iteration" and not r.get("paused")]
    if not candidates:
        return {"available": False, "reason": "no advancing support sample yet",
                "sim_time_s": float(env.env.stepper.time), "pose": dict(env.env.pose)}
    latest = max(candidates, key=lambda r: r["iteration"])
    iteration, epoch = latest["iteration"], latest.get("epoch", 0)
    w = next((r for r in reversed(wrench_rows) if r.get("kind") == "joint_wrench_sample" and
              r.get("iteration") == iteration and r.get("epoch", 0) == epoch), None)
    native_row = next((r for r in reversed(native_capture.samples)
                       if r.get("iteration") == iteration), None)
    return {"available": True, "epoch": epoch, "iteration": iteration,
        "sim_time_ns": latest.get("sim_time_ns"), "sim_time_s": float(env.env.stepper.time),
        "pose": dict(env.env.pose), "support": latest.get("supports"),
        "joint_wrench": w, "native": native_row,
        "actual_joint_velocity": {side: (w.get(side, {}).get("actual_velocity_rad_s") if w else None)
                                  for side in ("left", "right")},
        "command": dict(env.env.controller.last_command)}


def _state_snapshot_at(output, native_capture, sim_time_s):
    if sim_time_s is None:
        return {"available": False, "reason": "exact production UP phase time unavailable"}
    support_rows = _finite_json_rows(Path(output) / "continuous_support_iterations.ndjson")
    wrench_rows = _finite_json_rows(Path(output) / "joint_transmitted_wrench.ndjson")
    limit_ns = int(round(float(sim_time_s) * 1e9))
    candidates = [r for r in support_rows if r.get("kind") == "support_iteration" and
                  not r.get("paused") and int(r.get("sim_time_ns", -1)) <= limit_ns]
    if not candidates:
        return {"available": False, "reason": "no advancing support sample at/before UP phase boundary",
                "target_sim_time_s": sim_time_s}
    row = max(candidates, key=lambda r: (int(r.get("epoch", 0)), int(r["iteration"])))
    iteration, epoch = int(row["iteration"]), row.get("epoch", 0)
    w = next((r for r in reversed(wrench_rows) if r.get("kind") == "joint_wrench_sample" and
              int(r.get("iteration", -1)) == iteration and r.get("epoch", 0) == epoch), None)
    n = next((r for r in reversed(native_capture.samples) if int(r.get("iteration", -1)) == iteration), None)
    return {"available": True, "epoch": epoch, "iteration": iteration,
        "sim_time_ns": row.get("sim_time_ns"), "target_up_phase_sim_time_s": float(sim_time_s),
        "support": row.get("supports"), "joint_wrench": w, "native": n,
        "actual_joint_velocity": {side: (w.get(side, {}).get("actual_velocity_rad_s") if w else None)
                                  for side in ("left", "right")}}


def _execute_captured(env, action, phase):
    start = float(env.env.stepper.time)
    command_sequence = getattr(env.env.controller, "publish_sequence", 0)
    result = None
    exception = None
    try:
        result = env.step(action)
    except Exception as exc:
        exception = _failure(exc)
    evidence = (getattr(result, "execution_evidence", None) or {} if result is not None else
                exception.get("evidence", {}) if exception else {})
    phases = evidence.get("execution_phases") or evidence.get("execution_evidence", {}).get("phase_evidence", [])
    if not phases:
        phases = _find_phase_evidence(evidence)
    acquire = next((p for p in phases if p.get("phase") == "ACQUIRE_LINEAR"), None)
    published = getattr(env.env.controller, "publish_sequence", 0) > command_sequence
    up_time = (acquire.get("start_sim_time") if acquire else
               start if phase == "CLEAN_UP" and published else None)
    last_published = getattr(env.env.controller, "last_published_command", None) or {}
    transition = dict(env.env.telemetry.get("action_transition", {}))
    action_sequence = transition.get("action_publish_sequence")
    fresh_up_transition = bool(type(action_sequence) is int and action_sequence > command_sequence and
        transition.get("commanded_twist", {}).get("linear", {}).get("x") == .5)
    actual_up_published = fresh_up_transition or (published and last_published.get("linear", {}).get("x") == .5)
    if phase == "CLEAN_UP" and fresh_up_transition:
        up_time = transition.get("action_command_sim_time")
    return {"up_reached": action == "up" and actual_up_published and up_time is not None,
            "last_published_command": last_published, "action_publication": transition,
            "phase": phase, "action": action, "start_sim_time": start,
            "end_sim_time": float(env.env.stepper.time),
            "up_command_sim_time": up_time if action == "up" else None,
            "execution_evidence": evidence,
            "result_reason": getattr(result, "reason", None),
            "terminated": getattr(result, "terminated", None),
            "telemetry": dict(env.env.telemetry.get("gazebo_dqn_training", {})),
            "exception": exception}


def _find_phase_evidence(value):
    if isinstance(value, dict):
        phases = value.get("phase_evidence") or value.get("execution_phases")
        if isinstance(phases, list):
            return phases
        for child in value.values():
            found = _find_phase_evidence(child)
            if found: return found
    elif isinstance(value, list):
        for child in value:
            found = _find_phase_evidence(child)
            if found: return found
    return []


def _relative_analysis(case):
    support_rows = [r for r in case.get("support_rows", []) if r.get("kind") == "support_iteration" and not r.get("paused")]
    wrench_rows = [r for r in case.get("wrench_rows", []) if r.get("kind") == "joint_wrench_sample" and not r.get("paused")]
    if not case.get("events"):
        return {"status": "NO_UP_PHASE", "support_iteration_count": len(support_rows), "wrench_iteration_count": len(wrench_rows)}
    up_event = next((e for e in reversed(case["events"]) if e.get("action") == "up"), None)
    if not up_event:
        return {"status": "NO_UP_PHASE", "support_iteration_count": len(support_rows), "wrench_iteration_count": len(wrench_rows)}
    command_time = up_event.get("up_command_sim_time", up_event["start_sim_time"])
    t0_ns = int(round(command_time * 1e9))
    merged = {}
    for row in support_rows:
        merged.setdefault((row.get("epoch", 0), row["iteration"]), {})["support"] = row
    for row in wrench_rows:
        merged.setdefault((row.get("epoch", 0), row["iteration"]), {})["wrench"] = row
    timed = [row for row in support_rows + wrench_rows if row.get("sim_time_ns") is not None]
    if not timed:
        return {"status": "MISSING_ITERATION_TIMES"}
    # Command publication precedes the advancing PostUpdate sample that first
    # observes its effect. T0 is that first iteration strictly after the
    # production acquisition phase's recorded start time.
    after_command = [r for r in timed if int(r["sim_time_ns"]) > t0_ns]
    if not after_command:
        return {"status": "NO_ADVANCING_SAMPLE_AFTER_UP_COMMAND"}
    t0_row = min(after_command, key=lambda r: (int(r["sim_time_ns"]), int(r["iteration"])))
    t0_iteration = int(t0_row["iteration"])
    t0 = int(t0_row["sim_time_ns"])
    rows = []
    for (epoch, iteration), data in sorted(merged.items(), key=lambda kv: kv[0][1]):
        s, w = data.get("support"), data.get("wrench")
        ns = (s or w or {}).get("sim_time_ns")
        if ns is None: continue
        dt = int(iteration) - t0_iteration
        if -5 <= dt <= 15:
            rows.append({"epoch": epoch, "iteration": iteration, "sim_time_ns": ns,
                "delta_iteration": dt, "delta_ms": (int(ns) - t0) / 1e6,
                "support": s.get("supports") if s else None,
                "left": w.get("left") if w else None, "right": w.get("right") if w else None,
                "exact_support_wrench_same_iteration": bool(s and w)})
    return {"status": "ANALYZED", "up_phase_start_sim_time_s": command_time,
        "t0_iteration": t0_iteration,
        "t0_sim_time_ns": t0, "relative_rows": rows,
        "support_iteration_count": len(support_rows), "wrench_iteration_count": len(wrench_rows),
        "join_key": "(epoch, UpdateInfo.iterations)",
        "t0_selection": "first advancing observer iteration with sim_time_ns strictly after production UP command/acquisition start"}


def _preup_comparison(case_a, case_b):
    a, b = case_a.get("pre_up_state"), case_b.get("pre_up_state")
    if not isinstance(a, dict) or not isinstance(b, dict) or not a.get("available") or not b.get("available"):
        return {"verdict": "PRE_UP_STATE_DIFFERENCE_BELOW_CURRENT_RESOLUTION",
                "reason": "one or both exact-boundary snapshots are unavailable",
                "case_a": a, "case_b": b}
    def flatten(x, prefix=""):
        out = {}
        if isinstance(x, dict):
            for key, value in x.items():
                if key in ("iteration", "epoch", "sim_time_ns", "sim_time_s", "target_up_phase_sim_time_s"):
                    continue
                out.update(flatten(value, f"{prefix}.{key}" if prefix else key))
        elif isinstance(x, list):
            for i, value in enumerate(x): out.update(flatten(value, f"{prefix}[{i}]"))
        elif isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x)):
            out[prefix] = float(x)
        return out
    av, bv = flatten(a), flatten(b)
    common = sorted(set(av) & set(bv))
    delta = {key: bv[key] - av[key] for key in common}
    verdict = "PRE_UP_STATE_EQUIVALENT" if common and all(value == 0.0 for value in delta.values()) else "PRE_UP_STATE_DIFFERENT"
    return {"verdict": verdict, "common_numeric_field_count": len(common),
            "numeric_delta_case_b_minus_case_a": delta,
            "case_a_iteration": a.get("iteration"), "case_b_iteration": b.get("iteration"),
            "case_a": a, "case_b": b}


def validate_case(case):
    """Fail closed: only runtime records and advancing, timed streams qualify."""
    reasons = []
    up = next((e for e in reversed(case.get("events", [])) if e.get("action") == "up"), {})
    transition = up.get("up_command_sim_time")
    streams = {}
    for name, key, kind, time_key, scale in (
        ("support", "support_rows", "support_iteration", "sim_time_ns", 1e-9),
        ("wrench", "wrench_rows", "joint_wrench_sample", "sim_time_ns", 1e-9),
        ("native", "native_samples", None, "simulation_time_s", 1.0)):
        rows = []
        malformed = False
        for row in case.get(key, []):
            if (kind and row.get("kind") != kind) or row.get("paused") is not False:
                continue
            iteration, stamp = row.get("iteration"), row.get(time_key)
            if (type(iteration) is not int or iteration < 0 or
                type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0):
                malformed = True
                continue
            rows.append((iteration, stamp * scale))
        rows = sorted(set(rows), key=lambda r: r[1])
        advancing = (len(rows) >= 2 and all(b[0] > a[0] and b[1] > a[1]
                     for a, b in zip(rows, rows[1:])))
        covered = bool(advancing and transition is not None and
                       rows[0][1] <= transition < rows[-1][1])
        if malformed or not advancing or not covered:
            reasons.append(name + ": missing/invalid/nonadvancing samples or UP boundary not covered")
        streams[name] = {"sample_count": len(rows), "advancing": advancing,
            "first_iteration": rows[0][0] if rows else None,
            "last_iteration": rows[-1][0] if rows else None,
            "first_sim_time": rows[0][1] if rows else None,
            "last_sim_time": rows[-1][1] if rows else None,
            "up_transition_covered": covered}
    sdf = case.get("sdf_path")
    fatal = case.get("infrastructure_failure") or case.get("close_error") or next(
        (e["exception"] for e in case.get("events", []) if e.get("exception") and
         e["exception"].get("type") != "PhysicalControlFailure"), None)
    reset = case.get("reset_evidence", {})
    checks = {"gazebo_launched": case.get("gazebo_launched") is True,
        "runtime_sdf_exists": bool(sdf and Path(sdf).is_file() and case.get("observer_sdf", {}).get("observation_only")),
        "runtime_sdf_launched": bool(sdf and case.get("runtime_sdf_passed_to_gazebo") == sdf),
        "reset_completed": case.get("reset_completed") is True and reset.get("normal_reset_pass") is True,
        "stopped_verified": reset.get("body_residual_velocity_stopped") is True and reset.get("odometry_fresh_and_stopped") is True,
        "control_sequence_started": bool(case.get("events")),
        "up_reached": up.get("up_reached") is True,
        "case_result_written": case.get("case_result_written") is True,
        "shutdown_completed": case.get("shutdown_completed") is True,
        "no_fatal_error": fatal is None}
    reasons.extend(key for key, value in checks.items() if not value)
    if fatal:
        reasons.append(str(fatal))
    return {**checks, "runtime_sdf": sdf, "fatal_error": fatal,
        **{name + "_sample_count": data["sample_count"] for name, data in streams.items()},
        "first_iteration": min((d["first_iteration"] for d in streams.values() if d["first_iteration"] is not None), default=None),
        "last_iteration": max((d["last_iteration"] for d in streams.values() if d["last_iteration"] is not None), default=None),
        "first_sim_time": min((d["first_sim_time"] for d in streams.values() if d["first_sim_time"] is not None), default=None),
        "last_sim_time": max((d["last_sim_time"] for d in streams.values() if d["last_sim_time"] is not None), default=None),
        "up_transition_covered": all(d["up_transition_covered"] for d in streams.values()),
        "streams": streams, "invalid_reasons": reasons, "case_valid": not reasons}


def capture_integrity(cases):
    names = ("A_clean_up", "B_history_up")
    records = {name: validate_case(cases.get(name, {})) for name in names}
    identities = [cases.get(name, {}).get("runtime_identity", {}) for name in names]
    isolated = bool(all(i.get("partition") and i.get("topic") for i in identities) and
                    identities[0]["partition"] != identities[1]["partition"] and
                    identities[0]["topic"] != identities[1]["topic"])
    return {"cases": records, "fresh_case_identities": identities,
        "cases_isolated": isolated, "invalid_reasons": [] if isolated else ["case partition/topic isolation not proven"],
        "both_cases_valid": isolated and all(r["case_valid"] for r in records.values())}


def run(artifact_dir, output):
    artifact_dir, output = Path(artifact_dir).resolve(), Path(output).resolve()
    if output.exists():
        allowed = {"observer_builds", "history_ab_preflight.json", "preflight_case", "preflight_A", "preflight_B"}
        unexpected = [p.name for p in output.iterdir() if p.name not in allowed]
        if unexpected:
            raise FileExistsError(f"refusing to overwrite runtime or unknown output entries: {unexpected}")
    output.mkdir(parents=True, exist_ok=True)
    replay = extract_reversal_replay(artifact_dir)
    scenario = ScenarioSpec.from_dict(replay["scenario"])
    seed = int(scenario.seed)
    libraries, builds = _build_all(output / "observer_builds")
    cases = {}
    for name, history in (("A_clean_up", False), ("B_history_up", True)):
        case_dir = output / name
        case_dir.mkdir()
        if cases and not cases["A_clean_up"].get("shutdown_completed"):
            cases[name] = {"infrastructure_failure": {"message": "A shutdown incomplete; B not launched"}}
            continue
        cases[name] = _run_case(name, history, scenario, case_dir / "world", case_dir,
                                libraries, seed)
    integrity = capture_integrity(cases)
    (output / "capture_integrity.json").write_text(json.dumps(integrity, indent=2)+"\n")
    report = {"schema_version": "0.7.1", "status":
        "CAPTURED" if integrity["both_cases_valid"] else "CAPTURE_FAILED",
        "cases": cases, "capture_integrity": integrity, "observer_builds": builds,
        "production_behavior_modified": False, "production_physics_modified": False,
        "production_sdf_sha256_expected": PRODUCTION_HASH,
        "runtime_verdict": "PENDING_OFFLINE_ANALYSIS" if integrity["both_cases_valid"] else "HISTORY_AB_CAPTURE_INVALID"}
    (output / "history_ab_capture.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = preflight(args.artifact_dir, args.output) if args.preflight_only else run(args.artifact_dir, args.output)
    except Exception as exc:
        print("CAPTURE_FAILED: " + type(exc).__name__ + ": " + str(exc))
        return 1
    print(result["status"])
    print("evidence: " + str(args.output))
    if result["status"] == "CAPTURE_FAILED":
        for reason in result["capture_integrity"].get("invalid_reasons", []):
            print(reason)
        for name, case in result["capture_integrity"]["cases"].items():
            if not case["case_valid"]:
                print(name + ": " + "; ".join(case["invalid_reasons"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
