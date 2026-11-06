# Consumer-Specific ABI Verification V1

## 1. 목적 및 판정

**CONSUMER_ABI_PARTIALLY_VERIFIED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.**

Gazebo Harmonic의 설치 DART 소비 ELF를 대상으로 정적 심볼 및 격리 Loader를 검증했다. 전체 DART ABI 동등성이나 물리 계측 중립성을 인증하지 않는다. Host 실행은 현재 보류한다.

## 2. 기존 결과 확인

V2 `reports/final_report.md`, `verdict.json`과 원래 main 작업 폴더의 parity-v1 final/missing_24 및 implementation final 보고서를 읽었다. 최초144, parity44, V2 153 PASS는 과거 보고 결과다. V2의 capability3=1, core5739 exports, 9개 layout 일치, 설치 DWARF/buildinfo 부재를 확인했다. V2 Native45와 프로젝트 회귀108은 이번에 다시 실행한 결과를 아래에 별도로 기록한다. 과거 DWARF 비교는 재실행하지 않았다.

## 3. 환경 및 Git

Ubuntu24.04.5, gz-harmonic1.0.0, libgz-sim8 8.15.0, gz-physics7 7.8.0, DART6.13.2+ds1-1~osrf2~noble, ROS Jazzy ros-base0.11.0, GCC13.3.0/GNU ld2.42를 확인했다. `environment.json` 참조. 초기 조회의 `gz-sim8`은 패키지명이 아니어서 NOT_FOUND였으며 실제 `libgz-sim8`을 추가 조회했다. 도구 설치는 없다.

실험 worktree `/tmp/AeroAIStudio-dart-internal-trace`, 초기 HEAD b3c3f0f3960786799b38350a8c572955f3e62433는 clean이며 원격 실험 HEAD와 같았다. main의 기존 변경은 보존했다. 기존 인계의 docs-only 범위는 이번 명시적 소비자 검증 요청으로 갱신하며 물리 실행 금지는 유지한다.

## 4. 실제 소비자

설치 `/usr/lib/x86_64-linux-gnu` 및 `/opt/ros/jazzy/lib`에서 경로에 gz-/gz_가 포함된 공유 ELF를 검색하고 NEEDED 및 Undefined DART 참조로 선별했다. 이 검색 범위 밖의 사용자 플러그인이나 런타임 dlopen 대상 전체를 발견했다고 주장하지 않는다.

|소비 경로|DART 관련 undefined|SHA-256 / Build ID|
|---|---:|---|
|`/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0`|252|아래 공통 값|
|`/usr/lib/x86_64-linux-gnu/libgz-physics7-dartsim-plugin.so.7.8.0`|252|아래 공통 값|

두 경로는 같은 바이너리 내용이다. SHA-256 `1ee9350aa09d5a5eb43a5075c9c61d2cdcb85113d2ff1e0f32136847edf1688e`, Build ID `c53e1a304ceb0f0dac85ff0e4872d0ffc50a28ac`. **504개 경로별 참조는 고유252개 인터페이스의 중복 관측**이다. `consumer_inventory.json`, `discovery.json` 참조.

## 5. 직접·전이 의존성

직접 DART 의존성은 core, collision-bullet, collision-ode다. external-odelcpsolver는 core를 통해 전이 로드된다. 그 외 sdformat14, gz-physics7/common5/math7, assimp, Bullet LinearMath, libstdc++/libgcc/libc 등이 있다. 전이 FCL/Octomap/ODE/Bullet/압축·mesh library를 포함한 실제 경로 전체는 소비자별 inventory의 direct_dependencies/transitive_dependencies와 `loader_results.json`에 있다.

B/C는 새 core/external/ODE를 선택하지만 **설치 collision-bullet을 유지**한다. 이는 명시적으로 분석한 혼합 구성으로, 완전한 격리 DART 스택이라고 하지 않는다. 이 보조 소비자의 DART 참조53개도 별도로 추출했고 설치 core가 제공하던 참조의 B/C 누락은0이다(`auxiliary_consumers.json`). binary type 호환성은 UNKNOWN이다.

## 6. 소비 심볼 비교

`consumer_symbols.json`은 mangled/demangled, type/binding/visibility/version, A/B/C 제공 경로·metadata, 실제 참조, 근거·판정을 담는다. 새로 빌드하지 않은 Bullet 제공 심볼은 B/C 자체 제공과 설치 보조 모듈을 통한 effective 제공을 분리했다. effective 제공 누락0, 비교한 type/binding/visibility/version 및 OBJECT size 차이0이다. 함수 code size는 호출 ABI 기준으로 사용하지 않는다.

심볼 존재와 relocation 해결은 검증했으나 함수 반환 ABI·inline 코드·객체 레이아웃의 완전한 호환성과 runtime 의미는 별개다. DART 참조는 unversioned이며 표준 라이브러리 version 요구는 실제 loader가 검사했다.

