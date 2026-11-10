# Request guard v7 — 자원 결정안과 비실행 준비

기준 HEAD `a19fb1c076e57f91ce5df491ce257c54e3e20d01`, `experiment/dart-internal-trace`. 최신 HEAD는 동일했다. context-handoff·AGENTS·DEVELOPMENT_RULES·handoff·v6 final/integration contract·원래 봉인 실행 계약을 읽었다. 기존 16경로/5객체 대조와 555개 결과를 artifact hash로 인증해 재사용했으며 재실행·합산하지 않았다.

**Stage B BLOCKED / 위험 수용 미결정 / 실제 런타임 미검증. PARTIAL / NOT DEPLOYABLE / 비실행 전체 준비 미완료.** 원래 launcher 및 candidate main의 서비스·marker 전 exit78을 보존했다. 자원 한도·원래 계약·시스템 설정 변경과 native ELF 실행은 전혀 하지 않았다.

## 사용자 결정안 — 적용하지 않은 최소 설정 집합

현재 한도 안에서 실제 로더 입력의 bytes 불변성·최종 hash/identity·RO 전달·실행 가능 매핑을 모두 충족하는 대체 저장 방식의 근거는 없다. 권장 결정은 **원래 target 한도는 그대로 두고, 별도의 bounded owner/collector domain을 승인할지**이다. 별도 domain을 무제한 우회로로 사용하지 않는다.

|정확한 설정과 적용 대상|현재값|제안값(bytes)|산정 근거|
|---|---|---:|---|
|catalog per-object byte ceiling (all prepare/verify checks) — preparer/native catalog|67108864|543979760|largest mandatory logical file; same value must guard prepare and final verify|
|catalog_prepare admission ceiling — preparer/native catalog|536870912|2159132672|303 distinct output objects page-rounded once + one nested copy/hash buffer pair; excludes overhead by design|
|owner MemoryMax / memory.max — NEW dedicated preparer+native owner+Python collector cgroup outside target cleanup domain|UNDEFINED_NO_OWNER_UNIT; target536870912 unchanged; see read-only cgroup observations|5368709120|worst modeled output+source page caches 2159001600 output + validated-input cache 2171359232 + buffers 131072 + explicit reserve 268435456 = 4598927360; remaining 769781760; reserve NOT measured peak guarantee|

첫 항목은 native catalog의 준비·최종 검증에 흩어진 67108864 비교를 함께 묶는 **하나의 객체 크기 정책**이다. 두 번째는 `catalog_prepare`의 budget 상한 536870912 비교이다. 이번에 상수나 호출 budget을 변경하지 않았다. 세 번째는 현재 존재하지 않는 전용 owner unit/domain의 새 MemoryMax이다. **현재 target MemoryMax512MiB를 5GiB로 올리는 제안이 아니다.**

owner의 관측된 inherited FSIZE/AS는 unlimited(-1), NOFILE은 soft/hard1048576이다. 따라서 이 호스트의 권장 배치에서는 이 셋의 **증가 설정이 필요하지 않다**. target의 FSIZE1048576, NOFILE256, AS2147483648은 자식에서 그대로 적용한다. 전체303 객체 보유 시 owner NOFILE 알려진 floor316+ambient 여유, 생성자 FSIZE floor543979760은 재검사 조건이다. 다른 호스트/제한된 owner에서 이를 못 만족하면 owner만의 추가 결정이 필요하며 target을 대신 올리지 않는다.

이 3개 설정을 승인해도 실행 승인이 되거나 전체 구현이 완료되는 것은 아니다. 5GiB는 아래 알려진 모델+명시적 reserve에 근거한 **정확한 제안값**이며 실측된 안전 peak나 성공 보장이 아니다. 초과/OOM/admission 실패는 거부로 남겨야 한다. 실행 없는 상태에서 모르는 비용을 임의로 정확한 최소값으로 단정하지 않았다.

## 객체별·동시 보유·준비 비용 (bytes)

