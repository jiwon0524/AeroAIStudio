# DART Destructor Cleanup Boundary Verification V4

## 1. 기존 V3·규칙·Git 확인

**DESTRUCTOR_BOUNDARY_PARTIALLY_VERIFIED / Host: NEEDS_TARGETED_EVIDENCE / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.**

V3 final/verdict/shapenode_slots/destructor_contract/ownership_boundary/exception_abi를 읽고194 PASS, loader12 오류0, 보존30188 변경0, 설치67슬롯 0 IDENTIFIED/48 INFERRED/19 UNRESOLVED, B/C67 local identities 및 설치 full layout·lifetime/EH 중립성 한계를 대조했다. 이 수치는 과거 결과다.

승인 worktree `/tmp/AeroAIStudio-dart-internal-trace`, branch experiment/dart-internal-trace, 시작 HEAD a7a7b32b9aade588a0f134637b46b4211a973cc4 clean 및 원격 일치, main46134c6을 확인했다. main 기존 dirty/evidence를 수정·stage하지 않았다. 초기 handoff REVIEW_REQUIRED는 c22f947 snapshot과 게시 a7a7b32 HEAD 차이 하나였고 parent/30파일/evidence hash로 예상 전이를 확인했다. helper 자체를 초기 MATCH로 보고하지 않는다. 지침·원본은 보존했고 추가 validation AGENTS는 없었다.

## 2. 슬롯18의 위치·경계·정체

|항목|A 설치|B Baseline|C Trace|
|---|---|---|---|
|slot18 ELF VA|0x2f0b70|0x2f0f60|0x2f0fd0|
|FDE 바이트 수|997|997|997|
|table offset / primary address point|144/144|144/144|144/144|
|실제 이름|stripped·미복구|ShapeNodeD1Ev 로컬 심볼|ShapeNodeD1Ev 로컬 심볼|
|V4 정체|**INFERRED D1**|IDENTIFIED D1|IDENTIFIED D1|

table index18은 primary AP에서0번째 complete destructor word이며 index19의 deleting destructor와 구분한다. 원시 entry/RELA·sym aliases·FDE·SHA/Build ID와 bounded assembly는 `slot18_analysis.json`에 연결했다. 주소는 ELF link VA이며 실행 ASLR 주소가 아니다.

V3에서 미해석한 이유는 두 private helper(CompositeNode base cleanup 후보 및 RB-tree erase 후보)의 recursive/cold/간접 경로를 끝까지 증명하지 못했기 때문이다. 이번에는 무한 helper 추적 대신 AP 역할, D0의 실제 call, complete-object vptr 재설정, 알려진 base cleanup 순서와997byte 정규화 body를 함께 확인해 **이름 정체를 제한적으로 추론**했다. Baseline/Trace 이름이 같다는 이유만으로 IDENTIFIED로 승격하지 않았다.

## 3. D0/D1/D2와 Node 경계

A ShapeNode primary D0는0x2f1020이며 **0x2f1030에서 slot18 진입 주소를 직접 call**, 이후 RDI를 원 객체 주소로 복구하고 RSI=0x680(1664)으로 sized delete에 tail jump한다.

A Node-subobject를 위한 ShapeNode D0 thunk는0x2f1280이다. **0x2f1289 `lea -0x90(%rdi),%rbx`**, RDI로 전달 후0x2f1297에서0x2f0b70을 call하고 size1664로 delete한다. 이는 Node subobject의 this−144 보정이다. 설치 core NodeDestructor wrapper의 vptr+8 dispatch 및 동적 타입이 ShapeNode인 조건과 연결된다.

**일반적인 Node D0→Node D1 관계를 가정하지 않는다.** B/C에서 전용 Node D2는 관측되지만 Node D0/D1과 ShapeNode D2의 독립 정의는 이번 ELF inventory에서 관측되지 않았다. inline·alias·abstract/base 최적화 가능성이 있어 심볼 부재를 ABI 누락으로 판정하지 않는다. 설치 A에는 해당 local variant 이름이 없고, 선택된 dynamic delete 경로는 조정된 ShapeNode D0→추론 D1이다(`destructor_call_graph.json`).

