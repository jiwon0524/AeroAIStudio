# 외부 리소스 경로 검토 및 ODE 초기화 실패 수정

## 판정

**PARTIALLY_RESOLVED / EXTERNAL_RESOURCE_CLOSURE_BLOCKED. Stage B BLOCKED, 위험 수용 UNDECIDED, 실제 런타임 UNVERIFIED.**

시작 HEAD는 요청한 `2ee5c8a744ff903c349f55d349872d9ea8221e2e`와 일치했다. tracked/index clean, 기존 dangling plugin symlink만 untracked였다. context-handoff 스킬 및 현재 AGENTS/DEVELOPMENT_RULES/인계/계약 보고서를 읽고 봉인된 입력 전체를 contract.validate로 대조했다. 기존 237 source/object 바인딩과 경로별 source hash를 다시 검증했다.

이번에 발견한 NDEBUG 초기화 오류는 후보 ELF에서 수정했다. 외부 접근 전체를 차단했다고 주장하지 않는다. 기존 launcher는 manager 조회·service·marker 전에 exit 78을 유지한다. 실행 검토안은 제출하지 않는다.

## 경로별 결과

정확한 코드 경로·행·해시, provider ELF 해시 및 mount alias는 `review.json`에 있다. 분류는 해당 행의 제한된 호출 범위에만 적용된다. 라이브러리의 계약 내 배치는 실제 매핑이나 실제 호출 관측이 아니다.

|경로 / 시점|분류|근거 및 남은 조건|
|---|---|---|
|ODE 초기화 / 시작|미확인; 반환 실패 처리만 후보에서 해소|선택된 DART 생성자는 dInitODE2, dAllocateODEDataForThread, dWorldCreate를 호출한다. libode 내부 TLS/allocator/오류 callback의 파일·설정·네트워크·로더 접근은 구현/바이너리 연결 근거가 부족하다.|
|ODE primitive 및 충돌 / 시작·100스텝|미확인|box는 dCreateBox 경로다. dSpaceCollide→CollisionCallback→dCollide의 실제 callback 횟수는 pair 생성에 달렸다. 접촉이 없을 예상만으로 broadphase나 외부 callback을 제외하지 않는다.|
|기본 FCL / 시작·종료|미확인|ConstraintSolver가 기본 DART FCL wrapper를 먼저 생성한다. 다만 검토한 wrapper 생성자 자체는 DART ManagerForSharableCollisionObjects 생성이며, 이 사실만으로 외부 FCL geometry/collision이 호출됐다고 단정할 수 없다. ELF 전역 생성/해제·지원 의존성은 별도 미해결이다. 이전 보고서의 포괄적인 FCL 언급을 이 범위로 좁힌다.|
|crypto / digest·provider 검사·종료|미확인|VerifyAnchor의 EVP_DigestInit_ex/EVP_sha256 및 native SHA256은 실제 소스상 호출이다. libcrypto 내부 provider/config 탐색·모듈 로딩 여부는 확인되지 않았다. openssl.cnf가 mount되지 않는다는 사실은 fallback 시도 검출이 아니다.|
|transport / 시작·동시 작업·100스텝·종료|미확인|유효한 고정 world에서 ParametersRegistry, Node 생성, Advertise, clock/stats publisher API를 거친다. transport/ZeroMQ 내부 socket/bind/connect/config/discovery와 thread 종료 경로의 사전 차단이 없다. peer 부재·독립 network namespace로 시도 자체를 배제하지 않는다.|
|record/playback 플러그인 / 시작|도달 불가 — 고정 harness 범위|ServerConfig 기본 record=false/playback=""이고 harness가 변경하지 않는다. LoadLoggingPlugins의 목록은 비어 있다. console 및 transport logging까지 제외하는 결론은 아니다.|
|console 및 지원 logging / 전 수명|미확인|gz-common stream의 sink 초기화/파일 탐색/종료 구현이 실제 빌드에 연결되지 않았다. ServerControl stop-thread의 gzlog 문장은 요청 조건부이며 실제 실행으로 분류하지 않는다.|
|Sim 플러그인 entrypoint / seal 후 전 수명|접근 전에 차단|기존 CheckLoadRequest가 lookup/open/LoadLib 전에 실패한다. native failed latch와 fatal packet 판정은 유지된다. 다른 DSO가 직접 수행하는 dlopen/open/socket까지 감싼다는 뜻은 아니다.|
|schema/config/plugin 필수 읽기 / 시작|고정된 입력·출력만 허용|기존 FD regular/device/inode/hash/parse/include/provider 결과를 재사용한다. 누락/대체/실패는 complete 및 ready/GO를 허용하지 않는다. 외부 DSO 전체 파일 열기의 allowlist는 아니다.|
|mesh·LocalResource·IKFast / 고정 명목 경로|도달 불가 — 제한된 분기|고정 box에 mesh/include/URI가 없고 IKFast를 구성하지 않는다. 기존 경로 근거를 해시로 재검증했다. 임의 callback/새 entity에 대한 전체 프로그램 증명은 아니다.|
|종료 / EXIT_ACK 이후|미확인|harness barrier 뒤에 Server local destructor, plugin/global destructor가 남는다. dWorldDestroy/dCloseODE/dSpaceDestroy, crypto·transport·allocator·DSO destructor의 접근 범위가 닫히지 않았다. ACK는 종료 완료 증거가 아니다.|