## 7. 소비자별 정적 ABI 범위

두 경로 모두 COMPATIBLE_WITH_LIMITATIONS. mangled 인자 시그니처, constructor/destructor 및 template 참조, ELF 가시성·버전·객체 metadata와 closure를 확인했다. 반환 타입은 일반 C++ mangling만으로 증명되지 않는다. 소비 플러그인의 inline offset과 모든 사용 클래스 layout은 미확정이다. 헤더 동일성·동일 B/C build profile은 설치 바이너리 타입 증거의 대체가 아니다.

## 8. VTable·RTTI·layout

새로 ELF에서 추출한 기존 DART VTable/RTTI/name 객체1299개의 metadata를 비교했다. 새 빌드에 존재하는 동일 객체의 크기·type/binding/visibility/version 불일치0. 보조 설치 모듈에만 있는 객체는 해당 원본을 유지하며 새 빌드 제공으로 간주하지 않는다. 가상 슬롯 순서·대상 함수 의미는 크기 일치만으로 입증되지 않는다.

기존 안전한 sizeof/alignof 실행 파일3개를 이번에 다시 실행해 9개 클래스 결과 일치를 확인했다: World984/8, Boxed720/8, Contact200/8, Joint304/16, Skeleton2592/16, BodyNode3760/16, Ipopt112/8, Nlopt144/8, OdeDetector24040/8. A-arm optional 헤더는 기존 같은 배포 source fallback이다. 소비자가 쓰는 모든 클래스의 layout을 커버하지 않는다. 설치본 type DWARF 부재는 유지한다. B→C DWARF 무변화는 **기존 V2 결과**다. `abi_comparison.json` 참조.

## 9. Loader 검증과 안전성

신뢰하는 시스템 `/usr/bin/ldd -r`의 glibc trace/relocation 모드를 사용했다. 프로그램 entry 및 init array로 제어를 넘기지 않으며 dlopen/플러그인 초기화/Gazebo를 실행하지 않는다. LD_*는 자식 환경에서 제거한 후 해당 검사에만 검색 경로를 지정했다. loader 자체와 relocation 검증은 실행했지만 plugin 생성자는 실행하지 않았다.

소비자2경로×A/B/C=6회 및 B/C optional IPOPT/NLOPT/ODE=6회에서 loader error/undefined0. core/external은 의도한 B/C를 선택했다. IPOPT/NLOPT는 실제 plugin closure에는 없으며 별도 모듈 relocation 범위다. RPATH/RUNPATH/NEEDED/SONAME은 provider inventory, 실제 검색 경로와 closure는 loader 결과에 기록했다. 중복 core/external SONAME의 동시 경로 선택은 관측하지 않았다. 별도 shared fmt/spdlog 의존성이 없는 core와 header-only fmt9/spdlog1.12 구성은 이전 profile을 인용한다. 전체 호스트의 모든 dlopen/플러그인 혼합은 미검증이다.

## 10. 계측 OFF/ON

`instrumentation_review.json`의 새 source delta와 기존 V2 정적 분석을 대조했다. OFF도 World ctor call_once/env, step scope TLS/예외 상태, 진단 진입 및 SetRow getDimension 인자 평가를 추가한다. 따라서 **OFF 실행 경로가 원본과 완전히 동일하다는 요구는 충족하지 않는다.** 제한된 synthetic fixture의 impulse·호출 순서 일치는 확인했다.

ON은 추가 getType 가상 metadata 조회, arena 복사/atomic/branch/cache 비용을 발생시킨다. Configure의 arena 할당과 window 뒤 JSON/stream 할당은 별도다. 기본 arena 약3.16MiB, 최대 약26.5MiB이며 직렬화 overhead는 제외한다. active 수집은 사전 할당 공간을 사용하고 overflow는 incomplete/fault 처리한다. owner-thread 검사는 일반적인 동시 Configure/GetStatus/Flush 안전성을 보장하는 전역 lock이 아니다. quiescent owner 경계가 필요하다. 예외 상태 검사는 물리 예외를 성공으로 바꾸지 않는다.

Constraint Assembly, Contact Jacobian/response A, LCP snapshot, Dantzig/PGS fallback, NaN repair, impulse 및 integration의 기존 토큰 보존은 기존 lexical 근거이며 이번 source delta에서 solver 알고리즘 변경은 없었다. 실제 effective mass/Jacobian·FP/시간·lock/thread·position integration·flush 중립성은 UNKNOWN이다. 메타데이터 호출이 모든 실제 constraint에서 무해한지는 미확정이다.

## 11. 신규 테스트

소비자 acceptance **12 PASS**, 실패/오류/skip0. inventory, effective symbol resolution, A/B/C relocation/core selection, retained auxiliary imports, layout, VTable/RTTI metadata, runtime 미검증 표현을 검사했다. 신규 테스트를 native 물리 계측 검증과 동일한 범위로 합치지 않는다.

