# Joint build v1 progress

BLOCKED_AFTER_PROBE_STAGE / NOT_EXECUTION_READY / NOT_RUNTIME_VERIFIED.

Input lock PASS (47087 unique files); sources3 extracted/patched in fresh copies and expected digests MATCH. Probe configure, selection(96 external files), compile/link, ELF closure(7 nodes), local-prefix stage command PASS. First failure: probe.receipt exit1; build/prefix SHA differ. Read-only comparison shows exactly one .dynstr byte at6339, colon58→NUL0 from CMake RPATH_CHANGE. Same Build ID/SONAME/NEEDED is not byte identity. No receipt accepted. DART/physics/Sim/harness NOT_STARTED. No retry/guard change/target load/run/CTest/try_run/service/marker/sudo/system change. Stage B BLOCKED, risk acceptance UNDECIDED. Original inputs and main metadata preserved.
