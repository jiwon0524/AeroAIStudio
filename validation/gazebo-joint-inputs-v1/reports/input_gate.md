# Gazebo 공동 빌드 누락 입력 확보 판정

2026-11-08 UTC. 시작 HEAD `72a9ff95f37eb955edf1395e6699c27b03056b8c`, branch `experiment/dart-internal-trace`, clean 직접 확인. context-handoff와 AGENTS.md/DEVELOPMENT_RULES/handoff/기존 build_plan 읽음. 기존 archive/배포 patch 검증은 `validation/gazebo-joint-build-plan-v1/reports/input_validation.json` 결과를 재사용했다. 이번에는 새 패키지 bytes·독립 후보 파일·비실행 대조만 검증했다.

**빌드 입력 준비: BLOCKED. Stage B: BLOCKED. 위험 수용: 미결정. NOT_RUNTIME_VERIFIED.**
아래에서 RESOLVED는 해당 입력 항목에 대한 판정이며 설치 Gazebo/DART 전체 ABI 또는 실행 승인 판정이 아니다. 이전 계획서의 여섯 세부 항목을 다음 다섯 게이트로 묶었다: ODE, Bullet, toolchain, 나머지 dependency closure+정확 명령/검색/배치, 계측 patch+harness.

|게이트|판정|직접 근거와 해소 조건|
|---|---|---|
|1. 외부 ODE 개발/runtime 입력|RESOLVED|정확 버전 dev/runtime 다운로드·추출, 설치 ELF byte MATCH, precision.h/pc/runtime 문자열 모두 double. packages.json, external_reuse.json, external_elf.json|
|2. 외부 Bullet 개발/runtime 입력|RESOLVED|정확 버전 dev/runtime 다운로드·추출. 설치 runtime 18개 파일 및 dev 관련 417개 파일 전부 MATCH. 일반 float branch 명시; float64 branch 배제. package_byte_summary.json, external_reuse.json|
|3. 실제 toolchain의 파일·버전 고정|RESOLVED|toolchain_summary.json, tool_elf_closure.json 및 로컬 toolchain_files.json. compiler helpers의 실제 위치는 /usr/libexec/gcc/.../13. 필수 driver/helpers/linker/CMake/Ninja/Python/protoc/표준 라이브러리의 정적 ELF closure 71개, 누락 0. 이 판정에 프로젝트의 transitive dependency 선택까지 포함하지 않음|
|4. 나머지 의존성/검색 순서/최소 target 배치 절차|BLOCKED|18개 패키지와 967개 추출 파일, 설치 config 1800개 snapshot 확보. 그러나 snapshot은 승인 allowlist가 아님. Sim root의 unconditional GUI/Qt/sensors/rendering/Fuel config와 codegen 도구의 실제 config/ELF/header closure를 패키지별로 연결해야 함. 선택 target만 빌드한 뒤 전체 install은 미빌드 target을 참조할 수 있어 staging recipe도 미완성. command_candidates.json은 정확 argv를 가진 후보이며 READY 명령이 아님|
|5. 계측 patch/harness의 완성된 입력|BLOCKED|독립 patch 3개, probe/ELF verifier/harness/CMake/toolchain 파일과 SHA 준비. git apply --check 세 개 PASS, 배포9개→DART 계측 patch 순서는 RAM 내 exact-context 검사 PASS. 다만 초기화 하위 호출 전체의 무스텝/동시성 및 mutation surface의 소스 검토가 닫히지 않았고 harness는 빈 world 관측 후보다. 기존 fixture와 Clock/Capture/자유낙하 계약을 연결한 최종 harness가 아님. input_files.json, patch_checks.json, ordered_patch_checks.json|

## 외부 라이브러리 재사용 확정 범위

설치 패키지의 실제 이름은 `libode8t64`, `libbullet3.24t64`다. 이전 libode8/libbullet3.24 표기는 SONAME 계열이지 현재 noble 패키지명이 아니다. 정확한 dev의 Depends가 해당 t64 runtime **동일 버전**을 요구한다.

|패키지|버전/아키텍처|공식 Ubuntu archive의 SHA-256|
|---|---|---|
|libode-dev|2:0.16.2-1.1build1 / amd64|b1e149fc088a94506594420ec0dbe621f53ed59908dcfabdf103c19e637e8833|
|libode8t64|2:0.16.2-1.1build1 / amd64|a8c773b9ea69a0bb29c54bb3e7295919abe0f0e58eb70b31f281e978f3c29143|
|libbullet-dev|3.24+dfsg-2.1build1 / amd64|1a8b3754869d4c0213f3baa71948cd596d3651c362682f681134a6328c70e9bd|
|libbullet3.24t64|3.24+dfsg-2.1build1 / amd64|2496d438988322ff005d16ced3aa41015782a45adc125ce81b857c0723ca3ec3|

