# 계측 구성 ABI 차단 재검토

2026-11-08 UTC. **자료 확보 PARTIAL / 혼합 ABI UNRESOLVED / Stage B BLOCKED / 위험 수용 미결정**.
시작 HEAD `5ebadc2f6fc7cbcecd0b293f6d24ea68d3ea5dfc`, experiment/dart-internal-trace clean. AGENTS.md, DEVELOPMENT_RULES, handoff, build_gate, material_review 및 context-handoff를 읽고 대조했다. 현재 요청은 자료 확보/추출/정적 비교만 허용한다. 기존 build_gate를 덮어쓰지 않고 이 문서로 판정을 세분화한다. 소스 수정·patch 적용·configure/build·대상 load/run·서비스·marker 생성/소비·sudo/설치/시스템/main 변경 없음. 추출 패키지에 포함된 테스트 ELF도 실행하지 않았다.

## 1. 실제 경계, 소유권, 요구 근거

|경계|실제 교환 계약과 수명|이번 근거 / 미확인|
|---|---|---|
|계측 Sim core ↔ Physics system|ECM/UpdateInfo와 새 동기 초기화 callback의 C++ 참조/함수 객체. Physics 내부 engine/entityWorldMap은 해당 인스턴스가 유지|기존 Sim source/debug 연결은 재사용. 새 interface는 아직 없으므로 양쪽을 동일 source/header/toolchain으로 빌드할 후보. 설치 core와 수정 system을 혼용할 근거 없음|
|Physics ↔ 공개 gz-physics feature/core/plugin|gz::plugin plugin handle → RequestEngine<policy,features>::From → EnginePtr/WorldPtr(EntityPtr proxy). plugin interface의 virtual method에 Identity 및 feature별 인자를 전달. Identity는 size_t id + const shared_ptr<void> ref(선택적 수명 참조). Entity proxy는 plugin Pimpl과 Identity를 보유. 단순 정수 핸들/C ABI가 아님|설치 core-dev 101개 파일 byte MATCH, 그중 release source와 대응하는97개 MATCH. core/plugin package ELF byte MATCH. 이것은 공개 header 일치 근거. gz-plugin QueryInterface/RTTI, virtual inheritance/this 조정, Identity/shared_ptr, 정책/feature template, Eigen/SDF/STL 등 실제 전달 인자, C++ ABI/flags/의존 헤더 closure 일치 검사는 미완료|
|추가 RetrieveWorld 경계|동일 entityWorldMap world proxy → Interface<RetrieveWorld> → virtual GetDartsimWorld(const Identity&) → dart::simulation::WorldPtr by value(std::shared_ptr<World>). CustomFeatures는 worlds.at(id)의 기존 shared_ptr를 복사. 독립 World 생성/소유권 이전 아님. WorldPtr와 plugin handle을 관측 종료까지 보유해야 함|공급자 release의 World.hh/CustomFeatures는 이전 tag와 byte MATCH. 내부 feature는 dartsim-dev 설치 header에 없음. 내부 Feature/Implementation virtual 계약, RTTI/등록과 설치 plugin 빌드 대응 미인증. export/thunk만으로 완료 불가|
|plugin/native world ↔ DART solver|WorldPtr → World::getConstraintSolver()의 borrowed ConstraintSolver*. source상 World가 unique ownership으로 solver를 유지하며 getter는 get() 반환. 관측 중 solver 교체/World 제거 금지|확보 DART source에서 타입/ownership 확인. 설치 DART는 6.13.2+ds1-1~osrf2~noble. public non-inline getter 호출이라 World private offset을 추정할 필요 없음. 그렇다고 compiler/헤더/feature macro와 객체 ABI 검증이 완료된 것은 아님|
|solver ↔ detector/provider|getCollisionDetector()는 shared_ptr<CollisionDetector> 복사; solver도 detector를 보유. virtual getType()은 const std::string&를 반환. wrapper GzOde/GzBullet는 DART adapter + GzCollisionDetector 다중 상속. collide는 group/option/result 등의 DART 타입을 받고 base에 위임|DART core/adapter의 RTTI/vtable/base layout, shared_ptr 소멸/control block, string dual ABI, exception/unwind, 외부 Bullet/ODE/FCL 및 Eigen 구성 근거 필요. getType/RTTI 심볼 존재는 이 계약 전체의 증명 아님. 활성 객체/provider는 실행 전 UNVERIFIED|

Identity/Entity/RequestEngine은 설치 include와 release source를 직접 읽었다. DART World.hpp/ConstraintSolver.hpp와 각 getter source도 직접 읽었다. 이는 소스 수준 계약이며 실제 관측을 주장하지 않는다. source 내부 ReferenceInterface의 구현을 확인했을 뿐 외부에서 ref를 사설 객체로 cast하지 않는다. private layout/vtable slot/offset 추정은 사용하지 않았다.

## 2. 확보 자료와 판정 분리

