# DART Consumer ABI Deep Verification V2

## 1. 목적·판정 및 이전 결과

**CONSUMER_ABI_DEEP_PARTIALLY_VERIFIED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.**

설치 Bullet–격리 core 경계의 객체·inline·virtual 위험을 정적 분석과 컴파일 전용 fixture로 좁혔다. 명백한 ABI 불일치는 발견하지 않았으나, 설치본 전체 타입 레이아웃이나 runtime 중립성을 인증하지 않는다. Host 진입은 **NOT_READY**다.

Consumer V1 final/verdict/test_summary/integrity를 대조했다: 고유 DART 참조252개(동일 binary2경로), 누락0, loader12회 오류0, 신규12/native45/regression108=165 PASS, 보존21091파일 변경0, CONSUMER_ABI_PARTIALLY_VERIFIED. 이는 **과거 결과**다. Capability V2 final/verdict와 원래 main의 parity-v1 및 implementation final을 읽었다. V2 core5739 exports, capability3 일치, 설치 타입 DWARF/buildinfo 미확보 한계를 유지한다. 이번 직접 관측과 과거 DWARF 결과를 합치지 않는다.

## 2. Git·Worktree 및 인계 대조

실험 worktree `/tmp/AeroAIStudio-dart-internal-trace`, 승인 branch `experiment/dart-internal-trace`, 시작 HEAD `2edd9e989e7ab8186a075cf605ddecb6b7dfa386` clean이었다. 원격 실험 HEAD가 동일하며 원격 main은 `46134c6bf5670ed61ba252f394ccdddb7ff2cf6b`임을 재조회했다. main의 기존 변경을 이동·초기화·stage하지 않았다.

기존 handoff verify는 실제로 REVIEW_REQUIRED를 반환했고 원인은 `GIT_CHANGED/head` 하나였다. 저장된 b3c3f0f는 현재2edd9e9의 parent이며, V1 게시23파일과 기록 evidence hash가 일치한다. **helper 자체가 MATCH였다고 표현하지 않는다.** 예상된 게시 전 snapshot→게시 후 HEAD 전이로 검토 완료했다(`handoff_reconciliation.json`). 기존 실행 중 분석 작업은 초기 visible same-user project-CWD 범위에서 없었으며 외부/원격/container는 UNKNOWN이다.

이번 디렉터리만 신규 생성했다. 기존 Consumer V1/Capability V2/원래 main의 분석은 읽기 전용 입력이다. 추가 AGENTS 지침은 validation 아래에서 발견되지 않았다.

## 3. Bullet–DART Core 객체 계약

실제 설치 `/usr/lib/x86_64-linux-gnu/libdart-collision-bullet.so.6.13.2`와 설치 core(A), 기존 격리 baseline(B)/trace(C)를 조사했다. Bullet3.24 및 DART6.13.2가 현재 설치·헤더/ELF 경계다. 라이브러리 SHA/Build ID는 이전 inventory에 연결되고 이번 integrity 대상에 포함한다.

|타입|컴파일 Size/Alignment|Base·member 근거와 한계|
|---|---:|---|
|CollisionObject|24/8|vptr0, detector8, ShapeFrame16. 설치 getter 기계어의 offset과 A/B/C compile 배치 일치|
|CollisionGroup|336/8|헤더 member/base 배치 일치; 설치 full layout UNKNOWN|
|CollisionDetector|32/8|enable_shared_from_this base8, manager unique_ptr24(컴파일 근거). 설치 full layout UNKNOWN|
|CollisionResult|136/8|컴파일 배치 일치; 설치 전체 레이아웃 UNKNOWN|
|Contact|112/8|public fields offset0,24,48,72,80,88,96,100,104; 선택된 Gazebo binary 접근/stride와 일치|
|BulletCollisionObject|48/8|CollisionObject base0, Bullet shared shape24, engine unique_ptr40. 설치 getter+40 및 new48 관측|
|BulletCollisionGroup|368/8|CollisionGroup base0, Bullet engine handles 후행(컴파일). 설치 full layout UNKNOWN|
|BulletCollisionDetector|88/8|CollisionDetector base0, map/group 후행(컴파일). 설치 full layout UNKNOWN|
|ShapeFrame|1184/16|다중·가상 상속 및 멤버 전체 compile dump 확보. 설치 full member/base layout UNKNOWN|
|ShapeNode|1664/16|다중·가상 상속. fresh compile의 ShapeFrame base+272; 설치 전체 base 배치 UNKNOWN|

