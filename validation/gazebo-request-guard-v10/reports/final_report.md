# Request guard v10 — 작은 무해 종단 드라이버 준비

기준/관측 HEAD e37a69229a1a1a77937f0c22335a78a2858f86a0, experiment/dart-internal-trace.
AGENTS/DEVELOPMENT_RULES/context-handoff/handoff/v9 final·candidate 계약을 먼저 대조했다.
원래 tracked/index dirt 없이 기존 untracked dangling symlink만 있었다. 새 v10 디렉터리와 handoff만 현재 작업 소유다.
**Stage B BLOCKED / 위험 수용 미결정 / 런타임 미검증.**

## 저장된 구현

- 별도 driver.py CLI와 owner_main.c, libc-only probe.c. 실제 launcher/v9 entry78 유지.
  별도 명시 승인 뒤에만 쓸 고정1회 CLI를 만들었고 지금 실행하지 않았다.
- v9 owner.py receiver와 owner_bridge.h를 byte-for-byte 재사용. native catalog/launch/control/metadata는
  compile-time4객체/5경로 프로필로 빌드했다. 전체468 정책을 줄여 배치한 것으로 기록하지 않는다.
- 초기O→C/K→placement P→independent audit/A→기존 run/step/finish collector와 harmless GO/100/EXIT_ACK
  상태머신을 연결했다. 24byte fixed와 별칭을 root/thread/process가 각자 broker를 통해 받게 구성했다.
  atexit callback은 EXIT_ACK 뒤 thread를 깨우고 alias read+join을 끝낸다. TASK_BORN/DEAD와 non-root INPUT_DELIVERED
  두 종류가 없으면 최종 V가 없다. 모든 거부·감사 loss·단절·종료 실패는 영구 실패다.
- v9 target rlimits/resources 유지; owner/collector 별도5GiB gate 및 target512MiB placement를 분리했다.
  manager 단일 호출은2s; owner safety timer40s, target30s. 실제 unit 생성/적용은0이다.
- 작은 프로필에만 필요한 poll/wait4/getrandom/madvise 및 정확한 glibc fork scalar subset을 허용했다.
  prlimit64는 pid0/new_limit=NULL인 self query만 scalar 검사해 허용한다. 임의 clone flags/exec는 거부한다.
  이 작은 정책으로 전체 v9 정상 loader 정책을 검증했다고 주장하지 않는다.
- map_files의 과거 EPERM 한계를 권한 상승 없이 처리하는 SmallProc를 분리했다. retained immutable pin+
  kernel map dev/ino+canonical RO FD/mount를 모두 확인하는 명시적 small-only fallback이며 v9 파일은 그대로다.
  fallback/5경로 readback을 독립 collector audit에 저장하고 PID/start/maps 안정성을 확인한다.
- unit 이름/description만으로 target을 stop하지 않도록 durable InvocationID/cgroup 영수증을 anchor 관찰 전에
  저장한다. 소유 증거를 잃으면 정리 UNKNOWN/FAIL, 임의 signal/stop 없음. marker/출력은 exclusive/새 경로다.

## 수정·재검증한 오류

새 small catalog projection의 digest 선택 필드 처리(KeyError)를 고쳤다. host finally에서 owner 정리 실패 시에도
별도 target 정리를 시도하도록 고쳤다. exec pass_fds가 private control FD CLOEXEC를 지우는 것을 owner_main에서
복구하고 실패 시 bootstrap 전에78로 거부한다. small policy self-prlimit query와 delayed thread/fork 입력 증거도
같은 작업에서 보강했다. 모의 fixture의 numeric start/schema·inode 변조 위치도 바로잡았다.
어떤 수정도 원래 v9 소스·보고서·ELF·marker를 덮어쓰지 않았다. 중간 native build/object/log는 각 timestamp work에 보존했고 최종 영수증 사본도 마지막 work에 보관했다.

## 검증한 범위와 해시

**6 TU compile/link**: probe, owner_main, catalog, launch, metadata, control.
**4 objects 재사용**: v9의 broker/bound/loader/namespace. 이전 dependency/object SHA와 새 동일 source를 확인했다.
anchor ELF도 SHA 인증 후 재사용했다. consumer DSO·Gazebo/DART/harness는 이 빌드에 없다.
-Wall/-Wextra/-Werror, stack protector, PIE/RELRO/NOW. readelf 정적 검사만 했고 어느 native ELF도 실행하지 않았다.

새 **2119 static/Python mock PASS**:1617 기존 tracked-file 보존 checks,376 source/dependency/artifact SHA checks,
나머지126 정책·전달·감사·종료·source invariant/모의 assertions이다. 2119을2119개 실제 실행 시나리오로 표현하지 않는다.
기존 v9의1638은 source/report hash로 재사용한 결과이며 이번 수에 합산·재실행하지 않았다.
기존 resolution harmless PASS_ISOLATION_PATH_ONLY(100 fixture, zero physics, GO/EXIT_ACK/EOF/cleanup)의
summary와 원시 결과/stdout/stderr hash를 인증해 재사용했으며 그 성공을 새 guard 실행 성공으로 확장하지 않았다.
ready stdout이 독립 입력 audit보다 먼저 도착하는 경우에는 근거를 기다리고, audit catch-up 뒤에만 GO를 보낸다.
필수 입력 audit가 끝내 없으면 GO/V 없이 실패하는 교차 채널 순서도 재검증했다.

