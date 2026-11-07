# 소멸 통지 이후 Gazebo 진입 조건 재평가

**NOT_READY_FOR_GAZEBO_EXECUTION / Stage B BLOCKED**. 기준 HEAD `bcbc5a75d5413cd0d6b1ebdc45e118b06c3e13fa`, experiment/dart-internal-trace, 시작 clean. 읽기 전용 파일/ELF 조사와 결과 문서·인계 작성만 수행했다. 구현/빌드/DART·Gazebo 로딩/이전검증 재실행/service/marker/sudo/install/system변경0. 위험 수용 결정 없음.

## 1. 결론과 증거의 범위

빈 Skeleton, B1 정상 생성관계·소유자 해제, ShapeNode→BodyNode 각1회 owner-reset 내 통지 및 등록잔여0은 기존 실행 보고서에서 확인한 **역사적 성공**이다. 이번에 재실행하지 않았다. 통지 순서는 개별 derived destructor 순서가 아니다. **개별 소멸자 NOT_OBSERVED / allocator NOT_MEASURED 유지**.

남은 B/C/D를 모두 설치본100step smoke의 절대적 독립 필수시험으로 해석하는 것은 적절하지 않다. 원 문서는 기본 증거 경로와 명시적 잔여위험 수용의 대체 경로를 모두 두고 있다. 반대로 이번 분석의 비적용 판정이 기존 프로젝트 gate를 자동 면제하지도 않는다. 실행할 backend/provider와 새 Gazebo payload/closure/step GO 계약은 아직 미확정이므로, 위험 수용 여부와 무관하게 지금 실행 가능한 상태는 아니다.

## 2. 예정 구성과 실제 provider

기존 `validation/gazebo-minimal-approval-v1/reports/approval_plan.md` §3의 제안은 설치본 DART, -s -r --iterations100, max_step_size0.001s, dynamic box1개/초기z1/무접촉/무센서/무GUI,local baseline·trace 교체 없음이다. 새 `validation/gazebo-minimal-physics-v1` 경로/world/observer/launcher는 여전히 존재하지 않는다. 명령이나 world가 고정·검증·승인된 실제 실행계약이라고 간주하지 않는다.

정적 후보 경로:

|역할|확인한 설치 경로|판정|
|---|---|---|
|CLI/dispatch|/usr/bin/gz, /usr/share/gz/sim8.yaml, /usr/lib/ruby/gz/cmdsim8.rb|sim8.15.0 dispatch와 physics-engine 인자 전달은 코드로 확인|
|Sim 진입/Physics system|/usr/lib/x86_64-linux-gnu/libgz-sim8-gz.so.8.15.0, libgz-sim8.so.8.15.0, libgz-sim8-physics-system.so.8.15.0|설치 후보 파일 확인; 새 실행에서 실제 로딩은 미확인|
|DART physics engine plugin|/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0|기존안이 명시 지정하는 후보; 실제 instance/active backend 미확인|
|DART Core/External|/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2, libdart-external-odelcpsolver.so.6.13.2|이전 검증 설치본 hash와 일치; 실제 Gazebo mapped provider 미확인|
|DART Bullet/ODE|/usr/lib/x86_64-linux-gnu/libdart-collision-bullet.so.6.13.2, libdart-collision-ode.so.6.13.2|plugin DT_NEEDED가 요구; 단순 optional 후보로 제거 불가|
|Bullet dependencies|/usr/lib/x86_64-linux-gnu/libBulletCollision.so.3.24, libLinearMath.so.3.24|Bullet adapter의 DT_NEEDED; 실제 detector 선택과 별개|

기존193파일 static_inventory를 재해시해 변경0을 확인했다. 주요SHA256과 readelf/nm 증거는 static_evidence.json. 예: DARTplugin1ee9350aa09d5a5eb43a5075c9c61d2cdcb85113d2ff1e0f32136847edf1688e, Coref74f4ec9820aee785ef94fb7bedafa7e4c832f209675a8ca1d35019c72b48e06, Bulletadapter897709e0c988e9e562c662292ed5bc860bce70ee2c64499501f54a6b5ca02201. 이는 default-directory NEEDED 후보 graph이지 future actual mount/cache/dlopen/Ruby/resource closure 인증이 아니다. SONAME의 미래 sandbox provider도 새FD/mount계약에서 확정해야 한다.

plugin의 dynamic symbol에는 GzBulletCollisionDetector::create, BulletCollisionDetector::createCollisionGroup/createCollisionObject/notifyCollisionObjectDestroying/destructor 참조와 dartsim::WorldFeatures::SetWorldCollisionDetector/GetWorldCollisionDetector가 있다. Bullet/ODE의 정적 존재·등록은 실제 활성 detector 증거가 아니다. 보존 DART ConstraintSolver.cpp:65의 기본 FCL 설정 역시 설치 Gazebo wrapper가 바꿀 수 있어 실제 선택의 근거로 사용할 수 없다. 해당 wrapper의 설치빌드와 대응하는 전체 source/선택분기/새SDF는 미확정이다. **실제 backend=DART인지, 실제 detector=Bullet/FCL/ODE인지, 전체 mapped closure는 모두 UNKNOWN**.

