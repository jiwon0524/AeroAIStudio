# 첫 스텝 전 계측 빌드 사전 판정

**BLOCKED_BEFORE_CONFIGURE / NOT_EXECUTION_READY / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.

2026-11-08 UTC. 시작 HEAD는 사용자 기준과 동일한 `60da9366a5711f1be64e20f27d844b21a6c2a24d`, branch `experiment/dart-internal-trace`, status clean. 루트/main 및 실험 AGENTS.md, DEVELOPMENT_RULES, handoff, material_review를 읽고 context-handoff snapshot과 실제 증거를 대조했다. 이전 handoff snapshot HEAD는 그 문서를 저장하기 전 부모이며 실제 60da936의 파일 목록과 일치한다. 이번 요청은 구현/빌드 준비를 허용하지만, 호환성 근거 부족 조합은 빌드 전 차단하도록 명시한다. 이 조건이 현재 적용된다. 새 구현/패치/빌드 산출물은 없다.

## 구성요소 선택과 ABI 경계

|경계/구성|검토한 구성|근거와 남은 차단|
|---|---|---|
|Sim core ↔ Physics system|둘을 같은 격리 Sim 소스로 재빌드하는 최소 후보. 설치 core와 수정 Physics 혼용 배제|Sim 8.15.0 배포 source/checksum, 무패치 packaging, matching debug 존재. 새 init callback/interface를 양쪽에 같이 넣어야 함. 실제 build closure/compiler flags는 미고정이며 원 buildinfo 미확보|
|Physics system ↔ gz-physics feature/plugin|설치 feature core와 dartsim plugin 재사용 후보 **거부**|upstream 7.8.0의 RetrieveWorld는 source 내부 virtual Feature/Implementation이다. 설치 헤더에서 대응 feature 미발견. export GetDartsimWorld 및 thunk의 존재는 interface inheritance/vtable/Feature 계약 ABI를 증명하지 않음. 정확 native 배포 payload·matching debug·buildinfo 없음|
|gz-physics plugin ↔ DART World/solver/detector|설치 DART core/adapter 재사용 후보 **미인증**|선택 ELF identity는 재확인. DART source/9 patches 확보와 SONAME/export는 C++ class/layout/inline/compiler ABI 전체의 증거가 아님. 대응 debug/buildinfo 없음. 기존 parity 보고서도 full ABI 인증 아님|
|provider entry 관측 대안|gz dartsim plugin + 선택 DART adapter/Core 추가 재빌드 후보 **거부**|정확 physics 배포 payload와 DART binary build 근거 부족. RTTI-only 관측으로 낮춰 요구를 충족했다고 할 수 없음. 새 provider를 빌드하면 설치 provider에 대한 관측과도 다른 대상|
|나머지 설치 ELF|재사용 승인 목록 **없음**|9개 고정 ELF는 audit의 비교 입력이며 승인된 실행 closure가 아님. 전이 의존성 전체 고정/ABI 검사도 미완료|

따라서 어떤 조합도 configure/compile/link 또는 실행 승인 대상으로 확정하지 않는다. matching debug 부재 자체를 보편적인 ABI 불일치 증명으로 쓰는 것은 아니다. 현재 **이 source 내부 인터페이스와 설치 구현의 동일성을 대체 입증할 증거도 없다**는 판단이다. 시스템 /usr/include/dart의 World.hpp/ConstraintSolver.hpp도 없음; 격리 헤더를 설치 대응 헤더로 임의 승격하지 않았다. 원 source/debug 획득 또는 동일 source/patch/toolchain으로 일관된 closure의 별도 범위 확정이 먼저다. 이번에는 추가 다운로드/시스템 설치/위험 수용으로 해결하지 않는다.

## typed 경로와 provider 증명 조건

직접 다시 읽은 physics source의 `dartsim/src/World.hh`는 RetrieveWorld::World::GetDartsimWorld → Interface<RetrieveWorld> → virtual Implementation 호출이다. CustomFeatures.hh는 Implements3d<CustomFeatureList<RetrieveWorld>>를 포함하고 plugin.cc가 CustomFeatures를 상속한다. CustomFeatures.cc는 worlds.at(identity)의 기존 shared_ptr를 반환한다. WorldFeatures.cc의 getter는 native World → getConstraintSolver → getCollisionDetector → getType를 호출한다. 이 경로는 **해당 upstream source에서 SUPPORTED**, 설치 플러그인과의 ABI 연결 및 실제 Sim 인스턴스 연결은 **UNRESOLVED**다. private offset/객체 reinterpret_cast/별도 World 생성은 사용하지 않는다.