호출 규약은 x86_64 SysV의 this=RDI, sized delete의 size=RSI 및 해당 base destructor의 숨은 VTT 인자=RSI를 실제 코드·현재 compiler ABI와 연결했다. 설치 full debug 타입 기반 전체 signature 인증은 아니다.

## 4. Base·Member Cleanup 순서

슬롯18은 complete-object vptr들을 재설정하고 첫 private base cleanup helper를 호출한 뒤 VTT/vbase 관련 포인터를 복원한다. 알려진 호출 순서는 **FixedFrame D2 → Frame D2 → Entity D2 → Subject D1 tail call**이며 그 사이 컨테이너·aspect/member 정리와 일부 indirect virtual 삭제가 있다. Frame this+0x1f0, Entity+0x348, Subject+0x4a8 등 관측 offset은 bounded assembly에 남겼다.

A의0x2e8cb0 helper에 objdump가 붙인 `ShapeFrameD2+0x240`은 nearest label이며 실제 함수 정체를 뜻하지 않는다. B/C의 CompositeNode D2 후보와 비교한393 instruction body에는 load scheduling 차이가 있어 전체 동일성을 선언하지 않는다. 다른176 instruction RB-tree helper의 정규화 형태는 일치하지만 nested callback 의미는 미확정이다.

D1 내부의 size16·48·가변 컨테이너 delete를 complete object 해제로 혼동하지 않는다. 전체1664바이트의 deleting 단계는 D0에서 관측된다. Base/Member 전체 의미·예외 중 정리 순서는 UNKNOWN이다.

## 5. Bullet/Core 소유권

소스상 Bullet factory가 new BulletCollisionObject를 unique_ptr<CollisionObject>로 넘기고 core manager가 release 후 custom-deleter shared_ptr로 감싼다. core deleter의 notify callback 뒤 base pointer delete가 virtual derived D0와 연결된다. Bullet shape/map callback의 detector/manager가 관리 객체·custom deleter보다 오래 살아야 한다.

선택된 실제 D0/allocator 경계와 소스상의 소유 설계를 구분했다. 등록 global/static과 Trace State/TLS/once_flag의 shutdown 순서, 복사/이동·동시 해제·dangling/double-free는 runtime 미검증이다. 명백한 allocator 계약 충돌이나 실제 삭제 실패를 발견한 것은 아니다(`ownership_contract.json`).

## 6. Sized Delete·Allocator ABI

설치 BulletCollisionObject D0의 size48, BulletCollisionGroup D0의 size368을 다시 읽었다. Detector D0는88이며, 세 arm의 새 compile-only fixture는 ShapeNode1664/align16, BulletObject48/Group368을 산출했다. 이것은 현재 matching header 근거이며 설치 full layout telemetry는 아니다.

실제 D0가 versioned `_ZdlPvm` sized operator delete로 연결되고 `_Znwm`/delete 관련 ELF import/version 요구를 기록했다. RDI 포인터·RSI size 호출 형태와 현재 closure의 C++ runtime 선택을 확인했다. 사용자 interposition, 다른 allocator hook, Bullet nested aligned allocations와 전체 memory lifetime까지 인증하지 않는다. 단순 크기 일치만으로 안전 판정을 만들지 않았다.

## 7. Exception/Unwinding Cleanup

선택된 A/B/C slot18·primary D0·Node-adjusted D0의 FDE에는 LSDA가 없다. 이는 **해당 FDE에 LSDA가 없다는 사실**이며 no-throw·terminate·동등한 unwinding 증명이 아니다. Personality/CIE와 versioned C++/unwind 시설도 따로 연결했다.

설치 Bullet factory createCollisionObject의 LSDA를 callsite/action 수준으로 해석했다.4개 보호 범위 중3개에 cleanup landing pad가 있고1개는 landing pad가 없다. Constructor call **0x2024d→LP0x20353→cold0x12c1c** 경로는 size48 sized delete, 공유 참조 정리 후보 호출, `_Unwind_Resume`로 이어진다. new call **0x20239→LP0x2035f→0x12c29**는 성공하지 못한 객체 storage를 다시 delete하지 않고 공유 참조 정리로 이어지는 경로다. claim 단계의 실패 경로는0x2036b→0x12c4e다.