## 12. 회귀 테스트

이번 실행 Native **45 PASS**, 프로젝트 offline regression **108 PASS**, 합계 신규 포함 **165 PASS**. `test_summary.json`과 로컬 `work/{consumer,native,regression}.xml/.log` 참조. Native fixture의 금지 호출 검색 및 기존 safety hash를 검토했으며 World ctor만 허용하고 step 호출은 없다. 프로젝트 회귀는 기존 explicit runtime fence로 launch/transport/비허용 subprocess를 차단했다. full DART suite/물리 실행 및 새 DWARF abidiff는 NOT_RUN이다.

초기 abi_review 파일 작성은 잘못된 main CWD에서 대상 경로 부재로 실패했으며 파일 변경 없이 종료했다. 실험 worktree에서 바로잡았다. 과학적 테스트 실패는 없었다. 원격 초기 조회의 sandbox DNS 실패는 승인된 네트워크 재조회로 해결했다. 기준 완화는 없다.

## 13. Production·Evidence 무결성

`integrity.json`은 이번 before/after manifest로 원래 main 소스/도구/테스트/validation, V2 보고서·소스, provider 라이브러리, dpkg 상태 및 기존 main AGENTS/handoff를 검사한다. manifest와 원시 로그는 로컬 work에 보존한다. 기존 코드·SDF·Physics·Clock·Capture·패키지·전역 loader 설정은 수정하지 않았다.

## 14. 완료 항목

소비 ELF 식별·해시, 252개 실제 import 제공, 보조 Bullet53참조, 새 ELF metadata, 제한된9 layout, 12 relocation 검사, 165개 offline 테스트와 무결성 검사를 완료했다. 재현 스크립트는 `scripts/analyze.py`, `abi_review.py`, `finish_analysis.py`, `check_integrity.py`다. 반드시 analyze→abi_review→tests→finish_analysis 순으로 실행하며 기존 산출물은 입력으로만 쓴다.

## 15. 미확정 항목

원 설치 binary 타입·배포 compiler/buildinfo, 전체 소비 클래스/inline 접근·반환 ABI·virtual slot, retained Bullet와 새 core의 객체 계약, 실제 dlopen 조합, instrumentation ON/OFF runtime 중립성은 미확정이다. 기존 optional packaged reference는 실제 설치본과 구분한다.

## 16. 호환성 문제

실제 required symbol 누락, relocation 오류, 확인된 metadata/layout 불일치 또는 solver 식 변경 증거는 없다. 다만 완전한 격리 closure는 아니며 OFF의 추가 실행과 ON metadata 조회를 확인했다. 이것을 계산 결과 불일치의 증거로 확대하지도, 무영향으로 축소하지도 않는다.

## 17. 위험 등급

두 소비 경로 모두 COMPATIBLE_WITH_LIMITATIONS / **HIGH**. 심볼/Loader는 VERIFIED_OFFLINE, 설치 type ABI·runtime은 UNKNOWN이다. 보조 Bullet도 binary type ABI UNKNOWN/HIGH다. 미확인 위험을 LOW로 두지 않는다. `risk_assessment.json` 참조.

## 18. Host 실행 검토

현 시점 Host 실행 보류. UNKNOWN인 inline/layout/virtual/metadata 항목이 Host에 영향을 줄 수 있다. 별도의 안전성 검토를 진행할 근거는 확보했지만 실행 허가나 실행 가능 판정은 아니다. 이번에는 어떤 Host 명령도 수행하지 않았다.

## 19. Host 전 최소 안전조건

원 배포 type debug/Build ID 자료를 확보하거나 정확한 소비 타입·inline/virtual 계약의 대체 증거 및 잔여 위험 수용 범위를 명시한다. retained Bullet 구성을 별도로 검증하거나 matching isolated Bullet을 준비한 후 같은 closure를 다시 검증한다. 계측 metadata 부작용·owner/quiescent 경계·용량 및 mapping/flush 검증 계획을 수립하고 별도 사용자 실행 승인을 받아야 한다. 기존 Capture/Clock 기준은 유지한다.

## 20. 다음 최소 작업

소비자가 실제 inline/virtual로 접근하는 타입과 retained Bullet→core 객체 계약을 좁혀 정적 증거를 보완한다. 전체 DART ABI 증명을 목표로 무제한 확장하지 않는다. Runtime 검증은 별도 승인 전까지 금지다.

## 21. Git 체크포인트

검증한 신규 scripts/tests/경량 JSON/이 보고서와 handoff만 실험 브랜치에 명시적으로 선택한다. 기존 원본·바이너리·work/raw manifest/log는 게시하지 않는다. commit/push 및 원격 일치 결과는 로컬 `reports/git_publication.json` 영수증에 기록한다. 보고서 자신의 commit hash를 넣기 위한 재귀 commit은 만들지 않는다. main push/merge·force push는 없다.