`/usr/include/gz/physics7/gz/physics/World.hh`의 CollisionDetector::World::GetCollisionDetector()가 구현API GetWorldCollisionDetector로 전달됨을 detail/World.hh에서 확인했다. `/usr/include/gz/sim8/gz/sim/components/PhysicsEnginePlugin.hh`는 library 문자열 컴포넌트이고, 기존 tools/gazebo_runtime_physics_backend_observer.cc는 그 문자열을 기록한다. 따라서 설정문자열/파일명/loaded mapping만으로 활성 engine·detector를 모두 확인했다고 할 수 없다. 향후 observer가 실제 engine world handle에 안전하게 접근 가능한지도 미확인이다.

설치 Core/External에서 알려진 local trace namespace dart::external::ode::trace::의 dynamic export0을 확인했다. local trace header internal_trace.h의 Configure/GetStatus/FlushExclusive는 이 프로젝트 계측판 API다. export부재만으로 임의숨은계측/전체중립성을 증명하지는 않지만, 설치파일 해시·local trace 비사용 설계와 함께 trace 기능 비적용의 정적 근거가 된다.

## 3. 항목별 분류

여기서 **필수 증거**는 실행 대상/계약의 식별에 반드시 필요한 것, **명시적 위험 수용 가능**은 V4 대체 경로가 있으나 아직 수용되지 않은 기술적 gap, **이번 구성에 비적용**은 고정할 설치본 smoke가 그 경로/주장을 포함하지 않는 경우의 기술적 범위 판정이다. 비적용은 아래 조건부이며 기존 기본 프로토콜의 생략 승인을 대신하지 않는다.

|잔여 항목|분류|문서·코드 근거와 판단|
|---|---|---|
|B Bullet 라이브러리/provider·선택 여부|**필수 증거**|plugin NEEDED에 Bullet/ODE, adapter NEEDED에 BulletCollision/LinearMath가 있어 실제closure/identity를 알아야 한다. 실제 활성detector도 UNKNOWN. 무접촉world라고 로딩/init을 제거할 수 없음|
|B Bullet factory/group/object/cast/정상해제 동작시험|**명시적 위험 수용 가능**(현재 미충족)|probe_plan.json B의 기본요구. V4 마지막문단의 항목별수용 대체경로는 있으나 이번 정상notification은 이를 검증하지 않음. Gazebo wrapper와 설치 Bullet 경계/실제선택을 식별한 뒤 생략위험을 특정해야 함. provider확인은 생략 불가|
|B 개별 destructor/D0/호출순서|**명시적 위험 수용 가능**(NOT_OBSERVED)|V4 destroy/allocator와 B의 destroy/notify 계약. notification은 Subject protected 송신 가능성 때문에 derived entry/free를 입증하지 않음. 직접관측 또는 구체적잔여위험수용 필요|
|B allocator/deallocator provider·balance|**명시적 위험 수용 가능**(NOT_MEASURED)|V4의 provider·callback·주소소유권/정확1회해제 요구. 정상exit·OOM0·약참조/notification은 누수·doublefree·allocator mismatch 증명 아님. 실제provider identity라는 일반게이트는 별도로 필수|
|B baseline/traceOFF 비교arm|**이번 구성에 비적용, 조건부**|원 probe_plan의 설치→baseline→traceOFF는 수정스택/계측 비교 계약. 설치Core·External만 쓰고 localBaseline/Trace를 마운트·로드하지 않으며 동일성/중립성주장을 하지 않는 단일arm smoke에는 비교대상이 없음. 다만 next_steps의 기본gate를 생략하는 범위변경은 사용자확인/항목별수용 없이 자동 적용하지 않음|
|C 예외·부분생성해제|**명시적 위험 수용 가능**(미검증)|probe_plan C는 정상B뒤 proven faultwindow/unwind/해제계약을 요구. fault injection을 하지 않는 정상smoke도 allocation/parse/초기화 실패와unwind 가능성이 있어 비적용으로 처리하지 않음|
|D localtrace OFF/ON/metadata/owner·quiescent/capacity/overflow/flush|**이번 구성에 비적용, 조건부**|설치 hash그대로/localtrace·recorder API 비사용/trace함수 비호출/계측출력없음으로 고정할 때만 비적용. trace replacement가 들어가면 즉시 재적용. export0은 보조정적근거, actualmaps부재확인이 필수. 기존프로토콜 생략결정은 이번에 하지 않음|

분류의 원문 근거: `validation/dart-targeted-evidence-v1/reports/probe_plan.json` 각B/C/D, `validation/dart-probe-readiness-v1/reports/next_steps.md` 계획순서2→3, `validation/dart-destructor-cleanup-v4/reports/targeted_evidence_plan.md`의 “이 증거 또는 항목별 잔여 위험의 명시적 수용 전에는 READY_FOR_SEPARATE_HOST_APPROVAL로 올리지 않는다.”. 기존 prerequisite_review.md의 설치본scope별수용은 적용제안이며 이미수용됐다는사실이 아니라고 명시한다. 이번사용자요청은 재분류조사이지수용승인이 아니다. 따라서 기본gate는 유지한다.

