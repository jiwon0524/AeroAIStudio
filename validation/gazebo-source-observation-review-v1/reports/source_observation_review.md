# Gazebo 소스 수준 관측 경로 검토

**UNRESOLVED / NOT_EXECUTION_READY / Stage B BLOCKED**.
시작 HEAD `60eabba9a1a384d85b56697e33c294b46d83bffa`, 브랜치 `experiment/dart-internal-trace`, tracked/staged 변경 없음을 확인했다. 이번 범위는 기존 로컬 자료의 읽기 전용 조사와 설계다. 소스 수정·빌드·테스트 실행·대상 로딩·서비스·marker·설치·다운로드는 하지 않았다. 새 문서와 인계 기록만 작성했다. 위험 수용은 결정하지 않았다.

## 결론과 근거 범위

|차단|판정|해소에 필요한 경로|
|---|---|---|
|Sim 소유 detector와 구현 provider 연결|미해결|동일 engine/world를 따라가는 typed source hook, detector identity 및 실제 메서드 구현 모듈 관측|
|첫 Step 전 iteration0/time0|미해결|runner의 첫 카운터/시간 진행 이전 초기화 전용 경로와 GO 장벽; 현재 Update 내부 gap만으로는 부족|

정확한 설치본 소스 라인에 관측 코드를 넣을 수 있다고 인증할 자료는 확보하지 못했다. 아래 함수명·ELF 주소는 기존 공개 API 감사의 정적 근거를 재사용하며, 새로 확인된 소스 라인으로 표시하지 않는다. 자료 부재는 조사한 로컬 범위에 한정한다. 기존 launcher/adapter/계약/승인안의 서비스·marker 이전 거부를 보존한다. 실행 승인 명령은 새로 발행하지 않는다.

## 설치본과 확보 자료 대조

패키지 및 source version은 `gz-sim8 8.15.0-1~noble`, `gz-physics7 7.8.0-1~noble`, `dart 6.13.2+ds1-1~osrf2~noble`이다. Physics system ELF의 소유 패키지는 `libgz-sim8:amd64`이고, DART 플러그인은 `libgz-physics7-dartsim:amd64`다. DART Core/Bullet/ODE/External은 `libdart-core+collisions+odelcpsolver6.13:amd64`에 속한다.

|ELF 역할|설치 Build ID|
|---|---|
|sim_core|`4785a0f397c1a9fea8eea659d89ccb559d82360f`|
|sim_physics_system|`d84fdca46ee5b0a981496fde744460e1b1d9deaa`|
|sim_cli_library|`3796557281a8e660befdccee64f5368d5175fc1a`|
|physics_dart_plugin|`c53e1a304ceb0f0dac85ff0e4872d0ffc50a28ac`|
|physics_feature_core|`4e60105d86d50ee9e394f6c461411e3cba5eeec1`|
|dart_core|`071aa565b343db80e31aae393aadaed33c7adb46`|
|dart_bullet|`8bda73145d9c6cc97d6faff5895c2ce1aa091f6f`|
|dart_ode|`2cbacdc0e4014e0ee69c4deeacd2d088d564599e`|
|dart_external|`abba8be3e710b1a505116d4bada0803f8bd49398`|

정확한 경로·SHA-256·패키지 소유·debuglink/altlink 후보는 [material_inventory.json](material_inventory.json)에 고정했다. 9개 ELF 모두 embedded `.debug_info`와 `.symtab`가 없으며 해당 Build-ID/debuglink/DWZ 후보 경로에 일치 디버그 파일이 없었다. unrelated debug 파일의 존재를 대응 심볼 확보로 취급하지 않았다.

확보된 DART `.dsc`의 SHA-256은 `15e661dc0b2ac663ae9466bf34347aef87e94b667d62a267f482f5294160b6b3`다. 대응 Debian tar는 DSC 해시와 일치하고 로컬 baseline-source의 packaging 파일 50개와 일치했다. 이는 패키징 부분의 일치이며 전체 upstream payload와 설치 빌드의 연결 증명이 아니다. DSC가 요구하는 `dart_6.13.2+ds1.orig.tar.xz`(10968976 bytes, SHA-256 `b900820b71463476463b9daeb31e81c74ebf59bd95139b7f833f5f6bb9b8058e`)는 조사 범위에서 확보하지 못했다.

로컬 baseline/trace Core에는 DWARF가 있지만 Build ID는 각각 `5b20c27ee40538cedd07931b3f703fadd3adc98d`, `a93979d2a4c513bc4e647e36571fad6988432f21`로 설치본과 다르다. 해당 DWARF를 설치본 타입/라인/주소에 적용할 수 없다. 기존 runtime-reference Core/External/Bullet ELF는 설치본과 SHA가 같지만 stripped 바이너리의 일치일 뿐 소스·디버그 일치는 아니다.

