# DART Internal Trace experimental worktree

- Branch: `experiment/dart-internal-trace`. The original main worktree remains at `/home/jiwon/Projects/AeroAIStudio` and its code/evidence remain read-only; preserve existing uncommitted work. The current explicit development-rules request updates only its existing local untracked AGENTS.md guidance.
- Current user authorization permits isolated dependency download/extraction, new baseline/trace builds, static ABI analysis and offline tests only. Commit/push only verified lightweight files on this experiment branch. No force push, main edit/push or merge.
- Never execute Gazebo, `World::step` or Stage B. Never modify production Physics/SDF, solver algorithms, system packages/libraries, global loader configuration, Capture Validity or Clock criteria. Stage B BLOCKED; NOT_RUNTIME_VERIFIED.
- Existing implementation/parity sources and artifacts are read-only inputs. Never overwrite their outputs. `validation/dart-capability-abi-v2/work` and `downloads` are isolated new artifacts and must not be committed.
- Read/update `handoff.md` using context-handoff after meaningful stages and before account/session changes. Record evidence paths rather than raw logs. Do not save secrets, switch accounts, terminate existing tasks or replay recorded commands automatically.

## 체크포인트 자동 게시

- 사용자 승인에 따라 [개발 기록·게시 규칙](docs/DEVELOPMENT_RULES.md)을 따른다. 구현/테스트 완료, 조사 단계 종료, 실패·차단 확인, 계정·기기 변경 전, 최종 마일스톤 완료 때 검증·기록 갱신 후 현재 승인된 실험 브랜치에 자동 commit/push한다. 조건을 만족하면 별도 게시 요청을 기다리지 않는다.
- 미검증 코드는 로컬에 보존하고, 확인된 실패 분석·인계 문서는 실패/미완료 상태 그대로 게시할 수 있다. 파일을 명시적으로 선택하고 실제 push와 원격 commit 일치를 확인한다.
- main/force push/무단 staging 정리는 금지한다. 인증·권한·분기 충돌·검증 부족이면 결과를 보존하고 차단을 알린다. 공통 스킬 저장소로 Aero 자료를 복사하지 않는다.
- 자동화는 작업 에이전트의 단계 종료 절차다. 상시 daemon/hook, 계정 전환, 기존 프로세스 종료는 수행하지 않는다. 이 승인은 물리 실행 제한을 바꾸지 않는다.
