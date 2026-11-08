# Gazebo 계측 공동 빌드 v1 결과

2026-11-08 UTC. 시작 HEAD `e272b2a8a6de5b517e888ad1b03c6991992efb36`, experiment/dart-internal-trace, clean 직접 확인. context-handoff 및 요청한 AGENTS/DEVELOPMENT_RULES/handoff/build_gate/build_commands 읽음. 이번 허용은 고정 입력 검증, 새 source 사본 패치 적용, configure/compile/link 및 정적 검사까지다.

**BLOCKED_AFTER_PROBE_STAGE / 공동 빌드 미완료 / NOT_EXECUTION_READY / NOT_RUNTIME_VERIFIED. Stage B BLOCKED / 위험 수용 미결정.**

최초 실패는 `probe.receipt`(고정 명령 index6), exit1이다. 소스 준비와 probe configure/선택 검사/컴파일·링크/ELF 검사/local-prefix stage command는 통과했으나 배치 provenance 영수증을 만들지 못했다. 그 즉시 중단했고 DART/physics/Sim/harness 단계는 시작하지 않았다. 변경된 guard/인자나 새 입력으로 재시도하지 않았다. 이 보고는 이전 정적 READY_FOR_BUILD 판정 뒤 실제 빌드에서 확인된 차단을 기록한다; 이전 보고서/증거를 덮어쓰지 않았다.

## 입력과 소스 준비

[input_verification.json](input_verification.json): 독립 input26, 재사용 정책/fixture6, 로컬 inventory4, source archive3, 배포9+계측3 patch12, 패키지 archive18, toolchain40806, toolchain ELF71, selected dependency35038개 항목을 대조했다. 중복 제외47087개 실제 파일의 SHA/mode 검사가 PASS, 누락/불일치0. 고정된 src/build/prefix가 비어 있음을 먼저 확인했다. 새 다운로드/패키지 설치/시스템 변경은 없었다.

고정 build_commands.txt의 source 명령으로 새 `validation/gazebo-joint-closure-v1/work/config-01/src/{dart,physics,sim}` 사본에만 archive 추출/patch를 적용했다. DART 배포9개→계측01, physics02, Sim03 순서이며 실제 적용 후 source_plan 기대 digest가 모두 일치했다. 원 archive/이전 추출 source/이전 독립 입력은 보존했다. source helper는 실패 없이 종료했고 configure 이전에 별도 대상 실행이 필요하지 않았다.

명령/환경/순서는 준비 기록 그대로 사용했다. [steps.json](steps.json)에 고정 command 파일 SHA `7a106ce38bc5b3aef4c4bbf05a0c8790e89dc614da9ddf4788bef5556fa08ba2`, index, exit code, 로그 위치/SHA, 관측된 command PID/start identity와 시간을 기록했다. raw host 환경/인증 정보는 기록하지 않았다.

## 단계별 결과

|단계|결과|근거 로그(프로젝트 루트 기준)|
|---|---|---|
|source|PASS: 새3 source 및 적용 후 digest 일치|validation/gazebo-joint-build-v1/logs/source.log|
|probe.configure|PASS: GNU C/C++13.3.0, OpenSSL3.0.13 Crypto, configure/generate 완료|동일 logs/probe.configure.log|
|probe.selection|PASS_STATIC_SELECTION: external96 파일 확인, errors0|동일 logs/probe.selection.log; actual_selection.json|
|probe.build|PASS:2 translation units compiler launcher 검사, shared link, symlink 생성|동일 logs/probe.build.log|
|probe.elf|PASS_STATIC_OUTPUT_CLOSURE:7 ELF nodes, 미해결/미고정 의존성0|동일 logs/probe.elf.log; probe_link_closure.json|
|probe.stage.0|stage command exit0, 별도 prefix에만 배치|동일 logs/probe.stage.0.log|
|probe.receipt|**FAIL exit1: staged bytes differ**|동일 logs/probe.receipt.log; staging_difference.json|
|DART / gz-physics / Sim / harness|**NOT_STARTED**|실패 latch 이후 명령 실행 없음|

