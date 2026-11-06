# DART Probe A Static Readiness Audit V1

## 1. 최종 판정

**PROBE_A_STATIC_NEEDS_EVIDENCE / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.

설치 Core의 정적 의존성 후보와 identity를 확보하고, DART에 연결하지 않는 C Native Fixture를 준비했다. 실제 DART/Gazebo/Probe A~D/World 생성·step/ShapeNode destructor는 실행하지 않았다. `ldd`, target ELF 실행, DART dlopen/dlclose, systemd transient service 신규 실행도 없었다. 이번 실행 파일 테스트는 loader code가 없는 별도 offline binary에서만 수행했다.

정적 후보가 모두 있다는 이유로 relocations·symbol versions·IFUNC·초기화·종료·Runtime 안전성이 해결됐다고 판정하지 않는다. 실제 실행용 좁은 dependency mount manifest, supervisor gate, mapped-library identity 검증은 아직 구현·결합 검증이 필요하다. 따라서 READY가 아니다. Probe B~D는 계속 BLOCKED다.

## 2. Git·인계·작업 경계

시작 HEAD **906402c9f93c618c6b93d93f78845359f4bacc07**, branch `experiment/dart-internal-trace`, worktree clean을 직접 확인했다. 원본 main HEAD **46134c6bf5670ed61ba252f394ccdddb7ff2cf6b**와 기존 수정8개·미추적31개·staged0을 보존했다. 소유 변경은 새 `validation/dart-probe-a-static-audit-v1/` 및 실험 worktree의 handoff뿐이다.

AGENTS·DEVELOPMENT_RULES·handoff, Cgroup Integration V1, Sandbox Hardening V2, Probe Readiness V1, Targeted Evidence V1, Destructor Cleanup V4/ABI 자료와 실제 ELF를 대조했다. context-handoff 스킬을 사용했다. 과거 Integration29PASS/5SKIP 및 V4 lifetime 결과는 역사적 근거이며 새 Runtime 결과로 합산하지 않았다. 기존 인계문에 남은 과거 전면 실행 금지를 현재 무해 fixture/정적 감사의 명시 승인과 구분했다.

## 3. 라이브러리 identity·의존성

`elf_identity.json`은 arm별14개 항목(존재12/예상경로누락2, 존재파일 canonical10개), 각 절대 요청 경로·symlink 여부/직접대상·최종실경로·mode/owner/size·SHA256·Build-ID·ELF64/x86-64·SONAME·NEEDED·RPATH·RUNPATH를 기록한다. 과거 SHA/Build-ID가 있는 **10항목/8고유ELF 전부 일치**했다. 중복된 설치 Bullet을 독립 ELF로 세지 않았다.

|설치파일|Build-ID|SHA-256|
|---|---|---|
|Core libdart.so.6.13.2|071aa565b343db80e31aae393aadaed33c7adb46|f74f4ec9820aee785ef94fb7bedafa7e4c832f209675a8ca1d35019c72b48e06|
|External LCP|abba8be3e710b1a505116d4bada0803f8bd49398|b890ed6936ea7cf486303fc5101ee5ff68356fc89596273ebaef83671aa4cb16|
|Collision ODE|2cbacdc0e4014e0ee69c4deeacd2d088d564599e|2940e0bd6b056f186d3596e051a26ec25f1c27add88d870cdfe673785dad4b44|
|Collision Bullet|8bda73145d9c6cc97d6faff5895c2ce1aa091f6f|897709e0c988e9e562c662292ed5bc860bce70ee2c64499501f54a6b5ca02201|

Core `DT_NEEDED`의 정적 전이 그래프는 **16개 ELF·58개 edge**, 후보 경로 누락0/서로 다른 real path의 중복 후보0이다. Core/External, FCL, Octomap/Octomath, Assimp, stdc++, m, gcc_s, libc, CCD, z, Draco, Minizip, pugixml, ld-linux를 포함한다. `ldconfig -p`로 기존 캐시 메타데이터만 읽고 `/usr/lib/x86_64-linux-gnu`·`/lib/x86_64-linux-gnu` 후보를 정규화했다. 캐시 및 전체 ELF 해시를 기록했다. 이 코드는 glibc 전체 로더·hwcaps·version binding을 에뮬레이션하지 않으며 **STATIC_CANDIDATE_NOT_RUNTIME_RESOLVED**다. constructors의 추가 dlopen/NSS/gconv/optional plugin은 그래프 밖이다.

