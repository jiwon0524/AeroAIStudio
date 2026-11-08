# 고정 fixture의 초기화/GO 경로 정적 검토

범위: 기존 minimal.sdf의 한 world/falling_box/body/box collision, 중첩 model·사용자 joint·battery·mesh·sensor·추가 system 없음. 위치와 원본 SHA는 call_path_locations.json. 다른 scene이나 plugin으로 일반화하지 않는다. 아래는 소스 검토이며 실제 무스텝 실행 PASS가 아니다.

|경로|확인한 하위 호출/효과|스텝·시간·중복 판정|
|---|---|---|
|Server 생성 → SimulationRunner::CreateEntities|SdfEntityCreator/level 초기 ECM 구성, 명시 Physics Configure/RequestEngine. world system이 이미 있으므로 1762행의 default-plugin fallback은 선택되지 않음. ServerConfig의 추가/로그 plugin 목록은 harness에서 설정하지 않음|native world 생성은 Run의 새 bootstrap으로 이어짐. constructor가 Run/paused RunOnce를 bootstrap으로 호출하지 않음|
|Run 입구 → ActivatePendingSystems|Configure는 AddSystemImpl에서 이미 동기 완료. ActivatePendingSystems는 interface 목록 활성화. ProcessSystemQueue는 PostUpdate worker를 시작할 수 있어 bootstrap에서 호출하지 않음|network 거부, 단일 Physics/PreUpdate0/PostUpdate0, currentInfo paused=true, iteration/time0, stepSize1ms, 요청100회 요구. realtime 시작과 첫 UpdateCurrentInfo 이전|
|CreatePhysicsEntities|CreateWorld → Model → Link → Collision → Joint → Battery. linkAddedToModel/jointAddedToModel clear는 처음 한 번 수행|++jointInitCount가 1인 경우만 진입. EachNew를 미리 지우지 않음. 첫 정규 Physics Update는 helper를 한 번 건너뛰므로 첫 UpdatePhysics가 필요한 bookkeeping을 볼 수 있음|
|CreateWorld → ConstructSdfWorld → ConstructEmptyWorld|World 생성, 중력, GzOde detector 생성/solver 교체, AddWorld의 map/Frame/Skeleton proxy 구성. World constructor는 timestep.001/time0/frame0, BoxedLcpConstraintSolver/FCL 초기 객체 구성|World::step/solve가 생성자 경로에 없음. transient FCL detector가 생겼다고 active FCL로 판정하지 않음. 실제 getter의 GzOde→ODE method entry가 GO 관측 대상|
|World::setConstraintSolver → ConstraintSolver 생성/교체|solver와 collision group 생성, timestep 전달. 초기 skeleton 목록 비어 있음. FCLCollisionDetector는 manager 객체, FCLCollisionGroup은 DynamicAABBTree manager 생성|integration/solve/collide 호출 경로가 아님. 생성 중 예외는 Run의 bootstrap catch로 반환|
|ODE 생성 leaf|OdeCollisionDetector: dInitODE2, thread-data allocation, dWorldCreate. OdeCollisionGroup: dHashSpaceCreate/setLevels. 정확한 재사용 패키지는 이전 ODE 대응 근거로 고정|해당 factory 호출에 DART World나 step callback을 전달하지 않음. native DART에 재진입하는 미확정 callback을 이 경계에서 허용하지 않는다. 외부 binary 내부의 임의 부작용/allocator/thread 초기화까지 정적으로 인증한 것은 아님|
|CreateModel → ConstructSdfModelImpl → Base::AddModel → World::addSkeleton|Skeleton/SimpleFrame 생성, frame/중력/timestep, solver.addSkeleton → CollisionGroup::subscribeTo. 이 시점 skeleton은 아직 body0이며 이후 link 생성|등록/version 추적, recording 좌표 수 갱신. time/frame 증가는 없음. World.cpp의 실제 mTime+= 및 mFrame++는 step에 있음|
|ConstructSdfLink → FreeJoint/BodyNode → ConstructSdfCollision|FreeJoint/body 생성, transform/inertia/중력, BoxShape 및 CollisionAspect/DynamicsAspect ShapeNode/마찰/filter metadata. shape/version 등록|고정 box 분기에는 mesh/heightmap/외부 resource callbacks 없음. 각 Create*의 joint/battery visitor는 fixture에서 0개. 임의 형상/사용자 callback의 무스텝성까지 주장하지 않음|
|다음 CreateLink/Collision 단계|Physics.cc 1418 부근 GetLink, 1539 부근 GetShape로 model parsing에서 이미 만든 객체를 찾아 ECM entity map에 등록|별도 body/shape를 다시 만들지 않는 분기. 새 코드가 duplicate DOM 구성을 반복하지 않음. 첫 정상 step 뒤 ClearNewlyCreatedEntities가 기존대로 실행됨|
|active world 관측|같은 entityWorldMap identity → RetrieveWorld → CustomFeatures.worlds.at 반환. WorldPtr 유지, borrowed solver, shared detector 유지. 같은 proxy를 다시 조회해 WorldPtr 동일성 확인|World/solver/detector/time/frame/init1, native body 자세/속도와 ECM 초기 상태 검사. getType 정상 virtual query를 실제 호출. private offset/vtable slot 추정 없음|
|GO → 정상 Run loop|ready_state 2개 및 engine/typed entry, 외부 기존 mapping/PID/정책 검증을 거쳐 FD3 GO. 자식은 GO 뒤 zero-state/provider 재검사 후 paused=false|UpdateCurrentInfo/SimulationRunner::Step/Physics::Update/native World::step에 GO 가드. detector collide 8개 overload도 pre-GO 거부. GO 전 오류·null·관측/pipe 실패·EOF/timeout에는 첫 time update 이전 반환|
|100회 실행 계약|Physics Update의 iteration1..100, dt1ms, simTime=i ms, native frame=i-1, solver/detector 동일성 검사. native Step 뒤 frame=i/time=.001*i와 state sample. Server 최종 IterationCount100|원 validate_run의 100 samples/1ms/자유낙하 기준 유지. 시간·counter 불일치 시 다음 native step 전 거부. 허용되지 않은 추가 step은 Run의 100회 한도와 각 entry 가드로 거부|
|해제|추가한 shared detector/World 참조를 Physics destructor body에서 먼저 release하고, 그 뒤 기존 dataPtr/engine 소유자가 해제되도록 준비|borrowed solver는 nullptr로만 정리. plugin보다 native 참조가 오래 남는 새 해제 순서 문제를 보완. destructor 실제 실행 NOT_OBSERVED, allocator NOT_MEASURED 유지|

