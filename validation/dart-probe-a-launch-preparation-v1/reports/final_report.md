# DART Probe A Runtime Launch Preparation V1

**PROBE_A_LAUNCH_READY / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.

실제 실행 가능한 Native Loader와 다음 단계의 Core-only 실행 계약을 준비했다. **이번에는 실제 DART dlopen/dlclose, Gazebo, World/step, Stage B를 수행하지 않았다.** 원본 main과 기존 미커밋 파일·Evidence는 보존했다. Autonomous Experiment Lab은 별도 DEFERRED 상태다.

## 구현과 무결성

시작 HEAD `9abcbff2cf1ef3f52a2c2d1a348779e87b304841` 및 clean 상태를 확인했다. 기존 Final Integration의 C 소스·Supervisor·stage·manifest/alias/mapped identity helper를 새 경로에서 재사용했다. 새 Loader는 기존 Core REL 소스를 포함해 `-ldl`로 링크한 executable ELF(DYN/PIE)다. DART는 DT_NEEDED에 없으며 libc/loader만 시작 시 매핑한다.

- 산출물: `work/native_loader` (로컬 ignored build, Git 제외), 26,088 bytes.
- SHA-256: `f7668a73461feca54d2178cd0ab3bef37958a1d8d3ab0118fec3511894f16cc3`
- Build-ID: `5215d51221cf598875d5b9b362c9b4d6afc412d4`
- 컴파일: C11/O2/Wall/Wextra/Werror/stack protector/RELRO/NOW. ELF header/dynamic 정보는 loader_identity.json.

기본 실행은 exit77이고 Core를 로드하지 않는다. `--contract`와 `launch.py` 기본 실행은 계약만 출력한다. 명시적 Supervisor `--execute-approved-core-load`가 stage의 `--owned-runtime-stage`와 Native `--harness-runtime`으로 연결될 때만 Core 로딩 경로에 진입한다. 기존 독립 Core CLI handler는 제거해 준비된 Sandbox 경로로 모았다.

Core canonical path는 `/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2`다. 기존16개 Allowlist와58개 전이 edge/SONAME alias를 재사용한다. immutable manifest pin과 열린 FD의 SHA/Build-ID/device/inode를 host 및 stage에서 검사하며, 바뀌면 launch/GO를 거부한다. 새 ELF도 같은 방식으로 pin했다. source hashes를 runtime_contract에 기록해 향후 실행 전 준비 소스 변경도 거부한다. 바이너리 재빌드나 다른 기기 이동 시 무조건 pin을 재생성해 불일치를 덮지 않는다.

## Supervisor·Sandbox 연결

systemd user transient service → 기존 Bubblewrap layout → 새 Native Loader → post-open WAIT → strict Core gate → GO → dlclose → 종료·정리 경로를 구성했다. 이 중 **실제 Core open/strict mapping 분기는 준비·mock dispatch 확인에 한정**하며 이번 서비스 실행은 같은 ELF의 no-load 모드다.

RO root/dev/FD files, net/user/mnt/pid isolation, private tmpfs, sterile environment 및 Core alias mounts는 기존 stage layout을 재사용한다. MemoryMax64M/swap0/TasksMax8/CPUQuota25%와 total8s/stop2s, CPU2s/AS256MiB 등 기존 한계를 유지했다. Native post-open 대기는3초다. runtime strict gate는 기존 readiness.post_open의 Core16 전체 mapping 검사를 사용하고 permission을 GO로 변환한다.

현재 실행 브랜치와 기준 commit의 ancestry를 확인하므로 준비 commit 이후에도 명령을 사용할 수 있다. 실제 동작 artifact와 source hash, profile identities는 별도로 검사한다. user/service/environment 설정 변경은 없다.

## 검증 결과

새 executable ELF의 기본/contract/unsupported/mock error 실행, 자체 identity, DT_NEEDED의 DART 부재 및 dlopen/dlclose 심볼 존재, 기존 Core manifest 일치, strict gate dispatch, 실제 cgroup/정리 및 GO 차단을 집중 검증했다. **12 PASS / 0 FAIL / runner SKIP0**.

새 ELF로 실제 무해 service3건을 실행했다: accept exit0/GO true/body true, SHA 불일치 reject exit78/GO false/body false, no-GO timeout exit78/약3초/body false. 세 실행 모두 기존64MiB/8task/25% readback, isolation gate, own unit/cgroup 제거·관측PID/start잔여0·canary/temp정리가 PASS다. reports/{accept,reject,timeout}에 원본 경량 증거가 있다. 기존 전체 테스트·DART 감사·이전 service attempt는 재실행하지 않았다.