cold FDE 한 개만 유한하게 추적했다. Local helper0x17b50과 indirect callback의 정확한 runtime 소유/정리 의미·catch typeinfo·모든 cleanup 경로·누락/이중 해제 가능성은 UNKNOWN이다. LSDA action filter를 해석했지만 실제 throw/catch 또는 대상 객체 삭제는 실행하지 않았다(`exception_cleanup.json`).

## 8. 소비자 관련성

설치 NodeDestructor wrapper는 실제 vptr+8로 동적 deleting destructor를 호출하므로, ShapeNode Node-subobject일 때 slot70→slot18은 INDIRECTLY_REACHABLE다. 일반 Node 인스턴스의 독립 D0/D1 체인이라고 부르지 않는다.

Gazebo V3 관측 convertContact site는 ShapeFrame slot107이며 destructor18 직접 호출은 해당 site에서 NOT_OBSERVED다. 이후 cleanup 미사용을 의미하지 않는다. Bullet/Core custom-deleter 경계도 INDIRECTLY_REACHABLE로 분류했으나 완전 whole-program/runtime callgraph는 아니다(`consumer_reachability.json`).

## 9. ABI 차이와 구현 차이·반복 종료

슬롯18의 A/B/C 주소·RIP data 위치는 다르지만 정규화 body와 유한 call/this 조정·base 순서가 일치했다. Helper의 load scheduling, LTO alias, stripped/local symbol, DWARF 유무를 ABI 파손과 구분했다. 반대로 이름·길이·부분 기계어만으로 전체 type/return/lifetime 계약을 인증하지 않는다.

`analysis_stop.json`: 선택된 Node-adjusted D0 직접 edge와 sized delete ABI 패턴은 A 종료조건에 도달했다. 설치 full identity/type 및 중첩 cleanup semantics는 **C 종료조건**이다. 같은19개 슬롯이나 private helper를 반복 추적하지 않으며 새 정적 단계를 자동 추가하지 않는다. 직접적인 B 조건(명백한 ABI 불일치)은 발견하지 못했다.

## 10. 신규 테스트

최종 신규 **12 PASS**, failure/error/skip0. slot18 AP/FDE/추론 보수성, 실제 D0 call/this−144, base cleanup 순서,1664/48/368 sized delete, compile-only fixture, LSDA callsite/action/cold cleanup, no-LSDA 한계, LPStart 처리·truncation/cycle/type filter 거부, 유한 종료 정책을 검사했다.

최초 신규는11 PASS/1 FAIL이었다. 테스트가 `$0x90` immediate를 기대했지만 실제 조정은 LEA −0x90와 MOV였다. 정확한 두 instruction과 −144 의미를 검사하도록 fixture 기대를 수정했다. production/ABI 기준을 낮추거나 parser를 바꾸지 않았고 `work/new-initial.xml/.log`와 최종 로그를 함께 보존했다.

## 11. 회귀·Loader와 NOT_RUN

이번 재실행 **V3 16 + V2 13 + V1 12 + 프로젝트 offline108 =149 PASS**. 신규12 포함 **161 distinct PASS**, 최종 failure/error/skip0이다. **Native45개는 NOT_RUN**. World 생성자, Skeleton/BodyNode/ShapeNode 및 실제 constraint/solver 생성이 V4의 객체 생성·삭제 금지와 충돌한다는 source audit를 기록했다. 과거194를 이번 통과로 더하지 않았다. 테스트 수 감소는 범위 제한이며 회귀 실패가 아니다.

정적/compile-only 회귀와 프로젝트 synthetic record/temp-file 회귀만 runtime fence 아래 실행했다. 새 deletion fixture의 delete 표현은 object code만 생성하고 호출하지 않았다. Loader12회는 trusted glibc trace relocation, undefined/error0, Gazebo252/Bullet53 import 누락0이다. init array/plugin entry/dlopen은 호출하지 않으며 IFUNC resolver 가능성은 구분한다. Gazebo/World::step/실제 DART 객체 생성·삭제/예외 runtime/Stage B는 NOT_RUN이다.

