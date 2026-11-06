# ShapeNode Virtual & Destructor Boundary Verification V3

## 1. 목적과 이전 V2 확인

**SHAPENODE_BOUNDARY_PARTIALLY_VERIFIED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.** Host Runtime 진입 준비는 완료되지 않았다.

V2 final/verdict/vtable_rtti/bullet_core_contract/boundary_fixture 및 V1·Capability V2 final 보고서를 직접 대조했다. V2의178 PASS(13+12+45+108), loader12 오류0, 보존30031 변경0, 선택된 객체/Contact 접근 일치, ShapeNode275개 table words 중67 local targets UNKNOWN, 설치 full layout·수명·예외·중립성 미확정과 CONSUMER_ABI_DEEP_PARTIALLY_VERIFIED를 확인했다. 이는 **과거 결과**다. 이번 새 테스트·hash·loader 관측을 아래에서 분리한다.

## 2. Git/Worktree 시작 상태

실험 worktree `/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`, 시작 HEAD `c22f9476d9d2244c244e87272fa1a927e49d6658`, clean이었다. 원격 실험 HEAD도 같고 원격 main은46134c6이었다. main 기존 dirty 파일은 보존했다. reset/rebase/stash/clean/merge/force push는 없다. 추가 validation AGENTS는 없었다.

기존 handoff verify의 REVIEW_REQUIRED는 head 차이 하나였다. 저장된2edd9e9는 c22f947의 parent이며, 게시26파일·checkpoint evidence hash 일치로 예상된 snapshot→게시 전이를 확인했다(`handoff_reconciliation.json`). helper 자체가 MATCH였다고 표현하지 않는다. 초기 project-CWD visible same-user 작업은 없었으며 외부/remote/container는 UNKNOWN이다.

## 3. ShapeNode67개 재현 및 슬롯 의미

V3의 독립 ELF64 reader로 A 설치 core, B baseline, C trace의 `_ZTVN4dart8dynamics9ShapeNodeE`를 다시 읽었다. V2의 **정확히 같은67 index와 주소**를 재현했다. table은275개의8byte word이며67개는49개의 고유 함수 주소를 가리킨다. 반복 슬롯을 서로 다른 함수67개로 세지 않는다.

각 행에 table index/byte offset, entry ELF virtual address/raw bytes/RELA, target address/full-symbol aliases·binding/visibility, demangle/addr2line, FDE 경계, normalized code, destructor/thunk, address point·상대 offset, 소비 분류·근거·한계를 기록했다(`shapenode_slots.json`). 주소는 ELF link virtual address이며 ASLR이 적용된 실행 주소가 아니다. 빌드별 절대 주소 차이로 mismatch를 선언하지 않는다.

GCC hierarchy의21 address point를 기존 compile dump에서 추출하고 설치 table의 offset-to-top/RTTI word와 대조했다. 배열 index를 virtual function ordinal로 부르지 않는다. 예: primary AP144에서 index18/19는 D1/D0, Node subobject AP552에서69/70, ShapeFrame subobject AP816에서102/103이 dtor pair다. 앞선 offset/RTTI·vbase metadata와 함수 entry를 분리한다. AP 위치의 출처는 compiler hierarchy이며 설치 full debug가 아니다.

## 4. IDENTIFIED/INFERRED/UNRESOLVED

|범위|IDENTIFIED|INFERRED|UNRESOLVED|
|---|---:|---:|---:|
|설치 A의67 slots|0|48|19|
|B의67 slots|67|0|0|
|C의67 slots|67|0|0|

B/C는 full ELF local symbol의 정확한 시작 주소와49 고유 target 모두의 DWARF addr2line source를 직접 확보했다. 설치 A에서는 stripped local 이름을 복구한 것이 아니므로 B/C 이름을 IDENTIFIED로 전파하지 않는다. A48은 FDE로 제한한 instruction/operand/internal branch shape·table 위치·B/C named identity를 이용한 **추론**이다. 이 중6 slots는 bounded local-call 비교까지 일치했고42는 RIP 주소/이름 없는 callee target 정규화 한계가 남는다. 이를 code/semantic equality로 부풀리지 않는다.

