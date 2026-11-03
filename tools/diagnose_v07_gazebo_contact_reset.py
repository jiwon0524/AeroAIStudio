#!/usr/bin/env python3
"""Observe Gazebo Harmonic contact publisher lifecycle across WorldControl.reset.all."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aero_ai_studio.core.storage import write_json
from aero_ai_studio.gazebo.diagnostics import gazebo_status
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.training.gazebo_dqn import dqn_validation_scenario

EXPECTED_CONTACT_TYPE = "gz.msgs.Contacts"
PHASE_SECONDS = 2.0
POLL_INTERVAL_SECONDS = 0.1


def _field(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def evaluate_topic_info(publishers, subscribers, expected_type=EXPECTED_CONTACT_TYPE):
    """Summarize discovery without conflating event silence with publisher loss."""
    publishers = list(publishers or ())
    subscribers = list(subscribers or ())
    types = sorted({str(_field(item, "msg_type_name", "")) for item in publishers
                    if _field(item, "msg_type_name", "")})
    return {
        "contact_topic_visible": bool(publishers or subscribers),
        "publisher_visible": bool(publishers),
        "subscriber_visible": bool(subscribers),
        "schema_visible": bool(publishers) and types == [expected_type],
        "message_type": types[0] if len(types) == 1 else types or None,
        "expected_message_type": expected_type,
        "contact_message_observed": None,
        "message_silence_means_publisher_absence": False,
    }


def classify_verdict(initial_discovery, reset_stats_contract, phases, timeline,
                     *, discovery_exception=False, process_stable=True,
                     progression_ok=True):
    """Return deterministic lifecycle verdict and first valid rediscovery time."""
    discovery_exception = discovery_exception or any(row.get("discovery_error") for row in timeline)
    if (not initial_discovery or initial_discovery.get("schema_visible") is not True or
            not reset_stats_contract or reset_stats_contract.get("pass") is not True or
            discovery_exception or not process_stable or not progression_ok):
        return "INCONCLUSIVE", None, "Initial schema, reset postcondition, discovery, process identity, or controlled progression was not verifiable."
    rows = [row for row in timeline if row.get("phase") in {"phase_A_paused_wall_clock", "phase_B_after_100_iterations", "phase_C_after_settle"}]
    required_phases = {"phase_A_paused_wall_clock", "phase_B_after_100_iterations", "phase_C_after_settle"}
    observed_phases = {row.get("phase") for row in rows}
    if not rows or observed_phases != required_phases:
        return "INCONCLUSIVE", None, "One or more bounded post-reset phases have no discovery observations."
    states = [bool(row.get("publisher_visible") and row.get("schema_visible")) for row in rows]
    if all(states):
        return "NO_PUBLISHER_LOSS", 0.0, "Expected publisher and Contacts schema remained visible throughout all post-reset phases."
    gap_seen = False
    for row, ready in zip(rows, states):
        if not ready:
            gap_seen = True
        elif gap_seen:
            return ("TRANSIENT_READINESS_GAP", row.get("wall_elapsed_since_reset"),
                    "Publisher/schema became valid again after an observed gap in the same Gazebo process.")
    return ("PERSISTENT_PUBLISHER_LOSS", None,
            "Publisher/schema was unavailable and did not recover during paused, post-progression, or post-settle windows.")


def _probe(env, phase, reset_wall, elapsed, attempt):
    row = {
        "phase": phase,
        "wall_elapsed_since_reset": max(0.0, elapsed),
        "discovery_attempt": attempt,
        "discovery_error": None,
    }
    try:
        publishers, subscribers = env.transport.node.topic_info(env.contact_topic)
        row.update(evaluate_topic_info(publishers, subscribers))
    except Exception as error:  # preserved as evidence; verdict becomes inconclusive
        row.update(contact_topic_visible=False, publisher_visible=False,
                   subscriber_visible=False, schema_visible=False, message_type=None,
                   expected_message_type=EXPECTED_CONTACT_TYPE,
                   contact_message_observed=None,
                   message_silence_means_publisher_absence=False,
                   discovery_error={"type": type(error).__name__, "message": str(error)})
    try:
        stats = env.transport.snapshot(env.stepper.topic)
        sample = stats.get("data") or {}
        from aero_ai_studio.gazebo.transport import stamp
        row.update(simulation_time=stamp(sample), stats_receive_sequence=stats.get("sequence"),
                   stats_paused=sample.get("paused"),
                   stats_iterations=sample.get("iterations_normalized", sample.get("iterations")))
    except Exception as error:
        row.update(simulation_time=None, stats_receive_sequence=None,
                   stats_error={"type": type(error).__name__, "message": str(error)})
    try:
        row["contact_receive_sequence"] = env.transport.cursor(env.contact_topic)
    except Exception:
        row["contact_receive_sequence"] = None
    try:
        row["process"] = env.manager.status()
    except Exception as error:
        row["process"] = {"status": "Unknown", "pid": None,
                          "error": {"type": type(error).__name__, "message": str(error)}}
    return row


def observe_phase(env, phase, reset_wall, duration=PHASE_SECONDS,
                  poll_interval=POLL_INTERVAL_SECONDS, *, monotonic=time.monotonic,
                  sleep=time.sleep, timeline=None):
    """Poll discovery on wall time only; this function never advances physics."""
    if timeline is None:
        timeline = []
    started = monotonic()
    deadline = started + duration
    attempt = 0
    while True:
        attempt += 1
        elapsed = monotonic() - reset_wall
        timeline.append(_probe(env, phase, reset_wall, elapsed, attempt))
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(poll_interval, remaining))
    return timeline


def run_diagnostic(output: Path, *, gui=False, phase_seconds=PHASE_SECONDS,
                   poll_interval=POLL_INTERVAL_SECONDS):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.7.1",
        "diagnostic": "Gazebo contact publisher lifecycle across reset.all",
        "status": "INCONCLUSIVE",
        "expected_message_type": EXPECTED_CONTACT_TYPE,
        "contact_semantics": "event_driven; message silence is not publisher absence",
        "forced_collision": False,
        "process_restart_during_diagnostic": False,
        "phase_definition": {
            "phase_A_paused_wall_clock": "bounded wall-clock discovery while reset world remains paused; no physics progression",
            "phase_B_after_100_iterations": "after one existing fixed 100-iteration PHYSICS step",
            "phase_C_after_settle": "after one additional existing fixed 100-iteration settle step",
        },
        "phase_A_paused_wall_clock": [],
        "phase_B_after_100_iterations": [],
        "phase_C_after_settle": [],
        "timeline": [],
    }
    env = None
    discovery_exception = False
    progression_ok = True
    process_before = process_after = None
    reset_wall = None
    try:
        env = GazeboEnvironment(dqn_validation_scenario(), max_steps=1,
            root=output / "worlds", gui=gui, control_mode="PHYSICS",
            max_sensor_age_ms=20, allow_geometric_fallback=False)
        launch = env.launch()
        if not launch.get("available", True):
            raise RuntimeError("Gazebo launch unavailable: " + str(launch))
        if env.injected or env.control_mode != "PHYSICS":
            raise RuntimeError("Diagnostic requires actual Gazebo PHYSICS transport")
        env.prepare()
        env.prepare_contacts()
        process_before = env.manager.status()
        initial_publishers, initial_subscribers = env.transport.node.topic_info(env.contact_topic)
        report["initial_contact_discovery"] = {
            "topic": env.contact_topic,
            "discovery_attempt": 1,
            "discovery_error": None,
            **evaluate_topic_info(initial_publishers, initial_subscribers),
        }
        if not report["initial_contact_discovery"]["schema_visible"]:
            raise RuntimeError("Initial contact publisher/schema discovery failed")
        report.update(world=env.world_name, partition=env.manager.partition,
                      pid=process_before.get("pid"), gazebo_version=gazebo_status(probe=True).get("detail"),
                      initial_process=process_before)

        # Existing environment reset provides normal zero-command PHYSICS progression
        # and sets the contact subscriber/epoch before the reset lifecycle observation.
        env.reset(seed=42)
        env.controller.stop_agent()
        env.stepper.pause()
        report["pre_reset_progression"] = {
            "simulation_time": env.stepper.time,
            "step_evidence": dict(env.stepper.last_verification),
            "zero_command_published": True,
            "paused_before_reset": True,
        }
        report["reset_rpc"] = None
        try:
            report["reset_rpc"] = env.stepper.reset_world()
        except Exception as error:
            report["reset_rpc"] = getattr(error, "reset_evidence", {
                "accepted": False, "failure": str(error)})
            raise
        report["stats_reset_contract"] = report["reset_rpc"].get("stats_reset_contract")
        reset_wall = time.monotonic()
        report["reset_wall_monotonic"] = reset_wall

        observe_phase(env, "phase_A_paused_wall_clock", reset_wall,
                      phase_seconds, poll_interval, timeline=report["timeline"])
        report["phase_A_paused_wall_clock"] = [r for r in report["timeline"] if r["phase"] == "phase_A_paused_wall_clock"]

        # Mirror the normal reset path's pose restoration before its fixed progress step.
        env.controller.reset_agent_pose(env.scenario.start[0] + .5,
                                        env.scenario.start[1] + .5, .16)
        report["set_pose_after_phase_A"] = dict(getattr(env.controller, "last_pose_request", {}))
        try:
            env.stepper.step_simulation()
        except Exception as error:
            progression_ok = False
            report["phase_B_step_error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        process_after_a = env.manager.status()
        progression_ok = progression_ok and process_after_a.get("pid") == process_before.get("pid") and process_after_a.get("status") == "Running"
        observe_phase(env, "phase_B_after_100_iterations", reset_wall,
                      phase_seconds, poll_interval, timeline=report["timeline"])
        report["phase_B_after_100_iterations"] = [r for r in report["timeline"] if r["phase"] == "phase_B_after_100_iterations"]

        try:
            env.stepper.step_simulation()
        except Exception as error:
            progression_ok = False
            report["phase_C_step_error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        process_after_b = env.manager.status()
        progression_ok = progression_ok and process_after_b.get("pid") == process_before.get("pid") and process_after_b.get("status") == "Running"
        observe_phase(env, "phase_C_after_settle", reset_wall,
                      phase_seconds, poll_interval, timeline=report["timeline"])
        report["phase_C_after_settle"] = [r for r in report["timeline"] if r["phase"] == "phase_C_after_settle"]
        process_after = env.manager.status()
        progression_ok = progression_ok and process_after.get("pid") == process_before.get("pid") and process_after.get("status") == "Running"
        progression_ok = progression_ok and all(
            row.get("process", {}).get("pid") == process_before.get("pid") and
            row.get("process", {}).get("status") == "Running" for row in report["timeline"])
        report["final_process"] = process_after
        report["process_identity_stable"] = progression_ok
        report["first_topic_visible_wall_time"] = next((r["wall_elapsed_since_reset"] for r in report["timeline"] if r.get("contact_topic_visible")), None)
        report["first_publisher_visible_wall_time"] = next((r["wall_elapsed_since_reset"] for r in report["timeline"] if r.get("publisher_visible")), None)
        report["first_schema_valid_wall_time"] = next((r["wall_elapsed_since_reset"] for r in report["timeline"] if r.get("schema_visible")), None)
        report["status"], report["first_recovery_time"], report["reason"] = classify_verdict(
            report["initial_contact_discovery"], report["stats_reset_contract"],
            [report["phase_A_paused_wall_clock"], report["phase_B_after_100_iterations"], report["phase_C_after_settle"]],
            report["timeline"], discovery_exception=discovery_exception,
            process_stable=progression_ok, progression_ok=progression_ok)
    except Exception as error:
        discovery_exception = any(row.get("discovery_error") for row in report["timeline"])
        if report.get("initial_contact_discovery") is None and "topic" in str(error).lower():
            discovery_exception = True
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        stats = report.get("stats_reset_contract")
        report["status"], report["first_recovery_time"], report["reason"] = classify_verdict(
            report.get("initial_contact_discovery"), stats,
            [report["phase_A_paused_wall_clock"], report["phase_B_after_100_iterations"], report["phase_C_after_settle"]],
            report["timeline"], discovery_exception=discovery_exception,
            process_stable=False, progression_ok=False)
    finally:
        if env is not None:
            process_after = env.manager.status()
            report.setdefault("final_process", process_after)
            report["process_identity_stable"] = bool(
                process_before and process_after.get("pid") == process_before.get("pid"))
            try:
                env.close()
                report["shutdown"] = "PASS"
            except Exception as error:
                report["shutdown"] = "FAIL"
                report["shutdown_error"] = str(error)
        report["process_restart_during_diagnostic"] = bool(
            process_before and report.get("final_process", {}).get("pid") != process_before.get("pid"))
        report["timeline_file"] = str(output / "contact_reset_timeline.json")
        report["evidence_file"] = str(output / "contact_reset_diagnostic.json")
        write_json(output / "contact_reset_timeline.json", report["timeline"])
        write_json(output / "contact_reset_diagnostic.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args(argv)
    report = run_diagnostic(args.output, gui=args.gui)
    print("contact reset diagnostic: " + report["status"])
    print("reason: " + report.get("reason", report.get("error", {}).get("message", "")))
    print("evidence: " + report["evidence_file"])
    return 0 if report["status"] != "INCONCLUSIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