ELF별 open/socket/connect/bind/dlopen/config 관련 undefined symbol 목록은 후보 지점 목록일 뿐이다. import 부재로 syscall/간접 호출 부재를 증명하지 않고, import 존재로 고정 경로에서 호출됐다고 단정하지 않는다. 외부 source/build receipt가 없는 호출의 내부 fopen/connect 위치를 추정해 작성하지 않았다. 정확히 확인한 마지막 호출 경계와 필요한 해소 조건을 남겼다.

## 최소 수정과 컴파일 경계

실제 사용 빌드의 `-DNDEBUG`에서 OdeCollisionDetector 생성자의 assert(initialized), assert(mWorldId)는 제거된다. dAllocateODEDataForThread 반환값도 무시됐다. 별도 후보 소스에서 세 반환 실패를 기존 `aero_resource::Fail`로 연결했다. thread/world 실패 시 성공한 ODE 초기화를 dCloseODE로 정리하고 실패 latch/예외를 발생시킨다. dCloseODE 자체의 내부 접근·예외/프로세스 종료 특성은 여전히 미확인이다. 이 수정은 ODE 내부 접근 전에 가로채는 guard가 아니다.

`ode_init_guard.patch`, `build_receipt.json` 참조. ODE wrapper TU 1개만 컴파일하고 ODE DSO 1개만 링크했다. 나머지 10개 object를 기존 해시로 재사용했다. 원래 빌드 ELF가 현재 계약의 실제 배치 ELF와 같은 hash임을 확인했다. DART core, physics, Sim, harness, libode, FCL, crypto는 재빌드하지 않았다. 공개 export 이름 동일, 헤더/클래스 배치/가상 인터페이스 및 정상 경로 수치 연산 변경 없음. 추가 undefined symbol은 기존 native ledger의 Fail 하나다. 기존 native observer DSO를 새 직접 의존성으로 링크했다. 이름 비교는 전체 ABI 인증이 아니며 exception/cleanup 동작은 실행 미검증이다.

`candidate_deployment.json`과 canonical JSON의 `candidate_deployment.sha256`은 기존 ODE namespace alias 2개에 대한 후보 ELF hash/device/inode 및 새 native dependency를 기록한다. 후보는 **NOT_DEPLOYED / NOT_RELEASED**다. 기존 manifest/봉인·allowlist·provider expectation·attestor를 부분 갱신하지 않았다. 이들은 모두 원래 ELF를 계속 요구하며 부분 mount 교체는 검사에서 거부된다. 외부 호출 차단을 먼저 해소한 뒤 전체 projection을 일괄 재봉인해야 한다. 이 미완료 배치 작업을 준비 완료로 보고하지 않는다.

