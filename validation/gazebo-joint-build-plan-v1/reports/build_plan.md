# 별도 Gazebo 계측 공동 빌드 계획

2026-11-08 UTC. **BLOCKED (입력 고정 미완료) / NOT_RUNTIME_VERIFIED / Stage B BLOCKED / 위험 수용 미결정**.
시작 HEAD `64ada5acd9a28ca1af5c3a6590e51317dc379551`, experiment/dart-internal-trace, clean 직접 확인. AGENTS.md, docs/DEVELOPMENT_RULES.md, handoff.md, 기존 reassessment.md/build_gate.md를 읽었다. 이번 변경은 계획/입력 검증 문서뿐이다. configure도 수행하지 않았다. 이 문서는 기존 판정을 덮어쓰지 않는 별도 구성의 계획이다.

## 1. 확정한 공동 범위와 재사용 판정

|경계|교환 타입·소유권|결정|
|---|---|---|
|전용 harness ↔ Sim core ↔ Physics|UpdateInfo/ECM C++ 참조, 동기 초기화 interface와 callback; ECM/Physics는 Sim 인스턴스 소유|Sim 8.15.0 한 소스에서 core, Physics system, 전용 harness 공동 빌드. 설치 core/system 혼용 배제. 새 interface 양쪽을 같은 헤더/도구로 빌드|
|Physics ↔ gz-physics core/dartsim|EntityPtr proxy, plugin Pimpl, Identity(size_t 및 shared_ptr<void>), virtual feature/RTTI, Eigen/SDF 인자|7.8.0 공개/내부 헤더와 core/dartsim 공동 빌드. dartsim CMake의 필수 sdf/heightmap/mesh 구성도 같은 소스에서 포함. 다른 엔진은 제외 후보이며 옵션/타깃 확정 필요|
|RetrieveWorld ↔ native DART|WorldPtr(shared_ptr) 복사, world map의 같은 객체; plugin handle과 WorldPtr 관측 종료까지 보유|설치 DART 재사용 배제. DART core, collision-ode, collision-bullet 공동 빌드. FCL/DART detector 구현은 core에 포함|
|World ↔ solver ↔ detector|World 소유 solver의 borrowed pointer, detector shared_ptr, virtual const string& getter, Gz wrapper 다중 상속|동일 DART 헤더/생성 config/표준 라이브러리로 빌드; solver/detector 교체 금지. 사설 offset 접근 없음|
|DART core ↔ external-odelcpsolver|DART 소스 내 solver helper; 외부 libode와 다른 라이브러리|같은 DART 소스로 함께 빌드 확정. 설치 libdart-external-odelcpsolver 재사용 배제|
|DART ODE adapter ↔ 외부 ODE|adapter는 DART C++ detector 구현. libode는 dWorldID/dGeomID 등 opaque handles와 dReal 배열/구조체를 받는 C API; API 생성 객체는 대응 ODE destroy로 해제|adapter 재빌드 필수. 외부 ODE 자체 재빌드는 구조적으로 필수 아님. 단 matching headers/precision(dSINGLE/dDOUBLE), ABI 및 closure 고정 전 설치본 재사용 승인 불가. 현재 /usr/include/ode/ode.h 없음: 입력 차단|
|DART Bullet adapter 및 plugin ↔ 외부 Bullet|adapter는 DART 클래스. 외부 BulletCollision/LinearMath는 btCollisionWorld 등 C++ 객체·가상함수·btScalar/inline/SIMD/alignment 경계. plugin도 LinearMath 직접 참조 가능|adapter 재빌드 필수. 외부 Bullet 재빌드는 자동 필수 아님. 설치 3.24 runtime과 dev header/config 일치, BT_USE_DOUBLE_PRECISION/SIMD/alignment 검증이 전제. 헤더 존재만 확인; 재사용 미승인|
|그 밖의 설치 의존성|gz-plugin의 loader/interface/RTTI, gz-math/Eigen inline, sdformat14, gz-common5, FCL 0.7, octomap1.9, assimp5, transport/messages/protobuf 등 실제 C++ 타입 및 STL 경계|설치본 재사용 대상 후보. 각 dev/runtime 및 전이 closure를 고정하지 못해 확정 승인 목록은 비어 있음. 부적합하면 해당 경계를 공동 빌드로 확장하고 계획 재심사|

