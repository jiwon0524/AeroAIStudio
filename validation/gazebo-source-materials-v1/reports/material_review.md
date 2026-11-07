# Gazebo 관측 소스·디버그 자료 확보 및 설계

**자료 확보 PARTIAL / 소스 경로 확인 / 실행 준비 미완료 / Stage B BLOCKED**.
시작 HEAD `9fba01825e6acdcd9fc9ef67aa72cfd44f3c8aac`, experiment/dart-internal-trace clean. context-handoff와 요청된 지침/이전 보고서를 읽었다. 사용자 허용 범위에서 공급자 파일 다운로드·격리 추출·해시/패키징/정적 ELF·디버그 정보만 조사했다. source 수정·patch 적용·configure/build·fixture/대상 실행·DART/Gazebo 로딩·서비스·marker 소비·설치·시스템 설정 변경은 하지 않았다. 위험 수용 미결정.

## 1. 확보 범위와 일치 판정

|대상|소스·배포 패치|디버그 Build ID|남은 자료|
|---|---|---|---|
|gz-sim8 `8.15.0-1~noble`|공급자 Sources/DSC/orig/debian archive SHA-256 일치. 설치 changelog도 byte 일치. Debian archive에 patch series 없음|**MATCH**: Sim core, Physics system, CLI 3개 Build ID와 debuglink CRC 모두 일치. DWZ 포함|원본 buildinfo/changes·컴파일 전체 flags/의존 버전 manifest·빌드 로그 미확보. DWARF의 모든 소스 byte checksum을 전수 증명하지는 않음|
|gz-physics7 `7.8.0-1~noble`|upstream tag 소스와 공급자 release commit 확보. Noble changelog가 설치본과 byte 일치. 해당 packaging에는 patch series 없음. **정확한 native source archive/DSC의 payload 일치는 미확인**|**UNVERIFIED/미확보**: 설치 plugin `c53e1a304ceb0f0dac85ff0e4872d0ffc50a28ac`, feature core `4e60105d86d50ee9e394f6c461411e3cba5eeec1`|7.8.0 native DSC/archive, 공급자가 쓴 upstream revision/전처리·추가 변경, buildinfo/changes/log, 두 Build ID의 debug와 DWZ|
|dart `6.13.2+ds1-1~osrf2~noble`|누락 orig archive 확보, 공급자 색인/기존 DSC SHA 일치. 기존 DSC/debian archive를 새 work로 복사해 색인 대조. patch series 9개 고정, 적용 안 함. 설치 changelog의 보존 history 일치(과거 항목만 잘린 footer 차이)|**UNVERIFIED/미확보**: Core/Bullet/ODE/External 각각 이전 inventory Build ID 유지|원본 buildinfo/changes/log와 해당 4개 Build ID의 debug/DWZ. 소스 package match가 설치 binary 재현을 뜻하지 않음|

확보 원본은 `validation/gazebo-source-materials-v1/work/downloads`, 추출본은 `work/extracted/{sim,sim-packaging,sim-debug,physics-upstream,physics-release,dart,dart-packaging}`에 있다. 원본 archive는 유지했다. 원격 코드는 실행하지 않았으며 deb는 `dpkg-deb --extract`만 사용해 maintainer script를 실행하지 않았다. 추출 source도 수정하지 않았다.

출처와 다운로드 SHA는 [acquisition.json](acquisition.json), [physics_acquisition.json](physics_acquisition.json), [provider_probes.json](provider_probes.json), 전체 파일 해시는 [download_hashes.json](download_hashes.json)에 있다. Sources 색인 출처는 `https://packages.osrfoundation.org/gazebo/ubuntu-stable/dists/noble/main/source/Sources.gz`다. HTTPS와 공급자 색인/DSC checksum 및 설치 metadata를 대조했으며 archive 서명 체인의 별도 GPG 검증은 수행하지 않았다.

중요 자료 SHA-256:

|파일|SHA-256|
|---|---|
|Sim DSC|`84ab65ae652fc95536e499c6a46e2f7c59bb986bb973b802ad4fee1f19f52ac0`|
|Sim orig.tar.bz2|`f457478cc8b319be148aa1e7a3bc14042c333c8881c1f92ea6d498344fea891d`|
|Sim debian.tar.xz|`fd14fe0cf6caeeadbae7c408b0a4b295137e175c70c304b56f615d15670bd806`|
|libgz-sim8-dbg deb|`4884d33c8036df02b275149797181316b962edd52b6864a924f436a69cb660cb`|
|physics upstream tag archive|`0d95b1dd3ea8c6f558535efe5fab6ecf5af947902a4367982e6fabd586752266`|
|physics release commit archive|`5319a1049cfe9b9a616db7c8ba4c51a9f701577f157b2388ed823bd1d677d751`|
|DART orig.tar.xz|`b900820b71463476463b9daeb31e81c74ebf59bd95139b7f833f5f6bb9b8058e`|