## 검증 및 보존

기존 31개 정적·모의 검사를 원본 source로 재사용했고 report 출력 및 임시 디렉터리만 이번 단계로 돌렸다. 원본 source/31-case report/manifest/seal/final report는 변경하지 않았다. 추가 25개 negative case는 시작 단계 fatal 3종과 GO 거부, 필수 config/provider/graph 누락, ACK 뒤 파일 fallback/network/load/fatal 및 EOF·exit·정리 성공으로도 실패 latch가 복구되지 않음, 후보 ELF 부분 배치 거부를 검사한다. `tests.json`, `reused_tests.json` 참조.

컴파일된 object의 dInitODE2/dAllocateODEDataForThread/dWorldCreate 및 Fail call relocation 3곳을 objdump로 확인했다. **native 실패 injection을 실행하지 않았다.** 생성 패킷 검사는 수집 정책 증거이며 외부 DSO의 실제 syscall 가로채기 증거가 아니다.

기존 ready_state → GO → 100×1ms → 마지막 live mapping → EXIT_ACK → 양쪽 EOF·exit0·소유한 작업 정리 조건은 변경하지 않았다. Clock/Capture 기준 및 기존 한도는 그대로다. ACK 후 위반이 관측되면 EOF/exit/정리 성공과 무관하게 실패다. 관측 패킷을 내지 않는 외부 요청까지 감지된다고 주장하지 않는다.

main HEAD/status 및 dirty/untracked 일반 파일 해시, 기존 dangling symlink inode/target, 봉인된 mount/code 입력 전체를 검사 전후 보존 확인했다. 기존 output/one-shot 부재 조건을 재검증했고 역사적 marker는 소비하지 않았다. Gazebo/DART 로딩, harness/harmless 실행, step, service 시작, sudo/install/system 변경을 하지 않았다.

## 남은 작업과 실행에서만 얻을 증거

1. 실제 libode/libccd, crypto provider/config/cleanup, gz-transport/ZeroMQ/gz-common 및 DSO 전역 init/destruction의 matching source→binary→callback 범위를 확보하거나, 정확한 구성요소에서 모든 thread 및 종료까지 유효한 접근 전 guard를 구현해야 한다. libc symbol interposition만으로 직접 syscall/dlmopen/간접 경로가 덮인다고 보지 않는다.
2. 필수 시작 입력을 명시하고 필요 없는 설정 탐색·네트워크·동적 로딩을 사전 거부하며, 거부 시도를 ready/GO/종료 수집기의 실패 latch에 연결해야 한다. 현재 namespace 누락/네트워크 차단만으로 이 요구가 충족되지 않는다.
3. 위 조건 이후에만 후보 전체 계약을 재봉인하고 deployment/ABI 소비자 검토를 마친다. 아직 1회 실행 명령이나 승인 요청을 만들 단계가 아니다.

실제 mount/cgroup/readback, loader/provider 및 native 결과, 동일 PID/start/maps, 전체 수명 접근 거부 효과, 실제 100스텝/freefall/시간·리소스 한도, ACK/EOF/exit/소유한 정리·무결성은 런타임 증거다. 별도로 Bullet lifetime/destructor, allocator balance, C-exception cleanup의 잔여 위험 수용은 사용자 미결정이다. 기술 차단 해소와 위험 수용·실제 실행 승인을 혼합하지 않는다.

재현: `python3 validation/gazebo-joint-external-review-v1/scripts/review.py`, `scripts/build_init_guard.py`, `scripts/candidate_receipt.py`, `tests/check_review.py` (후자의 세 경로도 동일 phase 아래). 컴파일은 target 실행을 하지 않는다. 빌드/정적 검사 원본은 work에 보존한다. /tmp 소스/object/ELF/원시 로그와 기존 ignored/untracked 증거는 host-local이며 Git 게시로 전달되지 않는다.