향후 구현은 Physics가 보관한 entityWorldMap의 동일 world identity에서 typed feature 요청을 시작해야 한다. native world/solver/detector의 소유권을 유지하고 null/복수 world/feature 미지원은 즉시 거부한다. getType 문자열·설정·maps에 ELF가 존재한다는 사실만으로 활성 구현을 판정하지 않는다. 정상 C++ cast로 연결한 동일 detector this에 대해 선택된 query 메서드의 source entry와 module-local anchor를 기록하고 실제 mapping 범위/offset, 열린 backing ELF의 hash/Build ID와 연결해야 한다. dladdr(typeid)만으로는 타입 모듈만 입증한다. wrapper와 base provider는 각각 기록하고 불일치·관측 누락·mapping 변경이면 GO를 거부한다. GO 전 collide 호출은 금지하며 query provider 관측을 collision 실행 증거로 주장하지 않는다. 이 observer는 아직 구현/실행되지 않았다.

## 초기화/GO 구현의 남은 검증

기존 소스 순서는 Run → UpdateCurrentInfo(time/iteration 증가) → Physics Update → CreatePhysicsEntities → Step이다. 따라서 기존 Update에 대기만 넣으면 iteration=0 요구를 만족하지 못한다. matching Sim source를 사용한 향후 변경 위치는 Run의 첫 UpdateCurrentInfo 및 realtime 시작 전이다. 같은 Physics 인스턴스에서 CreatePhysicsEntities만 동기 1회 실행하고 UpdatePhysics/RunOnce를 bootstrap으로 호출하지 않아야 한다.

필수 불변식은 init count=1, Sim iteration/time=0, native frame/time=0, 정확히 한 world/detector/provider 관측, bounded GO 전후 identity/zero-state 일치다. 첫 정규 Update의 생성 helper 중복 호출을 막되 EachNew 플래그를 미리 지우거나 link/joint-added bookkeeping을 잃지 않아야 한다. 대기 중 ECM 변경/제어/추가 plugin/network/reset을 거부하고 runner 진입 및 Physics Step 경계를 GO가 지배해야 한다. init 예외/실패·timeout·EOF·누락/잘못된 detector/provider는 Step 없이 종료해야 한다.

**컴파일/링크/정적 구현 검사/모의 상태기계 검증은 NOT_PERFORMED**: 아직 구현이 없고 ABI 사전 게이트에서 차단됐다. 문서의 설계나 독립 mock만으로 실제 runner의 무스텝성·초기화 1회 PASS를 만들지 않았다. 초기화 하위 호출 전체의 무스텝성/동시성 역시 미검증이다.

## 산출물·무결성·재개 게이트

`input_audit.json`과 `../scripts/audit_inputs.py`는 읽기 전용 hash/readelf 검사다. 직접 실행 결과: 71 파일 hash와 9 설치 ELF Build ID 일치, main HEAD/status 유지. source_files/download_hashes/material_inventory의 입력을 재검사하므로 원 archive·선택 source/fixture·기존 evidence/marker·설치 ELF를 포함한다. 전체 ignored tree의 무결성 주장은 아니다. Build ID 일치를 ABI 인증으로 해석하지 않는다. audit에는 정확한 비교 ELF 경로/hash/ID가 있다. 새 패치·컴파일 입력·ELF 산출물 hash는 **N/A (생성 안 함)**. 외부 소스/원시 자료는 기존 ignored 경로에 보존하며 설치 경로에 쓰지 않았다.

서비스 시작·marker 생성/소비 전에 거부 유지. 기존 launcher/contract/marker는 수정하지 않았다. 계측 바이너리/실제 DART/Gazebo 로딩, target 검사 실행, 물리 Step, sudo/패키지 설치/시스템 설정 변경 모두 수행하지 않았다. 위험 수용 미결정. destructor NOT_OBSERVED / allocator NOT_MEASURED 및 기존 자유낙하·Clock/Capture 판정 기준 유지.

**1회 실행 승인안은 발행하지 않는다.** 실행 파일이 없으므로 정확 명령/인자·새 ELF hash·의존 closure를 고정할 수 없다. 이전 승인안을 새 빌드에 재사용하지 않는다. ABI 게이트 해소 후 같은 source/patch의 최소 구현, 타깃을 실행하지 않는 compile/link와 정적/모의 검증, 전체 ELF closure 고정이 다음 순서다. 그 후에만 새 출력/one-shot, 격리·자원/벽시계 한도·GO timeout, GO 후 100 × 1ms와 기존 자유낙하 판정, 실패·정리·원본 무결성을 포함한 **계측 빌드 전용** 정확 승인안을 작성할 수 있다. 실제 로딩/실행은 그 뒤 별도 명시 승인이 필요하다. 이번 요청은 이 차단 기록/게시 후 종료한다.