설치 libdart와 두 adapter가 DT_NEEDED에 모두 존재하는 근거는 validation/gazebo-abi-reassessment-v1/reports/elf_boundaries.json에 있다. 설치 구성을 따라 두 adapter를 포함하는 보수적 계획이다. 로딩된 adapter와 활성 detector는 별개다. 외부 ODE/Bullet을 무조건 재빌드하거나, 반대로 무조건 설치 재사용한다고 결론내리지 않는다. 현재 외부 소스를 추가 선택할 근거/고정 입력도 없다.

## 2. 빌드에 필요한 기존 입력만 선택

경로는 worktree 상대. `input_validation.json`에서 아래 archive/patch의 기존 SHA-256과 현재 bytes를 직접 대조했고 선택 항목 모두 MATCH. 출처 기록은 gazebo-source-materials-v1/reports/acquisition.json 및 download_hashes.json, gazebo-abi-reassessment-v1/reports/manual_downloads.json에 보존돼 있다.

|입력|고정 source/출처 및 SHA-256|
|---|---|
|Sim|OSRF noble source 8.15.0-1~noble, gazebo-source-materials-v1/work/downloads/sim.orig.tar.bz2: f457478cc8b319be148aa1e7a3bc14042c333c8881c1f92ea6d498344fea891d|
|Sim packaging|같은 downloads/sim.debian.tar.xz: fd14fe0cf6caeeadbae7c408b0a4b295137e175c70c304b56f615d15670bd806. DSC checksum과 기존 일치; patch series 없음|
|gz-physics|공식 OSRF S3 gz-physics/releases/gz-physics-7.8.0.tar.bz2, gazebo-abi-reassessment-v1/work/downloads/upstream-release.tar.bz2: 120b7ea6e1dd9c34515948de3c69ab5e27ab098e56379a3ef61a414c6e606927. 새 구성은 이 upstream을 선택. native 배포 source 동일성 주장 안 함|
|DART|OSRF noble 6.13.2+ds1 source, gazebo-source-materials-v1/work/downloads/dart.orig.tar.xz: b900820b71463476463b9daeb31e81c74ebf59bd95139b7f833f5f6bb9b8058e|
|DART packaging|동일 downloads/dart_6.13.2+ds1-1~osrf2~noble.debian.tar.xz: 6e9049fcf7c5ddf507dcebd51ccc4e39059376f0e802f7d60398251474295092|

DART 패치 순서(개별 SHA는 packaging_comparison.json 및 새 input_validation.json): disable-skeltest-for-armhf-mips-x86.patch → fix-test_ForceDependentSlip-armel.patch → 0001-respect-ldflags.patch → 0005-build-type-none.patch → 0002-use-system-gtest.patch → 0007-fix-ikfast.patch → 0004-fix-pkgconfig.patch → 0006-Reduce-test-result-accuracy-to-fix-i386.patch → 0013-Deaktivate-assert-failing-with-Bullet-3.24.patch. 순서대로 적용 후 tree digest 고정 필요. 이번에는 적용 안 함. 이후 DART typed observer patch → physics typed bridge/wrapper observer patch → Sim init/GO interface와 harness patch 순서로 고정할 계획이나 **이 세 patch의 내용/hash가 아직 없으므로 build input 미완성**. Sim/physics에 미확보 native patch를 추정 적용하지 않는다.

디버그 deb, 원 설치 buildinfo, historical pool 검색 결과, 설치본 복제 deb는 새 구성 빌드 필수 입력에서 제외한다. 기존 설치와 동일성 판단의 근거로만 보존한다. 이전 source/debug 일치 보고는 이번 재실행 결과가 아니다.

