# v10 small-01 single approved execution — FAIL

User explicitly approved the exact 05721b8 proposal once. Observed HEAD was
05721b885aeb4b3dba2dfad17d695b162c9bf797, branch experiment/dart-internal-trace.
Contract SHA256: 63f630e5e0aee7c19c09b693a8cc9c6d45e54f77b8d022820eb0b6b85c5a7395.
Exact proposal command was executed once without argument changes; exit 78. No retry, rebuild, cap increase or repair.
Preflight: all 116 contract hashes and source dev/inode/size matched, 4 objects/5 paths,
output/marker absent including dangling links, both user units not-found. Sandbox bus query
was denied; a separately approved read-only host query confirmed absence before execution.
The one runtime invocation itself received environment execution approval.

|Required evidence|Observed result|
|---|---|
|Owner domain/handoff|Owner service invocation captured with MemoryMax 5368709120; collector failed `owner handoff disconnect`. Native PID1 handoff not established.|
|Actual sealed RO FD delivery|Not established; no C/K or delivery evidence. Control copies may have been prepared before failure; no claim of successful four-object delivery.|
|Threads/descendants and callback|Not established; no independent task trace or successful callback/join/COMPLETE/EOF evidence.|
|Independent audit continuity|FAIL: collector-audit.jsonl and native-audit.jsonl are both empty. owner-journal.raw and raw target streams also empty.|
|Exit codes|Exact command 78; systemd reports service main status 78; collector reports native parent wait 78 and status FAIL. Worker/target successful exit is unproven.|
|Cleanup|Collector target_cleanup true, host owner_cleanup true. Fresh unit readback: both not-found, MainPID 0, empty ControlGroup. Both recorded cgroup directories absent; /proc cgroup scan found zero matching residual processes, zero permission-unknown entries.|
|Original integrity|All 116 contract-file hashes unchanged after run; 1617 prior baseline files unchanged excluding intended handoff, original dangling symlink preserved. No tracked runtime-source changes.|

Host result reason is `unit ownership not proven`; collector result reason is `owner handoff disconnect`.
These are distinct observations. The earliest native root cause is UNRESOLVED; empty journal
and audit logs cannot support a more specific diagnosis. Host stdout/stderr were created with
mode 0664, unlike the proposal's stated 0600 logging mode; this additional discrepancy is
recorded without changing existing evidence. Other audit/raw logs were observed 0600.
No PASS is inferred from cleanup or earlier static/mock results.

Evidence: work/runtime-small-01/{host-result.json,collector-result.json,target-unit.json,
host.stdout,host.stderr,collector-audit.jsonl,native-audit.jsonl,owner-journal.raw,stdout.raw,stderr.raw}.
Exclusive marker work/harmless-small-01.once remains consumed and preserved.
Machine-readable verification and original evidence hashes: reports/runtime_small_01_verification.json.
Raw logs/marker remain local ignored artifacts; Git publication does not transfer them and /tmp is not durable.
Host: jiwon-System-Product-Name. Post-run project-CWD snapshot found no tasks; external/remote jobs UNKNOWN.
No original main files were written; pre-existing worktree untracked plugin symlink remains uncommitted.

No Gazebo/DART/harness or physical step, large object/full468 preparation, sudo/package/system change.
Original actual launcher exit78 is retained by source hash, not by running it again.
Stage B BLOCKED / risk acceptance UNDECIDED / Gazebo runtime UNVERIFIED.
Next action: stop. Any repair/rebuild/new execution requires a separate user scope and a new contract/approval;
this one-shot marker/output must never be reused or deleted for retry.