A-arm은 **설치 binary layout이 아니다**. 현재 `/usr/include/dart`는 없으며 `libdart6.13-dev`는 NOT_INSTALLED다. 기존 격리 prefix에 추출된 matching distribution core 헤더와 baseline source의 Bullet fallback을 사용한다. B/C source·generated config와 출처를 분리했다. V1의 ‘installed-header’ 표현을 실제 시스템 설치 헤더로 해석하면 부정확하므로 이 보고서에서 출처를 정정하며 기존 V1 기록은 수정하지 않았다.

소스 계약: Bullet factory가 unique_ptr<CollisionObject>를 반환하고 core manager가 release() 후 custom-deleter shared_ptr로 감싼다. deleter는 detector virtual notify 후 delete object를 수행한다. CollisionObject의 virtual destructor를 통해 derived 파괴로 이어지는 선언/ELF 경로를 확인했다. Bullet shape shared_ptr/deleter는 detector map 회수와 연결된다. detector/manager가 관리 객체보다 오래 살아야 하는 조건, allocator/예외 중 파괴의 실제 순서는 runtime 미검증이다. 강한 소유자·raw back pointer를 혼동하지 않는다.

`bullet_core_contract.json`은 10타입의 compile 상수, member/base dump 연결, 소스 hash/line, 선택된 설치 getter machine-code hash를 담는다. 모든 source-based 관측을 설치본 실제 layout 인증으로 올리지 않는다.

## 4. Inline·내부 접근

설치 Gazebo의 `SimulationFeatures::GetContactsFromLastStep`에서 vector<Contact>의 begin/end 사용 뒤 `0x236870: add $0x70,%rbx`를 확인했다. 이는 Contact stride112와 맞는다. `convertContact`는 입력 rdx를 r13에 보존하고 object1+72/object2+80, force+48, normal+24, depth+88을 읽는다. 설치 ELF의 직접 멤버 접근을 fresh compiler layout과 대조한 **선택된 binary 근거**다.

설치 core `CollisionObject::getShapeFrame`은 +16, getCollisionDetector는 +8을 읽으며 A/B/C의 해당3 getter 기계어 hash가 일치한다. 설치 Bullet getter는 +40을 읽고 createCollisionObject는 operator new(48) 뒤 해당 ctor를 호출한다. 전체 객체 크기·alignment가 입증된 것은 아니다.

Header-only vector<Contact> index, shared_ptr derived→base 변환, public depth getter/setter, dynamic_cast, virtual getType, ShapeNode→ShapeFrame upcast를 compile-only로 생성했다. 세 header arm의 disassembly는 동일하다. getType 호출은 vptr+0x18, fresh upcast는 +0x110, Contact depth는 +0x58을 사용한다. 이는 **현재 compiler와 recipe의 생성 코드 동일성**이며 과거 설치 compiler 설정 동일성은 아니다.

Gazebo convertContact에는 ShapeFrame vptr+0x28 간접 호출이 있다. header의 primary address point112와 더하면 offset152의 asShapeNode() const에 대응한다. 실제 derived object의 모든 local target identity는 미확정이다. 전체 binary scan의 간접 call instruction 수(Bullet436/Gazebo987)나 dynamic_cast call-site 수(1/17)는 위험 탐색용 정적 수치이며 실제 실행 횟수·전부 DART 호출이라는 뜻이 아니다. 모든 최적화 memory operand의 provenance를 복구하지 못했으므로 **전체 Inline 안전성은 UNKNOWN**이다(`inline_access.json`).

## 5. VTable·RTTI·Virtual Interface

