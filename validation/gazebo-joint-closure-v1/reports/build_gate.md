# Gazebo 공동 빌드 진입 게이트

2026-11-08 UTC. 시작 HEAD `0a0ff67dac42a3956fb64441741918cc2c8bd9e4`, experiment/dart-internal-trace, clean 직접 확인. AGENTS.md, DEVELOPMENT_RULES, handoff, input_gate, build_plan을 먼저 읽고 context-handoff 사용. 기존18개 패키지, ODE/Bullet 대응과 toolchain 증거를 재사용했다. 새 다운로드/시스템 설치 없음.

**READY_FOR_BUILD — 고정 입력과 정적 준비 게이트만 해당. NOT_EXECUTION_READY / NOT_RUNTIME_VERIFIED. Stage B BLOCKED / 위험 수용 미결정.**

|남은 항목|판정|근거|
|---|---|---|
|의존성 선택·배치 준비|RESOLVED|dependency_lock.json/package_lock.tsv, 로컬 selected_files/import_graph/elf_graph, install-selected.cmake, check_selection.py/compile_gate.py/audit_outputs.py/stage_receipt.py, 정확한 build_commands.json/txt|
|초기화·harness 연결|RESOLVED (고정 fixture의 정적 입력 범위)|initialization_review.md/call_path_locations.json, 새 독립 patch3개와 telemetry/broker/harness, patch_checks.json, ordered_patch_checks.json, direct_include_check.json, validation.json|

READY는 이번에 source application/configure/build를 실행한다는 뜻이 아니다. 현재 요청 범위는 준비/정적 검증으로 끝낸다. 실제 source 적용과 빌드에는 다음 명시적 허용이 필요하다. 실제 CMake 선택/생성 결과는 아직 존재하지 않으므로 아래 후속 게이트에서 실패하면 빌드를 중단한다. 그 미생성 결과를 현재 입력 누락과 혼동하지 않았다.

## 입력 및 경계별 선택

|소비자|공동 빌드 산출물|추출18개 패키지에서 선택|허용된 설치 의존성/타깃 범위|
|---|---|---|---|
|probe|aero-joint-probe shared DSO|없음|OpenSSL::Crypto, libdl, 고정 libc/libstdc++/libgcc|
|DART|dart, external-odelcpsolver, collision-ode, collision-bullet, utils, utils-urdf|ODE double의 header/libode.so.8, Bullet float의 headers 및 Math/Collision/Dynamics/SoftBody 표준 .so.3.24, fcl/ccd/octomap/octomath, urdfdom/headers/console_bridge dev+runtime|Eigen3::Eigen, assimp, fmt/spdlog, tinyxml2와 고정 toolchain. FindBullet MODULE과 명시 네 library 경로로 float64 branch 배제|
|gz-physics|core + sdf/mesh/heightmap/dartsim interface + dartsim-plugin|앞 단계 DART의 외부 의존성을 전이 참조|gz-plugin2 loader/register, gz-common5의 geospatial/graphics/profiler, gz-math7::eigen3, gz-utils2, sdformat14 및 각 고정 public SDK 의존성|
|Sim|gz-sim8 core + Physics system|새 DART/physics interface의 native header와 전이 closure|gz-transport13 log/parameters, gz-msgs10, common/math/plugin/utils, sdformat14, Fuel/GUI/Qt/sensors/rendering의 configure 의존성. GUI/renderer/sensor system binary 자체를 공동 빌드나 런타임 대상으로 추가하지 않음|
|harness|aero-joint-harness|위 공동 stack의 public headers/native bridge|새 Sim target만 직접 링크. fixture와 기존 mapping/GO/acceptance 정책은 reuse_files.json으로 고정|

DART core/두 adapter/LCP와 Sim/physics의 설치본 재사용은 허용하지 않는다. ODE/Bullet은 **외부 library**만 이전 대응 근거로 재사용한다. 새 source-built 결과는 원 설치 재현 판정과 분리한다.

소스는 source_plan.json에 archive 경로/버전/SHA/루트/patch 순서/수정 후 기대 파일 SHA로 고정했다. Sim8.15.0, upstream physics7.8.0, DART6.13.2+ds1 및 배포9 patches → 새01 patch, physics02, Sim03 순서다. 원 설치 physics native payload/buildinfo와 같다고 주장하지 않는다. 독립 입력26개와 실행 권한 mode의 SHA는 input_files.json. 기존 생성기/후보는 보존하고 새 validation/gazebo-joint-closure-v1에서 작업했다.

## 정적 의존성 대조와 배치