`resource_decision.json`에 303개 객체 전체 원본 dev/inode/hash·size·alias·페이지 반올림을 기록했다. 5개의 같은 FD에서 hash/identity를 다시 읽기 전용 검증하고 fs-verity 전후를 확인했다. 파일 size와 st_blocks는 metadata 관측값이며 메모리 실측값이 아니다.

|5개 원본 객체(서로 다른 dev/inode)|파일 bytes|dense 출력 pages bytes|단독 출력+공용128KiB 최소분|
|---|---:|---:|---:|
|`gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0`|99090256|99090432|99221504|
|`gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|543979760|543981568|544112640|
|`gazebo-joint-execution-contract-v1/work/prefix/lib/libgz-sim8.so.8.15.0`|74462608|74465280|74596352|
|`gazebo-joint-header-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|543979760|543981568|544112640|
|`gazebo-joint-physics-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|543979760|543981568|544112640|

|집계|bytes|성격|
|---|---:|---|
|5개 파일 byte 합|1805492144|metadata 확인값|
|5개 동시 보유 dense 출력 페이지|1805500416|계산값; alias마다 중복하지 않음|
|5개 순차 준비, 한 번의 복사/해시 buffer 포함|1805631488|계산된 알려진 구성분; peak 아님|
|기존 필수298 객체 출력 페이지|353501184|계산값|
|전체 필수303 객체 출력 페이지|2159001600|계산값|
|전체303 출력 + nested copy/hash buffers|2159132672|v6 최소 요구량 재사용·재확인|
|validator가 읽는 전체429객체+code/evidence/tools source 페이지|2171359232|inode 중복 제거한 cold cache 모델|
|준비 중 output+전체 source cache+128KiB|4330491904|cold cache 계산 모델, 상한 보장 아님|
|위 모델+268435456 명시적 reserve|4598927360|제안 산정값; reserve는 측정 결과 아님|
|제안 owner MemoryMax|5368709120|미적용 결정안; 위 모델 이후 추가 여유 769781760|

**실제 준비 중 최대 사용량: UNKNOWN / 미실행.** 이전 2159132672는 순수 출력+buffer만의 최소 구성분으로 정확하다. 그것을 전체 peak로 읽으면 안 된다. 이번에 validator가 비필수126 객체와 code/evidence/host tools까지 해시하며 읽는 cache를 추가했다. source cache가 이미 다른 cgroup에 charge되어 있다면 owner에 전부 새로 붙지 않을 수도 있지만, 이를 무료라고 가정하지 않는다.

중복 방지: copy64KiB와 그 안에서 final verify가 사용하는 digest64KiB를 **한 번만** 더했다. 5개 단독 최소분을 합산해 buffer5회를 넣지 않는다. 세 DART는 같은 SHA256이어도 원본 inode3개이므로 출력3개다. alias FD·RO reopen·mount·shared mapping 자체가 파일 전체 사본을 하나 더 만들지는 않는다. 기존298은 full303 안에 이미 포함된다. page cache와 memfd 출력은 서로 다른 페이지 집합으로 분리했다.

누락 가능한 비용: native EVP/allocator/stack·shared library resident pages, Python collector heap·imported code·queued protocol/native audit·증거 persistence cache, FD/inode/VMA/slab·page tables·seccomp/ptrace/pidfd·socket buffers, filesystem readahead/metadata/journal와 추가 임시 비용. 이들을 전부 정밀 산정하거나 실측하지 않았으며 reserve가 충분하다고 인증하지 않는다. native 준비 함수의 sequential user buffer 외에 native/collector 초기화 비용은 reserve/UNKNOWN이다. 빌드 compiler 메모리는 이후 서비스/준비 런타임과 별도 작업으로 구분한다.

## 실행 중 예상량과 귀속

|비용/한도|귀속|bytes / 상태|
|---|---|---|
|보유된303 memfd 출력|준비 시 생성한 owner charge domain; target에 RO FD 전달해도 사라지지 않음|2159001600 계산된 backing 페이지|
|위 출력 + 요청별 hash buffer64KiB|native owner|2159067136 알려진 동작 중 구성분|
|전체 검증 source cache 잔류 + 위 구성분|원 charge domain; conservative 모델에서는 owner|4330426368 계산 모델|
|위 모델+reserve+target가 cap까지 private charge를 사용하는 경우|owner+target 합산 시나리오|5135732736 계산 모델; 실제 RSS 아님|
|owner 제안 cap + 기존 target cap|두 domain budget 합계|5905580032; 사용량 예측/실측 아님|
|target private anonymous/COW/thread stack/allocator/library workload|target cgroup|UNKNOWN; MemoryMax536870912, SwapMax0 유지|
|target virtual address space|target process RLIMIT_AS|2147483648 유지; file bytes 전체를 AS로 더하지 않음|
|collector Python·출력/감사 parsing·journal page cache|권장 owner/collector domain|UNKNOWN; owner reserve에 포함할 설계, 측정 필요|

**실행 중 실제 최대량: UNKNOWN / 미실행.** PT_LOAD file/mem 합은 v6 resources의 기존 값이며 RSS와 같지 않다. shared memfd를 target가 매핑할 때 동일 backing bytes를 alias/프로세스 수만큼 다시 더하지 않는다. private COW와 anonymous/thread stack 등은 추가다. cgroup charge의 실제 위치와 공유/회수 동작은 커널 실행 검증 항목이다. target MemoryMax512MiB를 충족한다고 인증하지 않았다.

## 대체 저장 방식 판정

- 원본 disk file: 같은 FD hash/identity는 맞지만 5개 모두 fs-verity가 확인되지 않았다. 외부 writable alias를 배제할 kernel 불변성 근거가 없어 거부. v2의 기존 불변성 거부 결과와 일치하며 이번에도 설정을 켜지 않았다.
- Sparse memfd: zero hole을 보존해도 logical file size·객체 cap·FSIZE와 최종 hash/exec seal 조건은 그대로다. 현재 한도의 해결 근거가 아니다. 새 sparse 준비 실행 안 함.
- 압축 저장/strip: loader에 원 bytes를 재구성하면 출력 비용이 돌아오고, debug stripping은 승인 hash를 바꾼다. 계약 그대로의 대안으로 채택하지 않았다.
- disk copy+chmod/RO bind: 외부 writer/다른 writable description을 차단한 불변성 근거가 없다. fs-verity 설정·새 저장소·권한 변경을 이번 범위에서 만들지 않았다.
- 봉인 객체 재사용: 역사적 receipt는 object_retained=false이고 이5개는 원래 seal 성공도 없었다. 과거 FD 번호나 파일명으로 live authority를 대체하지 않았다.
- 이미 검토한 streaming은 반복 구현하지 않았다. native 크기 정책이나 admission 한도도 수정하지 않았다.

## 독립적인 비실행 준비와 검증

새 `layout.py`는 전체303 pin에 대한 최종 같은-FD verifier를 필수로 요구하고 468 alias FD-mount fragments, native expected hash/dev/inode, ELF mapping identity 투영을 하나의 candidate로 만든다. 원본 계약 root/SONAME/alias 범위를 바꾸지 않는다. 누락·추가·원본 identity/hash 불일치·seal/exec 불일치·FD 재사용·동일 SHA256 DART의 cross-origin 병합을 거부한다. 전 경로 투영은 **synthetic pin으로만 검사**했고 live303 사본 또는 실제 mount가 있다는 뜻이 아니다. 원 native original-inode 기준을 제거하지 않았다.

owner/collector가 target cleanup domain 안에 들어가거나 하위 cgroup에 있는 배치를 거부하는 `placement` validator를 추가했다. target limits readback과 preparer charge-domain identity를 요구한다. `preparation.json`에 owner-domain attest → 준비 → mount 재검증 → held child의 target-only placement → listener/exec/collector ACK → 기존 GO/live mapping/EXIT_ACK/EOF/target cleanup → V → owner 해제 순서를 기록했다. 실제 manager adapter나 unit을 만들지 않았다.

controller는 기존 v6 독립 감사 reader·NativeSession/ACK를 재사용한다. 새 wrapper는 mixed window/중복 stream FD를 거부하고 EAGAIN/EINTR를 readiness 재시도로 처리한다. 실제 read/selector 오류는 최종 실패로 latch한다. source EOF·protocol EOF 뒤 소유 audit FD/pidfd 해제 실패가 V **이전**에 거부되도록 하고 모든 run 종료 경로에서 해제를 시도한다. 기존 GO/100samples/종료 직전 live mapping/EXIT_ACK/EOF/실제 exit·cleanup/integrity 기준을 완화하지 않았다.

- 신규 **654 정적/Python 모의 검사 PASS** (`reports/tests.json`). 주로 468 path와 native role 투영 개별 검사이며 실제 syscall654개 성공이라는 뜻이 아니다. original sealed SourceLoader/NativeSession/ACK factories, full protocol과 controller의 성공/오류/해제 경로를 모의 검사했다. 기존555는 artifact hash로 재사용했다.
- native C/ABI를 바꾸지 않아 native rebuild/relink는 불필요했다. 기존 v6 ELF hash를 확인했고 새 Python source는 compile로 문법 검증했다. ELF 로딩·실행은0이다.
- 첫 resource report 생성은 artifact key를 absolute로 조회해 실패했고 상대 경로로 고쳤다. 새 테스트의 AST helper namespace에서 modules가 빠져 한 번 실패한 뒤 수정·전체 재검증했다. 원본 설명은 work/resource-first-failure.txt, work/test-first-failure.txt에 보존했다.
- 기존 tracked 파일(handoff 의도 변경 제외), v5의1767 evidence baseline, main HEAD/dirty status, dangling symlink dev/inode/link text 보존 검사를 통과했다. 기존 source/계약/증거/산출물/marker 변경 없음. ignored work/ 및 원본 evidence는 Git 전송 대상이 아니다.

재현 가능한 허용 작업(설정·서비스·native 실행 없음):

```bash
python3 validation/gazebo-request-guard-v7/scripts/resources.py
python3 validation/gazebo-request-guard-v7/tests/check.py
```

## 사용자 결정 / 남은 구현 / 런타임에서만 확인할 항목

**사용자 결정:** 위 3개 설정과 bounded owner/collector placement의 승인 여부. 이번에는 미적용이다. 한도 값과 owner domain 승인만으로 위험 수용 또는 실행 승인을 추론하지 않는다.

**남은 비실행 구현:** 실제 native identity consumer/bootstrap와 compiled plugin/native 기대값 연결; full copy FD mount 설치와 native468 policy; user manager를 통한 owner/target placement adapter/readback; race-safe multi-task FD 기반 file mmap/executable mprotect/metadata/negative lookup 정책. 순수 투영 validator가 이 실행 구현을 대체하지 않는다. 이들은 storage/owner/identity ABI 결정에 연결된 미완료 구현이며 단순 런타임 확인으로 넘기지 않는다. 현재 원래 full gate는452!=468로 fork 전78이다.

**실제 실행에서만 확인 가능:** kernel seal/exec mapping·SCM credential/pidfd/notification/ptrace·실제 mount identity, 정상 pthread/clone3/CET·정책 상속, concurrent task/exit callback/ECHILD/감사 단절, owner/target/collector peak와 charge 위치·OOM, 실제 target unit 정리와 V 순서. 별도 승인이 있어야 확인할 수 있다.

독립적인 계산·계약 투영 검증·controller fault 정리는 진행했으나 **비실행 전체 준비는 아직 끝나지 않았다.** 따라서 조건부 요청대로 이번에는 승인에 올릴 최소 무해 실행의 명령·범위·통과 기준을 제안하지 않는다. 실제 Gazebo/DART 로딩, harness·무해 시험, 서비스 시작, marker 소비, resource limit 변경, sudo/install/system 설정 변경은 하지 않았다.
