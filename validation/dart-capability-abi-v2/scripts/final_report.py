from common import *
from datetime import datetime,timezone

def read(name):return json.loads((R/'reports'/name).read_text())
abi=read('abi_summary.json');delta=read('instrumentation_delta.json');profile=read('build_profile.json');layout=read('abi_layout.json');tests=read('test_summary.json');integrity=read('integrity.json');debug=read('debug_coverage.json');dwarf=read('dwarf_comparison.json');deps=read('dependencies.json');elf=read('elf_summary.json')
assert len(dwarf)==10,'Wait for all requested DWARF analyses to finish; do not claim completion'
assert tests['native_tests']['failures']==0 and tests['regression']['failures']==0
assert integrity['status']=='PASS'
table='|모듈|A 참조|Baseline/C export|누락/추가(B)|누락/추가(C)|\n|---|---|---:|---|---|\n'
for part,label in [('core','설치 core'),('external','설치 external'),('ode','설치 collision-ode'),('ipopt','동일 DART 배포 deb; 미설치'),('nlopt','동일 DART 배포 deb; 미설치')]:
 b=abi['baseline_'+part];c=abi['trace_'+part];table+=f"|{part}|{label}|{b['export_count']}/{c['export_count']}|{b['missing_exports']}/{b['added_exports']}|{c['missing_exports']}/{c['added_exports']}|\n"
dwarf_table='|비교|exit code|관측 요약|\n|---|---:|---|\n'
for r in dwarf:
 summary=(r['summary'] or r['diagnostic'] or '변화 보고 없음').replace('\n','; ').replace('|','/')[:220]
 dwarf_table+=f"|{r['name']}|{r['rc']}|{summary}|\n"
package_table='|패키지|버전|SHA-256 앞12자리|\n|---|---|---|\n'
for r in deps['packages']:
 package_table+=f"|{r['package']['Package']}|{r['package']['Version']}|{r['sha256'][:12]}|\n"