설치 physics 패키지 버전은 dpkg-query로 `7.8.0-1~noble` 재확인. 고정 기준은 기존 material_inventory/input_audit의 hash/Build ID를 재사용했다. plugin ID `c53e1a304ceb0f0dac85ff0e4872d0ffc50a28ac`, feature core ID `4e60105d86d50ee9e394f6c461411e3cba5eeec1`. 설치 DART ID/hash는 기존 inventory 및 새 elf_boundaries.json 참조.

검색에서 공급자 ubuntu pool의7.8.0 과거 색인이 나왔으나 실제 GET은 현재7.9.0이며7.8.0 URL은404였다. ubuntu/ubuntu-stable/ubuntu-prerelease의 정확 native DSC/archive/buildinfo/changes 및 dbg 후보 모두404. Ubuntu debuginfod의 위 두 Build ID 조회도404. 이는 조사 URL 범위의 부재이며 세계 어디에도 없다는 판정이 아니다. buildfarm-config.json은 현재 release-tools 디렉터리 metadata일 뿐 해당 binary의 빌드 로그/환경이 아니다.

새로 찾은 공식 보관소는 [Gazebo distributions](https://classic.gazebosim.org/distributions/gz-physics/releases/)가 연결한 `https://osrf-distributions.s3.us-east-1.amazonaws.com/`다. paginated 목록을 확인해 releases/libgz-physics7 prefix의 모든 key를 보존했다. 정확 native source prefix gz-physics7_7.8.0은 비어 있고 해당 libgz prefix에 dbg key는 없었다. classic URL로 직접 받은 HTTP200 body는 HTML이므로 archive로 인정하지 않았다.

|자료|획득/일치 판정|ABI 의미|
|---|---|---|
|공식 gz-physics-7.8.0.tar.bz2|다운로드·안전 추출 완료. 기존 GitHub tag와 공통 파일464개 byte 일치, 차이0. release-only 목록은 static_comparison.json|upstream release identity 보강. native Debian source payload 또는 설치 binary 재현 증명은 아님|
|libgz-physics7-core-dev_7.8.0-1~noble_amd64.deb|다운로드/추출.101 설치 include 파일 전부 동일, source에 대응하는97개도 동일|공개 interface header 근거 강화. plugin이 실제 어떤 전체 headers/flags로 빌드됐는지는 미확인|
|libgz-physics7-dartsim-dev_7.8.0-1~noble_amd64.deb|다운로드/추출. 내부 RetrieveWorld header 미포함|내부 feature 계약의 빈칸은 유지|
|libgz-physics7 및 dartsim exact noble binary deb|추출 core/plugin SHA/Build ID가 기존 설치 기준과 일치. plugin의 두 설치 경로도 동일 bytes|공급자 보관 binary와 설치 ELF 연결 SUPPORTED. source/debug/ABI 인증과 별개|
|native DSC/tar.xz, 배포 patch payload|미확보. 이전 release packaging commit과 무patch-series 조사 결과 재사용|source package 일치 UNRESOLVED. upstream release와 packaging commit을 조합해 native payload MATCH로 표시하지 않음|
|matching debug/DWZ, buildinfo/changes/build log|새로 확보 못함.2개 ID의 Ubuntu debuginfod404|debug ↔ 설치 ELF 일치 NOT_ESTABLISHED. 버전/ID 문자열만으로 debug를 확보했다고 하지 않음|

출처·bytes·SHA는 acquisition.json, s3_acquisition.json, manual_downloads.json. 안전 추출은 tarfile data filter / dpkg-deb --extract만 사용했고 maintainer script/원격 코드 실행 없음. 공식 HTTPS와 byte identity 근거이며 별도 GPG archive 서명 검증이나 공급자 build attestation은 아니다. 소스/패키지 원본·raw listing은 ignored work/downloads와 work/extracted 아래에 있다.

## 3. 재사용과 최소 공동 빌드 범위

**혼합 구성 전체 SUPPORTED로 승격하지 않는다.** 공개 feature header와 공급자 binary identity는 보강됐으나 새 RetrieveWorld/native DART 경계의 ABI 및 provider 관측을 충족하지 못했다. 공개 gz-physics 경로만 쓰는 기존 Sim 설계를 내부 feature 확장까지 자동 인증하는 것은 부적절하다. 기존 설치 core/plugin/DART 쌍의 출처 기준점 재사용은 가능하나, 새 계측 client와의 혼합 호환성 또는 실행 승인은 아니다.

이전 build_gate의 “확장 plugin/adapter 재빌드도 거부”는 **설치본과 동일한 출처/ABI를 주장하는 조합에 대한 차단**으로 좁힌다. 별도 source-built 실험 구성을 만드는 데 원 설치 buildinfo가 반드시 있어야 하는 것은 아니다. 대신 새 구성 자체의 source/patch/toolchain/header/generated config와 closure를 고정해 증명해야 한다. 현재 요청은 빌드를 허용하지 않으므로 아래는 차후 후보 범위다.

1. Sim core + Physics system + 전용 server/harness: 동일 Sim8.15.0 source에서 init interface 양쪽 공동 빌드. GUI/렌더러/전체 Gazebo 재빌드는 필수라고 단정하지 않는다.
2. gz-physics7 feature core + dartsim plugin: 같은7.8.0 source/public+internal feature headers로 공동 빌드. 새 typed observer/GO hook은 이 조합 안에 둔다. core 재사용을 줄이려면 Identity/공개 ABI 경계를 별도 입증해야 하며 현재는 보수적 공동 범위에 포함한다. 새 diagnostic interface로 DART native shared_ptr를 Sim에 넘기지 않도록 설계하면 경계를 줄일 수 있으나 아직 구현/검증하지 않았다.
3. DART core + provider adapters: 고정6.13.2+ds1 source와 배포9 patches 및 새 생성 config에 맞춰 공동 빌드. **현재 plugin의 DT_NEEDED에는 Bullet와 ODE adapter가 모두 있으므로** ODE가 기본 후보라는 이유로 Bullet를 제외할 수 없다. 최소 보수 범위는 core + ODE + Bullet이며 source상 FCL/DART detector는 core. provider 선택을 제한하도록 plugin 구성을 바꾸는 대안은 새로운 scope/감사 대상이다. 동적 로딩은 실제 활성 detector 증거가 아니다.
4. DART external ODE LCP 및 그 밖의 의존성: core의 DT_NEEDED에 external-odelcpsolver, FCL/octomap/assimp 등이 있고 adapters는 Bullet/ODE에 의존. 이들 전부 재빌드를 자동 요구하지는 않는다. 설치 ELF를 재사용하려면 해당 **실제 호출 경계**와 헤더/ABI/flags/버전/closure 근거를 고정해야 한다. external ODE LCP의 재사용 근거가 부족하면 동일 DART source로 함께 빌드하는 것이 후보. 위 네 대상의 공동 빌드만으로 모든 제3자 C++ ABI가 해결되는 것은 아니다.

즉 현재 증거에서 무조건 인증된 설치 재사용 목록은 없다. 공동 빌드 범위도 “자동 빌드 승인”이 아니며, 새 build-input manifest에서 transitive boundary를 닫은 뒤 확정한다. source identity가 설치와 다르거나 계측으로 초기화 순서가 바뀌는 결과는 **별도 계측 구성에 귀속**, 원 설치 Gazebo/DART 전체 runtime 검증이나 위험 수용으로 승격하지 않는다.

## 4. 빌드 재개 조건과 종료

혼합 경로를 유지하려면 native source/patch 및 가능하면 matching debug/build metadata를 추가 확보하거나, 실제 교환 타입의 layout/virtual inheritance/inline/template/RTTI/ownership/compiler 설정을 대체 근거로 입증해야 한다. debug/buildinfo 자체도 만능 ABI 인증서는 아니다. 이 조건을 만족하지 못하면 위 공동 빌드 경로의 source hashes/patch series/새 toolchain·generated macros·dependency headers/ELF closure를 먼저 고정하고 설치 경계별 재사용 여부를 명시한다. 목표 source 수정/빌드에는 별도 사용자 요청이 필요하다.

후속 provider observer는 같은 Sim-owned world/detector에 대한 typed this와 실제 query method entry/anchor, mapping 및 backing ELF hash/ID를 연결해야 한다. 설정/getType 문자열/RTTI 모듈 존재만으로 활성 구현을 단정하지 않는다. GO 전 collide/Step, paused RunOnce, private offset 접근은 허용되지 않는다. iteration0/time0, init1회, 실패/GO timeout/관측 누락 시 무스텝 종료는 여전히 미구현/미검증이다.

비실행 검사: static_comparison.json에 기존71개 선택 파일 보존 PASS와 main HEAD/status 유지 기록. 기존 원본 보고서/marker/ELF는 변경하지 않았다. header_source_comparison.json은97개 source-header 일치. 외부 deb에 든19개 ELF 경로를 readelf/bytes로만 확인(중복 plugin 경로와 실행하지 않은 COMMON_TEST 포함). JSON/링크/diff 검사 수행, compile/mock/runtime test 없음. 전체 ignored tree 무결성을 주장하지 않는다. snapshot에서 같은 사용자 project-CWD 작업 없음; 외부 CWD/원격/컨테이너 UNKNOWN. 계정/기존 작업 종료·재시작 없음.

새 scripts는 다운로드/정적 비교 도구이며 대상 소스는 수정하지 않았다. 새 경량 reports/scripts와 handoff만 실험 브랜치에 게시한다. ignored 다운로드/추출물과 /tmp 원본은 Git으로 전송되지 않으며 영속성은 보장되지 않는다. 서비스 시작/marker 생성 전 거부 유지, 기존 실행 계약·Clock/Capture/자유낙하 기준 불변. **Stage B BLOCKED / NOT_RUNTIME_VERIFIED / 위험 수용 미결정**. 이번 자료 확보·비실행 대조 후 멈춘다.