실제 Owner.bind 및 Catalog와 coordinator의 전체O/4C/K/P/A/GO/ACK/V 흐름을 OS/transport/manager mocks로
검사했다. mandatory owner/FD/path 누락, alias/hash/RO/seal/inode 오류, record gap·early/late audit EOF,
callback/child-death/COMPLETE/terminal 증거 누락, concurrent request binding와 overlapping VMA 거부,
post-ACK worker FD 누락, pin release 실패, unit 재사용·영수증 누락, host 서비스/종료/정리 실패를 확인했다.
C 함수와 kernel/userns/ptrace/mount/pidfd/cgroup 서비스는 모의로 성공을 실증한 것이 아니다.

|연결 기록|SHA256|
|---|---|
|execution_contract.json|`63f630e5e0aee7c19c09b693a8cc9c6d45e54f77b8d022820eb0b6b85c5a7395`|
|source manifest canonical|`35d9ddaa88246d1809ff320472f77b770c83b16a99154a827747b316124673f5`|
|build_receipt.json|`f0a83d85ccaa5ca03567301e812844856a345de39a3d84afa4b6086c99217100`|
|tests.json|`f333b198db045193ae12d8b83da0cc697988bf77ee8b585bd4494f843e8eeab7`|

build receipt는 compiler/header/source/object/ELF SHA와 process host/PID/start/로그를, source manifest는 실제 C/Python/
policy/test와 재사용 Python을 묶는다. tests는 같은 source manifest, 실제 build receipt·계약·native artifact SHA를
검사 시작/종료에 재확인했다. Python-only 수정 뒤에는 native dependencies/ELF를 재확인하고 seal만 갱신했으며
그것을 C 재컴파일로 세지 않았다. 최종 테스트 후 source 변경은 없다. 문서/인계는 별도 artifacts index로 묶는다.

허용된 비실행 재현:

```bash
python3 -B validation/gazebo-request-guard-v10/scripts/build.py
python3 -B validation/gazebo-request-guard-v10/scripts/seal.py
python3 -B validation/gazebo-request-guard-v10/tests/check.py
```

재빌드는 ELF/path/inode/contract SHA를 바꿀 수 있으므로 기존 실행 승인안은 재생성·재검증해야 한다.
검사 함수에서 driver.main([])의78 거부 및 file-only 검증, mock coordinator/host 로직만 호출했다.
실제 driver --execute-once/--collector-stage, probe/owner/anchor, harness·DART/Gazebo는 호출하지 않았다.

## 실행 승인안과 남은 범위

**비실행 준비 완료 / 별도1회 실행 승인 대기.** 정확한 한 명령·모든 바이너리/입력 SHA,
두 unit/출력/새1회 marker·caps/deadlines·통과/중단/정리 기준은 [approval_proposal.md](approval_proposal.md)에 통합했다.
알려진 미해결 정적 차단은 없다. 실제 첫 gate는 계약/source hash/branch·unit/output/marker 부재 확인이며,
그 다음 owner5GiB readback·userns/namespace·initial owner 인계다. 관리자/커널 권한·LSM/userns/pidfd/AttachProcesses
등 실제 동작은 승인된1회에서만 판정한다. 미지원이면 marker/증거를 보존하고 FAIL; 자동 retry/cap 증가 없음.
소유 InvocationID 증거를 수집하지 못한 정리 경로는 UNKNOWN/FAIL이며 별도 소유 복구가 필요할 수 있다.

이번 실제 preparation0 objects / 전달0 paths / 새 unit0 / marker 소비0.
예정 작은 시험은 policy4 originals/5paths+별도 control memfd2개이며5개 대형 객체,303/468 전달,
최대 peak 메모리와Gazebo 동작은 제외다. 작은 입력의 known 비용 계산은 승인안에 있으며 메모리 실측값은 없다.
작은 성공을 대형 객체 준비·Stage B·전체 normal policy 통과로 기록하지 않는다.

## 보존·저장·게시

원래 main HEAD/dirty와 e37 기준1617 tracked파일(인계 제외), dangling symlink dev/inode/target를 확인했다.
기존 ignored 산출물과 marker에 쓰는 코드는 호출하지 않았고 old ELF/objects는 읽기 전용 hash검사로만 재사용했다.
빌드·검사 subprocess는 종료했고 다른 기존 작업 가시성은 UNKNOWN; 기존 작업 종료/재시작 없음.
source/고정입력/경량 보고서/인계만 publication_files.txt로 자동 게시하며 raw logs/ELF/objects/old raw evidence는 제외한다.
로컬 /tmp ignored work는 영구·원격 백업이 아니다. 이 문서는 게시 전 상태이며 commit/push/remote 일치는
work/publication-result.json 및 최종 응답에서 별도 확인한다. 실행은 게시와 무관하게 별도 승인 전까지 보류한다.