## 변경한 독립 입력

01 patch: detector query method entry와 정상 base cast/anchor; native World::step 및 8개 collide overload의 GO 가드. 02 patch: GzOde/GzBullet wrapper query entry와 CustomFeatures의 실제 RetrieveWorld method entry. 03 patch: typed init interface, runner 진입/시간/Step 가드, 제어/state/playback/runtime-plugin-add 거부, 위 동일 world/초기 상태/샘플/소유권 처리.

이전 후보에는 control callback 거부와 UpdateCurrentInfo 자체의 가드가 실제 diff에 없었다. 새 diff에 넣고 다시 --check했다. source별 파일 해시는 patch_checks.json/input_files.json에 있다. 타깃 트리에 적용하지 않았다.

harness는 빈 world 후보에서 fixture.sdf.in/fixture.hh로 바뀌었다. 원 minimal.sdf의 물리 subtree를 XML 구조로 비교해 동일함을 확인했다. 바뀐 것은 observer plugin 제거와 source-built Physics/engine의 절대 경로 연결뿐이다. 이전 pre-update observer는 수집 불가 시 무조건 종료하는 후보였으므로 새 bootstrap/typed 수집과 telemetry로 그 역할을 연결했다. 기존 파일/판정 함수/실행 contract 값은 수정하지 않았다.

## 기존 검증 코드 연결

inputs/broker.py의 drive_existing은 이미 승인된 supervisor가 가진 PID/관측 FD/GO FD를 인자로 받는다. process/service를 생성하지 않는다. entries_from_contract → 기존 identity.py 및 mapped.py의 PID start/map_files 또는 proc-root FD/hash/Build-ID/dev/inode/required-mapping 검사 → 정상 this/base/entry anchor 범위 및 engine/wrapper/base provider 대조 → 기존 gate.py Gate.authorize(같은 pre-GO 관측2개) → GO callback → validate_run 순서다. bounded_packets는 25초/64KiB 상한, 자식 GO 대기는 30초다. FD3/FD4는 FIFO로 확인하고 marker를 열지 않는다.

native zero-state는 raw ready에 실제 native frame/time/init count로 전달한다. 초기 ECM 속도0과 자세는 native BodyNode의 world transform/linear/angular velocity와 대조한 뒤 내보낸다. simulation state는 Util::worldPose 및 Physics가 갱신하는 WorldLinearVelocity component에서 수집한다. 이후100개 sample의 검증은 기존 validate_run을 직접 호출하며 z=.95095±.002, vz=-.981±.02 및 기존 lateral/rotation 한도를 바꾸지 않았다.

runtime contract가 EXECUTION_READY이고 위험 수용이 EXPLICITLY_RECORDED이며 실제 supervisor의 isolation/PID 관측이 있어야 drive_existing이 진행한다. 현재 이 상태를 만들거나 어떤 capability도 True로 바꾸지 않았다. child exit/cleanup/cgroup 한도 확인은 기존 supervisor 책임으로 유지한다. 결과가100개라는 사실만으로 cleanup/Clock/Capture PASS를 만들지 않는다.

## 판정 범위

**RESOLVED: 이 고정 fixture에 대한 계측 입력/호출 위치/프로토콜 설계 및 정적 검토.** 선택한 Sim/physics/DART source 사이의 미지정 init dispatch 지점은 남기지 않았다. 외부 재사용 library의 factory/allocator 내부와 실제 C++ ABI·초기화 동시성·binary의 무스텝성은 static source 검토로 인증하지 않는다. 새 빌드 후 compile/link/정적 closure 및 허용될 때의 별도 실패-path/실제 관측 검증이 필요하다. 이 경계를 runtime PASS로 승격하지 않는다.

실제 ABI, provider/ELF mapping 및 init-once/GO timeout의 native 동작은 **NOT_RUNTIME_VERIFIED**. Stage B BLOCKED, 위험 수용 미결정. 관측 결과가 생기더라도 해당 coherent source-built manifest에만 귀속한다.