## 3. 도구·옵션·검색 경로의 고정 상태

직접 bytes 확인한 도구 후보는 /usr/bin/x86_64-linux-gnu-gcc-13, g++-13, ld.bfd, /usr/bin/cmake, /usr/bin/ninja, /usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33이며 SHA는 input_validation.json에 있다. **도구 파일 해시만으로 toolchain closure가 완성되지 않는다.** cc1/cc1plus/as/collect2, libgcc/crt, libc/loader, C++/C 헤더 전체, CMake modules, Ninja 및 설치 dev 의존 패키지 payload/버전·hash 목록을 고정해야 한다. compiler/linker 자체도 이번에 실행하지 않았다.

새 구성 정책: Ninja, shared libs, RelWithDebInfo, C++17(각 source와 의존성의 수용 여부 정적 확인 필요), RTTI/exception ON, LTO OFF, _GLIBCXX_USE_CXX11_ABI=1, Eigen/SIMD 정합. DART 후보 옵션은 BUILD_SHARED_LIBS=ON, DART_ENABLE_SIMD=OFF, DART_BUILD_GUI_OSG=OFF, DART_BUILD_EXTRAS=OFF, DART_BUILD_DARTPY=OFF. tests/examples/GUI/renderer 비활성화와 Sim 최소 target closure의 정확 옵션 이름·효과는 **미고정**. 부정확한 -D 옵션은 조용히 무시될 수 있으므로 READY 근거로 쓰지 않는다. physics DART_HAS_CONTACT_SURFACE_HEADER는 새 DART 헤더에서 검사한 결과를 고정해야 하며 설치 헤더 결과 재사용 금지. Bullet CMake가 precision 검사를 수행하는 것도 확인했다. configure의 compile/run probe 정책을 먼저 감사하고 try_run 또는 target 자동 실행은 별도 승인 없으면 차단한다.

산출물 루트 예약: validation/gazebo-joint-build-plan-v1/work/config-01/{src,build,prefix,logs,manifests}. 아직 생성/추출/빌드하지 않았다. build/dart, build/physics, build/sim, build/harness 분리. prefix는 그 루트/prefix만 허용; /usr 또는 기존 work 산출물에 쓰기 금지. source archive는 기존 경로에서 읽고 새 src에만 추출/패치할 후속 계획.

검색 정책: 새 prefix의 DART_DIR, gz-physics7_DIR, gz-sim8_DIR를 실제 생성 config 디렉터리의 절대경로로 지정; CMAKE_PREFIX_PATH 선두에 새 prefix; 패키지 registry OFF. /usr 전체를 금지하면 재사용 제3자도 막히므로 패키지별 config/include/library 절대경로 allowlist 필요. 각 compiler include 순서와 -L/-l 실제 해석을 manifest로 고정한다. DART headers/생성 config와 physics public/internal headers는 새 src/build/prefix만 허용. 설치 /usr/include/dart, 설치 DART config, 설치 gz-physics headers의 우선 발견은 즉시 중단. **현재 allowlist와 정확 *_DIR 경로가 없어 검색 경로 고정 미완료**. LD_LIBRARY_PATH만으로 격리됐다고 판정하지 않는다.

## 4. 순서·명령 계약과 중단 조건

BLOCKED이므로 아래는 후속 절차의 명령 형태이며 실행 가능한 완성 recipe가 아니다. 미정 값을 임의로 채워 configure하지 않는다. 정확 전체 configure argv/toolchain 파일/target 목록을 versioned manifest로 완성하는 것이 해소 조건이다. 현재 허용된 정적 재검사는 `git rev-parse HEAD`, `git status --short`, `sha256sum <input_validation.json에 명시된 각 절대 입력 경로>`, `readelf -d -n -V <명시된 ELF 경로>`이며 마지막 두 명령의 경로 목록은 manifest를 따른다. ldd/loader --list/target 실행은 사용하지 않는다.