출처 URL/Source/Depends/version/arch는 packages.json. `https://archive.ubuntu.com/ubuntu/pool/universe/o/ode/` 및 `.../b/bullet/`에서 받았고 로컬 APT metadata SHA와 다운로드 bytes를 대조했다. 새 InRelease/GPG archive-chain 검증은 수행하지 않았다. dpkg-deb --extract만 사용; maintainer script/ode-config/대상 ELF 실행 없음. 별도 work/extracted 아래 원본 추출을 보존하고 work/deps에 새 overlay 추출했다. 패키지 자체는 설치하지 않았다.

ODE `precision.h` 기본 dDOUBLE, ode.pc precision=dDOUBLE, 설치 ELF 문자열 ODE_double_precision이 대응한다. dIDESINGLE/dSINGLE override는 금지한다. Bullet은 선택한 libBulletCollision.so.3.24의 btStaticPlaneShape 생성자 심볼이 float이다. 일반 bullet.pc/BulletConfig는 double define이 없고 별도의 float64 config/library도 패키지에 있으므로 혼용 금지. 헤더의 Linux x86_64 기본 조건을 사용하고 BT_USE_DOUBLE_PRECISION 및 임의 SSE/NEON/alignment override를 넣지 않는다. DART의 double link probe는 향후 **compile/link 허용 후** false 기대; 다른 결과면 중단. 이번에는 probe를 수행하지 않았다.

**외부 ODE/Bullet은 이 입력 조합의 재사용 대상으로 확정**한다. 설치 runtime bytes와 같은 추출 ELF를 isolated dependency 경로에서 링크하는 후보를 택했다. 이는 두 외부 라이브러리의 재빌드를 요구하지 않는다는 뜻이다. DART의 collision-ode/collision-bullet C++ adapter, core 및 DART 소스 내 external-odelcpsolver는 재사용 대상이 아니며 공동 빌드한다. 이후 결과는 새 공동 빌드 구성에만 귀속한다. 배포 dev/runtime 쌍과 precision 근거는 임의 flags의 C++ ABI 전부를 인증하지 않는다.

## 추가 확보한 실제 필수 입력

gz-physics dartsim의 CMake는 DART collision-bullet/collision-ode뿐 아니라 **utils와 utils-urdf**도 요청한다. 따라서 후속 DART target 목록에 dart-utils와 dart-utils-urdf가 필요하다. 이 사실을 반영해 libfcl-dev/libccd-dev/liboctomap-dev/liburdfdom-dev/liburdfdom-headers-dev/libconsole-bridge-dev와 대응 runtime을 다운로드·추출했다. 총18개 패키지 모두 metadata SHA와 일치. 각 버전/아키텍처/출처/hash는 packages.json, 새 overlay 파일·symlink 목록은 로컬 dependency_files.json, CMake config 위치는 dependency_configs.json. 새 runtime 전체를 설치본과 동일하다고 승격하지 않았다(ODE/Bullet 외는 이번 package byte 비교 대상 아님).

재배치가 필요한 pkgconfig는 **원 추출 파일을 수정하지 않고** inputs/pkgconfig에 별도 복사본을 만들었다. prefix를 work/deps/usr로 고정했다. ODE 헤더, dev symlink와 runtime ELF가 같은 overlay 안에 존재한다. Bullet은 취약한 상대경로 BulletConfig 자동 선택 대신 DARTFindBullet의 MODULE 방식과 명시 include/Math/Collision 경로를 후보에 넣었다.

## 도구와 검색 경로

고정 toolchain: GCC/G++13.3.0-6ubuntu2~24.04.1, GNU binutils2.42-4ubuntu2.10의 ld.bfd, CMake3.28.3-1build7, Ninja1.11.1-2, libstdc++6 14.2.0-4ubuntu2~24.04.1, glibc2.39-0ubuntu8.9. compiler13과 runtime libstdc++14의 실제 bytes를 각각 고정했다; 같은 버전이라고 가정하지 않았다. SHA/realpath/패키지 버전은 toolchain_summary.json 및 tool_elf_closure.json, C/C++/kernel headers/crt/specs/static archives/CMake modules 등 파일별 목록은 로컬 toolchain_files.json. 프로토콜 생성에 필요한 protoc/Python도 파일 목록에 포함된다. 이것은 설치본 원 빌드 도구와 동일하다는 판정이 아니다.

