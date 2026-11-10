# Request guard v9 — 승인된 준비 한도와 전체 후보 계약

기준 HEAD `35bc722847bc8676fc808b392b5680c6d08b2c29`, branch `experiment/dart-internal-trace`.
AGENTS, DEVELOPMENT_RULES, context-handoff, handoff, v7/v8 final과 원래 봉인 계약을 대조했다.
v8의 로컬 검증 보고서에 남은 NOT_COMMITTED는 당시 이력이다. 실제 게시 기준은35bc722이다.
v8 소스·보고서·산출물은 그대로 보존하고 v9만 추가했다.

**Stage B BLOCKED / 위험 수용 미결정 / 런타임 미검증.**
이번 결과는 후보 구성·callable 통합·빌드·정적/Python 모의 검증이다. 배치·실행 준비 전체 완료는 아니다.
원래 launcher와 candidate entry는 서비스·marker 생성 전 exit78. 실제 한도/서비스/시스템 설정 변경 없음.

## 구현 완료

|후보 설정|기존|승인된 후보값(bytes)|귀속|
|---|---:|---:|---|
|객체 cap|67108864|543979760|native catalog 준비·최종 verify 모두 같은 preparation_limits.h|
|준비 admission cap|536870912|2159132672|303개 출력의 페이지 합+공용128KiB; 모든 stage/bootstrap 호출|
|MemoryMax|전용 owner domain 미배치|5368709120|별도 preparer/native owner/Python collector 공용 domain의 구성값만|

추가 상향 근거는 현재 없다. 승인된 값보다 높이지 않았다. owner_properties는 MemoryMax만 반환하며
대상 properties와 병합하지 않는다. native preparation_domain은 복사 전에 자신과 collector peer의
cgroup 일치 및 memory.max 정확한5GiB를 읽기 전용 검사한다. 루트·불명확·다른 domain·한도 불일치와 잘린 cgroup 경로를 거부한다.
owner receiver도 정확히5GiB 및 held PID1/parent/ELF/pidfd/credential과 두 번의 readback을 확인한다.
BootstrapCoordinator는 Python 측 parent/collector PID/start/domain/target 분리를 확인한 뒤 최초O,
303 C/K, PLACE/P, 독립 audit/A, 기존 controller를 연결하고 최초 host deadline을 수집 시간의 상한으로 전달하고 정리 후 최종 판정 직전에도 확인한다.
O는 준비 성공이 아닌 identity ACK이며, catalog final과 모든 필수FD 검증 없이는 다음 phase로 가지 않는다.

대상은 원래 MemoryMax536870912/Swap0/Tasks64/CPU100%/Runtime30s/stop2s,
RLIMIT CPU10/AS2147483648/FSIZE1048576/NOFILE256/CORE0이다. 자식의 기존 정확한 setrlimit와
대상 unit readback, namespace/cap drop 검사를 보존했다. owner5GiB가 대상512MiB를 대체하지 않는다.
preparer FSIZE floor543979760 및 NOFILE303 pins+현재 FD+3 여유는 기존 native admission에서 검사한다.
Python 관측 AS/FSIZE unlimited, NOFILE1048576은 candidate_contract의 읽기 전용 현 호스트 관측이며
미래 프로세스의 보장이 아니다. 어떤 rlimit도 이번 작업에서 적용하지 않았다.

## 468경로 계약 대조와 live FD 계약

candidate_contract.json은 원래 canonical 봉인SHA
`789737d947f8c0ebd1466300792667fc9c838adba5834168e5c82bc6e4846aae`를 인증한 뒤 생성했다.
필수468경로=303 원본 dev/inode 그룹. 5개 대형 객체=16경로이며 모두 기존 봉인 범위에 있다.
각 경로의 원본 승인 identity/hash, 후보 source identity/hash, size, executable intent, aliases를 기록했다.
303 source를 O_RDONLY/O_NOFOLLOW 같은FD로 열어 전후 stat(dev/inode/size/mtime/ctime)와 SHA256을
확인했다. C allowlist468행과 JSON 전체를 일치 비교했다. 누락/중복/별칭별 불일치/다른 원본 합치기는 거부한다.
v8에서 검증된 native DSO와 생성된 joint-elf allowlist 두 대체 객체만 재사용하고 그 해시도 다시 확인했다.
원래 봉인 manifest를 수정하거나 새 candidate를 원래 실행 승인으로 취급하지 않았다.