미해석 index19개: **18,20,23,26,42,43,44,46,47,48,49,51,52,53,55,56,57,58,59**. B/C 후보 이름은 있어도 A의 complete destructor·EntityNode state/name 및 Jacobian 계열 내부 callee·cold path 대응이 충분하지 않아 UNRESOLVED다. slot18 primary D1은 여기에 포함된다. 초기48/19 결과와 refinement 원본은 work에 보존했다.

## 5. 함수 정체와 구현 차이

B/C에서67개 모두 같은 local symbol identity를 가진다. 단 **slot58 getLinearJacobianDeriv(offset, Frame*) const**는 register/stack/생성 코드가 달라 normalized code도 다르다. 동일 함수 정체·호출 시그니처와 구현/최적화 차이를 구분하며, 이 차이만으로 ABI mismatch라고 하지 않는다. 설치 A의19개 unresolved도 실제 mismatch 확인이 아니다.

정규화는 instruction 주소와 RIP 배치를 지우지만 member offset·register·stack·내부 분기 상대 위치를 보존한다. 외부 callee 이름을 마스킹한 경우를 명시한다. recursive helper 비교는 깊이2로 제한하며 미확인 edge를 통과시켜 PASS로 만들지 않는다. 기계어의 부분 구조 일치는 설치본 type signature·반환 ABI·전체 의미의 증명이 아니다.

## 6. 소비자별 실제 Virtual Dispatch

설치 Gazebo convertContact의 실제 `0x2354b2` 등 callsite에서 ShapeFrame vptr+0x28 호출을 재확인했다. ShapeNode의 해당 subobject compiler AP816+40은 **index107**이며, V2의67개에는 포함되지 않는다. receiver의 runtime dynamic type은 관측하지 않았다.

설치 core `NodeDestructor::~NodeDestructor`의 `0x2b15bf: jmp *0x8(%rax)`는 source의 delete Node*와 연결된다. 실제 동적 타입이 ShapeNode라면 compiler Node AP552+8의 **slot70 D0 thunk**로 이어질 수 있다. 이 행은 INDIRECTLY_REACHABLE다. BodyNode가 destructor set을 clear하고 NodeDestructor를 소유하는 source 경로도 기록했다. 실제 Gazebo cleanup 발생/순서를 실행으로 확인한 것은 아니다.

67개 분류: DIRECTLY_REFERENCED0, INDIRECTLY_REACHABLE1, NOT_OBSERVED25, UNKNOWN41. NOT_OBSERVED는 실행 불가능 판정이 아니다. 나머지 dtor entries는 다른 base deletion·간접 호출 가능성 때문에 UNKNOWN으로 둔다. 설치 Bullet/Gazebo의 ShapeNode/ShapeFrame undefined refs와 external A/C의 관련 참조도 실제 추출했다. External LCP에서 관련 직접 참조는 발견하지 못했지만 전체 program graph를 증명하지 않는다(`consumer_virtual_calls.json`).

## 7. Constructor/Destructor 계약

ShapeNode/ShapeFrame/Node, CollisionObject/Group/Detector, Bullet derived types, CollisionResult/Contact의 C1/C2/C3 및 D0/D1/D2가 실제 ELF에 존재하는 범위를 수집했다. C1 complete ctor, C2 base ctor, D1 complete dtor, D2 base dtor, D0 deleting dtor를 구분하고 alias도 남겼다. inline·abstract·최적화로 variant symbol이 없을 수 있어 부재 자체를 ABI 누락으로 판정하지 않는다. Contact/CollisionResult copy/move의 실제 동작은 이번 runtime 검증 범위가 아니다.

