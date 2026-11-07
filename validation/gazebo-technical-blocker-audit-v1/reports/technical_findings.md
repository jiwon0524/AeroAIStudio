# Gazebo 남은 기술 차단 감사

**미해결 / 실행 불가 / Stage B BLOCKED**.
시작 HEAD `e811d8fe44cfeb777cf0486d5e0d1251133e6817`, experiment/dart-internal-trace clean을 확인했다. 사용자 지시에 따라 설치 공개 헤더·패키지 파일 목록·고정 ELF를 읽고 compile/link와 비실행 검사를 수행했다. private ABI가 필요해지는 경계에서 runtime 구현을 중단했다. 이전 server/observer/adapter/launcher/contract/승인안은 변경하지 않았다.

## 항목별 판정

|요청|판정|확인 근거와 남은 차단|
|---|---|---|
|1. 실제 detector 객체와 구현 ELF 식별|**미해결**|실제 객체를 조회하는 내부 getter 경로는 확인했으나, Sim이 소유한 해당 engine/world handle·detector 객체를 공개 API로 전달받는 연결을 확보하지 못했다. 결과 문자열만으로 객체 provider를 확정하지 않음|
|2. iteration0/time0 초기화 관측|**미해결**|Physics Update 내 world 생성→갱신→Step 호출 경로와 paused 분기는 확인. 공개 initialization-only hook과 그 시점의 실제 world·detector 접근은 미확정. paused RunOnce는 iteration1이므로 사용하지 않음|
|3. 실제 실행 증거 수집 연결|**미해결·미연결**|1·2가 성립한 경우에만 연결하라는 조건을 충족하지 못했다. 기존 mock collector를 실제 수집으로 승격하거나 private 구조를 추정해 연결하지 않음|

모든 항목이 해결되지 않았으므로 실행 승인안은 갱신하지 않는다. launcher의 서비스·marker 이전 거부, adapter=false, trustedReady=false를 그대로 유지한다. 기술 차단을 사용자 위험 수용으로 대체하지 않는다.

## 1. 활성 detector와 provider 경로

### 확인된 공개 API

- `/usr/include/gz/sim8/gz/sim/Server.hh`: AddSystem/IterationCount 등은 공개되어 있지만 조사한 인터페이스에서 소유 중인 Physics engine/world/detector handle getter는 찾지 못했다. `ServerPrivate`와 `dataPtr`는 private다. 이름이 GetPhysicsEngine인 공개 getter 부재는 compile-time trait로도 확인했으나, 이 특정 trait만으로 가능한 모든 외부 API의 부재를 증명하지는 않는다.
- `SystemPluginPtr.hh`의 공개 Sim system 인터페이스는 System/Configure/PreUpdate/Update/PostUpdate다. 이는 active gz-physics EnginePtr를 넘겨주는 계약이 아니다.
- `components/Physics.hh`의 PhysicsCollisionDetector는 “name ... to be used”인 문자열 component다. PhysicsEnginePlugin도 문자열이다. 설정/선택 문자열은 객체 구현 provider의 직접 관측으로 사용하지 않는다.
- gz-physics `World.hh`와 `detail/World.hh`: 공개 GetCollisionDetector는 const std::string&를 반환하고 GetWorldCollisionDetector로 전달된다. 이 반환형은 컴파일 static_assert로 확인했다.

### 설정값 이상의 근거를 제공하는 getter는 존재

고정 설치 DART 플러그인의 `WorldFeatures::GetWorldCollisionDetector`를 정적으로 읽으면 다음 직접 call을 확인한다.

- `0x23c1f9`: `dart::simulation::World::getConstraintSolver()`
- `0x23c205`: `dart::constraint::ConstraintSolver::getCollisionDetector()`
- 그 뒤 `0x23c211`에 간접 virtual call이 있다. 이 간접 슬롯을 검증되지 않은 installed class layout으로 함수명에 억지 대응하지 않았다.

따라서 이 getter를 단순 SDF 설정 echo라고 단정하면 안 된다. 해당 implementation identity/world handle을 얻을 수 있다면 실제 constraint solver의 detector에 기반한 질의를 할 근거가 있다. 하지만 반환되는 것은 문자열이며, 현재 Sim adapter에는 그 **동일 인스턴스**의 engine/world handle·detector object pointer·실제 dispatch/vtable provider를 안전하게 얻는 연결이 없다.

별도 RequestEngine::From/새 DART World/Detector를 만들어 조사하는 것은 Sim이 사용하는 동일 객체를 관측하는 방법이 아니므로 하지 않았다. 이미 map된 Bullet/FCL/ODE ELF 중 하나를 type 문자열만 보고 provider로 선택하지도 않았다. dladdr는 유효하게 얻은 객체 dispatch 주소에 적용할 때 provider 정보를 줄 수 있지만, mapping 이름이나 독립 dlsym 결과만으로 활성 객체의 provider가 되지는 않는다. 그 유효한 주소를 얻는 부분이 현재 차단이다.