실제 준비는 최종 sealed memfd의 RO reopen/seals0x2f/hash/파일 identity를 확인하고 FD로 bind한다.
RDONLY/NOSUID/NODEV 및 객체별 NOEXEC, canonical open identity를 유지한다. 별칭은 같은pin,
동일SHA의 서로 다른3 DART inode는 별도3출력이다. Collector는 live retained FD를 독립 재검증하고
완전한303 pins에서만468경로 projection을 만든다. constructor에서도 전체 정책·한도를 재판정한다.
기존 single exec guard, listener/ACK, descendant tracking, 독립 감사, GO, 종료 직전 live mapping,
EXIT_ACK, COMPLETE/audit EOF/stdout+stderr EOF/exit/정리/integrity와 pins-close-before-V를 유지한다.
거부·audit record loss·중첩 mutation·단절·phase 오류·deadline·종료 증거 누락은 실패한다.

**정적 source/계약 검증468 / 이번 실제 준비0객체 / 실제 mount·loader 전달0경로.**
기존 historical298/452 준비를 현재 보유 FD로 재사용하지 않았다. 새FD 또는 서비스 실행은 없다.

## 비용: 계산값과 미측정값 구분

5개 파일 bytes: dartsim99090256, codegen DART543979760, Sim74462608,
header DART543979760, physics DART543979760. 합1805492144, dense pages1805500416.
세 DART는 동일SHA지만 다른 원본 inode라 세 번 보유한다. aliases16은 추가16복사가 아니다.

|계산 항목|bytes|귀속/설명|
|---|---:|---|
|v9 후보303 출력 pages|2158563328|preparer 생성 후 owner/collector 공유; alias/mount/dup마다 복사하지 않음|
|native 출력+직렬64KiB copy/64KiB hash|2158694400|native 준비 admission 모델|
|승인 admission cap|2159132672|438272 여유; overhead를 포함하는 총 메모리 cap 아님|
|collector 출력+1MiB hash buffer|2159611904|별도 hash phase; native128KiB와 무조건 중첩 합산하지 않음|
|v7 cold source cache 포함 모델|4330491904|all429 source+validator cache2171359232와 구 출력 포함; 계산 재사용|
|위 모델+명시 reserve268435456|4598927360|Python/native heap, FD/VMA/slab/socket/audit-cache 등 reserve; 실측 상한 보장 아님|
|owner/collector cap|5368709120|구 모델 대비769781760 여유; v9 출력 감소438272는 추가 보수 여유|
|독립 target cap|536870912|private/COW/anonymous/thread stacks/page tables 등 target charge는 runtime 확인|
|owner+target 두 domain 상한 합|5905580032|논리 합계; 공유 페이지가 domain별로 중복 청구된다는 뜻 아님|

새 supervisor ELF961336 bytes는 catalog 출력303에 넣지 않는다. supervisor/anchor/source/code/report
page cache와 allocator/kernel/IO 비용은 owner overhead 쪽이며 이전 cache 모델에 새 v9 비용이 전부
포함됐다고 주장하지 않는다. 5GiB에 대한 추가 reserve의 충분성, 실제 페이지 charge domain,
preparation memory.peak, 실행 중 memory.current/peak는 모두 UNKNOWN_NOT_RUN이다.
대상 AS2GiB는 가상주소 한도이고 owner의 출력2.16GB와 같은 계정이 아니다. 실측 성공을 추정하지 않는다.

## 빌드·검사와 파일 버전

-Wall/-Wextra/-Werror로 catalog+launch **2 TU**만 컴파일하고 후보를 링크했다.
v8 최신 repaired launch.o를 포함한 기존 object 집합 재링크 SHA 재현 후 **9 TU**를 재사용했다.
DSO90144bytes 및 anchor16016bytes도 해시 인증 후 재사용했다. readelf만 사용, ELF/DSO 로딩 없음.
최초 cap 매크로 전환의 signed 비교 경고를 음수 거부 후 uint64_t 비교로 수정하고 빌드 통과했다.
실패 로그와 모든 재검사 snapshot은 work에 보존했다. Python 보존 검사의 handoff 제외를 절대 경로에 맞게 고쳤다. Python 모의 fixture의 sealed module-name
충돌을 경로별 module import로 고쳤고, 최종 검사 이후 source 수정은 없다.

정적/Python 모의 **1638 PASS**. v8에서 이식한1082를 현재 source에서 재검증했고 새556을 추가했다.
v7/v8의 과거 결과를 추가 합산하지 않았다. 경계 cap/+1/minimum/-1, 5개 그룹과16 aliases 누락,
468개 각각 잘못된 해시, compiled policy 일치, FD/seal/SCM/alias/인계 실패, 저번호 FD·중첩·redirect 실패,
초기O부터catalog/placement/audit/terminal cleanup/V 연결, domain 혼입, PID재사용,
동시 mutation 및 audit sequence loss/중간 transaction/종료 단절·증거 누락을 검사했다.
Python OS/manager/transport mock을 native 동작 실증으로 표기하지 않는다.