configure의 compiler ABI/ID용 실행 파일은 컴파일·문자열 검사 대상이며 실행하지 않았다. CMake trace에서 try_run 명령0이고, Ninja의 실제 대상 build 명령은 compile2/link1/cmake_symlink_library1이다. CTest/subject binary/loader/ldd를 실행하지 않았다. [command_execution_audit.json](command_execution_audit.json)은 이 command/trace 증거이며 syscall trace를 수집한 것처럼 주장하지 않는다.

## 최초 실패 원인

고정 stage_receipt.py는 prefix ELF의 SHA가 build ELF의 SHA와 완전히 같아야 영수증을 만든다. 그러나 CMake의 생성된 `build/probe/cmake_install.cmake:67`은 정상 배치 과정에 `file(RPATH_CHANGE)`를 수행했다.

- OLD_RUNPATH: `${config}/prefix/lib:${phase}/work/deps/usr/lib/x86_64-linux-gnu:`
- NEW_RUNPATH: `${config}/prefix/lib:${phase}/work/deps/usr/lib/x86_64-linux-gnu`

여기서 phase는 `/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-closure-v1`, config는 `${phase}/work/config-01`이다. 실제 전체 문자열은 artifacts.json/readelf 로그에 있다.

정적 전체 byte 비교 결과: 두 파일 크기361424로 같고 **오직 offset6339(0x18c3), .dynstr의 byte 하나만 58(`:`)→0(NUL)**로 바뀌었다. 나머지 모든 byte는 같다. 이는 install script가 기록한 RUNPATH 변경과 일치한다. Build ID/SONAME/DT_NEEDED도 동일하다. C++ 컴파일이나 링크 오류가 아니라, 이번 고정 배치 절차의 RUNPATH 변환과 provenance 검사의 byte-equality 가정이 맞지 않는 것으로 확인했다.

이 원인 확인은 실패를 PASS로 재분류하거나 검사 완화 승인으로 쓰지 않았다. `manifests/staged.json`은 생성되지 않았다. 실제 prefix ELF를 수동 승인/재등록하지 않았고, 다시 stage/build/receipt하지 않았다. 새 정적 설계가 실제 배치 변환까지 검증됐다는 이전 추정은 여기서 제한된다.

## 생성 ELF와 연결

공통 SONAME `libaero-joint-probe.so.1`; Build ID `f8d0e5ccb7cc9ef6dff3a2e3bef7a3c4ad81f4c7`.

|산출물|경로(phase/work/config-01 기준)|SHA-256|
|---|---|---|
|build ELF|build/probe/libaero-joint-probe.so.1.0|a18c2eef8fe7014dd51670ff5bf647bb786955827ec69cf2a000f5b1d443b34a|
|prefix ELF(영수증 거부됨)|prefix/lib/libaero-joint-probe.so.1.0|ccd88699b6b08d3f54a9b3c0886fb5b0086a74aefe915162c933c34279c87dc1|

[artifacts.json](artifacts.json)에 절대 경로/크기/hash/Build ID/SONAME/DT_NEEDED/RPATH/RUNPATH를, [artifact_links.json](artifact_links.json)에 .so/.so.1 alias와 실제 파일 경로를 기록했다. 두 ELF 모두 DT_RPATH는 없고 DT_RUNPATH가 있다. 같은 Build ID는 배치 전후 byte identity의 증거가 아님을 이 사례에서 직접 확인했다.

직접 NEEDED와 정적으로 확인한 파일은 다음과 같다. 각 파일의 SHA/Build ID 및 전이 연결은 probe_link_closure.json에 있다.

|NEEDED|계획한 설치 재사용 파일|
|---|---|
|libcrypto.so.3|/usr/lib/x86_64-linux-gnu/libcrypto.so.3|
|libstdc++.so.6|/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33|
|libgcc_s.so.1|/usr/lib/x86_64-linux-gnu/libgcc_s.so.1|
|libc.so.6|/usr/lib/x86_64-linux-gnu/libc.so.6|