실제 installed dev root28개에서 Depends/Pre-Depends를 정적으로 추적한 package version 목록은 package_lock.tsv. 이 host의706개 package metadata가 재사용 후보의 상한이다. 모든 package 내용을 prefix로 복사하거나 전부 런타임에 필요하다고 주장하지 않는다. 선택한 configuration/header/archive/codegen/template/ELF 파일34112개를 hash-pin했고, config1623개에서 find-package/target-ref/import-location 전이 참조를 기록했다. 패키지 root 누락0, 전이된 금지 stack package/ELF0, 정적 ELF 후보1261개의 unresolved DT_NEEDED0. 소수 OGRE driver plugin은 이 고정 Physics-only scene에서 선택/로드하지 않는 별도 dynamic plugin이므로 ELF seed에서 제외했다. 그 파일이 실제 선택/매핑되면 후속 선택/실행 게이트에서 별도로 거부/검토해야 한다.

이 수치는 필수 runtime의 최소 closure가 아니라 configure 후보 상한이다. `import_graph.json`의 변수/조건식과 실제 활성 타깃은 CMake를 실행하지 않고 확정하지 않았다. actual trace/target-property/compile input에서 허용 후보로 수렴하는지를 다음 단계에서 검사한다. 설치 config의 byte identity나 SONAME만으로 C++ ABI 인증을 만들지 않는다.

18개 추출본은 원본을 건드리지 않고 새 work/deps로 복사했고 각 복사 파일의 hash를 확인했다. pkgconfig는 inputs/pkgconfig의 별도 재배치본이며 raw package 내용을 수정하지 않았다. 설치 CMake/header/library는 개별 파일 소유 package/버전/realpath/SHA allowlist로 고정하고, 큰 toolchain header snapshot 전체를 임의의 third-party 승인 목록으로 쓰지 않는다. 표준 toolchain subset과 선택 package 파일만 소비 허용한다.

새 prefix는 work/config-01/prefix, source는 src/{dart,physics,sim}, build는 build/{probe,dart,physics,sim,harness}, logs/manifests도 같은 config-01 아래다. 현재는 빈 산출물 디렉터리만 준비했고 native artifact는 없다.

전체 cmake --install을 사용하지 않는다. 새03/02/01 patch의 마지막에서 install-selected.cmake를 포함해 **aero-joint-libraries**, **headers**, **aero-joint-cmake** component만 배치한다. library component는 위 명시 target만, CMake component는 요구한 export/config/version/Find 모듈/pkgconfig만 다룬다. gfx/gui 등 미빌드 target의 원래 Unspecified install을 실행하지 않는다. dartsim의 lib/engine-plugins, Physics의 lib/system-plugin 양 경로도 같은 선택 target에서 배치하고 stage_receipt로 build bytes와 일치시킨다. predecessor ELF의 출처는 manifests/staged.json으로 고정하고 다음 단계 ELF 검사에 사용한다. component export 집합/생성 파일 존재 여부는 configure 후 반드시 확인한다.

## 정확한 명령과 검색 정책

[build_commands.txt](build_commands.txt)는 shell quoting을 포함한 전체 제안 명령, [build_commands.json](build_commands.json)은 같은 argv 목록이다. **어느 명령도 실행하지 않았다.** 순서: source 준비/배포9개 및 독립 patches 적용(향후 별도 허용) → probe configure/guard/build/audit/stage/receipt → DART → physics → Sim → harness. source application helper도 독립 파일로만 작성했고 실행하지 않았다. 기존 src/build가 있으면 자동 삭제/덮어쓰기 대신 중단한다.

toolchain은 이전 GCC13.3/ld.bfd2.42/CMake3.28.3/Ninja1.11.1 및 libstdc++14/glibc2.39 파일 lock을 재사용한다. C++17/ABI1/RTTI·exception ON/LTO OFF/Eigen alignment16/DART SIMD OFF로 명시했다. Python3/protoc/pkg-config도 /usr/bin의 고정 파일이다. 검색 순서는 새 prefix → 새 deps/usr → 허용 /usr SDK다. DART_DIR=prefix/share/dart/cmake, 각 gz-physics component와 gz-sim8_DIR=prefix/lib/cmake/해당 package를 명시했다. Bullet 네 library와 ODE/fcl/ccd/octomap/urdfdom config는 새 deps 경로로 고정했다.

CMake registry/system-env/CMake-env/package-root env 검색을 끄고 /usr/local·/opt·/home·/snap prefix는 무시한다. 모든 제안 명령은 LD_PRELOAD/LD_AUDIT/LD_LIBRARY_PATH/CPATH/각 언어 include path/가변 CMake·pkgconfig·Python 검색 경로를 제거한 같은 env로 실행하도록 썼다. PATH=/usr/bin:/bin, Python user-site/bytecode 쓰기 OFF. pkgconfig는 새 prefix/lib/pkgconfig → inputs/pkgconfig → 명시한 설치 pc 순서다.