67개 중 **D1 21 slots/D0 21 slots**이고, secondary entries에 this-adjusting thunk가 포함된다. primary D0 slot19와 Node D0 slot70은 A에서 INFERRED지만 primary D1 slot18은 unresolved다. A D0의 호출 대상에 objdump가 붙이는 nearest exported label을 실제 함수명으로 믿지 않는다.

설치 BulletCollisionObject/Group의 vtable dtor pairs는 로컬 이름이 없어서 INFERRED, BulletCollisionDetector의 exported pair는 IDENTIFIED다. Object D0는 **0x20f3e의 size48**을, Group D0는 **0x21f35의 size368**을 준비하고 sized operator delete로 이어진다. 현재 header sizeof48/368과 일치하지만 모든 allocator·정리 경로의 안전성을 입증하지 않는다(`destructor_contract.json`).

## 8. Bullet/Core 소유권과 Cross-Module 해제

소스상 Bullet module이 new BulletCollisionObject를 unique_ptr<CollisionObject>로 반환하고 core manager가 release 후 custom-deleter shared_ptr로 감싼다. core deleter는 detector virtual notify 후 base pointer delete를 수행하므로 derived D0는 Bullet 쪽, 최종 일반 delete는 C++ runtime 경계로 이어진다. Bullet shape deleter는 detector map을 참조한다. detector/manager와 shared shape/map owner의 수명이 callback보다 길어야 한다.

ShapeNode는 별도의 NodeDestructor shared-control 구조이며 BodyNode destructor set·detach와 연결된다. source의 raw back pointer·weak destructor reference와 strong ownership을 분리했다. 선언상 new/delete 경로의 명백한 모순이나 실제 mismatch 증거는 발견하지 못했다. 그러나 실제 double-free/dangling·copy/move·shutdown/global registrar·exception cleanup 순서는 UNKNOWN이다. 설치 Bullet registrar와 Trace State/TLS/once_flag의 전역 수명도 기존 객체 layout과 별개다(`ownership_boundary.json`).

## 9. RTTI, Dynamic Cast, Thunk

ShapeNode/ShapeFrame의 실제 RTTI descriptor·type-name을 A/B/C에서 새로 읽어 일치를 확인했다. 복잡한 multiple/virtual base metadata는 header AP 모델과 구분한다. selected67에는 **non-virtual thunk12 entries, virtual thunk30 entries**가 있으며 동일 target 반복을 포함한다. `_ZThn144` 등의 고정 this 보정과 `_ZTv...n32` 등의 vcall-offset 보정을 local symbol·실제 bounded assembly로 연결했다.

선택된67에서 covariant `_ZTc` target은 관측하지 못했으며 다른 범위의 부재를 주장하지 않는다. RTTI 가시성/binding은 raw ELF metadata로 남겼다. compile-only dynamic_cast<void*>(Node*) 코드도 생성했지만 cast·catch를 실행하지 않았다. RTTI 이름·descriptor 일치가 모든 runtime cast/exception type matching을 보장하지 않는다(`rtti_thunks.json`).

## 10. Exception/Unwinding

`.eh_frame`, `.eh_frame_hdr`, `.gcc_except_table`, CIE augmentation/personality, FDE range, LSDA pointer 및 __cxa_throw/begin/end_catch, _Unwind_Resume, __gxx_personality와 version 요구를 추출했다. A/B 각 FDE10713·LSDA포인터 포함4152, C는10714/4156이었다. 수치 차이는 계측 관련 코드 범위 차이이며 그 자체로 mismatch가 아니다. Bullet565/177, Gazebo1906/567, external A76/0·C104/8도 기록했다.

선택49개 함수 시작 주소의 FDE를 찾았고, decoded LSDA는 `.gcc_except_table` 내부로 연결된다. A FDE 전체 시작/끝은 독립 readelf frames-interp와 테스트로 대조했다. LSDA action/catch table 의미와 cleanup landing-pad의 전체 동등성은 미해석이다. CFI·LSDA·personality 시설의 존재와 실제 stack unwinding 안전성은 별개이며 throw/catch runtime 시험은 NOT_RUN이다(`exception_abi.json`).

