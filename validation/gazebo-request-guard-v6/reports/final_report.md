# Gazebo request guard v6 — 경로 대조와 controller 연결

기준 HEAD `0b9c8457ee1cf3e533d5a430e1fa2cddc2e53baf`, `experiment/dart-internal-trace`. 더 진행된 HEAD는 없었다. 기존 v5 구현·빌드 영수증·봉인 실행 계약을 재사용했다. 새 결과는 v6에만 기록했다.

**PARTIAL / NOT DEPLOYABLE / 비실행 전체 준비 미완료. Stage B BLOCKED / 위험 수용 미결정 / 실제 런타임 미검증.** 실제 launcher와 candidate main의 서비스·marker 생성 전 `exit 78`을 유지한다. 이 단계는 구현·컴파일·링크·정적 및 Python 모의 검사뿐이다.

## 452와 468의 출처와 근본 원인

`reconciliation.json`에 양쪽 전체 경로 목록, 468개 경로의 계약 identity·SHA256·요구 witness chain·원본 FD mount argv 위치를 기록했다. 읽기 전용 sealed validator는 원본 manifest와 code/evidence/tools/mount 파일을 검사했다. 계약 seal은 `789737d947f8c0ebd1466300792667fc9c838adba5834168e5c82bc6e4846aae`이며 v3 copy receipt 파일의 pinned SHA256도 v4 reader로 확인했다.

- 468경로/303객체: v4 classify의 역할·required canonical mappings·payload roots에서 SONAME graph를 탐색하고 native expected 및 joint ELF allowlist를 더한 정적 필수 집합.
- 452경로/298객체: 그 집합 중 v3 역사적 `SEALED_BYTES_VERIFIED` 객체만 생성한 v5 compile-time allowlist. 역사적 prepared는 현재 live FD가 있다는 뜻이 아니다.
- 객체는 원본 `(device,inode)`로 묶는다. witness가 하나라도 있으면 봉인 계약 안의 그 객체의 모든 alias를 집계한다. 경로 수와 객체 수를 혼합하지 않는다. 동일 SHA256의 서로 다른 원본 inode를 합치지 않는다.
- 양방향 차이: required−compiled **16경로**, compiled−required **0경로**. 중복 경로·객체와 계약 버전 불일치 없음. 원인은 5개 필수 객체가 그대로인 64MiB 준비 한도를 초과한 것이다. 수치를 맞추려고 필수 경로를 삭제하거나 이전 계약을 재봉인하지 않았다.

다음 차이 경로는 모두 기존 승인 입력 계약에 포함된다. 필요성은 객체별 명시 역할/필수 mapping 또는 해당 객체의 승인 alias이다. 원본 `--ro-bind-fd`는 원 계약의 근거일 뿐 새 sealed copy mount 완료 증거가 아니다. 전 경로를 계속 거부한다. witness chain·전체 source 경로·dev/inode·SHA256·mount argv 위치는 JSON의 각 동일 경로 행이 원본이다.

|차이 경로|원본 dev:inode|SHA256|원본 mount FD|필수 근거|
|---|---|---|---:|---|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7`|66309:4481392|`c652c1af1ccf37d0dcc0b185849045a41f074262ad8a6a7c6f38e75ddecc370c`|17|required_canonical_mapping; role:dartsim|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0`|66309:4481392|`c652c1af1ccf37d0dcc0b185849045a41f074262ad8a6a7c6f38e75ddecc370c`|17|required_canonical_mapping; role:dartsim|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/libdart.so.6.13`|66309:4481427|`42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4`|19|required_canonical_mapping; role:dart; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|66309:4481427|`42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4`|19|required_canonical_mapping; role:dart; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/libgz-sim8.so.8`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/libgz-sim8.so.8.15.0`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-execution-contract-v1/work/prefix/lib/libgz-sim8.so`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-execution-contract-v1/work/prefix/lib/libgz-sim8.so.8`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-execution-contract-v1/work/prefix/lib/libgz-sim8.so.8.15.0`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-header-fix-v1/work/config-01/prefix/lib/libdart.so.6.13`|66309:4364178|`42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4`|28|required_canonical_mapping; role:dart_ode|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-header-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|66309:4364178|`42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4`|28|required_canonical_mapping; role:dart_ode|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-native-resource-v1/work/prefix/lib/libgz-sim8.so`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-native-resource-v1/work/prefix/lib/libgz-sim8.so.8`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-native-resource-v1/work/prefix/lib/libgz-sim8.so.8.15.0`|66309:4616985|`aff30b58cff49ed97e1aae4a792fd7cac525df915b4d1e1b49bf3e2e96bf1099`|24|required_canonical_mapping; role:physics|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-physics-fix-v1/work/config-01/prefix/lib/libdart.so.6.13`|66309:4371174|`42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4`|35|required_canonical_mapping; role:dartsim|
|`/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-physics-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|66309:4371174|`42ff81108e013b45ed1b11a1433cea0ea18964d2280d09c61d05d0fbe49b4af4`|35|required_canonical_mapping; role:dartsim|