### private ABI 경계와 중단

`PhysicsPrivate::{CreatePhysicsEntities,CreateWorldEntities,...}`가 ELF에 export돼 있다는 사실은 public API/안정된 구조체 layout 계약이 아니다. 이 메서드를 직접 부르려면 Sim 소유 PhysicsPrivate 인스턴스와 내부 engine/entity map에 접근해야 한다. 조사한 설치 헤더에는 해당 구조 정의·공개 hook가 없다. `Server::dataPtr`나 Physics 내부 storage를 guessed offset으로 읽는 방식, private symbol 호출, reinterpret_cast, vtable patch/interposition은 구현하지 않았다.

설치 libgz-sim8-dev `8.15.0-1~noble`의 파일 목록에는 대응 Physics.cc/PhysicsPrivate source가 없고, 조사한 dev headers와 /usr/src에서 매칭 소스를 찾지 못했다. 보존 DART baseline 소스는 Gazebo Physics 시스템의 대응 소스가 아니다. 전체 Configure/private 간접 호출 그래프를 완전히 인증할 자료가 없으므로, “모든 가능한 구현에서 불가능”이라는 전역 결론 대신 **현재 고정 설치본·공개 표면에서 승인 가능한 연결을 확보하지 못함**으로 판정한다.

## 2. iteration0/time0와 초기화 위치

고정 Physics system ELF의 이름이 확인되는 call만 근거로 삼았다. 해당 ELF SHA와 Build-ID는 api_path_evidence.json에 고정돼 있으며 이전 준비 manifest SHA와 대조했다.

|호출 지점|정적 관측|
|---|---|
|Physics::Update `0xb850c`|PhysicsPrivate::CreatePhysicsEntities 호출|
|`0xb8518`|PhysicsPrivate::UpdatePhysics 호출|
|`0xb8525`|UpdateInfo의 public paused 필드에 대응하는 조건 분기|
|`0xb853b`|그 뒤 진행 경로에서 PhysicsPrivate::Step 호출|
|CreatePhysicsEntities `0xb11b4`|CreateWorldEntities 호출|

public UpdateInfo의 paused/iterations offset은 설치 Types.hh에 대한 static_assert로 확인했다. 이것은 공개 struct의 field 검증이며 PhysicsPrivate 객체 layout을 읽거나 추정한 것이 아니다. 위 순서는 해당 정적 경로의 call 순서다. Configure에도 많은 간접/private helper 호출이 있어 “Configure에서는 절대로 world가 없다”는 식으로 전체 호출 그래프를 단정하지 않는다.

막히는 초기화·hook 후보는 다음과 같다.

- **ISystemConfigure**: UpdateInfo/실제 physics world handle을 전달받는 공개 계약이 없고, Sim이 생성한 active detector object를 읽는 연결도 없다. ServerConfig::InitialSimTime=0은 설정값이지 실측값이 아니다.
- **ISystemPreUpdate**: Physics Update의 CreateWorldEntities 경로보다 앞선 훅이다. 여기서 첫 Update를 막으면 필요한 physics world가 이미 존재하고 접근 가능하다는 근거가 없다. unpaused 첫 UpdateInfo.simTime은 System.hh 설명상 dt이므로 초기 time0이라고 정규화하지 않는다.
- **CreatePhysicsEntities 이후, Step 이전**: ELF에서 후보 gap는 보이지만 PhysicsPrivate 내부이며 설치 공개 observer hook가 확인되지 않았다. 그 gap에 들어가려면 private 호출/객체 layout/후킹에 의존하므로 사용자의 중단 조건에 해당한다.
- **paused Update/PostUpdate 또는 paused RunOnce**: paused는 physical Step을 건너뛸 수 있지만 Server.hh는 RunOnce가 simulation iteration을1 증가시킨다고 명시한다. “물리 Step0”과 “iteration0”은 다르다. 사용자가 요구한 iteration0/time0를 만족한다고 처리할 수 없으며 RunOnce를 호출하지 않았다.
- **contact surface event**: 설치 physics/Events.hh는 collision 검사 후 Update 단계의 이벤트라고 명시한다. 무접촉 box 사례에서 이벤트가 발생한다는 보장도 없으며 최초 초기화·iteration0 observer로 대체할 수 없다.

iteration/time을0으로 다시 쓰거나 첫 iteration을 제외하고 카운트하는 우회는 하지 않는다. 현재 공개 훅으로 active engine/detector 관측과 iteration0/time0를 동시에 보장하는 경로는 **미확정**이다. 이전 mock의 GO 전 iteration/time 변화 거부 조건은 유지한다.