이름/크기 비교를 넘어 ELF64 section bytes와 relocation을 해석했다. core의 관련 vtable/RTTI35 records(템플릿·base typeinfo 포함), 582개의8byte entries를 A/B/C에서 추출했다. 34 records는 relocation target symbol/offset/scalar가 일치한다. ShapeNode vtable275 slots 중67 local target slots는 stripped 주소만 남아 identity가 미확정이고, 비교 가능한 나머지 슬롯에는 차이가 없다. 주소 재배치 차이를 ABI mismatch로 처리하지 않는다.

Bullet8 records/43 entries, Gazebo7 records/73 entries도 추출했다. Bullet CollisionObject/Group/Detector의 RTTI가 해당 core base RTTI를 참조함을 확인했다. Group/Object의 local destructor targets는 미해석이다. core Typeinfo name49개는 A/B/C에서 같은 이름 내용을 제공하며, RTTI descriptor의 base/flag/offset word도 비교했다. `vtable_rtti.json` 참조.

헤더 기반 GCC class/vtable dump는 A/B/C에서 동일하다. CollisionObject의 virtual dtor·update, Group engine interface, Detector clone/getType/createGroup/collide/distance/raycast/createObject/refresh/notify 선언 순서와 ShapeFrame/ShapeNode의 복잡한 virtual bases를 포함한다. RTTI·dynamic_cast relocation은 확인했지만 cast를 실행하지 않았다. thunk/covariant/virtual-base 조정 중 익명 local target 의미와 runtime exception type matching은 UNKNOWN이다. vtable 심볼 존재만으로 슬롯 전체 인증을 선언하지 않는다.

## 6. Compiler ABI·매크로

현재 GCC13.3.0, secondary Clang18.1.3, C++17, __GXX_ABI_VERSION1018, CXX11 string ABI1, RTTI/EH 활성 macro를 확인했다. compile fixture는 btScalar4, Eigen MAX_ALIGN/MAX_STATIC_ALIGN16, string32/shared_ptr16/unique_ptr8이다. Bullet header3.24/Eigen3.4.0 및 HAVE_BULLET/IPOPT/NLOPT/ODE=1은 세 arm에서 일치한다. BT_USE_DOUBLE_PRECISION는 이 fixture에서 정의되지 않았다.

기존 B/C core 실제 flags.make/cache/config를 다시 읽었다: -O2/-g, LTO/fat objects, hardening, default visibility, no explicit no-rtti/no-exceptions/packing override. RTTI·unwind ELF 시설을 추출했다. fmt9/spdlog1.12 사용은 기존 build recipe/profile 및 현재 패키지 근거와 연결한다. B/C generated config의 source/data 경로 차이는 유지하며 숨기지 않는다.

설치 A/Bullet/Gazebo에서는 `.comment` producer 문자열이 확보되지 않았고 원 buildinfo도 없다. B/C .comment는 현재 GCC13.3 producer를 기록한다. **설치본의 정확한 compiler/optimization/LTO/visibility/Eigen alignment/모든 매크로는 UNKNOWN**이다. 현재 fixture 매크로로 설치 binary 조건을 역추정하지 않는다(`compiler_abi.json`).

## 7. Boundary Fixture 범위

`tests/boundary.cpp`를 A/B/C에 대해 GCC object compile, class/vtable dump, Clang syntax/layout dump, macro preprocess로 검증했다. static_assert로 base 관계와 virtual destructor를 검사하고 ELF object 상수로 sizeof/alignof/offsetof를 읽었다. linked DART executable이나 World를 만들지 않았다. fixture 함수에 object 접근/cast 경로가 생성되지만 **그 함수를 실행하지 않았다**. 포함 헤더가 내보내는 모든 함수가 실행 안전하다고 인증하지도 않는다.

독립적인 아주 작은 Base 클래스 공유 ELF를 compile/link만 한 parser test는 relocation 슬롯을 의도적으로 바꿨을 때 table 차이를 탐지한다. 이 ELF도 load/execute하지 않는다. 새 객체 runtime 생성·충돌 계산·World·solver 호출은 새 fixture에서 전부 NOT_RUN이다.

## 8. 계측 OFF/ON의 객체 ABI 영향