## 12. Evidence·Production 무결성

새 manifest는 V3 이전 보존 목록과 V3 전체 reports/scripts/tests/work를 새 hash로 고정했다. 이번 **30,673개 파일 변경0**, main HEAD/status 보존을 확인했다(`integrity.json`). 기존 V1~V3 코드·기록·evidence는 읽기 전용으로 유지했다. 시스템 패키지·DART 교체·전역 loader·Physics/SDF·solver·Clock/Capture 기준 변경은 없다. raw ELF/assembly/FDE/최초 실패/manifests는 새 work에만 두고 Git 제외다.

## 13. 해결·축소된 위험

슬롯18을 모호한 local address에서 **다중 정적 근거의 INFERRED D1**로 좁혔다. 정확한 primary/Node-adjusted D0의 call 및 this 보정, base/member 단계와 전체 sized delete를 분리했다. Bullet constructor-failure의 실제 cold cleanup까지 한 단계 연결해 deallocation/Unwind_Resume 경계를 확인했다. 일반 Node D0→D1 가정과 nearest-symbol 오독을 제거했다.

## 14. 남은 위험

설치 원본 symbol/type 및 전체 member layout, helper·indirect callback·allocator lifetime, 모든 EH action/catch/cleanup 의미, shutdown/concurrency는 남는다. OFF 추가 진입/getDimension/once/TLS와 ON 추가 metadata·global recorder·thread/FP/cache/flush의 중립성은 미검증이다. 미확인 위험은 HIGH로 유지한다. 확인한 selected static 경계와 loader/보존의 범위를 넘어 LOW로 확장하지 않는다(`risk_assessment.json`).

## 15. Host 진입 판단

**NEEDS_TARGETED_EVIDENCE**. 명백한 ABI/삭제 불일치로 HOST_BLOCKED를 선언할 근거는 없지만 READY_FOR_SEPARATE_HOST_APPROVAL로 올릴 증거도 충분하지 않다. 실제 Host는 실행하지 않는다.

다음 최소 방법은 matching Build-ID debug/symbol 자료 또는 **별도 승인될 비물리 객체 수명·allocator/unwind probe**다. 객체 생성·삭제 자체가 필요하므로 이번 V4 권한으로 실행할 수 없다. `targeted_evidence_plan.md`에 고정 closure/A 대조/B/Trace OFF, 유한 객체 소유/해제와 예외 경계 관측, 미계측 sanitizer 한계·종료 기준 초안을 남겼다. subprocess·짧은 실행만으로 ABI UB나 계측 오염을 통제했다고 하지 않는다.

## 16. 다음 최소 작업

무한 정적 재분석을 멈춘다. `targeted_evidence_plan.md`의 비물리 probe 계획을 검토하거나 정확한 원본 debug/symbol 자료를 제공받는 것이 다음 최소 작업이다. 별도 승인 전 probe/Host/World::step/Stage B를 실행하지 않는다. 원본과 다른 symbol 자료를 설치 사실로 전파하지 않는다.

## 17. Git Commit·Push·재현

신규 V4 scripts/tests/경량 reports와 handoff만 승인 실험 branch에 명시적으로 선택한다. staged diff/whitespace/민감정보/ownership 검토 후 commit/push 및 원격 SHA 일치를 확인한다. 최종 commit·push 영수증은 로컬 `reports/git_publication.json`과 최종 응답을 따른다. 자기 SHA를 넣기 위한 재귀 commit은 하지 않는다. main merge/push·force push는 없다.

재현은 `reports/reproduction.md`. 기존 isolated source/build/추출 헤더·main의 미커밋 regression 입력 및 새 work/raw 자료는 로컬이며 Git만으로 다른 기기에 전달되지 않는다. **DESTRUCTOR_BOUNDARY_PARTIALLY_VERIFIED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED** 유지.
