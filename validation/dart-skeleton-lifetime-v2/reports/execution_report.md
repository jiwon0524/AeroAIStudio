# Empty Skeleton V2 — approved one-shot execution

**EMPTY_SKELETON_LIFETIME_PASS / Stage B BLOCKED**. Explicit user approval covered exactly one launch at f96f5b028fac6e3847b6e6a9fad2ce16c1f4db45 on experiment/dart-internal-trace. The specified command ran once, wrapper exit0; retries0, limit increases0, code changes0.

Preflight: HEAD/branch/clean, 22 pinned source hashes, pinned manifest, executable and Core16 readonly FD identities PASS. Static actual Bubblewrap argv resolved62edges; libdart.so.6.13 points to the same approved canonical Core FD. All prior V2 outputs and markers absent. Initial sandbox bus read was denied; authorized outside-sandbox read confirmed manager running before launch. No launch retry occurred.

Runtime: strict Core16 plus executable identity PASS_FILE_IDENTITY before GO. Fixture host PID227792/start25079688, same-unit membership and separate mnt/net/user/pid namespaces confirmed. stdout: post_open_ready WAIT -> created empty:true -> lifetime_success expired:true. Source contract checks weak_ptr validity before reset and expiration after reset. systemd-run exit0, stderr code=exited/status=0, service897ms, CPU222ms, swap peak0B. No signal/timeout event observed; collected unit final execution properties unavailable after unit removal.

Live limits: memory.max67108864, memory.swap.max0, pids.max8, cpu.max25000 100000; RuntimeMax8s and TimeoutStop2s readback matched. Observed memory.current4460544, peak11812864 bytes, pids.current3; last sample memory.current4108288, peak11812864, pids3. memory.events all recorded counters0 including max/oom/oom_kill. Last sample is not guaranteed final. Limit-excess enforcement not tested.

Cleanup PASS: unit not-found, cgroup removed, observed PID/start remnants0, host temporary directory and canary removed; host connections absent. During CPU-controller activation differences were expected by the existing gate; selected controller settings before/after diff0. Original integrity PASS: changed/missing0, new files in existing scope0, original main HEAD/status unchanged. Both consumed markers and raw stdout/stderr/snapshots remain intact.

File identity limitation: map_files direct FD open EPERM; existing proc-root FD fallback matched hashes/Build-ID/device/inode, including Core alias. This does not certify resident COW pages or constructor side effects. Full ABI/runtime neutrality, Gazebo, World::step and Stage B remain uncertified/blocked.

Evidence: execution_review.json, runtime/{mapped_library_validation,native_fixture_execution,runtime_observation,resource_readback,process_cleanup,controller_diff,supervisor_integration}.json and runtime_integrity.json. Raw ELF/pins/snapshots/markers under work are local and not transferred by Git. No Probe A/V1 rerun, package/system/production/main modification. No further execution authorized.