accept 이후 실행 분기의 HEAD 조건을 branch/ancestry로 일반화하고 last-cgroup sample 수집을 추가했다. 변경된 Supervisor는 reject/timeout에서 검증했고, accept의 launch/gate/cleanup 경로는 동일하다. 불필요한 accept 재실행은 하지 않았다. 마지막 source 주석 정정 후 재빌드한 ELF의 bytes/SHA가 같음을 확인했고 집중 테스트를 재확인했다.

SKIP: 실제 Core open/close/init/fini/maps,64MiB 충분성, resource 초과 강제효과, 강제 systemd timeout/신호 주입. Native timeout은 systemd RuntimeMaxSec 강제효과 인증이 아니다.

## Runtime 계약과 위험

runtime_contract.json은 별도 승인 후 사용할 명령과 dlopen/error, mapped libraries/allowlist, memory.current/peak/events, exit/signal/timeout, cleanup, 원본 무결성 수집을 정의한다. Native/서비스 원시 이벤트와 stderr를 보존한다. 종료 직전 cgroup 표본이나 수거된 unit의 exit metadata를 놓칠 수 있으므로 근거가 없으면 UNKNOWN이며, not-found 기본 property를 runtime 결과로 해석하지 않는다. native signal 이벤트·전파 rc와 관측된 마지막 자원 표본도 함께 보관한다.

map_files EPERM fallback은 proc-root FD와 maps device/inode 및 SHA/Build-ID의 제한된 file identity다. resident COW/relocation 페이지·검사 이후 mutation을 인증하지 않는다. post-open gate 전에 ELF constructors/IFUNC가 이미 실행되므로 초기화 부작용을 사전 차단하지 못한다. dlclose finalizer/hang/잔류 mapping 위험도 남는다.

무해 peak는 resource_assessment.json에 기록했다. DART 초기화가64MiB·8tasks·25%/8초 안에 가능한지는 미검증이다.128MiB는 필요 시 검토할 후보일 뿐 설정 변경이나 충분성 주장이 아니다. 메모리 부족/timeout이면 증거를 보존하고 종료하며 임의 상향·재시도하지 않는다.

## 다음 실제 실행 절차 — 이번에 실행하지 않음

1. 별도 Core-only Runtime 실행 승인을 받으며 fallback/초기화/자원 위험을 함께 검토한다.
2. 같은 실험 worktree에서 `scripts/launch.py` 기본 실행으로 계약을 읽는다. source/ELF/manifest pin이 변경되거나 build가 없으면 중단하고 재검증한다.
3. 승인 후 단1회 다음 명령을 실행한다. 이 문서 작성 단계에서는 실행하지 않았다.

```bash
cd /tmp/AeroAIStudio-dart-internal-trace
env -u LD_PRELOAD -u LD_AUDIT -u LD_LIBRARY_PATH PYTHONDONTWRITEBYTECODE=1 python3 validation/dart-probe-a-launch-preparation-v1/scripts/launch.py --execute-approved-core-load
```

4. wrapper가 실행 전 original/main/evidence snapshot을 만들고, service를 wait/cleanup한 뒤 runtime_integrity.json을 작성한다. reports/runtime/의 observation/mapping/resource/cleanup 및 stdout/stderr로 open→strict identity→GO→close 순서·exit·signal·timeout을 검토한다. 이미 존재하는 runtime attempt는 재사용/덮어쓰지 않는다.
5. 오류·UNKNOWN·불완전 수집은 성공으로 올리지 않고 정지한다. 다른 Probe나 World/Gazebo/Stage B로 자동 진행하지 않는다.

## 보존과 게시

integrity.json은 기존 파일 전체 SHA 비교와 main HEAD/status 유지 결과다. 신규 task와 실험 handoff만 이번 변경이며 기존 source/evidence·시스템·Clock/Capture 기준은 변경하지 않았다. 경량 source/tests/reports만 commit/push한다. binary/raw snapshots/pin/attempt 및 로컬 git_publication receipt는 제외한다. /tmp/ignored/untracked 자료는 다른 기기에 자동 전달되지 않는다. 실제 게시SHA/원격 일치는 receipt 및 최종응답 참조.