새 전달 조건은 최종 봉인된 RO FD의 hash/size/dev/inode/exec mode, 동일 객체 alias mount, canonical openat2의 동일 사본 확인, INPUT_OBJECT 정책 index와 ADDFD_SEND이다. 현재 5개는 사본과 mount와 전달 모두 0이다. old native/plugin/collector는 원본 inode를 요구하므로 사본 identity projection을 별도 계약으로 완성해야 한다. 해시만 같거나 옛 FD 번호만 있다는 이유로 통과시키지 않는다.

## 대형 객체 5개의 처리 판정

파일 크기 및 ELF PT_LOAD는 이번에 읽기 전용으로 확인했다. 아래 알려진 준비 최소분은 페이지 반올림된 dense memfd 전체 + 복사/해시 buffer 131072 bytes이다. **실측 최대치가 아니며** interpreter/allocator/page cache/kernel/cgroup overhead는 추가다. 따라서 안전한 peak 상한은 UNKNOWN이다.

|객체 source (validation 아래)|bytes / 객체 cap 최소|준비 최소분 bytes|PT_LOAD file / mem bytes|판정|
|---|---:|---:|---:|---|
|`gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0`|99090256|99221504|3135297 / 3136673|DENY / 한도 변경 보류|
|`gazebo-joint-codegen-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|543979760|544112640|9097303 / 9113599|DENY / 한도 변경 보류|
|`gazebo-joint-execution-contract-v1/work/prefix/lib/libgz-sim8.so.8.15.0`|74462608|74596352|3196082 / 3202674|DENY / 한도 변경 보류|
|`gazebo-joint-header-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|543979760|544112640|9097303 / 9113599|DENY / 한도 변경 보류|
|`gazebo-joint-physics-fix-v1/work/config-01/prefix/lib/libdart.so.6.13.2`|543979760|544112640|9097303 / 9113599|DENY / 한도 변경 보류|

- 64KiB streaming은 이미 v5에 있다. buffer만 줄이며 dense 보유 출력과 객체당 64MiB cap을 없애지 못한다. 새 streaming 우회나 debug byte 제거로 계약 hash를 바꾸지 않았다.
- 이 5개는 v3에서 봉인에 성공하지 않았고 retained FD도 없다. 나머지 역사적 receipt도 `object_retained=false`여서 재사용 근거가 아니다. 검증되지 않은 persistent pathname이나 타 프로세스 FD 검색으로 대체하지 않았다.
- 준비자 FSIZE 최소는 각 파일 bytes이다(위 표). 가장 큰 객체 cap/FSIZE 최소 543979760 bytes. 기존 target FSIZE=1048576을 변경하지 않았다. 준비자와 target FSIZE는 서로 다른 요구다.
- full 303객체 보유 출력 페이지 2159001600 bytes + buffers = 2159132672 bytes, 추가 overhead 필요. 준비된 298객체만의 출력은 353501184 bytes이다. 한 DART 사본의 알려진 준비 최소분 544112640조차 536870912 MemoryMax를 넘는다. 이 계산을 새 MemoryMax 승인값으로 삼지 않는다.
- 서비스 중 사용량은 UNKNOWN이다. 위 PT_LOAD file/mem은 ELF segment 합계이며 RSS/cgroup 최대나 실제 매핑 합계가 아니다. debug file 전체 크기를 target AS 요구량으로 취급하지 않는다. target AS=2147483648, MemoryMax=536870912, SwapMax=0을 유지한다. owner가 준비 페이지를 계속 보유하면 그 charge가 사라지는 것도 아니다.
- 보유자 NOFILE 알려진 최소: 298객체 준비자308/supervisor311, 전체303객체313/316 + ambient/sparse/library 여유. target256과 구분한다. 생성자 domain·charge·service cleanup 소유권은 미승인/미구현 배치 계약에 남긴다.

## controller와 감사 최종 판정 연결

새 `scripts/controller.py`는 private handoff 수신부터 3개 stream을 순회하는 callable poll loop이다. v5 receive_audit/LiveReader/NativeJournal/JournalAdapter/AuditGate를 재사용하고 원래 봉인 SourceLoader의 NativeSession/ACK/Lines로 검증했다. 새 entry로 자동 실행하지 않았다. `integration_contract.json`은 실행 승인 계약이 아닌 BLOCKED 연결 명세다.