기존 선언403 .hpp 전부 B/C hash가 같다. targeted collision/dynamics/common 중 matching packaged header214개도 모두 baseline과 일치한다. 기존 공개 member/base/virtual 선언 추가는 발견하지 않았다. 계측의 새 internal_trace.h는 별도 진단 API다.

새 static State, thread_local Context, once_flag는 기존 객체 필드와 구분한다. World ctor initializeEnvironment/step scope/destructor FinishWorld가 추가되며 기존 World 필드를 늘리지 않는다. core→external의 추가 recorder imports와 external의 추가 stdlib/thread/EH dependencies는 기존 V2 근거를 유지한다. 이번에는 실제 새 core/external Loader 선택도 다시 확인했다.

OFF도 진단 진입·getDimension 인자 평가·once/env/TLS/예외 상태 검사를 추가한다. 원본과 동일 실행 경로가 아니다. ON metadata 가상 조회·copy·atomic/cache 및 구성/flush의 allocator·serialization 비용이 있다. owner check가 전역 상태의 일반적 동시 접근 안전성을 보장하지 않는다. Configure/GetStatus/Flush는 owner/quiescent 경계가 필요하다. runtime 객체 수명·lock 순서·실제 solver 결과·FP/시간 중립성은 UNKNOWN이다(`instrumentation_abi.json`).

## 9. 신규 테스트 및 최초 분석 오류

신규 pytest **13 PASS**, failures/errors/skips0. 세 arm compile, base/member/offset/constants, 설치 getter 코드, 실제 resolved vtable/RTTI, Bullet base RTTI, inline/virtual/cast 생성 코드, loader/import, 계측 선언, ELF encoding 거부 및 relocation slot mutation을 검사했다.

분석기 개발 중 ET_REL section 주소를 일반 ELF virtual address로 읽어 잘못된 상수가 나온 초기 JSON을 `work/contract_initial_rel_address_bug.json`에 보존했다. section index+offset으로 수정한 뒤 상수112/24 등의 compiler dump 및 실제 binary 근거와 대조했다. GCC dump의 `0x0x...` compiler identity 정규화와 stripped local 주소의 UNKNOWN 분류도 수정했으며 원시 초기 출력은 work에 남겼다. 이는 실제 ABI 불일치 발견이나 테스트 기준 완화가 아니다. 최초 pytest부터13 PASS였고 실패한 테스트를 삭제하지 않았다.

## 10. 기존 테스트와 Loader 재실행

이번 실행 **Consumer V1 12 + Native45 + 프로젝트 regression108 PASS**. 신규13 포함 **178 distinct PASS**, failures/errors/skips0이다. Native의 synthetic algebra/constraint 회귀는 이전 검토된 fixture hash·금지 호출 검색을 확인하고 실행했고 프로젝트 regression은 기존 runtime fence를 적용했다. 이 결과를 새 boundary 객체 runtime 검증과 혼동하지 않는다. Gazebo/World::step/full DART suite/Stage B는 NOT_RUN이다.

새 Loader 검사12회: Gazebo/Bullet 각각 A/B/C=6, B/C optional IPOPT/NLOPT/ODE=6. undefined/error0, 각 arm에서 Gazebo252/Bullet53 DART import 누락0 및 관측 metadata 불일치0. 신뢰하는 glibc ldd trace/relocation이며 init array·plugin entry·dlopen은 실행하지 않는다. system IFUNC resolver가 실행될 수 있는 loader 성격은 구분한다. 물리 API는 호출하지 않았다. B/C의 설치 Bullet 혼합은 명시적 구성이고 core/external/ODE는 격리 빌드를 선택한다(`loader_results.json`).

## 11. Production·Evidence 무결성

새 manifest는 main 원본/V1의 전체 결과·work/Capability V2 source·build·reports/provider/system package 상태와 이전 explicit 보존 목록을 새 hash로 기록했다. 이번 **30,031개 파일 변경0**, main HEAD/status 보존을 확인했다. 전후 결과는 `integrity.json`에 있으며 기존 baseline 숫자를 이번 검사 숫자로 재사용하지 않는다. raw manifest는 Git 제외 work/preservation.json에 보존한다. main HEAD/dirty 상태와 기존 보고서·산출물을 보존했다. Production Physics/SDF/패키지/DART/전역 Loader/Clock/Capture/solver 알고리즘 변경은 없다.