## 4. 위험 수용 판단에 필요한 잔여 위험·완화 조건

- **Bullet 정상수명**: wrapper-specific cast/owner lifetime/deleter/shape cache 경계에서 crash/UB/중복해제 위험. 실제plugin+detector+adapter/provider hashes와 init/closure를 고정하고 단1개 box/무접촉/설치arm/유한100step/격리·cgroup·정리·전후무결성/실패즉시중단으로 노출을 줄일 수 있다. 라이브러리 메모리안전성 자체를 보장하지 않음. 선택detector가비Bullet이어도 DT_NEEDED init/registration 잔여위험은 남는다.
- **개별 destructor·allocator**: 관측되지 않은 D0/free/주소소유권/해제균형을 안전하다고 단정할 수 없음. 기존 세 단계의 유한 정상경로 결과·고정설치Core/단일프로세스/짧은run/core dump금지/원본RO/동작범위제한이 완화근거일 뿐 누수0/전체ABI보장은 아니다. 해당미검증영역과주장제외를 명시해야 수용 여부를 판단할 수 있다.
- **C 예외해제**: allocation/초기화 실패시 leak/doublefree/unwind provider 불일치/terminate 미시험. 주입없이정상입력·유한자원·어떤예외/allocator진단/signal/timeout도FAIL·자동retry/상향0·wholecgroup정리로 제한. 자원한도자체가 실패경로를 유발할 수 있으며 미시험위험을 없애지는 못한다.
- **비교arm/D 범위제외**: local build/mount/searchpath/환경을 배제하고 실제maps에없음을확인,trace API호출/recorder출력/neutrality주장을하지않는설치본smoke로한정해야 한다. fixed closure가확정되지않은현재에는조건충족미확인. 명시적scope변경과필요한수용은 사용자가결정해야 하며 이번에는없음.

## 5. 남은 필수 차단 하나와 최소 신호

**차단항목: 새 Gazebo100step의 고정 provider/closure 및 step전 GO 계약이 준비·검증되지 않았다.** 새world·observer·launcher가없고,activeengine/detector와actualmount를알수없다. 이는 개별destructor/allocator gap을사용자가수용하더라도남는기본실행계약의부재다. 다른B/C/D검증을자동추가하거나이번에구현에착수하지않는다.

최소해소기준은 다음과 같이 고정할 수 있다(향후준비·별도실행승인이필요):

1. 실행전 source/실행ELF/PhysicsSystem/DARTplugin/world/observer·전체필수provider의canonicalpath/SHA256/FDidentity·실제ROmountargv·SONAME/동적resource closure를고정하고readelf 기반사전검사PASS. 외부검색/URI·다른provider/localtrace가있으면차단. 새한도·출력·one-shot도별도고정.
2. step전 **READY_PAUSED** 신호: engine instance/provider가승인DARTplugin에대응,PhysicsEnginePlugin컴포넌트일치,해당engine world의 GetCollisionDetector값과그객체/provider identity/허용타입일치,live mappedELF허용목록일치,PID/start/cgroup/격리/한도PASS. iteration0/simtime0와초기state를실측하고GO미수신동안step0유지. 단순plugin이름·설정값·loadedmapping만으로대체불가. 안전한observer접근·pause/GO실현방법은아직미확인.
3. host가위필수자료완전수집후만1회GO; 이후advancingiteration1..100,각dt1ms,finaltime100ms,예정자유낙하state검사,exit0/정리/원본무결성PASS. missing/unknown/다른detector이면GO미전송·중단. 사후선택해명이나자동fallback금지.

2는향후World생성후첫step전에검증할runtime gate이며,이번에World를만들거나관측하지않았다. 1의새준비를먼저완성하고별도승인받은뒤에만가능하다. 미래runtime gate를지금정적PASS라고표기하지않는다. 이기준은설계제안이며사용자가이미실행을승인한것이아니다.

B/C/D의기본미충족요건에대해서는별도증거경로또는사용자의명시적범위/위험수용결정도필요하다. 필수providergate를해결했다고자동면제되지않는다. **Stage B BLOCKED 유지**.

## 6. 보존과 이번 종료

이번에읽은문서/코드/이전marker해시와193기존설치후보 재해시를static_evidence.json에기록했다. 원본전수파일재해시는이번에수행하지않으며선별입력과main HEAD/status를전후대조한다. 기존marker삭제·재생성/실행없음. 새runtime/attempt나소스·build는만들지않았다. 결과보고서·경량정적증거·인계만실험브랜치에기록하며main/기존code/evidence는보존한다. /tmp ignored원본은Git만으로다른기기에옮겨지지않는다. 조사결과보고후멈추고구현이나빌드로진행하지않는다.