Collision ODE/Bullet은 별도 optional 그래프로 **추가5개 ELF·27개 edge**, 후보누락0이다. libBulletCollision.so.3.24, libLinearMath.so.3.24, libode.so.8.0.2를 직접 조사했다. 이들 plugin은 Core의 DT_NEEDED에는 없으므로 이번 축소된 prospective Core-only Probe에서 직접 로딩하지 않는다. 과거 A의 Core/ODE/Bullet 전체 arm 검증과 다른 범위임을 execution_plan에 명시했다.

이전 B/C의 `build-*-final/lib/libdart-external-odelcpsolver.so.6.13.2` **두 예상경로는 여전히 MISSING**이다. 실제 파일은 각 `build-*-final/dart/external/odelcpsolver/`에서 확인·해시했다. 파일을 이동하거나 symlink를 추가하지 않았고 이전 MISSING 결과를 수정하지 않았다. 실제 파일이 있다는 사실만으로 B/C dependency 경로 문제를 해결한 것으로 처리하지 않는다.

## 4. RUNPATH·검색 규칙

설치 A Core 및 위16개 전이 ELF는 RPATH/RUNPATH가 없다. 로컬 B/C Core·ODE에는 과거와 같은 절대 build/dependency 경로와 **후행 빈 항목**이 있다. `$ORIGIN`은 해당 조사 대상의 실제 경로값에서 사용되지 않았다. `runpath_audit.json`에서 빈 항목·상대항목·ORIGIN을 별도 분류한다.