- source manifest canonical SHA: `3160c6ff78f406c25358c4e243705c553f802727d37ad8518cb9624a6a754f24`
- candidate contract 파일 SHA256: `8842653e5f26d47f47d3575b4edc7403108fa5f61832b41c0600f0c7bf24ddb6`
- build_receipt 파일 SHA256: `62908284d72477023e232e05723ac511565b787d3a83146bfe5ce34d2629d28b`
- tests 파일 SHA256: `65d1dc568c80214da663675e4424649eba39cb992d51a41de57960c53889e408`

build는 native input/system-header/object/ELF SHA와 source snapshot을, tests는 같은 snapshot과 실제
build receipt/ELF SHA를 묶는다. Python/test 수정 후 C inputs/outputs 재확인 및 snapshot refresh만 수행했고
이를 native 재컴파일로 세지 않았다. 최종 artifact index는 문서/인계까지 묶으며 자기 자신은 제외한다.

허용된 비실행 재현(로컬 v8 objects가 필요):

```bash
python3 -B validation/gazebo-request-guard-v9/scripts/build.py
python3 -B validation/gazebo-request-guard-v9/tests/check.py
```

candidate_contract.py 재생성은 read-only source 검증이지만 현 시점 rlimit 관측을 담으므로 해시가 바뀔 수 있다.
재생성하면 receipts.py refresh와 tests 재검증이 필요하다. 어떤 native 바이너리도 이 명령에서 실행하지 않는다.

## 남은 최초 차단과 다음 조건

**기존 용량 cap에 의한 정적 admission 차단은 해소됨. 한도 변경만으로 배치 준비가 끝나지는 않는다.**
현재 실행 가능한 candidate main(inputs/entry.c)은 무조건78이며 candidate_owner_bootstrap과
BootstrapCoordinator를 실제 전용 owner unit 생명주기/CLI에 연결한 released driver가 없다.
새 candidate digest는 content binding이며 위험 수용·실행 승인·원래 봉인 계약 대체 서명이 아니다.
최초 실제 진입 실패는 서비스/marker 전에 exit78이다. 이 guard를 열지 않았다.

따라서 **최소 무해 종단 실행의 정확한 runnable 명령은 아직 제시할 수 없다**. 미존재 driver나
그대로78인 candidate를 종단 검증 명령으로 제시하지 않는다. 다음 비실행 최소 작업은 원래 launcher를
유지한 별도 harmless-only driver/CLI 및 immutable probe payload/anchor 계약을 만들고, owner/collector
5GiB sibling domain의 생성·실패정리·실제 native bootstrap 호출과 collector poll/wait/final verdict를
연결해 빌드·mock 및 SHA 봉인하는 것이다. 그 후 별도 실행 승인을 받아야 한다.

승인 후보의 최소 범위는 DART/Gazebo 미로딩·physics0·실제 marker 미소비로 한정하여 동일303/468
sealed preparation/RO 전달과 harmless loader/thread/descendant/종료 callback만 확인하는1회이다.
한도는 위 승인3값, 독립 target512MiB/AS2GiB/CPU10s/NOFILE256/FSIZE1MiB/Tasks64/runtime30s,
원래 host40s/collection25s/ACK5000ms 및 stream caps를 유지한다. 통과 기준은 sameFD hash/seals/identity,
468 canonical RO mount, 실행 가능 매핑의정책, initialO/C/K/P/A/GO/live mapping/EXIT_ACK,
누락 없는 독립 audit COMPLETE+EOF/exit/target cleanup/pins release/V, residual0,
실제 cgroup/rlimit 분리와 peak 기록이다. 오류/한도 초과/OOM/누락은 실패이며 자동 상향하지 않는다.

userns/pidfd/SCM credentials, init STOP/CONT, mount/chroot/LSM, loader/CET/pthread/clone3,
정책 상속/동시 실제 요청, 종료 중 audit 단절, callback 종료와 최종 cleanup, charge/peak는
실제 실행에서만 판정 가능하며 현재 전부 미검증이다. 현 단계 실행 명령이나 서비스 생성은 없다.

## 보존·게시

v8 게시파일(인계 제외)과 원래1767 evidence/main HEAD+dirty/dangling symlink 보존 검사를 통과했다.
marker 소비/기존 프로세스 종료·재시작 없음. 다른 기존 작업 관측은 UNKNOWN; 본 빌드/검사는 종료했다.
main 및 시스템 변경 없음. 로컬 work/ELF/objects/log는 ignored이며 다른 기기에 자동 전송되지 않고
/tmp는 영구 보관소가 아니다. 경량 source/계약/검사/기록만 publication_files.txt로 명시한다.
저장·검증 완료와 commit/push는 분리한다. 이 문서는 게시 직전 상태이며 실제 commit/remote 일치는
로컬 work/publication-result.json과 최종 사용자 응답으로 확인한다. 자동 게시는 DEVELOPMENT_RULES에 따른다.