1. 입력 게이트: 모든 archive/patch/toolchain/dependency dev+runtime hash 검증. 새 patch 내용/적용 순서/tree digest, 외부 ODE 헤더/precision와 Bullet ABI 대응을 고정. 하나라도 미해결이면 configure 전 중단.
2. 새 src에만 추출 후 배포 series → 계측 patches 적용. 적용 거부/fuzz/offset/예상 밖 tree diff면 중단. 기존 source는 수정 안 함. 이 단계는 향후 별도 승인 대상.
3. DART core+ODE/Bullet adapters+external-odelcpsolver → physics core+sdf/heightmap/mesh+dartsim → Sim core+Physics → harness 순서. 각 단계 명령 계약은 `cmake -S <고정 source> -B <전용 build> -G Ninja --toolchain <고정 파일> <고정 옵션 전부>`, `cmake --build <전용 build> --target <고정 타깃 전부> --parallel 2 --verbose`, `cmake --install <전용 build> --prefix <전용 prefix>`. 이 placeholder 계약은 READY 절차가 아니며 실제 target/config 경로·argv 확정 전 실행 금지. install은 별도 prefix 파일 배치만 의미하고 시스템 설치는 금지. custom commands/install scripts의 대상 실행 여부도 선행 감사한다.
4. configure 로그/CMakeCache/imported targets/generated config/compile_commands/link command/include dependencies/link map을 단계별 보존. dependency 누락으로 ODE/Bullet target이 자동 비활성화되거나 예상 밖 package/ContactSurface macro/표준/ABI가 선택되면 즉시 중단. unused -D 경고도 중단 사유.
5. 빌드 후 ELF별 SHA/Build ID/SONAME/DT_NEEDED/RPATH/RUNPATH/심볼 버전과 재귀 dependency graph 고정. 각 SONAME을 allowlist realpath/hash로 해석; 같은 SONAME의 다른 bytes, unresolved/중복 DART, 절대 /usr DART 경로, 설치 Physics/dartsim 선택 가능성이 있으면 거부. RUNPATH는 전이 적용되지 않으므로 각 DSO를 별도 확인. log의 -L 순서/실제 linker 입력 및 link map이 새 DART/core/adapters/LCP를 가리켜야 한다. 단 DT_NEEDED 문자열/Build ID만으로 선택 경로나 ABI가 증명되지 않는다.
6. plugin 검색은 의존성 graph와 별개: 새 dartsim 설치의 lib 및 engine-plugins 두 경로 realpath/hash가 같아야 하고 전용 harness의 명시 절대 plugin 경로 및 Sim system 경로만 허용. 설치 기본 검색 fallback의 코드 경로가 남으면 실행 게이트 차단. 정적 검증은 실제 runtime mapping을 증명하지 못한다. 향후 명시 실행 승인 후 backing ELF/mapping 관측 없이는 runtime 혼입 없음 PASS를 내리지 않는다.

컴파일/링크·상태기계 검사도 이번 수행 아님. 단계 3 이후에 별도 무실행 검증과 실행 승인안 검토가 필요하며 이번 요청으로 실행 승인이 생기지 않는다.

## 5. 패치 위치와 관측 설계

Sim src/SimulationRunner.cc Run(761행 시작)의 첫 UpdateCurrentInfo(890행)와 realtime 시작 전, 시스템 Configure가 끝난 동일 Physics 인스턴스에 동기 init callback을 호출하고 GO 장벽을 둔다. src/systems/physics/Physics.cc Update(1044~1045행)의 CreatePhysicsEntities/UpdatePhysics를 분리하고 CreatePhysicsEntities(1075행)만 init 1회 호출한다. 3208행의 추가 생성 경로도 포함해 정규 Update의 중복 생성과 link/joint bookkeeping을 감사한다. EachNew를 임의로 지우지 않는다. RunOnce/UpdatePhysics/Step은 bootstrap으로 사용하지 않는다. init 하위 경로가 무스텝임을 아직 검증하지 않았다.