worktree validation, 원본 main validation, `/usr/src`에서 Gazebo Physics/SimulationRunner 및 gz-physics DART 구현 소스와 source/buildinfo 후보를 조사했다. 대응 Gazebo 소스·buildinfo/changes를 확인하지 못했다. 기존 remote404/debug 탐색과 Ubuntu의 다른 DART 버전 후보는 과거 보고 결과이며 이번에 네트워크로 재확인하지 않았다. 다른 패키지 버전의 ddeb는 대체 증거가 아니다.

## 함수·호출 지점과 조건부 계측 설계

### 동일 detector와 provider

기존 감사에서 설치 DART 플러그인의 `WorldFeatures::GetWorldCollisionDetector`는 `0x23c1f9`에서 `World::getConstraintSolver`, `0x23c205`에서 `ConstraintSolver::getCollisionDetector`를 호출한다. 이후 `0x23c211`의 virtual call은 검증되지 않은 슬롯 해석으로 메서드명을 붙이지 않았다. 이 경로는 실제 detector에 접근하는 근거지만 공개 결과는 문자열이고, 현재 harness에는 Sim이 소유한 동일 world/engine으로 연결되는 안전한 handle이 없다.

대응 소스가 확인되면 해당 getter 또는 인접한 명시적 diagnostic feature에서 **Sim의 기존 world identity → 그 world의 solver → 소유 중인 detector**를 typed 코드로 전달하도록 설계한다. 별도 World/engine/detector 생성은 금지한다. owner를 유지한 채 객체 상관 식별자, 실제 타입, provider 증거를 같은 스냅샷에 기록한다. 설정 문자열이나 mapping 목록만으로 detector를 판정하지 않는다.

`dladdr(&typeid(*detector))`가 식별하는 것은 RTTI 모듈이다. 이것만으로 실제 collision 알고리즘 메서드의 구현 ELF가 입증되지는 않는다. wrapper와 base 알고리즘이 다른 모듈일 수도 있다. 정확한 구현 증거가 필요하면 실제 선택 객체에서 호출되는 안전한 비스텝 query 메서드의 소스 진입점에서 typed `this` 상관관계와 module-local non-interposable anchor 주소를 기록하고, 호스트가 그 주소의 실제 mapping/파일 identity/SHA/Build ID를 대조하도록 설계한다. 이 query가 Step·collision 진행·detector 교체를 유발하지 않는지는 소스 감사가 선행되어야 한다. query 관측은 그 메서드 provider의 증거이고, 별도 collide 메서드 실행을 입증하지 않는다. 알고리즘 provider까지 주장하려면 상속/위임 소스와 대응 ELF 연결을 추가로 확인한다. RTTI만 수집되면 code provider는 UNVERIFIED로 남긴다.

필요에 따라 gz DART wrapper 및 선택된 DART adapter(Bullet이면 collision-bullet, FCL이면 해당 Core 구현 등)의 source hook가 추가된다. vtable 오프셋, private layout 추정, 가상 멤버 포인터를 코드 주소로 억지 변환하는 방식은 사용하지 않는다. 현재 활성 detector/provider는 여전히 UNVERIFIED다.

### 초기화 후, 첫 반복 및 Step 전

기존 설치 Physics `Update`의 확인된 호출은 `0xb850c CreatePhysicsEntities → 0xb8518 UpdatePhysics → 0xb8525 paused 분기 → 0xb853b Step`이고 CreatePhysicsEntities의 `0xb11b4`가 CreateWorldEntities를 호출한다. 이 gap는 **소스 계측 후보 위치**일 뿐 iteration0 보장 지점이 아니다. 공개 runner iteration 진입 이후의 Update에서 대기하면 첫 iteration=1 문제를 해소하지 못한다.

필요한 설계는 대응 `SimulationRunner` 소스에서 첫 iteration/time 진행 전에 pending system Configure와 engine/world/entity 생성 및 초기 detector 선택이 완료되는 초기화 전용 phase를 분리하고, 그 phase 끝에 READY/GO 장벽을 두는 것이다. Physics Configure/CreatePhysicsEntities/CreateWorldEntities와 초기 설정 부분은 후보지만, 실제 함수·라인·최소 diff는 대응 소스 부재로 **미확정**이다. UpdatePhysics 전체를 초기화로 재사용하지 않는다. control/force 적용이나 solver 작업이 섞이는지 감사해야 한다. 전체 Configure 간접 호출과 asynchronous 경로도 감사 대상이다.

통과에 필요한 소스 증명은 (1) 같은 Sim 소유 engine/world/detector가 완성됨 (2) runner iteration/time와 DART world frame/time 실측이 모두0 (3) 모든 Step 진입이 단일 GO 장벽 뒤에 있음 (4) 대기 중 다른 worker/queued command가 world·detector를 진행/교체하지 못함이다. owner thread에서 GO 전후 두 번 관측하고 변경·누락·EOF·기한 초과는 거부한다. iteration/time 초기화 재설정이나 첫 iteration 제외 계산은 금지한다. paused RunOnce를 호출하지 않는다. 기존 Configure/PreUpdate/PostUpdate의 공개 계약만으로 이 요건은 아직 입증되지 않는다.