새 경로는 `/tmp/AeroAIStudio-dart-internal-trace/validation/gazebo-joint-inputs-v1/work/config-01`의 src/{dart,physics,sim}, build/{probe,dart,physics,sim,harness}, prefix, logs, manifests. 아직 source 배치/configure/build/install 없음. 이전 계획의 config-01 경로를 덮어쓰지 않고 이 새 경로를 사용한다.

inputs/toolchain.cmake와 command_candidates.json에 구성요소별 argv를 작성했다. C++17, shared, RelWithDebInfo, ABI=1, RTTI/exception ON, LTO OFF, DART SIMD OFF. 표준 컴파일러 include는 source/generated headers → 새 prefix/dependency headers → 허용된 /usr dependency headers → GCC13/C++13/OS headers 순서를 요구한다. 실제 target의 -I/-isystem 순서는 생성될 compile_commands와 include dependency로 확인해야 하며 현재 문서의 희망 순서를 관측 결과로 쓰지 않는다. .pc는 생성한 inputs/pkgconfig → 승인될 설치 .pc 순서다.

명시 DART_DIR=prefix/share/dart/cmake; gz-physics7/core/dartsim/sdf/mesh/heightmap 및 gz-sim8_DIR=prefix/lib/cmake/해당 package. CMAKE_INSTALL_LIBDIR=lib로 고정한다. 나머지 fcl/ccd/octomap/urdfdom/console_bridge config는 work/deps/usr의 실제 추출 디렉터리로 지정한다. prefix 검색 순서는 새 prefix → isolated deps/usr → /usr다. /usr는 제3자 후보 검색에만 필요하며 **그 전체를 승인한 것은 아니다**. registry와 환경 검색은 OFF 후보. CPATH/CPLUS_INCLUDE_PATH/LIBRARY_PATH/LD_PRELOAD/LD_LIBRARY_PATH 등 상속 우선순위 제거 정책도 command_candidates에 명시했다. 이 값들은 이번 환경에 설정/실행하지 않았다.

CMake cross mode와 거부 emulator 파일은 try_run의 대상 실행을 차단하는 후보다. CMake execute_process/custom command 전부를 차단하는 장치는 아니므로 reachable config/module/custom/install script의 target 실행 여부 감사가 여전히 필요하다. CMake configure는 try_compile/link를 할 수 있으므로 이번에는 수행하지 않았다.

## 계측 독립 파일과 검증 한계

inputs/01-dart-typed-entry.patch: ODE/Bullet/FCL/DART detector의 실제 virtual getType method entry에서 typed this, 정상 base cast, 같은 method의 module-local anchor를 기록한다.

inputs/02-physics-wrapper-entry.patch: GzOde/GzBullet wrapper의 getType override에서 wrapper/base this를 기록하고 해당 DART adapter getter에 정상 위임한다. collide를 호출하지 않는다. 실제 외부 ODE/Bullet collision 함수 실행은 이 query로 관측되지 않으며 NOT_OBSERVED로 남겨야 한다.

inputs/03-sim-prestep-go.patch: Run 입구에서 network/비영 상태 거부, pending system 활성화(Configure는 이미 수행됨), 단일 Physics init을 첫 UpdateCurrentInfo와 realtime 시작 전에 호출한다. CreatePhysicsEntities만 1회 수행하고 첫 정규 Update의 중복 생성만 건너뛰어 link/joint bookkeeping을 남긴다. EntityFeatureMap의 같은 world를 RetrieveWorld로 재확인하고 WorldPtr/solver/detector 수명을 유지한다. typed getter 관측 및 GO 전후 iteration/time/native frame=0을 요구한다. 고정 FD3의 bounded GO pipe를 기다리고 실패 시 Step 없이 반환한다. Run/Physics Update/Step 가드를 둔다. control/state/playback callback 거부, runtime plugin injection 거부와 SystemManager freeze 후보도 포함한다. 모든 변경은 이 별도 빌드용이며 원 설치 동작으로 일반화하지 않는다.

inputs/probe.{hh,cc}, verify_anchor.cc: 공유 observer DSO의 thread/entry 수 검사, typed detector base 일치, dladdr anchor 모듈, /proc mapping dev/inode와 열린 backing file의 SHA-256 대조 후보. 입력 allowlist가 없거나 불일치면 GO 거부. SHA/Build ID/DT_NEEDED를 만드는 scripts/make_elf_allowlist.py는 **향후 빌드 후** 정적 도구 후보이며 이번 실행하지 않았다. Build ID는 SHA와 함께 후속 manifest로 연결할 설계다. ELF 목록을 만든 사실만으로 전체 dependency closure 검증이 되지는 않는다.