동일 entityWorldMap → physics dartsim/src/World.hh RetrieveWorld → CustomFeatures.cc worlds.at(identity)의 shared_ptr 경로 사용. World/borrowed solver/shared detector를 typed getter로 연결하고 수명 유지. GzOde/GzBullet wrapper 및 DART dart/collision/ode/OdeCollisionDetector.cpp getType(132행), bullet/BulletCollisionDetector.cpp getType(131행), core FCL/DART detector의 대응 query entry에 관측 지점을 둔다. 정상 typed cast를 거친 this/base 조정과 호출별 method-entry anchor를 연결. getType 문자열만 기록하는 것은 부족하다. module-local anchor와 backing ELF hash/Build ID/mapping offset을 함께 확인한다. query 관측은 collide 실행 증거가 아니다. 외부 Bullet/ODE 함수가 query에서 호출되지 않으면 그 실제 실행 provider는 NOT_OBSERVED로 남기고 충돌을 일으켜 증거를 만들지 않는다.

GO 전후 Sim iteration/time=0, native frame/time=0, init count=1, 단일 world와 동일 solver/detector/provider를 요구. init 실패/null/복수 world/feature 누락/관측 불일치/timeout/EOF/GO 오류에는 Step 없이 종료. 대기 중 ECM/제어/reset/추가 plugin 변경 차단, Run 및 Physics Step 양 경계에 GO 조건 필요. marker는 새로 만들거나 소비하지 않는다. 이 불변식은 설계이며 PASS 아님.

## 6. 최종 판정 및 해소 조건

**설치본과의 일치: PARTIAL source/header/binary identity, mixed ABI UNRESOLVED.** Sim source provenance/debug의 기존 근거는 유지하지만 원 설치 flags/buildinfo와 physics native payload/DART ABI 미해결. 원 설치의 재현 빌드라고 주장하지 않는다.

**별도 구성 자체의 재현 가능성: BLOCKED.** (a) 계측 세 patch와 harness source/hash, (b) 외부 ODE dev headers/config 및 runtime 대응, (c) Bullet precision/SIMD/header/runtime 대응, (d) 나머지 C++ 경계별 dependency allowlist와 transitive dev/runtime hashes, (e) toolchain 전체 closure, (f) 정확 CMake argv/타깃/생성 config 기대값/검색 경로가 미고정이다. matching 원 설치 debug/buildinfo 자체는 새 구성 READY의 필수 조건이 아니다. 위 새 구성 입력을 고정하거나 재사용 불가 경계를 소스 공동 빌드로 확장해 같은 기준으로 닫아야 해소된다. 자료 부족을 이유로 무제한 다운로드/전체 Gazebo 재빌드를 요구하지 않는다.

직접 검증: input_validation.json의 선택 archive/patch hash 모두 일치, ODE header 부재, 도구 후보 bytes, 시작 Git/브랜치 확인. 기존71개 보존 검사는 이전 보고 결과이며 이번 재실행 아님. main metadata는 input_validation.json에 보존. 기존 source/evidence/marker에 쓰지 않았다. 같은 사용자 project-CWD 작업 없음(스킬 snapshot); 외부 CWD/원격/컨테이너 UNKNOWN. 원시 자료는 ignored local 경로 및 /tmp에 있고 Git push가 전송/영속 보관을 보장하지 않는다.

참조: validation/gazebo-abi-reassessment-v1/reports/{reassessment.md,elf_boundaries.json}, validation/gazebo-instrumented-prestep-v1/reports/build_gate.md, validation/gazebo-source-materials-v1/reports/{packaging_comparison.json,download_hashes.json,static_line_evidence.json}. 모든 경로는 프로젝트 루트 기준이다.

이후 계측 결과는 이 공동 빌드 구성의 최종 manifest/hash에만 귀속한다. 원 설치 Gazebo/DART 또는 production 전체로 일반화하지 않는다. 소스 패치 적용/컴파일/링크/대상 로딩·실행/서비스/marker 소비/sudo/패키지/시스템 변경 없이 계획 및 입력 검증 후 종료. Stage B BLOCKED, 위험 수용 미결정 유지.