physics upstream source: [gz-physics7_7.8.0](https://github.com/gazebosim/gz-physics/tree/gz-physics7_7.8.0). Packaging commit: [dd4ca6f5bdd3d1d2b52b9151ee953a562c3dbbd2](https://github.com/gazebo-release/gz-physics7-release/tree/dd4ca6f5bdd3d1d2b52b9151ee953a562c3dbbd2/noble/debian). 현재 공급자 색인은 physics7.9.0이며 pool listing에서7.8.0을 찾지 못했고7.8.0 DSC는404다. main archive도 참고용으로 받았지만7.8.0 일치 판정에는 쓰지 않았다. buildinfo·debug 후보404는 검사한 URL 범위의 부재이지 전 세계 자료 부재 주장이 아니다. 디렉터리 listing에 changes/buildinfo가 없었으며 별도 빌드 서버 보관본은 확보하지 못했다.

DART 패치 중 `0013-Deaktivate-assert-failing-with-Bullet-3.24.patch`는 ContactConstraint.cpp의 assertion을 비활성화한다. 이것을 upstream 무패치 소스와 같다고 처리하지 않았다. 검토한 World.cpp/ConstraintSolver.cpp 및 detector getType 구현 파일은 해당9개 패치의 변경 대상이 아니다. patch 목록·개별 SHA·changelog 대조는 [packaging_comparison.json](packaging_comparison.json), 읽은 구현 파일 해시는 [source_files.json](source_files.json)에 있다.

## 2. 설치 디버그와 소스 호출 지점 연결

|설치 ELF|Build ID|판정|
|---|---|---|
|libgz-sim8.so.8.15.0|`4785a0f397c1a9fea8eea659d89ccb559d82360f`|debug Build ID/CRC MATCH|
|libgz-sim8-physics-system.so.8.15.0|`d84fdca46ee5b0a981496fde744460e1b1d9deaa`|debug Build ID/CRC MATCH|
|libgz-sim8-gz.so.8.15.0|`3796557281a8e660befdccee64f5368d5175fc1a`|debug Build ID/CRC MATCH|

DWZ `libgz-sim8.debug` Build ID `42495ca78866eac2440b676cb6a908fac5e0fcd7`도 debugaltlink 값과 일치한다. [debug_matches.json](debug_matches.json), [dwz_identity.json](dwz_identity.json)에 해시가 있다.

최초 addr2line은 절대 DWZ 경로를 찾지 못했다. 설치 경로를 변경하지 않고 추출 디렉터리만 GDB sysroot/debug-file-directory로 지정하자 해결됐다. **GDB는 auto-load/debuginfod를 끈 static symbol-file/info line 용도로만 사용했다. inferior 생성·run·attach·함수 호출은 없었다.**

정적 디버그가 가리킨 원본 빌드 경로는 `/usr/src/gz-sim8-8.15.0-1~noble/`다. 기존 disassembly 주소 `0xb850c`는 Physics.cc:1044(CreatePhysicsEntities), `0xb853b`는:1050(Step), `0xb11b4`는:1082(CreateWorldEntities)에 대응했다. `0xb8518`은 최적화된 unique_ptr header line으로 나타나므로 소스1045라고 단정하지 않는다. Sim core의 UpdateCurrentInfo/Run/Step도 각각 SimulationRunner.cc:367/:762/:1015로 연결된다. [static_line_evidence.json](static_line_evidence.json)은 원문을 보존한다. 이것은 설치본의 정적 호출/라인 근거이며 실행 중 state의 증거가 아니다.

## 3. 실제 Sim 소유 detector를 읽는 typed 경로

이전 공개 감사의 한계를 유지하되 이번 소스로 더 구체화했다. Sim `Physics::Configure`(Physics.cc:902–1032)는 로드한 plugin에서 `RequestEngine<...>::From(plugin)`(:998)으로 자기 engine을 보관한다. `CreateWorldEntities`(:1092)는 그 engine의 `ConstructWorld(world)`(:1117) 결과를 `entityWorldMap.AddEntity`(:1118)에 보관한다. 따라서 별도 engine을 만들 필요 없이 이 map의 **동일 world**를 사용해야 한다.

physics 소스에서는 `SDFFeatures::ConstructSdfWorld`(:489–) → `EntityManagementFeatures::ConstructEmptyWorld`(:763–) → `AddWorld`/worlds map으로 이어진다. `WorldFeatures::GetWorldCollisionDetector`(:88–94)는 `ReferenceInterface<dart::simulation::World>(_id)` → `getConstraintSolver()` → `getCollisionDetector()` → `getType()`다. 설정값 echo가 아니다.

새로 확인한 대안은 `dartsim/src/World.hh`의 **RetrieveWorld** feature다. `CustomFeatures::GetDartsimWorld`(CustomFeatures.cc:26–30)는 `this->worlds.at(_worldID)`의 shared_ptr를 반환한다. 설치 ELF에도 `CustomFeatures::GetDartsimWorld`가 `0x1dee80`에 export돼 있다. [provider_static_symbols.json](provider_static_symbols.json)에 wrapper RTTI 및 DART getType symbol의 모듈별 근거를 보존했다. 그러나 feature 정의는 이 source의 src/World.hh에 있고 설치 include에서 대응 헤더를 찾지 못했다. Sim의 private map은 여전히 외부 공개되지 않는다. 함수 export만으로 외부에서 private 인스턴스를 찾아 호출할 수 있다는 주장은 하지 않는다.

**계측 후보:** Sim Physics.cc 내부에서 자기 `entityWorldMap`의 feature cast를 이용해 RetrieveWorld를 요청하고 native shared_ptr를 얻은 뒤 `world->getConstraintSolver()->getCollisionDetector()`를 읽는다. source header를 명시적인 실험 의존성으로 고정하고 인터페이스/기존 plugin 등록과의 일치를 추가 검증해야 한다. 일치가 불충분하면 gz-physics에 명시적 diagnostic feature를 추가하는 별도 빌드를 선택한다. 어느 경우도 private offset이나 사설 객체 reinterpret_cast가 필요하지 않다. 독립 World 생성은 금지한다.

provider는 한 모듈로 뭉개지 않는다. 이 physics 소스의 기본 ConstructEmptyWorld는 GzOde detector를 만들고, Sim CreateWorldEntities에서 component가 있으면 SetCollisionDetector로 교체한다. `WorldFeatures::SetWorldCollisionDetector`는 bullet→GzBullet, ode→GzOde, fcl→FCL, dart→DART 객체를 선택한다. 따라서 DART 엔진이라고 Bullet 활성이라고 단정할 수 없다. 실제 detector는 여전히 **UNVERIFIED**다. 기존 `fixtures/minimal.sdf`에는 dart/collision_detector가 없고 server.cc는 DART engine 경로만 지정한다. Sim SdfEntityCreator.cc:428–434는 해당 SDF 요소가 있을 때만 PhysicsCollisionDetector component를 만든다. 따라서 확보 소스대로라면 이 고정 입력의 후보는 기본 GzOde지만, exact physics native source/debug 연결과 실제 객체 관측이 없으므로 ODE 활성 확정으로 승격하지 않는다. Bullet 위험의 비적용도 자동 결정하지 않는다.

GzBullet/GzOde wrapper는 plugin의 GzCollisionDetector.hh/.cc에 있고 collide override가 각각 DART Bullet/ODE 메서드로 위임한다. getType은 wrapper가 override하지 않아 DART adapter의 메서드가 사용된다. 후보 provider는 wrapper RTTI/override의 gz plugin과 base 알고리즘의 libdart-collision-bullet 또는 libdart-collision-ode이며 FCL/DART는 Core 측 구현을 따로 확인한다.

native 객체를 보유한 상태에서 실제 dynamic type의 RTTI 주소를 dladdr/mapping/FD hash/Build ID로 대조하는 것은 **타입 제공 모듈** 증거다. 이것만으로 실제 virtual 메서드 실행 provider를 입증하지 않는다. 강한 provider 증거가 필요하면 해당 query 메서드(getType 등)의 source entry에 typed this와 module-local anchor를 기록하고 동일 객체와 주소 mapping을 연결해야 한다. DART getType은 확보 소스상 type 문자열 반환이며 Step이 아니다. inherited base this와 wrapper this는 정상 C++ cast로 상관시킨다. 실제 collide 실행까지 주장하려면 GO 이후 wrapper/base collide entry도 별도 관측해야 한다. GO 전에 collision 검사를 실행해 provider를 증명하는 우회는 하지 않는다.

## 4. 초기화와 첫 iteration을 분리할 최소 변경 설계

확인한 기존 호출 순서:

1. SimulationRunner constructor → CreateEntities(:322). CreateEntities(:1703–1784)가 SDF ECM/active level/server plugins/logging 설정을 만들고 initial ECM을 저장한다. SystemManager::AddSystemImpl(:260–309)는 Configure를 즉시 호출하고 Update callbacks만 pending queue에 둔다. Physics Configure는 engine 선택까지 수행하며 물리 world/entities는 만들지 않는다.
2. SimulationRunner::Run(:761) → loop(:880) → UpdatePhysicsParams(:886) → **UpdateCurrentInfo(:890)**. UpdateCurrentInfo의:426–428이 unpaused simTime += stepSize / ++iterations를 수행한다.
3. runner Step(:1013) → ProcessSystemQueue(:1029) → UpdateSystems(:1041) → PreUpdate/Update/PostUpdate. 여기서 Physics::Update(:1038) → CreatePhysicsEntities(:1044) → UpdatePhysics(:1045) → !paused이면 Step(:1050).
4. PhysicsPrivate::Step(:3321) → 저장 world->Step(:3333) → physics SimulationFeatures::WorldForwardStep(:72) → DART world->step(:111). DART World.cpp:167–206의 끝에서 mTime/mFrame 증가.

따라서 기존 순서에서 물리 객체 완성 후 대기는 iteration1/time1ms 구간이다. paused RunOnce, counter reset/보정, 첫 iteration 제외 계산은 사용하지 않는다.

**최소 변경안(설계만, 미구현):**

- `SimulationRunner::Run`에서 network 경로를 명시적으로 거부하고, realtime watch 시작(:789 부근) 및 첫 UpdateCurrentInfo **이전**에 one-shot `PreparePhysicsForValidation` phase를 삽입한다. constructor/CreateEntities 종료로 ECM과 Configure가 완료된 동일 runner를 대상으로 한다. 기존 Reset/rewind/seek/control 재사용은 하지 않는다.
- 새 명시적 동기 event/interface를 통해 Physics::Configure에서 등록한 callback으로 **그 Physics 인스턴스**에 ECM과 currentInfo를 전달한다. pending system의 Update를 실행하거나 PostUpdate worker를 시작할 필요가 없다. subscriber 수·응답 world 수가 정확히1인지 확인하고 아니면 거부한다. 새 인터페이스 이름은 제안이며 기존 API로 표시하지 않는다.
- Physics callback이 CreatePhysicsEntities(:1075)를 한 번 실행한다. 생성 순서는 World→Model→Link→Collision→Joint→Battery다. CreateWorldEntities가 detector/solver 설정까지 적용한 뒤 모든 shape까지 생성 완료한 시점에 앞 절의 native world/detector를 관측한다. UpdatePhysics 전체는 force/commands/mask 등을 처리하므로 bootstrap으로 통째 호출하지 않는다. 고정 최소 world에 필요한 초기 상태 설정만 분리 감사한다.
- 생성 helper들은 EachNew와 linkAddedToModel/jointAddedToModel 상태를 사용한다. 첫 정규 Update에서 중복 생성/추가 상태 유실이 없도록 **bootstrap 완료 flag로 첫 CreatePhysicsEntities 호출만 건너뛰는 처리**를 설계하고, 그 사이 ECM 변형·추가 entity를 금지한다. runner의 ClearNewlyCreatedEntities(:1067)를 앞당기면 다른 system의 첫 관측을 바꾸므로 금지한다. 이 변경의 첫 step 의미/cleanup은 별도 테스트 대상이다.
- runner가 실측 currentInfo.iterations=0, simTime=0, DART getSimFrames=0/getTime=0, 완료된 객체 수와 동일 detector/provider 증거를 수집한 뒤 bounded GO wait를 수행한다. DART 초기 mTime/mFrame=0은 World.cpp:68–69, getter는:215/:221에 있으나 실행 시 값은 반드시 실측한다. GO 직전 재측정과 identity 비교, EOF/timeout/누락/변화 거부를 유지한다.
- GO 후에만 기존 UpdateCurrentInfo→Step으로 진입한다. single-world, no-network/no-level-streaming/no-control/no-reset, 허용 plugin만 사용하고 다른 thread/queued command가 대기 중 world를 변경하지 못함을 감사·검증해야 한다. 추가 방어가 필요하면 PhysicsPrivate::Step 및 plugin WorldForwardStep의 GO 전 호출 거부 hook도 포함한다. 현재 소스 설계만으로 이러한 runtime 불변식이 PASS했다고 판정하지 않는다.

DART solver 생성/getter와 객체 생성 경로는 typed 소스로 이해할 수 있게 됐지만, 모든 초기화 하위 호출의 무스텝성·동시성 및 동적 resource closure는 아직 실행 승인 요건이다. 두 차단은 **변경 설계 가능**, 원 설치 순서 그대로는 **미해결**이다.

## 5. 빌드 범위·증거 경계·별도 승인 조건

설계상 최소 대상은 Sim core(`src/SimulationRunner.cc`, 새 event/interface header)와 Physics system(`src/systems/physics/Physics.cc/.hh`, source-defined RetrieveWorld dependency)이다. CMake 선언은 core의 `gz_create_core_library` 및 `gz_add_system(physics ...)`로 확인했다. 선택 detector의 타입/RTTI 모듈 관측만으로 범위를 한정하고 source-defined RetrieveWorld 계약이 충분히 검증되면 gz-physics/DART ELF 교체를 피할 가능성이 있다. 이는 아직 링크/런타임 인증된 경로가 아니다.

패키징의 build rules도 확보했다. Sim은 RelWithDebInfo와 libgz-sim8-dbg 분리를, physics는 RelWithDebInfo 및 특정 LTO flag 제거를 지정한다. DART rules/patch도 원본에 보존했다. 이는 빌드 의도와 의존 패키지명을 보여주지만 실제 빌드 환경의 모든 버전·flags를 대신하지 않는다.

정확한 provider query 실행 증거나 내부 GO guard가 필요하면 `dartsim/src/WorldFeatures.cc`, `CustomFeatures.cc`, `GzCollisionDetector.cc`, `SimulationFeatures.cc`의 diagnostic/guard를 포함하는 **gz-physics7-dartsim-plugin** component와, 실제 선택된 DART detector의 getType/필요시 collide 구현을 제공하는 **해당 adapter 또는 Core**를 추가 빌드한다. 모든 DART/Gazebo/GUI를 재빌드하는 범위로 자동 확대하지 않는다. 선택 target과 실제 전이 의존성/헤더 ABI는 빌드 승인안에서 확정해야 한다.

설치본에서 현재 얻은 증거는 패키지 버전·ELF SHA/Build ID, Sim matching debug/line call path, source/patch 자료, exported symbol과 typed 소스 경로다. **실제 활성 detector/provider, runtime iteration/time, GO 무스텝성은 얻지 않았다.** RTTI 주소를 사용한 기존 ELF 관측도 실제 실행 전에는 미확인이다.

초기화 분리·새 diagnostic·GO 장벽의 실행 증거는 별도 계측 빌드에서만 얻는다. unmodified plugin/DART를 그대로 매핑한다면 그 ELF에서 관측한 사실은 byte identity와 함께 제한적으로 주장할 수 있으나, **수정된 Sim과 초기화 순서에서의 결과를 원 설치 Gazebo 전체 실행 검증으로 승격할 수 없다.** 계측된 DART/provider는 새 SHA/Build ID의 별도 대상이다. 원 설치본 소스 기반 설계와 계측 대상 검증을 분리한다.

다음 별도 승인에는 수정 파일·diff와 패치 provenance, source-defined feature 계약 확인, 정확한 target/빌드 범위·compiler/flags/closure, 비실행 검증 항목, 새 ELF hashes/Build IDs, 격리/GO/one-shot·출력 경로·자원/시간 한도·수집/중단/정리 계약이 필요하다. 빌드 승인과 이후1회 실행 승인은 구분한다. missing original buildinfo/debug를 어떤 수준의 증거 제한으로 남길지도 명시해야 한다. 과거 lifetime one-shot을 재사용하거나 원래 Gazebo gate를 완화하지 않는다.

Bullet 정상 수명·개별 소멸자·allocator·C 예외 해제 위험은 미수용이며 개별 소멸자는 NOT_OBSERVED, allocator는 NOT_MEASURED다. 비교 arm/D trace의 조건부 비적용은 계측으로 범위가 바뀌므로 재검토해야 한다. 이번에는 어떤 절차도 면제하지 않았다.

## 6. 보존 및 종료

기존 launcher/계약/승인안/증거/marker를 수정하지 않았다. 새 경량 reports와 handoff만 게시하고 외부 source/debug/deb 및 raw 정적 도구 출력은 ignored work에 보존한다. 다른 장치에 이 원본들이 자동 전송되지 않으며 /tmp 영속성은 보장되지 않는다. 검증은 다운로드/DSC hash, packaging 비교, debug Build ID/CRC/altlink, static line/symbol, JSON/link/diff 및 선택 무결성 검사에 한정한다. 컴파일·테스트·대상 실행 결과는 없다. [integrity.json](integrity.json)에 종료 대조를 기록한다. **Stage B BLOCKED**, 위험 수용 미결정, 보고 후 멈춘다.