- listener SCM_RIGHTS+credential/ACK, 단발 exec TRACE, exec-stop/FD0..4 증거와 task 추적은 기존 native 경로를 유지한다. 5 preexec record가 모이기 전 A/GO가 나가지 않는다. prefix 전 protocol bytes는 기존 총량 안에서 보류한다.
- Native owner candidate_run과 collector Controller.run이 각자의 독립 loop를 제공한다. native loop는 task stop 처리 뒤에도 notification을 poll하며 감사 channel 및 collector channel 단절/예상 밖 조기 V를 실패로 처리한다.
- collector는 bounded nonblocking read를 stream별 순회하며 audit를 protocol stdout/stderr와 분리한다. 거부·누락·재전송·overflow·persist 실패는 영구 실패로 남긴다. 실패 뒤에도 deadline까지 물리 stream drain을 계속하고 GO/ACK/V를 새로 보내지 않는다.
- root 종료나 EXIT_ACK로 감시를 끝내지 않는다. 자손 요청·exit callback·all-task death/ECHILD·COMPLETE·audit EOF까지 추적한다. audit ALL_DEAD보다 늦게 도착한 buffered protocol bytes는 live task 증거로 사용하지 않고 기존 NativeSession 순서/identity 판정으로 검사한다. 원래 AuditGate의 live packet API는 변경하지 않았다.
- 두 ready와 world 관측, native closure 후 기존 GO; final_wait 100sample 시 기존 live mapping/PID/start 재검사 후 EXIT_ACK; 이후 audit EOF·stdout/stderr EOF·실제 target rc0·cleanup/integrity/final mapping이 모두 있어야 기존 finalize와 V가 가능하다. 하나라도 없으면 실패다.
- owner가 V를 기다리는 동안 target cleanup을 관찰해야 하므로 같은 cleanup cgroup에 넣으면 순환 대기다. 이를 해결하는 배치·자원 소유 계약은 아직 없다. 새 loop가 있다는 이유로 전체 controller 배치 완료로 판정하지 않는다.

정상 pthread/clone3 ABI·CET·실제 filter 상속·loader와 executable mapping·정상 metadata/negative lookup·스레드 경합·kernel notification/SCM/mount 경계·실제 종료 callback과 resource peak는 런타임 미검증이다. 현재 file mmap/executable mprotect/path metadata는 계속 거부하며 정상 DART 초기화 지원을 주장하지 않는다.

## 빌드·검증·보존

- 새 native launch 1개 TU만 v6/work에서 Werror/PIE/stack protector로 컴파일하고, 기존 catalog/broker/control/entry 4개 object의 SHA256 및 모든 dependency를 parent receipt와 대조한 뒤 RELRO/NOW로 링크했다. ELF 정적 검사만 했고 로딩/실행하지 않았다. build_receipt.json에 compiler PID/start 및 hash가 있다.
- 신규 555 정적/Python 모의 검사 PASS (`tests.json`). 경로 양방향 대조, 필수 누락, alias/FD/hash/source/mode/seal 불일치, handoff credential/count/truncation, prefix 단절, 동시 자손 요청, root 선종료, ACK 뒤 거부/감사 단절/종료 증거 누락, 원 protocol 전체와 injected poll loop를 포함한다. 과거 573개를 재실행하거나 합산하지 않았다.
- 추가 wrong_exec 테스트 fixture가 XOR 후 여전히 executable mode를 남겨 한 번 실패했다. fixture를 clear/set 방식으로 수정하고 전체 재검증했다. 원 verifier 변경 없음. 원본 설명은 work/test-fixture-failure.txt이다.
- 이전 1767파일 evidence baseline 및 이번 시작 tracked 파일을 대조했다(handoff 의도 변경 제외). main HEAD/dirty status와 dangling symlink 보존을 확인했다. 기존 source·산출물·marker·봉인 계약·v5 보고서 수정 없음. ELF/log/baseline/pycache는 ignored local 산출물이며 Git으로 전달되지 않는다.

재현(실행 허용 범위인 읽기/빌드/정적·모의만):

```bash
python3 validation/gazebo-request-guard-v6/scripts/reconcile.py
python3 validation/gazebo-request-guard-v6/scripts/build.py
python3 validation/gazebo-request-guard-v6/tests/check.py
```

## 남은 최초 차단과 승인 경계

최초 native full-run 차단은 여전히 **452 != 468, fork 전78**이다. 5객체와 전체 보유자 자원 계약 → full sealed copy mount/native·collector identity projection → owner/target cleanup domain 배치 → 정상 loader metadata/mapping 정책의 순서로 미완료를 닫아야 한다. 독립적으로 가능한 경로 대조·controller API·빌드·모의 연결은 이번에 진행했다.

**비실행 전체 준비가 완료되지 않았으므로 런타임 승인에 올릴 명령·실행 범위를 제시하지 않는다.** 실제 DART/Gazebo loading, harness/무해 시험, 서비스, 물리 step, marker 생성·소비, sudo/install/system 설정 변경은 하지 않았다. 차단을 우회하거나 runtime 승인 대기 단계로 승격하지 않았다. Stage B BLOCKED / 위험 수용 미결정 / 실제 런타임 미검증 유지.
