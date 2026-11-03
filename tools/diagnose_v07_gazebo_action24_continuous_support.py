#!/usr/bin/env python3
"""Diagnostic-only continuous four-support ContactSensorData capture for Action24.

--preflight-only performs no Gazebo launch. The default mode is intended for Host.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shlex, shutil, subprocess, tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT=ROOT/"validation/v071-host/gazebo-dqn-full-stage1-post-r2l"
DEFAULT_OUTPUT=ROOT/"validation/v071-host/gazebo-action24-continuous-support-phase3hac"
PLUGIN_SOURCE=ROOT/"tools/gazebo_continuous_support_observer.cc"
PLUGIN_CLASS="aero_diagnostic::ContinuousSupportObserver"
SUPPORTS={"left_wheel":("left_wheel","left_collision"),"right_wheel":("right_wheel","right_collision"),"front_caster":("front_caster","front_collision"),"rear_caster":("rear_caster","rear_collision")}

from tools import diagnose_v07_gazebo_action24_support_load_distribution as support_diag
from tools import diagnose_v07_gazebo_action24_native_contact_kinematics as native_diag
from tools import diagnose_v07_gazebo_action24_wheel_ground_contact as contact_diag
from tools import diagnose_v07_gazebo_action24_wheel_joint_state as joint_diag
from tools.analyze_v07_gazebo_action24_continuous_support import analyze_file, classify_action24_support_case
from tools.verify_v07_gazebo_control_executor_linear_reversal import extract_reversal_replay
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.scenario.models import ScenarioSpec


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_observer(output_dir):
    output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    library=output_dir/"libaero_continuous_support_observer.so"
    pkg=subprocess.run(["pkg-config","--cflags","--libs","gz-sim8","gz-transport13","gz-msgs10"],check=True,text=True,capture_output=True)
    cmd=["c++","-std=c++17","-shared","-fPIC",str(PLUGIN_SOURCE),"-o",str(library),*shlex.split(pkg.stdout)]
    run=subprocess.run(cmd,text=True,capture_output=True)
    if run.returncode: raise RuntimeError("continuous support observer build failed:\n"+run.stderr[-6000:])
    info={"command":cmd,"source_sha256":sha(PLUGIN_SOURCE),"library_sha256":sha(library),"plugin_library":str(library.resolve())}
    gz=shutil.which("gz")
    if gz:
        p=subprocess.run([gz,"plugin","--info","--plugin",str(library)],text=True,capture_output=True)
        info["plugin_info_exit_code"]=p.returncode; info["plugin_info_stdout"]=p.stdout; info["plugin_info_stderr"]=p.stderr
        if p.returncode or PLUGIN_CLASS not in p.stdout or "ISystemPostUpdate" not in p.stdout:
            raise RuntimeError("plugin registration inspection failed: "+p.stdout+p.stderr)
    ldd=shutil.which("ldd")
    if ldd:
        p=subprocess.run([ldd,"-r",str(library)],text=True,capture_output=True)
        unresolved=[x.strip() for x in (p.stdout+p.stderr).splitlines() if "not found" in x or "undefined symbol" in x]
        info["ldd_exit_code"]=p.returncode; info["unresolved_dependencies"]=unresolved
        if p.returncode or unresolved: raise RuntimeError("plugin dependency inspection failed: "+repr(unresolved))
    return library,info


def insert_observer(diagnostic_sdf, library, output_ndjson):
    path=Path(diagnostic_sdf); root=ET.parse(path).getroot(); world=root.find("world")
    if world is None: raise ValueError("diagnostic SDF has no world")
    if world.find(f"plugin[@name='{PLUGIN_CLASS}']") is not None: raise ValueError("continuous observer already inserted")
    plugin=ET.SubElement(world,"plugin",{"name":PLUGIN_CLASS,"filename":str(Path(library).resolve())})
    ET.SubElement(plugin,"model_name").text="simple_agent"
    ET.SubElement(plugin,"ground_collision").text="ground::body::collision"
    ET.SubElement(plugin,"output").text=str(Path(output_ndjson).resolve())
    ET.indent(root); ET.ElementTree(root).write(path,encoding="utf-8",xml_declaration=True)
    return {"plugin_class_name":PLUGIN_CLASS,"plugin_library":str(Path(library).resolve()),"output_ndjson":str(Path(output_ndjson).resolve()),"plugin_scope":"world"}


def _semantic(node):
    if node.tag=="sensor" and node.get("name") in support_diag.DIAGNOSTIC_SENSOR_NAMES: return None
    if node.tag=="plugin" and (node.get("name")=="gz::sim::systems::JointStatePublisher" or "aero_diagnostic::" in node.get("name","")): return None
    children=tuple(x for x in (_semantic(c) for c in node) if x is not None)
    return (node.tag,tuple(sorted(node.attrib.items())),(node.text or "").strip(),children)


def resolve_support_collisions(root):
    model=root.find(".//model[@name='simple_agent']")
    if model is None: raise ValueError("production SDF has no simple_agent model")
    resolved=[]
    for label,(link_name,collision_name) in SUPPORTS.items():
        link=model.find(f"link[@name='{link_name}']")
        collision=link.find(f"collision[@name='{collision_name}']") if link is not None else None
        if collision is None: raise ValueError(f"unresolved support collision {label}: {link_name}/{collision_name}")
        resolved.append({"label":label,"link":link_name,"collision":collision_name})
    return resolved


def _sdf_preflight(artifact_dir, output, library):
    replay=extract_reversal_replay(artifact_dir); actions=replay["completed_episode_actions"][0]
    if len(actions)<24 or actions[22:24]!=["down","up"]: raise ValueError("source replay lacks Action23 DOWN → Action24 UP")
    if replay.get("target_action")!="up" or replay.get("previous_action")!="down": raise ValueError("source reversal contract mismatch")
    scenario=ScenarioSpec.from_dict(replay["scenario"])
    with tempfile.TemporaryDirectory(prefix="phase3hac-sdf-") as td:
        td=Path(td); production=GazeboWorldGenerator().generate(scenario,td,closed_loop=True,control_mode="PHYSICS")
        prod_hash=sha(production); diag,joint_info=joint_diag.instrument_diagnostic_sdf(production)
        contact_info=contact_diag.instrument_contact_sensors(diag,production)
        support_diag.add_caster_contact_sensors(diag,production,contact_info)
        support_diag._validate_observation_sdf(diag,production,joint_info,contact_info)
        observer_info=insert_observer(diag,library,output/"continuous_support_iterations.ndjson")
        prod_root=ET.parse(production).getroot(); diag_root=ET.parse(diag).getroot()
        if _semantic(prod_root)!=_semantic(diag_root): raise ValueError("diagnostic SDF changes more than observation-only additions")
        resolved=resolve_support_collisions(diag_root)
        if joint_info.get("production_sdf_unchanged") is not True or sha(production)!=prod_hash: raise ValueError("production SDF integrity failed")
        return {"production_sdf_sha256":prod_hash,"diagnostic_sdf_sha256":sha(diag),"only_observation_additions":True,
            "resolved_support_collisions":resolved,"observer":observer_info,"production_sdf_unchanged":True}


def preflight(artifact_dir, output):
    artifact_dir,output=Path(artifact_dir),Path(output)
    if not artifact_dir.is_dir(): raise FileNotFoundError(f"artifact dir missing: {artifact_dir}")
    replay=extract_reversal_replay(artifact_dir)
    if not replay.get("scenario"): raise ValueError("deterministic replay scenario missing")
    output.mkdir(parents=True,exist_ok=True)
    probe=output/".preflight-write-test"; probe.write_text("ok",encoding="ascii"); probe.unlink()
    header=Path("/usr/include/gz/sim8/gz/sim/components/ContactSensorData.hh")
    if not header.is_file(): raise FileNotFoundError("installed ContactSensorData public header missing")
    library,build=build_observer(output/"observer_build")
    sdf=_sdf_preflight(artifact_dir,output,library)
    # Synthetic one-iteration data exercises strict parser and four-support aggregation.
    syn=output/".synthetic-support.ndjson"
    supports={k:{"state":"VALID_EMPTY_CONTACT_SET","component_available":True,"contact_count":0,"contacts":[],"collision":{"entity_id":i+1}} for i,k in enumerate(SUPPORTS)}
    syn.write_text(json.dumps({"kind":"support_iteration","iteration":1,"sim_time_ns":1000000,"paused":False,"supports":supports})+"\n",encoding="utf-8")
    sample=analyze_file(syn,{"synthetic":[.001,.001]}); syn.unlink()
    if sample["phases"]["synthetic"]["total_ground_support_fn_N"]["median"]!=0: raise ValueError("synthetic analyzer check failed")
    report={"status":"PREFLIGHT_PASS","gazebo_launched":False,"artifact_dir":str(artifact_dir),"output_dir":str(output),
        "action_sequence":replay["completed_episode_actions"][0][22:24],"ContactSensorData_header":str(header),
        "observer_build":build,"sdf_integrity":sdf,"synthetic_analyzer":"PASS"}
    (output/"continuous_support_preflight.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return report


def run_diagnostic(artifact_dir,output):
    artifact_dir,output=Path(artifact_dir),Path(output); output.mkdir(parents=True,exist_ok=True)
    library,build=build_observer(output/"observer_build")
    ndjson=output/"continuous_support_iterations.ndjson"
    old=joint_diag.instrument_diagnostic_sdf; capture={}
    def instrument(production_sdf):
        diagnostic_sdf,info=old(production_sdf)
        capture["observer_sdf"]=insert_observer(diagnostic_sdf,library,ndjson)
        return diagnostic_sdf,info
    joint_diag.instrument_diagnostic_sdf=instrument
    try: native=native_diag.run_diagnostic(artifact_dir,output/"native_observation")
    finally: joint_diag.instrument_diagnostic_sdf=old
    if not ndjson.is_file(): raise RuntimeError("observer output was not created")
    rows=[json.loads(x) for x in ndjson.read_text(encoding="utf-8").splitlines() if x.strip()]
    intervals=native.get("phase_intervals_s",{})
    analysis=analyze_file(ndjson,intervals)
    native_by_iteration={row.get("iteration"):row for row in native.get("native_velocity_samples",[])
                         if isinstance(row.get("iteration"),int)}
    for phase in analysis.get("phases",{}).values():
        for sample in phase.get("transition_timeline",[]):
            native_row=native_by_iteration.get(sample["iteration"])
            links={item.get("name","").split("::")[-1]:item for item in (native_row or {}).get("links",[])}
            wheel=links.get("right_wheel",{}); body=links.get("body",{})
            sample["right_wheel_angular_velocity_world_rad_s"]=wheel.get("angular_velocity_world_rad_s")
            body_linear=body.get("linear_velocity_world_m_s")
            sample["body_forward_velocity_m_s"]=body_linear[0] if isinstance(body_linear,list) and len(body_linear)==3 else None
    phase_contact=native.get("contact_kinematics",{}).get("action24_acquisition",[])
    contact_by_time={round(float(row["simulation_timestamp_s"])*1e9):row for row in phase_contact
                     if row.get("simulation_timestamp_s") is not None and row.get("wheel")=="right_wheel"}
    up=analysis.get("phases",{}).get("action24_up_acquisition",{})
    for sample in up.get("transition_timeline",[]):
        contact=contact_by_time.get(sample["sim_time_ns"])
        sample["right_wheel_contact_relative_tangential_velocity_m_s"]=(contact.get("derived_contact_kinematics",{}).get("tangential_relative_speed_m_s") if contact else None)
    action24_failure_reproduced=bool(native.get("target_production_step_call_started") is True and
        native.get("target_production_step_returned") is False and native.get("target_exception"))
    report={"schema_version":"0.7.1","verifier":"continuous ContactSensorData support observation","status":"CAPTURED",
        "observer_build":build,"observer_sdf":capture.get("observer_sdf"),"observer_ndjson":str(ndjson),"observer_record_count":len(rows),
        "phase_intervals_s":intervals,"support_analysis":analysis,"native_diagnostic":native,
        "action24_failure_reproduced":action24_failure_reproduced,
        "production_behavior_modified":False,"production_sdf_changed":False,"physics_changed":False,
        "support_case_classification":classify_action24_support_case(analysis,action24_failure_reproduced)}
    out=output/"action24_continuous_support.json"; out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir",type=Path,default=DEFAULT_ARTIFACT)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight-only",action="store_true")
    args=parser.parse_args(argv)
    report=preflight(args.artifact_dir,args.output) if args.preflight_only else run_diagnostic(args.artifact_dir,args.output)
    print("Gazebo continuous support diagnostic: "+report["status"])
    print("evidence: "+str(args.output))
    return 0
if __name__=="__main__": raise SystemExit(main())