## 별도 빌드의 최소 범위와 증거 한계

소스 확보 후 예상되는 최소 변경 범위는 Sim core의 initialization/runner 장벽, Physics system의 동일 engine/world diagnostic 연결, gz-physics DART plugin의 typed detector 관측이다. provider 메서드 직접 관측에 필요할 때만 선택된 DART adapter를 추가한다. 실제 CMake target명과 필요한 전이 빌드는 소스 감사 후 확정해야 하며 현 단계에서 한 파일 수정으로 충분하다고 판정하지 않는다. harness/observer 연결과 evidence supervisor도 별도 검증 대상이다.

이는 설치 경로를 변경하지 않는 별도 실험 빌드로 설계한다. 변경 source hash, compiler/flags/dependencies, 새 ELF SHA/Build ID, closure/mount, 비실행 검증, 새로운 one-shot과 별도 실행 승인이 필요하다. 현재 자원 한도나 과거 성공을 자동 승계하지 않는다. 새 초기화 phase는 순서/수명/thread/플러그인 ABI 영향을 재검증해야 한다.

**계측 결과는 설치본 원본의 실행 증거로 인정할 수 없다.** 변경된 ELF/초기화 순서를 가진 별도 검증 대상이다. matching debug 자료는 원본의 정적 라인·타입·호출 경로 확인에 쓰이며 runtime hook를 만들어주거나 실행을 승인하지 않는다. 원본 소스와 무계측 재빌드가 bit-identical한 경우에만 그 동일 파일의 재현성을 별도 입증할 수 있고, 계측 ELF는 여전히 다른 대상이다. 설치 원본과 과거 marker/증거는 읽기 전용으로 보존한다.

## 확보해야 할 자료와 이유

1. `gz-sim8 8.15.0-1~noble`: 원본 `.dsc`, 그 Checksums에 지정된 upstream/debian archives와 patches/revision, 원본 `.buildinfo`/`.changes` 및 대응 .deb 해시·빌드 로그/flags/dependency manifest. 위 Sim core/Physics/CLI Build ID에 맞는 debug와 DWZ supplementary 파일. 이유: Configure/runner 카운터 진행/Physics 초기화 및 Step dominance를 정확한 소스에 연결해야 한다.
2. `gz-physics7 7.8.0-1~noble`: 동일한 source/build provenance 묶음과 DART plugin `c53e1a...`, feature core `4e6010...`의 matching debug 및 DWZ. 이유: Sim world identity가 실제 DART world/solver/detector로 연결되는 코드와 wrapper/base 구현을 검증해야 한다.
3. `dart 6.13.2+ds1-1~osrf2~noble`: 위 누락 orig archive 및 original buildinfo/changes/log; inventory의 Core/Bullet/ODE/External 각 Build ID에 대응하는 debug와 DWZ. 이유: 소유·getter·query의 무스텝 성질과 실제 provider 구현을 검증해야 한다.

가능한 debug 패키지명(libgz-sim8-dbgsym, libgz-physics7-dartsim-dbgsym, merged DART dbgsym 등)은 검색 후보이지 배포 존재 확인이 아니다. 자료를 확보하면 Build ID, debuglink CRC/altlink identity, DWARF 소스 경로·checksum, 패치 적용본과 빌드 manifest를 함께 대조해야 한다. 같은 버전 문자열이나 upstream tag만으로 일치를 선언하지 않는다. 이번에는 자료 취득·설치·재빌드를 수행하지 않았다.

## 보존·다음 단계

조사 입력과 기존 marker 해시는 inventory에 기록했다. 검토 종료 시 선택된 입력/설치 ELF 해시, main HEAD/status, 기존 Gazebo runtime/attempt 부재를 다시 대조한다. 이는 선택 범위의 무결성 확인이며 전체 ignored 파일의 전수 비교를 새로 수행한 것은 아니다. 문서 JSON/링크/diff만 검사하고 과거 compile/mock PASS를 재실행 결과로 표시하지 않는다.

Bullet 정상 수명·개별 소멸자·allocator·C 예외 해제 위험은 NOT_ACCEPTED, 개별 소멸자는 NOT_OBSERVED, allocator는 NOT_MEASURED를 유지한다. 비교 arm/D trace의 조건부 비적용은 원 설치본 전용/no-local-trace/no-recorder/no-neutrality-claim와 실제 closure 확인을 전제로 한 이전 검토다. 계측 빌드로 범위가 바뀌면 다시 검토해야 하며 자동 적용하지 않는다. 다음 최소 작업은 위 provenance 자료의 확보·대조를 별도 허용 범위에서 진행하는 것이다. 실행·빌드·위험 수용은 이번 결과에서 승인되지 않는다. Stage B BLOCKED를 유지하고 보고 후 멈춘다.