CMake cross mode의 deny emulator는 try_run을 거부한다. 임의 execute_process 전체에 대한 sandbox가 아니므로 현재 선택한 CMake/script 파일을 hash로 고정했다. configure 자체가 try_compile/link를 하므로 이번에는 실행하지 않았다. 향후에도 compiler/protoc/Qt/msgs codegen 등 빌드 도구와 물리 target 실행을 구분하고 DART/Gazebo subject 실행을 허용하지 않는다.

## configure/빌드 단계에서 반드시 통과할 게이트

1. source/patch/input/dependency/tool hashes와 branch 확인. 새 source 적용 뒤 source_plan의 기대 수정 파일 digest 일치. 기존 작업 경로/예상 밖 파일을 덮어쓰지 않는다.
2. configure가 필요한 DART6개, physics core/plugin+interfaces, Sim core/Physics target 및 선택 export를 만들었는지 확인. missing/disabled adapter나 utils-urdf, 미생성 config/header/export, unused -D 또는 feature/config 오류는 중단. Bullet double probe는 false 기대, ContactSurface는 새 선택 DART header 결과와 일치해야 한다.
3. check_selection.py가 actual configure JSON trace, raw imported/build target properties, compile_commands를 검사한다. 미해석 generator expression도 자동 허용하지 않는다. 설치 DART/Sim/gz-physics header/config/library, lock 밖 파일 또는 바뀐 hash, ABI/AVX/native compiler flag 불일치면 build 전 중단. /usr/include 디렉터리가 보인다고 그 아래 모든 파일을 허용하지 않는다.
4. compile_gate.py는 compiler launcher로 depfile의 실제 header 파일을 검사한다. 설치 stack 또는 lock 밖 파일이 쓰이면 비정상 종료해 Ninja의 의존 link 진행을 막는다. 이것을 실행해 확인한 것처럼 표시하지 않는다.
5. audit_outputs.py는 링크 후 selected target SONAME/Build ID/hash/recursive DT_NEEDED/RPATH를 정적으로 검사한다. 계획 밖 자체 target, 출처 미기록 predecessor, 설치 다른 DART, 미해결/미고정 ELF, 자체 output의 예상 밖 RPATH면 stage 전에 중단. stage_receipt는 선택 target의 양 plugin 경로 및 ELF bytes를 build 산출물과 대조한다. DT_NEEDED 문자열만으로 런타임 선택을 증명하지 않으며 RUNPATH는 각 DSO별로 검토한다.
6. build 이후에도 실제 ABI·매핑·초기화1회·GO 실패/timeout·100×1ms native 계약은 별도 검증 대상이다. runtime mapping은 기존 mapped.py의 FD/hash/Build-ID/dev/inode/PID 안정성 관측과 typed entry 관측을 함께 요구한다. build/ELF 검사가 통과해도 실행 contract/risk acceptance/Stage B 상태를 자동 변경하지 않는다.

## 이번 검증과 종료

patch3개 git apply --check PASS, 배포9개 뒤01 patch의 순차 exact-context RAM 검사 PASS(CRLF를 보존해 source 적용 후 기대 digest도 고정). 대상 source tree에 적용한 것은 아니다. 추가 C++ include43개의 실제 source/SDK 경로 및 새 patch header 존재를 정적으로 확인했고 Python AST/fixture 물리 subtree 비교 PASS. configure trace/산출물이 없을 때 두 검사기가 기대대로 거부하는 negative check도 수행했다. 실제 configure/compile/link/동작 검증으로 승격하지 않는다.

원 source의 확인 파일, 이전 독립 입력18개의 hash, main HEAD/status를 대조해 보존했다. 이번 독립 입력은26개다. 이전 archive/package/toolchain 조사는 재사용이며 과거 실행 결과를 새로 수행했다고 쓰지 않았다. validation.json 참조. marker 생성/소비, 서비스 시작, sudo/시스템 설치·설정 변경 없음. 기존 Clock/Capture 및 자유낙하 판정 코드는 그대로다.

큰 allowlist/graph와 uncompiled 입력/미실행 future builder는 로컬에 남기고, 검증한 경량 보고서·정적 조사 기록만 실험 브랜치에 게시한다. /tmp/ignored 입력은 Git으로 다른 기기에 전달되지 않으며 영속 보관이 보장되지 않는다. input_files/reuse_files/local_inventory_index를 원본 경로와 함께 유지한다.

최종 **READY_FOR_BUILD (정적 입력 게이트)**. 실제 ABI/무스텝성 NOT_RUNTIME_VERIFIED, destructor NOT_OBSERVED / allocator NOT_MEASURED, **Stage B BLOCKED / 위험 수용 미결정** 유지. 이후 결과의 적용 범위는 이 coherent configuration manifest에 한정한다. 이번에는 보고/게시 후 멈춘다.