flags=profile['profiles']['trace']['flags'];classes=layout['trace']['execution']['stdout'];date=datetime.now(timezone.utc).isoformat()
text=f'''# DART Capability 및 ABI Parity V2 최종 보완

작성: {date}. 별도 worktree `/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`.

## 1. 최종 판정 및 기존 보고서 확인

**PARTIALLY_RESOLVED / HOST_BLOCKED_ABI_PARITY_PENDING / NOT_RUNTIME_VERIFIED. Stage B BLOCKED.**

IPOPT/NLOPT/ODE capability3개는 실제 의존성 검색·모듈 빌드까지 해소했다. 설치 core와 새 core의 export 이름5739개 및 기존 ELF 객체 metadata 계약은 유지된다. 설치본의 타입 debug 정보·원 배포 buildinfo가 확보되지 않아 전체 ABI/Build Parity는 인증하지 않는다. 계측은 별도 진단 API와 의존성을 추가하므로 모든 바이너리·동작이 설치본과 동일하다는 뜻도 아니다.

기존 implementation final_report.md, parity-v1 final_report.md/missing_24_report.md, cache/ELF/테스트 산출물을 직접 읽었다. 최초144 및 이전 parity44 PASS는 이전 결과로 구분했다. 이전 fmt8/9 선택과 LTO 차이를 해소한 source/config를 재사용했으며 원래 보고서·evidence는 수정하지 않았다. 앞선 Contact/Constraint 원인 추적 요청은 사용자가 취소했으며, 그 요청에서 읽기만 수행하고 새 분석/실험 산출물을 만들지 않았다.

## 2. Git 초기 상태와 분리

원래 main HEAD는 `46134c6bf5670ed61ba252f394ccdddb7ff2cf6b`. 기존 수정8개(567 additions/34 deletions)와 미추적31개를 파일별로 읽고 hash/선언/기존 diff를 로컬 preexisting_work_audit.json에 기록했다. 내용은 이전 contact/clock/collision 진단·테스트 및 AGENTS/handoff 작업이며 이번 commit 대상으로 섞지 않았다.

기존 로컬 실험 브랜치가 없고 원격 조회도 main만 반환했다. 원래 main의 dirty 파일을 이동·stash·삭제·초기화하지 않고, 같은 HEAD에서 별도 worktree에 새 실험 브랜치를 만들었다. 원래 main 파일·HEAD·변경 상태는 유지했다. 새 지침/인계문도 실험 worktree에만 작성했다. Git index/ref 갱신은 이 실험 브랜치의 관리 작업이며 main commit/edit/push/merge는 없다.

## 3. Capability별 원인·API·ABI 영향

|항목|이전 원인|확보/검색 결과|모듈 및 영향|
|---|---|---|---|
|HAVE_IPOPT|runtime/dev 미설치|IPOPT3.11.9 dev/runtime pair, find_path IpIpoptNLP.hpp + find_library ipopt + pkg-config version|dart-optimizer-ipopt; IpoptSolver API, ipopt→MUMPS/Scotch/BLAS/LAPACK runtime 의존. Core contact LCP를 IPOPT로 바꾸지 않음|
|HAVE_NLOPT|runtime/dev 미설치|NLOPT2.7.1 dev/runtime pair, nlopt.h + libnlopt + pkg-config version|dart-optimizer-nlopt; NloptSolver API. Dantzig/PGS 선택에는 직접 영향 없음|
|HAVE_ODE|ODE runtime만 설치, dev 헤더/검색 metadata 부재|설치 runtime와 정확히 같은2:0.16.2-1.1build1 dev 추출|dart-collision-ode; OdeCollisionDetector API, unchanged libode.so.8 재사용. 새 solver 알고리즘 아님|

실제 DARTFind/Find*.cmake와 각 모듈 CMake 파일은 capability_sources.json에 보존했다. dart core의 C++ 소스에서 이3개 HAVE 매크로의 직접 계산 분기는 없고 config.hpp 생성 지점만 관측된다. 상위 Python binding/모듈 가용성은 별개다. 헤더를 강제로 꾸미지 않고 실제3개 component target을 생성·컴파일·링크했다. 설치/새 Baseline/새 Trace의 값은 모두1이다.

IPOPT/NLOPT의 원 배포 빌드 당시 정확한 의존 버전은 buildinfo 부재로 **UNVERIFIED**다. 선택한 것은 Noble archive의 서로 맞는 dev/runtime 쌍이며 역사적 빌드 재현이라고 주장하지 않는다.

## 4. 의존성 확보와 보존

apt-get download와 dpkg-deb -x만 사용했다. 설치·제거·업데이트·ldconfig는 없다. 설치되어 있던 BLAS/LAPACK/Fortran 및 ODE runtime은 변경하지 않았다. FCL/CCD/Octomap와 spdlog/fmt 헤더는 기존의 matching 자료를 새 prefix로 복사했다.

{package_table}

이11개에 더해, 설치되지 않은 optimizer의 ELF 참조를 얻기 위해 동일 OSRF DART6.13.2+ds1-1~osrf2~noble runtime deb2개를 별도로 추출했다. **다운로드 총13개이며 실제 시스템 설치0개**다. 전체 해시·archive package metadata·출처는 dependencies.json/reference_modules.json이다. 모든 deb는 apt index SHA-256과 일치한다. 격리 pkg-config7개의 prefix만 재배치했고 변경 전/후 hash·근거를 기록했다. 시스템의 .pc나 글로벌 환경은 수정하지 않았다.

## 5. 격리 재빌드 결과 및 실패 처리

초기 두 빌드는 합쳐진 dependency include 경로가 -I가 되면서 Octomap std::iterator deprecated 경고가 -Werror에 걸려 실패했다. 실패로그/초기 object 디렉터리를 보존했다. 이를 성공으로 표시하지 않았다. 기존 V1처럼 fmt/spdlog만 앞선 일반 include prefix로 분리하고 나머지 외부 헤더의 SYSTEM 분류를 복원했다. Werror/최적화/solver 계산을 완화하지 않았다. 근거는 build_failure_resolution.json이다.

새 `build-baseline-final`/`build-trace-final`에서 core/external/optimizer-ipopt/optimizer-nlopt/collision-ode target이 모두 완료됐다. 이전 작업의 source/build 디렉터리는 덮어쓰지 않았다. 초기 실패한 이번 빌드도 별도 디렉터리로 남겼다. install target·예제·전체 DART simulation suite는 실행하지 않았다. source는 이전 검증본을 그대로 복사했으며 이번 추가 계측/solver 코드 변경은0이다. 게시용 patch는 Git whitespace 검사에 맞게 zero-context로 직렬화했으며, 원래 계측 source7개와의 patch 적용 후 SHA가 모두 일치한다(patch_roundtrip.json).

## 6. A 설치본 대비 ELF ABI

{table}

A의 core/external/ODE는 실제 설치 파일이다. optimizer 두 개는 설치되지 않아 같은 DART 배포의 **packaged reference**이며 설치되어 있었다고 표현하지 않는다. 전체 exported/undefined 이름, binding/visibility/version/size/type 변화는 symbol_differences.json, 원시 전체 symbol inventory는 로컬 보존했다.

Core B는 설치본 대비 함수 코드 size32개, C는63개가 다르지만 공유 symbol의 type/binding/visibility/version 및 OBJECT size 차이는0이다. ODE/optimizer의 관측 차이도 함수 코드 size뿐이다. 함수 코드 bytes 차이를 class layout ABI 파손과 동일시하지 않는다. 설치본과 export 개수만 비교한 결론이 아니다.

## 7. 동일 설정 Baseline과 Trace 차이

Core export 추가·제거0, recorder 참조 undefined12개 추가. External은 기존71개 유지·진단 ELF export19개 추가 및 undefined45개 추가다. 타입이 있는 함수 관점에서는 constructor alias 등을 합쳐17개 추가로 보고될 수 있어19 ELF 심볼과 구분한다. 새 core/external의 기존 함수 code size는 계측 삽입 영향으로 변한다. ODE/IPOPT/NLOPT 모듈은 B/C 사이의 export/undefined·공유 metadata 변화가 없다. 원시 차이는 instrumentation_delta.json이다.

External의 새 표준 라이브러리·파일출력·예외/thread 관련 imports, libgcc_s 및 loader NEEDED, GLIBC2.38(__isoc23_strtoull)/2.34(pthread), GLIBCXX3.4.22 등의 요구는 실제 ELF에 기록했다. 현재 Noble host의 child loader 검사로 해소됐지만 다른 OS의 호환성이나 runtime 중립성을 인증하지 않는다.

## 8. Symbol·Loader·Compiler 설정 검사

Core SONAME은 libdart.so.6.13, external은 libdart-external-odelcpsolver.so.6.13로 유지된다. Core NEEDED9개는 설치본과 같다. fmt/spdlog는 선택한 header-only 경로에서 정의되어 core에 별도 shared dependency가 붙지 않는다. 실제 compiler dependency 파일에서 local spdlog/fmt8 참조0을 확인했다. 상세 SONAME/NEEDED/RPATH/RUNPATH/versions는 elf_summary.json이다. 격리 build RUNPATH는 설치본(없음)과 다르며 배포 동일성으로 숨기지 않았다.

현재 compiler GCC13.3.0, GNU ld2.42, libstdc++/gnu++17, _GLIBCXX_USE_CXX11_ABI=1, fmt9.1/spdlog1.12다. CMAKE_BUILD_TYPE=None, -O2/-g, fat LTO, stack/fortify protection, -Bsymbolic-functions, RELRO/NOW를 B/C에 공통 적용했다. 원 배포 compiler 세부 버전·모든 flags는 미확보다. 실제 flags/link recipe/cache 요약은 build_profile.json과 configure_commands.json이다.

각 구성의5개 library 및 설치 dartsim 소비 plugin의 `ldd -r`에서 미해결 symbol0을 확인했고 새 core/external 경로 선택을 확인했다. LD_LIBRARY_PATH/PKG_CONFIG_PATH/LDFLAGS는 지정한 자식 프로세스에만 적용했다. loader 검사는 Gazebo 실행이 아니다. 기존 소비 library 참조도 consumer_references.json으로 대조했다.

## 9. 공개 구조 및 DWARF ABI

관측한 공개 클래스9개의 size/alignment(bytes)는 matching header/B/C에서 같다. core6개는 설치 dev header를 기준으로 하고, 설치되지 않은 optimizer 및 optional ODE header는 같은 배포 source fallback을 사용했다. 후자의 A-arm 결과는 원 설치 binary type layout의 직접 관측이 아니다.

```text
{classes.rstrip()}
```

403개 기존 선언 헤더는 B/C 동일하고 관측 DART vtable size 차이도0이다. 이 검사 범위를 넘는 원 설치 binary의 전체 type layout은 다음 한계가 있다.

{dwarf_table}

**중요한 coverage 한계:** 설치/packaged reference5개 모두 embedded DWARF 없음, 분리 debuglink/altlink 대상 미확보이고 `abidw`가 만든 corpus에는 abi-instr/function-decl가 각각0개다(debug_coverage.json). 따라서 reference→trace abidiff의 exit0도 full type ABI PASS가 아니다. --fail-no-debug-info 옵션만 신뢰하지 않고 실제 type corpus를 검사했다. libabigail은 debug 자료가 없으면 ELF symbol 비교로 제한된다. [공식 abidiff 설명](https://sourceware.org/libabigail/manual/abidiff.html).

동일 버전 dbgsym ddeb/deb 및 buildinfo의 원 배포 후보 URL3개도404였다(original_debug_buildinfo_probe.json). 이것은 조회한 후보 부재이며 모든 저장소에서 영구히 없다는 증명은 아니다. source/header 동일성, class size 또는 loader 통과만으로 이 빈칸을 채우지 않는다. 원 설치본의 debug 심볼/buildinfo 또는 명시적으로 합의된 소비자 ABI 검증 범위가 추가로 필요하다.

Generated config의 capability들은 모두 일치했다. 남은4개 define 차이는 격리 source/prefix의 ROOT/DATA 경로다. 기본 resource lookup에 영향을 주므로 의도적인 차이로 기록하며 완전히 같은 Build라고 주장하지 않는다.

## 10. 오프라인 테스트

최종 **native45 + 기존 회귀108 =153 distinct PASS**, FAIL/ERROR/SKIP0. 이전144/44를 이번153에 중복 합산하지 않았다.

native fixture source를 먼저 읽어 Gazebo/World::step/system/exec 호출이 없는지 검사했다. 실제 DART Constraint/LCP 함수에 synthetic input을 주어 Recorder OFF/ON, input deep copy·padding 배제·row identity, Dantzig 실패/NaN/실제 PGS fallback, overflow/incomplete/schema를 검증했다. World 생성자 검사만 있고 step은 호출하지 않았다. 기존 회귀108은 original main의 기존 진단 소스를 읽기 전용으로 사용하고 runtime launch/transport/subprocess guard로 막았다. 다른 작업의 이 미커밋 진단 코드는 본 branch에 commit하지 않았으므로 clean remote checkout만으로 해당108을 재현할 수 있다고 주장하지 않는다.

새 metadata audit는 초기 OFF getType 기대가 틀려1 FAIL/44 PASS가 났다. 실제 Active guard를 다시 읽고, OFF는 baseline과 같고 ON에서 metadata call이 추가됨을 확인하도록 fixture 기대를 수정했다. 계측 source나 허용 기준을 변경한 것이 아니다. 초기 XML/log와 최종45 PASS를 별도로 보존했다. solve/apply 호출 순서와 impulse는 비교4조건에서 일치한다. test_summary.json/test_safety_review.json/metadata_call_observation.json 참조.

## 11. 계측 중립성 검토

Constraint Assembly, local Contact Jacobian, effective-response matrix A 구성, LCP input, Dantzig/PGS 선택·NaN 처리·impulse 적용·position integration의 원 코드 토큰은5개 파일에서 순서대로 보존됐다. 추가 코드는 기존 fields를 복사하며 solver를 재실행하지 않는다. 이는 lexical 검사이며 형식적 의미 동등성 증명이 아니다. synthetic response A 테스트가 실제 articulated chassis의 effective mass나 전체 Jacobian을 검증하는 것도 아니다.

World ctor의 call_once/env 검사, step scope의 TLS/예외 상태 확인, OFF diagnostic entry 및 SetRow argument의 getDimension 조회, ON getType metadata 가상 호출, 활성 창의 arena memcpy/atomic/branch/cache pressure가 추가된다. 기본 arena는 x86_64 Record296bytes 가정 시 약3.16MiB, hard cap 약26.5MiB이며 post-window JSON/stream 임시 메모리와 allocator overhead는 별도다. Configure 전 기본OFF에는 record/value arena를 할당하지 않는다. 잠깐 비활성화해도 vector capacity가 즉시 반환된다는 보장은 없다.

World::step 자체는 컴파일만 했다. 실제 clock/time mapping,5frame 범위, shutdown flush, thread owner, timing/FP/cache 영향·runtime neutrality는 이번에 검증하지 않았다. 계측OFF의 작은 비용도0이라고 하지 않는다. 기존 actual path의 solve/apply 결과가 제한된 fixture에서 같다는 근거와 Runtime 중립성 인증은 분리한다.

## 12. Evidence 및 Production 무결성

원래 파일 **{integrity['original_files_checked']}개**(이전 두 source/build 전체, evidence/source/system closure 및 package status 등) 전후 hash가 같고, 원래 main HEAD/dirty 상태도 동일하다. 복사한 새 source 역시 configure 전 hash와 일치한다. `/var/lib/dpkg/status` 유지, 시스템 install/upgrade/library replacement 없음. Production/SDF/Clock/Capture 판정 변경 없음. 기존 build/evidence를 덮어쓰지 않았다.

## 13. 해결된 항목

- 실제3 capability discovery와3 optional module build/loader 검증.
- 설치된/packaged 모듈의 기존 ELF exports·metadata·소비자 참조 유지, 새 core 누락0.
- 소스 변경 없이 독립 B/C 빌드 및153개 오프라인 테스트, 제한된 public layout 확인.
- 경고 분류로 인한 첫 build 실패를 source/경고 기준 완화 없이 분리·수정.

## 14. 미해결·Host 실행 전 조건

- 원 설치본 전체 type ABI와 역사적 compiler/flags/dependency buildinfo 미확보. full ABI_BUILD_PARITY_VERIFIED_OFFLINE 아님.
- new recorder API/import/메모리·호출 비용, isolated RUNPATH/DATA 경로 차이 및 portability 한계 존재.
- 실제 frame mapping, identity completeness, capture/flush/runtime neutrality는 미검증. Host 승인은 별도 검증과 별도 사용자 범위에서만 검토한다. 이번 작업에서 Host로 넘어가지 않는다.

## 15. 다음 최소 작업

원 배포 build ID에 맞는 debug 자료와 buildinfo의 별도 제공 경로를 확보하거나, 소비자별 타입/호출 ABI 검증 범위를 명시적으로 정해 남은 gap을 평가한다. 새 물리 모델/solver 개발이나 새로운 campaign은 시작하지 않는다. NOT_RUNTIME_VERIFIED 및 Stage B BLOCKED 유지.

## 16. Git 게시

검증된 경량 source patch, 분석 script, fixture/tests, 보고서/설정만 실험 브랜치에서 명시적으로 선택한다. work/download/shared library/전체 third-party source/캐시/raw 대용량 manifests·logs는 제외한다. commit/push 최종 값은 `reports/git_publication.json`에 별도 기록한다. main edit/push/merge 또는 force push는 하지 않는다. 원래 dirty 파일은 commit하지 않는다.
'''
(R/'reports/final_report.md').write_text(text)
save('verdict.json',{'verdict':'PARTIALLY_RESOLVED','host_status':'HOST_BLOCKED_ABI_PARITY_PENDING','runtime':'NOT_RUNTIME_VERIFIED','Stage_B':'BLOCKED','capabilities':'IPOPT_NLOPT_ODE_MATCH_1','existing_core_export_names':'MATCH_5739','tests':tests,'integrity':integrity['status'],'full_installed_type_ABI':'UNVERIFIED_MISSING_DEBUG_CORPUS','original_buildinfo':'UNVERIFIED','World_step_or_Gazebo_executed':False})
print('Final limitation-aware report written')