## 12. 줄어든 위험

심볼 존재만 확인하던 범위에서 실제 collision 관련 resolved vtable/RTTI slots, CollisionObject core getter 기계어, Bullet allocation/pointer offset, Gazebo Contact stride·선택된 멤버 접근까지 binary 근거를 확보했다. 10개 타입의 compiler base/member 배치, template/cast/virtual 생성 코드, 현재 매크로 및 계측 선언 무변경을 재현 가능한 fixture로 보완했다. 이는 선택된 인터페이스의 위험 감소이며 전체 설치 객체 ABI의 증명은 아니다.

## 13. 남은 위험

Bullet/Core 객체 전체 및 Inline 접근은 COMPATIBLE_WITH_LIMITATIONS/HIGH, vtable/RTTI는 partial/HIGH다. 원 설치 compiler ABI, 계측 ON의 객체 수명·thread/lock·FP/시간은 UNKNOWN/HIGH다. 비교 가능한 subset에 명백한 mismatch는 없다. ShapeNode67 local slots와 Bullet local destructor identity, 실제 allocation ownership/unwinding, 소비자 전체 inline provenance와 설치 debug/buildinfo 부재가 남았다. 미확인을 LOW로 처리하지 않는다(`risk_assessment.json`).

## 14. Host 준비 조건과 통제 가능성

현재 Host 실행은 보류한다. 최소 조건은 (a) 실제 소비 경계의 남은 virtual/local destructor·필수 inline/member offset 증거를 확보하거나 항목별 잔여 위험을 명시적으로 수용, (b) 선택한 설치 Bullet+격리 core/external/ODE closure를 고정·해시 검증, (c) detector/manager/group/object 소유권과 allocator/EH 경계를 검증할 안전한 비물리 객체 시험을 별도로 설계·승인, (d) recorder OFF/ON owner/quiescent·overflow·metadata·flush·time mapping 계획과 기존 Clock/Capture 기준 유지, (e) 제한된 실행 범위에 대한 별도 사용자 승인이다.

프로세스 격리·짧은 실행·fail-fast는 production 영향 범위를 줄일 수 있지만 ABI UB나 잘못된 계측값을 통제했다는 증거가 아니다. 따라서 ‘짧게 돌리면 안전’으로 불확실성을 수용하지 않는다. 이번 근거로 **다음 안전성 계획을 검토할 수는 있지만 Runtime 시작 준비 완료는 아니다**. 안전성이 확인되지 않은 객체 생성 시험도 이번에는 수행하지 않았다.

## 15. 다음 최소 작업

원 binary Build ID에 대응하는 debug/symbol map을 확보하거나, 소비 경계에서 실제 쓰이는 ShapeNode/Bullet local virtual/destructor target과 남은 critical member offset을 좁혀 disassembly 근거를 보완한다. 그 다음 별도 승인될 수 있는 비물리 객체 수명·cast·unwind 검증 계획부터 검토한다. Gazebo/World::step/Stage B로 자동 진행하지 않는다.

## 16. Git 게시·재현

승인 branch에 신규 scripts/tests/경량 reports와 handoff만 명시적으로 선택해 staged diff·whitespace·비밀정보·ownership을 검토하고 commit/push한다. 원격 commit 일치는 로컬 `reports/git_publication.json` 영수증에 저장한다. 보고서 자체 commit hash를 넣기 위한 재귀 commit은 하지 않는다. 이전 게시 commit은2edd9e9이며 이번 최종 commit은 영수증/최종 응답을 따른다. main/force push·merge는 없다.

재현 순서는 `reports/reproduction.md`와 각 scripts를 따른다. 기존 V1/Capability build·추출 헤더 및 원래 main의 미커밋 회귀 입력은 원래 위치에 필요하며 Git만으로 전달되지 않는다. 새 work 디렉터리의 raw dump/바이너리는 게시하지 않는다. NOT_RUNTIME_VERIFIED / Stage B BLOCKED 유지.