## 11. 객체 Layout·Inline 및 Compile Fixture

V2의10타입 sizeof/alignof/member 관측과 selected Contact/core/Bullet offsets는 기존 근거로 재사용했다. 이번에는 ShapeNode의 actual table offset-to-top/secondary pointers, destructor의 vptr 재설정·멤버 정리 offset, Node delete/this-thunk를 추가로 살폈다. 설치 full member layout·alignment·모든 inline 접근은 여전히 UNKNOWN이다. 원 설치 debug/buildinfo는 확보하지 못했다.

새 `tests/lifetime.cpp`는 extracted matching packaged core headers + source Bullet fallback(A-header), B/C source/config로 **object compile만** 수행했다. delete base pointer, dynamic_cast<void*>, ShapeNode→ShapeFrame upcast를 코드로 만들었으나 실행하지 않았다. 세 arm sizeof[1664,16,48]와 생성 disassembly가 일치한다. 현재 시스템 DART dev header는 미설치이므로 A-header를 설치 binary type telemetry로 표현하지 않는다.

## 12. 신규 테스트·최초 실패

최종 신규 **16 PASS**. 정확한67 mapping, identity 보수성/AP, destructor/thunk, RTTI, 실제 callsite, FDE/LSDA, compile-only lifetime, ownership, ET_REL section addressing, relocation swap·미지원 relocation, 잘못된 ELF offset/symbol index, EH signed encoding·truncation을 검사했다.

최초 신규는 **15 PASS/1 FAIL**이었다. 미지원 EH application 인코딩을 검사하려고 빈 입력을 줘, parser가 먼저 올바른 truncation 오류를 반환했는데 테스트가 다른 오류를 기대했다. 완전한8byte 입력으로 미지원 application을 독립 검사하도록 fixture를 수정했다. 별도의 truncation/잘못된 offset/relocation 거부 검사는 유지했다. parser 및 production 판단 기준은 바꾸지 않았고 `work/new-initial.xml/.log`를 보존했다. 최종 결과만 남겨 최초 실패를 숨기지 않는다.

## 13. 기존 회귀·Loader

이번 재실행 V2 **13**, V1 **12**, Native **45**, 프로젝트 offline regression **108 PASS**. 신규16 포함 **194 distinct PASS**, 최종 failure/error/skip0. 과거178을 더하지 않았다. Native source hash·금지 호출을 재검토했고 원래 regression runtime fence를 적용했다. Native synthetic algebra와 새 fixture의 compile-only 범위는 서로 다르다.

Loader는 Gazebo/Bullet×A/B/C 및 optional IPOPT/NLOPT/ODE×B/C **12회**, undefined/error0. Gazebo252/Bullet53 DART import 누락0을 새 ELF 추출로 확인했다. B/C core/external/ODE와 명시적으로 유지한 설치 Bullet 구성을 기록했다. trusted glibc trace/relocation만 수행하며 plugin init/dlopen/entry는 호출하지 않았다. system IFUNC resolver 가능성은 구분한다. Gazebo/World::step/Stage B/full DART suite/대상 객체 생성·삭제/예외 runtime은 NOT_RUN이다.

## 14. Production/Evidence 보존

새 manifest는 V2 이전 explicit 보존 목록과 V2의 전체 reports/scripts/tests/work까지 새 hash로 고정했다. 이번 **30,188개 파일 변경0**, main HEAD/status 보존을 확인했으며 결과는 `integrity.json`에 기록한다. raw manifest/disassembly/FDE/최초 실패 로그는 새 work에서 보존하며 Git 제외다. 기존 V1/V2 파일·main 코드/evidence를 덮어쓰지 않았다. 시스템 패키지·DART·Physics/SDF·Loader 전역 설정·Solver·Capture/Clock 기준 변경은 없다.