[ld.so(8)](https://man7.org/linux/man-pages/man8/ld.so.8.html)의 규칙상 slash가 포함된 요청은 pathname으로 선택하지만 전이 NEEDED는 별도 검색된다. RPATH는 RUNPATH가 없을 때 고려되며 RUNPATH는 direct dependency에만 적용된다. 환경·cache·default/hwcaps도 영향이 있다. 절대 Core 경로 지정만으로 전이 closure가 고정되지 않는다.

[glibc2.39 dl-load.c](https://raw.githubusercontent.com/bminor/glibc/glibc-2.39/elf/dl-load.c)의 `fillin_rpath`435~537 및 `decompose_rpath`611을 읽어 빈 path element가 길이0 directory로 처리되는 cwd 검색 메커니즘을 확인했다. 이는 upstream tag 소스 근거이며 설치 Ubuntu 패치 binary와의 byte 동등성을 검증한 것은 아니다. 별도 sourceware URL은 도구가 열지 못해 upstream source mirror를 읽었으며 관측 실패를 보존했다. 실제 cwd library 대체 공격은 실행하지 않았다.

A/B/C Core의 SONAME은 모두 `libdart.so.6.13`이며 파일명 중복이 실제 공급자 혼동으로 이어질 수 있다. A-only manifest에서 로컬 B/C 경로를 제외해야 한다. `/lib`와 `/usr/lib` alias는 canonical path로 합쳤고, 별개 파일 후보와 구분했다.

미래 설계는 LD_PRELOAD/LD_AUDIT/환경 라이브러리 경로를 제거하고, sterile readonly cwd와 검증된 개별 ELF readonly bind만 사용한다. 시스템 loader 설정이나 기존 ELF RUNPATH를 고치지 않는다. 현재 Python sandbox의 넓은 `/usr`·project read bind가 곧 엄격한 Native allowlist가 되는 것은 아니다.

## 5. 초기화·종료·TLS·EH

Core `.init_array`16B의 file pointer는 **0x1787d0/0x176840**, `.fini_array`8B는 **0x178790**다. 각 slot의 `R_X86_64_RELATIVE` addend도 일치했다. 이는 ASLR 전 file-relative 값이며 Runtime 주소가 아니다. 실제 relocation과 각 진입점의 제한된 disassembly를 `core_init_fini_disassembly.txt`에 남겼다. stripped binary의 objdump 근처 exported-name+offset을 실제 constructor 이름으로 인증하지 않았다. 전체 init call graph를 추적한 결과도 아니다.

Core는 `malloc/free`, `__cxa_atexit/__cxa_finalize`, `__cxa_throw`, `_Unwind_Resume`, **dlopen**을 import한다. 마지막 import의 소스 후보는 기존 baseline-source `dart/common/SharedLibrary.cpp:41`의 DYNLIB_LOAD이다. import가 존재한다는 사실은 초기화 중 그 함수가 실행된다는 증거가 아니다. 미래 동적 plugin 로딩 가능성을 static DT_NEEDED closure만으로 배제하지 않는다.

동일 버전 소스의 FCLCollisionDetector.cpp610, BulletCollisionDetector.cpp103은 static Registrar를 선언하고 Factory-impl.hpp179~183은 creator를 singleton registry에 등록한다. creator 등록과 실제 detector 생성 호출은 다르다. 이 소스는 global registry 변경 가능성 근거이나 설치된 optimized init 주소와의 정확한 함수 대응을 증명하지 않는다(`source_registration_evidence.json`).

전이 의존성의 TLS section, IFUNC, GNU_UNIQUE를 직접 조사했다. 예를 들어 Assimp/stdC++/gcc_s/libc/Draco에 TLS가 있고, libm IFUNC85개·libc63개, stdC++ GNU_UNIQUE106개·Draco5개가 있다. 이 항목 수는 동작의 안전성·실제 실행 횟수를 의미하지 않는다. EH sections/imports가 있지만 cross-module unwind 안전성은 미검증이다. 기존 ShapeNode slot18 INFERRED 및 Destructor/Allocator 경계 판정은 유지한다.

[dlopen(3)](https://man7.org/linux/man-pages/man3/dlopen.3.html)에 따라 초기화는 open 반환 전에 실행될 수 있고 close 성공이 완전 unmap을 보장하지 않는다. fixture가 직접 DART 객체 API를 호출하지 않아도 implicit global constructor/destructor 및 allocator 동작은 미확정이다. 정적 감사로 이 부작용을 제거했다고 주장하지 않는다. 설치 매뉴얼 두 파일의 SHA도 `loader_documentation.json`에 보존했다.

## 6. Native Fixture

`fixtures/probe_a.c`는 C11/POSIX/glibc만 사용한다. DART/Gazebo 헤더, link dependency, object API, dlsym/native symbol 호출은 없다.

- 기본 `fixture_offline`: `dlopen`/`dlclose` import 자체가 없고 NEEDED는 libc.so.6 하나다. `--contract`, `--simulate success/open-error/close-error`, harmless `--await-signal`만 테스트했다. 실제 load command는 exit77로 거부했다. simulation의 success를 Probe success로 분류하지 않는다.
- `PROBE_A_LOADER_ENABLED=1` 분기는 **REL object `loader_review_only.o`까지만** 컴파일했다. 링크·실행하지 않았으며 이 object를 실행할 수 없다. 미래 reviewed rebuild+별도 승인 없이는 활성화하지 않는다.
- 향후 경로는 secondary namespace/readonly/limit/preexisting maps gate → 고정 `/audit/libdart.so.6.13.2` 1회 RTLD_NOW|RTLD_LOCAL → bounded512 mapping records → close1회다. 다른 라이브러리 선택/재시도/다음 Probe 자동 호출이 없다. source gate만으로 external launcher 전체 검증을 대체하지 않는다.
- event schema는 sequence, host monotonic timestamp, pid, phase/result, detail, loader_compiled, detail_truncated. bounded escape를 사용하고 truncation은 표시한다. 실제 host receive time은 미관측 값으로 만들지 않고 외부 supervisor 책임으로 남겼다.
- open20/close21/mapping22/invalidinput64/output74/disabled77/gate78/caughtSIGTERM143. fatal signal의 음수 returncode는 외부 supervisor가 구분해야 한다.
- SIGTERM handler는 고정 최소 JSON을 async-safe write 후 _exit143한다. destructor를 signal handler에서 부르지 않는다. 정상 return이 아닌 경우 close/글로벌 정리가 보장됐다고 하지 않는다. offline signal test는3초 alarm failsafe가 있으며 timeout 관측 후 SIGTERM·wait로 정상 정리했다.

컴파일은 `-Wall -Wextra -Werror`를 유지했다. 최초 write() 반환값 무시 경고로 컴파일 실패했고, 반환값을 받도록 최소 수정 후 두 target 모두 warning0으로 빌드했다. `fixture_build_initial.json` 보존. ELF parser가 version suffix `(8)`을 symbol로 잘못 읽은 정적 검토 발견도 최초 JSON으로 보존하고 UND 뒤 name 추출 및 회귀 테스트로 교정했다.

## 7. Sandbox·종료 결합 설계와 위험

현재 단계에서는 새 systemd unit이나 Bubblewrap을 실행하지 않았다. 기존 **Integration V1이 검증한 것은 Python fixture 조합**이다. prospective `systemd user service → Bubblewrap → Native Fixture`에서 MemoryMax64M/swap0/TasksMax8/CPUQuota25%/period100ms/RuntimeMax8s/TimeoutStop2s/KillModecontrol-group/Delegate=no를 유지하는 설계다. 64MiB가 DART 초기화에도 충분하다고 가정하지 않고 자동 상향을 금지한다.

진짜 load 전 외부 supervisor의 immutable file/hash manifest, per-file bind/interpreter closure, own cgroup/PID-start/namespace 검증, 환경 제거, private net/tmpfs 및 live mapping identity 대조가 필요하다. script `plan.py`는 JSON을 출력할 뿐 실행 능력이 없다. runtime command와 runtime campaign directory는 만들지 않았다.

정상/비정상/timeout 모두 기록을 보존하고 own InvocationID unit만 정리하는 계약을 설계했다. close가 멈추면 timeout 실패로 남기며 라이브러리 계산을 재실행하지 않는다. 타 서비스·상위 cgroup을 복구 명목으로 변경하지 않는다. resource 초과와 실제 kernel namespace failure는 과거부터 UNVERIFIED다.

`remaining_blockers.json`의12개 항목 판정: Build-ID identity VERIFIED, 경로/정적 의존성/RUNPATH/sandbox PARTIALLY_VERIFIED, 초기화·종료·destructor/allocator·EH·초과강제효과·kernel failure·실제DART Runtime UNVERIFIED. B/C의 경로/RUNPATH는 별도 BLOCKED 범위를 유지한다.

## 8. 오프라인 테스트와 원본 보존

신규 **27 PASS**, 회귀 **49 PASS**(Integration15/Smoke6/Hardening6/Targeted22), 합계 **76 PASS / 0 FAIL**. unittest runner SKIP0. 별도로 실제DART load/close·Native service·resource 초과·kernel failure4개 활동은 NOT_RUN/SKIP으로 기록한다. 과거 Runtime PASS를 더하지 않는다. 초기 compile/parser 문제와 retest는 위 경로에 있다.

정확한 명령:

```
PYTHONDONTWRITEBYTECODE=1 python3 validation/dart-probe-a-static-audit-v1/scripts/build_fixture.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s validation/dart-probe-a-static-audit-v1/tests -p 'test_*.py' -v
```

회귀는 같은 unittest discover의 tests 경로를 각각 `validation/dart-cgroup-integration-v1`, `dart-cgroup-smoke-v1`, `dart-sandbox-hardening-v2`, `dart-targeted-evidence-v1`로 바꿔 실행했다. 실제 결과는 `tests.log`/`regression_*.log`/`test_summary.json`이다. audit 재현은 `PYTHONDONTWRITEBYTECODE=1 python3 validation/dart-probe-a-static-audit-v1/scripts/audit.py`로 가능하나 새 task 보고서만 재생성하며 이전 증거 root에는 쓰지 않는다. 필요한 로컬 B/C 빌드·이전 ignored evidence가 없는 기기에서는 동일 감사가 불가능하므로 자동 다운로드·다른 binary 대체를 하지 않는다.

`integrity.json`: **54,610개 기존 파일 변경·누락0/기존범위신규0, main HEAD/status 유지 PASS**. main과 실험 기존파일을 읽고 새 task·실험handoff·.git·pycache만 제외했다. installed21개(Core closure16+optional5) ELF의 해시를 추가로 재확인한다. 원본 source/evidence·production·SDF·패키지·시스템 loader·AppArmor·Clock/Capture 기준 변경은 없다.

## 9. 게시·남은 최소 작업

검증된 새 source/tests/경량 reports와 실험 handoff만 명시적 staging/diff 검토 후 실험 branch에 commit/push한다. 바이너리·object·work/full preservation manifest는 제외한다. 실제 SHA와 원격 일치는 로컬 `git_publication.json` 및 최종응답을 따른다. main 게시/force push/reset/rebase/stash/merge는 없다. `/tmp` build/raw와 main ignored/untracked 원본은 GitHub에 자동 이전되지 않는다.

**다음 최소 작업은 기존 sandbox/supervisor에 immutable per-file dependency manifest와 mapped-library identity 검증을 연결하고, 실제 DART를 로드하지 않는 무해한 Native Fixture로 그 경계를 검증하는 것이다.** 그 결과와64MiB 미확정·implicit init/fini 잔여 위험을 검토한 뒤에만 별도 Core-only Probe 승인 요청 여부를 결정한다. 이번 종료 후 자동 후속 실행은 없다. 실제 Runtime 명령을 제공하지 않는다.