## 3. 실제 증거 수집은 조건부 미착수

앞의 두 경로가 성립하지 않아 실제 mapping·GO 이벤트·cgroup·exit/signal/timeout·cleanup·원본 무결성을 새 runtime supervisor에 연결하지 않았다. 미완성 adapter에 synthetic READY를 공급하거나 “설정과 mapping이 맞으니 통과”로 완화하지 않았다. 필수 증거가 없으면 거부하는 기존 정책과 final resource sample이 없으면 UNKNOWN이라는 원칙은 그대로다.

`100×1ms`, iteration1..100/final100ms, z0.95095±0.002m, vz-0.981±0.02m/s 및 기존 state 오차 계약도 변경하지 않았다. 이번에 실제 자료는 수집하지 않았으며 최종 cgroup resource 표본·실제 활성 provider는 UNKNOWN/UNVERIFIED다. service/marker를 전혀 만들지 않았으므로 exit0 같은 runtime 결과를 새로 기록하지 않는다.

## 4. 컴파일·링크와 비실행 검사

새 `src/public_api_audit.cc`는 설치 공개 타입·문자열 반환형·접근 제한·public UpdateInfo field를 compile-time 검사하고, Server::IterationCount 참조를 shared ELF에 링크한다. Server/world를 생성하는 코드나 private layout dereference는 없다. audit ELF SHA-256은 `7de7c7c6980ef47650d7ff4b3a91e4cd68bbf12e65b1e761ac55949732d600c3`다. 이 ELF는 **로드/실행하지 않았다**. 컴파일·링크 PASS, compiler stderr0이다.

새 차단·근거 검사8개 PASS와 기존 Gazebo 비실행 gate 회귀42개 PASS를 확인했다. 기존 launcher가 실제 blocked contract와 위조 ready flag 모두 거부하고, source adapter=false와 runtime 출력/marker 부재가 유지됨을 검사했다. 기존 42개는 양성 synthetic model이 live 데이터가 아니라는 원래 한계를 유지한다. mock 테스트 성공을 기술 차단 해소로 해석하지 않는다.

원본 source/contract/approval/marker를 바꾸지 않고 새 audit 경로에 소스·compiler 결과·정적 증거·로그를 남겼다. 전체 preservation 비교 결과는 integrity.json에 기록한다. 대용량 disassembly와 audit ELF/빌드로그/snapshot은 local work에 보존하며 경량 증거에는 Build-ID/SHA와 직접 이름이 확인된 call만 담는다. 이름 없는 내부 함수가 가장 가까운 export명으로 표시되는 objdump 주석은 함수 식별 근거로 사용하지 않았다.

## 5. 위험·조건부 비적용·다음 입력

Bullet 정상 수명/cast/deleter, 개별 소멸자/D0/free, allocator 및 C 예외 해제 위험은 사용자 결정 사항으로 남고 **NOT_ACCEPTED**다. 기존 Subject 통지 순서는 개별 destructor 호출 순서가 아니며 개별 소멸자는 NOT_OBSERVED, allocator는 NOT_MEASURED다.

비교 arm과 D trace는 installed-only Core/External 고정, local baseline/trace ELF·recorder API 비사용, 실제 mapped closure 배제 확인, neutrality/recorder 비교 주장 없음일 때만 기술적으로 조건부 비적용이다. 원 probe_plan B/C/D와 next_steps A→B→C→D→Gazebo의 절차 생략은 자동 결정하지 않는다. V4 targeted_evidence_plan 마지막 문단의 항목별 명시적 위험 수용 대체 경로도 이번에 사용하지 않았다. 아직 실제 closure가 없으므로 조건부 비적용의 runtime 충족은 미확인이다.

다음에 필요한 것은 같은 Build-ID에 대응하는 Physics/runner 소스·지원되는 공개 관측 hook 계약 등으로, **Sim이 소유한 동일 detector 객체/provider와 physics world 초기화를 iteration0에서 관측할 수 있음을 입증할 자료**다. 그 자료 없이 private ABI를 추정해 연결하지 않는다. hook 추가를 위한 다른 빌드/플러그인 교체는 현재 설치본 검증 범위의 자동 연장이 아니며 별도 범위 검토가 필요하다. 이번에는 다운로드·설치·재빌드·후킹·조건 완화로 우회하지 않았다.

모든 기술 항목이 해결된 경우에만 승인안을 갱신하라는 조건에 따라 기존 approval_plan.md는 보존한다. 새 실행 승인 명령을 제안하지 않으며 launcher의 서비스·marker 전 거부를 유지한다. **Stage B BLOCKED**, 보고 후 추가 작업 없이 멈춘다.