## 15. 해결·축소된 위험

67개를49개 실제 target으로 중복 해소하고 B/C67 local identity와 DWARF source를 직접 연결했다. 설치48개는 제한적인 이름 추론이 가능해졌고19개는 후보만 남겨 미해석으로 유지했다. secondary AP·D0/D1·this thunk와 실제 소비 callsite를 구분했고, selected Node deletion·Bullet sized delete 및 실제 FDE/LSDA 경계를 확보했다. 기존 ‘이름 없는 주소67개’에서 추적 가능한 partial 계약으로 발전했지만 설치 symbol 복구나 전체 ABI 인증은 아니다.

## 16. 남은 위험

primary ShapeNode D1 slot18, EntityNode/Jacobian 내부 local callee·cold path, 설치 full layout/compiler ABI, 전체 간접 소비 graph, Cross-Module owner lifetime 및 LSDA cleanup/catch 의미가 남는다. 계측 OFF에도 진단 entry/getDimension/once/TLS가 있고 ON은 추가 metadata virtual call/global recorder/thread·allocator/FP/cache/flush 위험이 있다. OFF 동일 실행·ON 중립성을 선언하지 않는다. 미확인 항목은 HIGH이며, loader·보존의 정의된 offline 범위만 LOW다(`risk_assessment.json`).

## 17. Host Runtime 진입 조건·최종 판정

**SHAPENODE_BOUNDARY_PARTIALLY_VERIFIED**, Host **NOT_READY**. 명백한 ABI 불일치나 실제 위험한 해제 실패를 관측한 것은 아니지만 핵심 complete-dtor/ownership/EH 위험을 확정하지 못했다.

최소 조건: (1) primary D1 및 실제 쓰는 D0/custom-deleter edge를 matching debug/symbol map 또는 충분한 disassembly로 보완하거나 항목별 잔여 위험을 명시적으로 수용, (2) 고정한 library closure/hash와 C++ runtime allocator 경계를 검증, (3) 별도 승인될 비물리 lifetime/cast/unwind 시험 계획을 준비, (4) Trace owner/quiescent·capacity/overflow·metadata·flush/time mapping과 기존 Clock/Capture 기준을 명시, (5) 별도 사용자 실행 승인을 받는다.

격리 subprocess/sanitizer·명시적 객체 수명/예외 주입 계획은 향후 위험 탐지에 도움이 될 수 있으나 ABI UB나 계측 오염을 이미 통제했다는 증거는 아니다. 짧은 물리 실행으로 미해결 ABI를 건너뛰지 않는다. 이번에는 해당 runtime·예외 시험도 수행하지 않았다.

## 18. 자동 Git 게시

새 V3 scripts/tests/경량 reports와 handoff만 승인 실험 branch에 선택한다. staged diff·whitespace·민감정보·ownership을 확인하고 commit/push 및 원격 일치를 검증한다. 최종 hash·push 영수증은 로컬 `reports/git_publication.json`에 기록하며 자기 hash를 넣기 위한 재귀 commit은 만들지 않는다. main 직접 게시/병합·force push는 없다. 원시 work/바이너리/기존 evidence는 게시하지 않는다.

## 19. 다음 최소 작업·재현

가장 먼저 **ShapeNode primary D1 slot18의 내부 base cleanup/callee와 Node D0→D1 경계**, 이어 Bullet custom-deleter·EH cleanup의 critical edge를 좁혀 설치본 근거를 보완한다. 그 후 비물리 수명/cast/unwind 검증 계획을 별도 검토한다. 자동으로 Host·World::step·Stage B로 진행하지 않는다.

재현 명령과 입력 의존성은 `reports/reproduction.md`. 기존 build·추출 헤더·main의 미커밋 regression 입력과 새 raw work는 로컬이며 Git만으로 다른 기기에 전달되지 않는다. **NOT_RUNTIME_VERIFIED / Stage B BLOCKED 유지.**