inputs/harness.cc와 CMakeLists.txt: prefix 내부의 절대 Physics/engine 경로 및 inherited FIFO FD3만 허용하는 전용 후보. marker 파일을 열지 않는다. 빈 world의 초기화/typed query/GO/100 iterations용이며 기존 Clock/Capture/자유낙하 acceptance fixture를 대체하지 않는다. 해당 fixture와 판정 연결은 아직 필요하다.

각 독립 파일의 SHA-256은 input_files.json. patch_checks.json의 **git apply --check만** 실제 수행했다. DART9개 배포 patches 후 계측 patch의 context는 check_series.py가 RAM에서 순차 대조해 PASS; hypothetical digest를 기록했으나 파일/소스 트리에 적용하지 않았다. source 변경 없음은 validation.json의 입력별 재해시로 확인. check 통과는 C++/CMake 정확성이나 초기화 무스텝성 PASS가 아니다.

구체적으로 게이트5 해소에는 CreatePhysicsEntities→각 Create*→feature/plugin/native 생성 하위 호출의 Step/collide/숨은 Update·동시 변경 부재를 닫는 정적 call-path 검토가 필요하다. 남은 public mutation API와 reset/엔티티 추가·삭제 경로도 제한된 harness의 호출 그래프 기준으로 점검해야 한다. provider module ELF/entry 검증 및 GO 실패 경로의 코드 검토, 기존 acceptance fixture의 경량 참조/hash와 최종 harness 연결이 필요하다. 컴파일을 하지 않았다는 사실만으로 BLOCKED를 만든 것은 아니다. 아직 끝나지 않은 입력 설계/검토를 구분해 차단했다.

## 다음 해소 조건과 중단 기준

게이트4의 정확한 미완료 산출물은 (1) Sim root의 GUI/Qt/sensors/rendering/Fuel 및 codegen까지 닫힌 package/config/header/ELF allowlist, (2) 실제 사용할 target별 include/link 순서 기준과 config fallback 거부 감사, (3) 선택 target만으로 완결되는 `stage-selected` 절차 또는 그에 맞춘 명시적 build 범위 변경이다. 기존 command_candidates의 cmake --install 전체 호출을 현재 실행하면 안 된다. 후보 명령에 빈 placeholder는 없지만 이 세 검토 없이 그대로 사용할 명령으로 승인하지 않는다. 추가로 반드시 다운로드해야 할 특정 패키지를 현재 증거 없이 추정하지 않는다; ODE/FCL 계열의 확인된 누락 dev는 이미 확보했다.

후속 configure 전 모든 입력 hash/허용 search path 재검사. configure trace/cache/imported target에서 설치 DART 또는 설치 gz-physics/gz-sim header/config/lib가 선택되면 중단. link map/verbose log에서 새 core/adapters/LCP 대신 /usr DART 또는 다른 기존 build가 나타나면 중단. 의도한 ODE/Bullet adapter/utils target의 자동 비활성화, ContactSurface macro 불일치, Bullet double probe의 예상 밖 결과, unused -D 경고도 중단 사유다.

ELF별 recursive DT_NEEDED를 exact realpath/hash/Build ID로 해석하고 RPATH/RUNPATH를 각 DSO별 검사한다(RUNPATH는 전이 적용되지 않음). 같은 SONAME의 다른 bytes/미해결 항목/복수 DART가 있으면 거부. plugin의 lib와 engine-plugins 설치 두 경로가 같은 bytes인지 검사하고 절대 경로 밖 fallback은 거부. readelf와 빌드 로그는 실제 runtime mapping 증명이 아니며 로딩 검증은 별도 승인 이후에만 가능하다. ldd/loader 실행은 사용하지 않았다.

이번 작업은 여기서 입력 준비 PARTIAL/BLOCKED로 끝낸다. uncompiled 후보 소스와 생성기는 규칙에 따라 로컬에 보존하고 자동 게시하지 않는다. 확인된 보고서/해시/check 결과/검증한 자료 확보/감사 스크립트만 게시한다. work 다운로드·추출물, 큰 로컬 inventory, 독립 후보 파일은 Git으로 자동 전달되지 않으며 /tmp는 영속 보관소가 아니다. 다른 기기에서는 원본 경로 접근이나 명시적인 별도 이관이 필요하다.

금지 작업(패치 적용/컴파일/링크/대상 로딩·실행/서비스 시작/marker 소비/sudo/패키지 설치/시스템 변경) 없음. main metadata와 선택 source 입력 보존 PASS; 이전 archive/71파일 검증은 재사용 결과이지 이번 재실행이 아니다. 실행 중 작업은 handoff snapshot 범위로만 기록하며 기존 작업 종료/재시작 없음. 새 구성의 향후 관측 결과는 그 최종 source/toolchain/ELF manifest에 한정한다. **Stage B BLOCKED / 위험 수용 미결정**.
