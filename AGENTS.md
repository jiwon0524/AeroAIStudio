# DART Internal Trace experimental worktree

- Branch: `experiment/dart-internal-trace`. The original main worktree remains at `/home/jiwon/Projects/AeroAIStudio` and is read-only for this task; preserve all of its existing uncommitted files and evidence.
- Current user authorization permits isolated dependency download/extraction, new baseline/trace builds, static ABI analysis and offline tests only. Commit/push only verified lightweight files on this experiment branch. No force push, main edit/push or merge.
- Never execute Gazebo, `World::step` or Stage B. Never modify production Physics/SDF, solver algorithms, system packages/libraries, global loader configuration, Capture Validity or Clock criteria. Stage B BLOCKED; NOT_RUNTIME_VERIFIED.
- Existing implementation/parity sources and artifacts are read-only inputs. Never overwrite their outputs. `validation/dart-capability-abi-v2/work` and `downloads` are isolated new artifacts and must not be committed.
- Read/update `handoff.md` using context-handoff after meaningful stages and before account/session changes. Record evidence paths rather than raw logs. Do not save secrets, switch accounts, terminate existing tasks or replay recorded commands automatically.