직접·전이를 합치면 외부 ELF6개(추가 libm.so.6, ld-linux-x86-64.so.2 포함)와 자체 module1개로 구성된다. 계획 allowlist의 realpath/hash와 일치했다. `prefix_link_inspection.json`은 byte 비교와 동일 NEEDED에 따른 정적 연결만 기록하며 **배치 provenance 실패 상태를 유지**한다. 실제 dynamic loader 매핑 결과가 아니다. 이 단계에는 DART/Sim/gz-physics ELF 의존성이 없었고 후속 공동 stack의 전체 closure는 검증하지 못했다.

추가 정적 관찰: build RUNPATH는 끝에 빈 항목(`:`)이 있고 prefix RUNPATH에는 없다. 기존 output auditor가 빈 항목을 생략하므로 그 PASS를 실행 검색 정책 승인으로 해석할 수 없다. 이 항목도 후속 설계 검토 대상으로 남긴다. 실제 로딩은 하지 않았다.

## 실제 선택 경로와 검증 범위

[actual_selection.json](actual_selection.json)에 whitelist한 CMake cache/toolchain 필드, 자체/IMPORTED target의 include/link/location/options를 보존했다. Ninja `-t deps`(metadata 조회 전용)로 얻은 실제 두 객체의 header dependency330개를 재대조해 누락/allowlist 불일치0을 확인했다(header_dependencies.json; raw logs/probe.header_deps.txt). 원 compiler launcher도 두 compile에서 성공했다. 대상 실행/로딩 없이 확인한 compile/link 경로 증거다.

다른 configure helper ELF4개와 object2개는 other_generated_elfs.json에 별도 inventory로 기록했다. 실행/로딩 대상이나 검증된 harness로 분류하지 않았다. 임시 helper를 실행한 테스트 결과는 없다.

harness binary, DART/core/adapters/LCP, gz-physics core/plugin, Sim core/Physics plugin은 **NOT_BUILT**여서 경로별 SHA/Build ID가 없다. world runtime 파일도 생성하지 않았다. 기존 world template/source hash는 준비 기록의 input_files/reuse_files에 있지만 runtime artifact hash로 대신하지 않는다. 따라서 별도 실행 승인안은 발행하지 않는다.

## 보존·후속 조건·종료

preservation.json: 준비 input26개 및 확인한 원 source SHA, 이전 main HEAD/status 보존. 새3 source의 적용 후 기대 digest도 재대조했다. prefix/build/source/log와 설치 전·후 ELF 둘 다 남겼다. 기존 미커밋 변경/evidence/marker를 정리하거나 이동하지 않았다. 기존 전체 ignored tree 무결성을 검사한 것처럼 주장하지 않는다.

후속 최소 작업은 **별도 허용된 수정 단계**에서 (a) CMake RUNPATH 변환을 provenance 모델에 어떻게 포함할지, 또는 처음부터 배치 전후가 byte-identical이 되도록 고정할지 결정하고 (b) 빈 RUNPATH 항목을 검사 정책에서 처리하는 것이다. 새 입력/검사/명령은 원래 기록과 분리해 검증해야 한다. 현재 config-01에는 적용 완료 source와 산출물이 있으므로 fresh-layout/source helper를 그대로 재실행하면 보존 가드가 거부한다. 자동 삭제/덮어쓰기/가드 우회/재시작으로 해소하지 않는다.

이 차단이 해소된 뒤에도 DART→physics→Sim→harness configure/build/static-closure 및 최종 path-bound world/실행 contract가 필요하다. 실제 ABI·typed provider/전체 매핑·초기화1회·GO 실패/timeout·100×1ms native 동작·Clock/Capture/cleanup은 별도 명시적 실행 허용 전까지 미검증이다. 위험 수용을 기록하거나 Stage B를 해제하지 않는다.

현재 작업은 실패 원인/산출물/인계 기록 게시 후 끝낸다. 결과의 적용 범위는 이 계측 구성과 probe 단계에 한정한다. 로컬 큰 로그·원 archive/source/deps/build/binary는 Git으로 전달되지 않고 /tmp의 영속성도 보장되지 않는다. 프로세스는 해당 step의 종료 코드를 관측했으며 기존 작업을 종료/재시작하지 않았다. 전역/원격/다른 namespace의 실행 상태는 snapshot 범위 밖 UNKNOWN이다.
