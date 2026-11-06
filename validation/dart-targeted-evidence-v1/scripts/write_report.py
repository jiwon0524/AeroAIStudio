from evidence import *
from datetime import datetime,timezone
inv=json.loads((ROOT/'reports/binary_inventory.json').read_text())['binaries']
rows='\n'.join('|'+r['role']+'|`'+r['build_id']+'`|`'+r['sha256']+'`|' for r in inv)
paths='\n'.join('- **'+r['role']+'**: `'+r['real_path']+'`' for r in inv)
save('test_summary.json',dict(tests=22,failures=0,errors=0,skipped=0,log='work/tests-final.log',log_sha256=sha(WORK/'tests-final.log'),scope='standard-library unittest; compile/read-only independent tiny ELF fixtures; no target ELF execute/load',historical_tests_not_added=[161,194,178,165],native='NOT_RUN',probes='A-D NOT_RUN',loader='NOT_RUN in this phase'))
save('failure_analysis.json',dict(events=[{'stage':'network','fact':'sandbox DNS failures; retried only with explicit tool escalation','result':'official requests completed; original DNS JSON preserved in work'},{'stage':'official metadata collector','fact':'HTTPS ddebs Release returned HTTP downgrade location; curl proto-redir rejected downgrade and postcheck raised','result':'no HTTP fetch; collector changed to never follow redirects; final 301 recorded; initial raw headers retained in tool trace, final work files are final responses'},{'stage':'source control parser','fact':'initial parser rejected valid empty Checksums-Sha256: field','result':'accept empty control field; add regression test; retry succeeded; no ABI/production criteria changed'}],test_failures=0,notes='Operational/parser failures are not ABI mismatch. No scientific result promoted from failed/missing requests.'))
text=f'''# Targeted Evidence Verification V1 — 최종 보고서

관측일: {datetime.now(timezone.utc).isoformat()}. 이번 단계는 설치본 식별·공식 증거 수집·Probe 설계만 수행했다.

## 1. 최종 판정과 V4 기준

**TARGETED_EVIDENCE_UNAVAILABLE / Host NEEDS_ADDITIONAL_EVIDENCE / NOT_RUNTIME_VERIFIED / Stage B BLOCKED.**

필요한 정확한 설치본 debug/type 증거는 확보하지 못했다. 원본 패키지와 빌드 규칙을 확보해 출처는 강화했으나 핵심 ABI 불확실성을 줄일 새 타입/함수 증거는 없다. 전 세계 자료의 부재를 증명한 판정이 아니다.

V4 보고 결과는 DESTRUCTOR_BOUNDARY_PARTIALLY_VERIFIED, Host NEEDS_TARGETED_EVIDENCE,161 PASS, loader12 오류0,30673파일 변경0이다. 이번에 그 테스트·loader·전체 V4 manifest를 재실행한 결과로 표시하지 않는다. slot18은 INFERRED D1이며 런타임 안전성은 미검증이다.

## 2. Git·Worktree·인계 대조

작업 위치 `/tmp/AeroAIStudio-dart-internal-trace`, branch `experiment/dart-internal-trace`. 시작 로컬 HEAD와 실시간 원격 모두 `f42f2abbdca5b3f7db9d5e4ab130d478f778a0f7`, clean. 원격 main은46134c6이다. main 수정8/미추적31/staged0을 보존했다.

context-handoff verify는 REVIEW_REQUIRED이며 원인은 HEAD 하나였다. snapshot a7a7b32는 f42f2ab의 직접 부모다. V4 게시29파일 목록과 local publication receipt, 저장된 verdict/integrity SHA 일치로 예상 전이를 확인했다. helper 자체가 MATCH였다고 하지 않는다. 원본 main의 이전 handoff보다 실험 worktree의 최신 지침을 우선했다. rules/AGENTS와 V3 ShapeNode·Destructor/V4 자료를 읽었다. 기존 단계 파일을 덮어쓰지 않았다.

## 3. 실제 바이너리 목록

{paths}

6개 고유 ELF다. Gazebo engine-plugins 경로와 상위 경로는 같은 hash이며 별도 소비자로 중복 집계하지 않는다. 심볼릭 링크/링크 대상/정규화 경로는 `binary_inventory.json`에 구분했다. 설치본은 패키지 ELF이고 B/C는 별도 로컬 빌드다.

## 4. SHA-256와 Build-ID

|대상|Build-ID|SHA-256|
|---|---|---|
{rows}

V4 verdict의 A/B/C/Bullet 4개 식별자와 해시/Build-ID가 모두 일치한다. External/Gazebo는 해당 V4 verdict identifier 목록에 없음을 표시하고 새로 관측했다. SONAME/NEEDED/RPATH/RUNPATH/섹션·debuglink는 inventory 원본을 따른다. 설치4개에는 debug_info가 없고 B/C에는 있다.

## 5. 패키지와 출처 검증

설치 Core/External/Bullet의 실제 소유 패키지는 모두 **libdart-core+collisions+odelcpsolver6.13:amd64,6.13.2+ds1-1~osrf2~noble**다. 개별 Ubuntu libdart-collision-bullet6.13 패키지가 설치된 것으로 혼동하지 않는다. Gazebo 소비자는 libgz-physics7-dartsim:amd64 **7.8.0-1~noble**이며 현재 APT candidate7.9.0과 다르다. 업그레이드하지 않았다.

공식 [OSRF 저장소](https://packages.osrfoundation.org/gazebo/ubuntu-stable/) InRelease를 로컬 OSRF 공개 keyring으로 gpgv 검증했다. Packages/Sources.gz의 SHA-256·크기도 서명된 인덱스와 일치했다. 다운로드 전 amd64 원본 패키지 크기 **1,469,456 bytes**, SHA-256 **7602bf8695cb1e673be9008ed17222e9ff1a08b3bbaa211a05a4ce73c579037e**를 확인하고 다운로드 후 재검증했다. work에만 dpkg-deb --extract했다. 설치·maintainer script 실행은 없다.

이 원본 패키지의 Core/External/Bullet 세 ELF는 설치본과 byte hash 및 Build-ID가 모두 같다(`official_binary_matches.json`). 이는 현재 공식 배포 아티팩트와 설치 파일의 동일성이다. 과거 설치 트랜잭션의 다운로드 출처까지 확정하지 않는다. Gazebo는 이번 원본 패키지 다운로드 대조 범위 밖이다.

## 6. Debug Symbol 탐색 결과

순서대로 (1)실제 Build-ID local debug 경로 (2)dpkg 로컬 debug 패키지 (3)debuglink 파일 경로 (4)설치/apt 메타데이터 (5)APT archives cache (6)공식 저장소/Build-ID 서비스 (7)공식 동일 버전 배포 파일·소스 메타데이터를 확인했다. 무제한 파일 시스템 검색은 없다.

- 설치4개가 가리키는 debug 파일과 해당 local Build-ID debug 파일은 없다. 관련 설치 debug 패키지와 APT cache 후보도 없다.
- OSRF noble 서명 Release의 component는 main이며, 해당 Packages에 DART debug package가 없다. dart pool 디렉터리에도 dbg/debug/buildinfo/changes 이름이 광고되지 않았다. 조회한 main/debug 경로3개는404다. 상위 gazebo 저장소 목록에도 별도 debug 저장소 안내를 발견하지 못했다.
- Ubuntu debuginfod의 Core/External/Bullet/Gazebo **정확한 Build-ID별 요청4개 모두404**다. [Ubuntu debuginfod 매뉴얼](https://manpages.ubuntu.com/manpages/noble/man1/debuginfod-find.1.html)의 Build-ID 조회 방식을 따른다. 해당 서버 응답 범위의 부재이며 다른 서비스의 부재는 아니다.
- ddebs.ubuntu.com noble Release HTTPS는 HTTP로301 안내해 자동 추종하지 않았다. 이후 공식 HTTP 주소의 Release와 universe amd64 인덱스(5,115,004 bytes)·분리 서명만 명시적으로 받았다. 기존 Ubuntu 공개 keyring으로 로컬 APT 인덱스를 인증하고, 거기에 기재된 ubuntu-dbgsym-keyring4,528 bytes 패키지를 해시 대조·격리 추출해 **debug Release 서명도 검증**했다. 시스템 keyring 설치/변경은 없다.
- Ubuntu DART debug 패키지는 **6.13.2+ds-0ubuntu3**로 설치 OSRF 버전과 다르다. 서명된 메타데이터의 Core Build-ID `72d206d70515066d8eeed2a9d9802a92902a4bdf`, Bullet `bd762891ca50ecbb55d1964ab7624de23d071e6a`도 설치본과 다르다. VERSION_ONLY_MATCH 후보/advertised Build-ID mismatch로 기록하고90MB Core·3.75MB Bullet ddeb는 다운로드하지 않았다. 실제 debug 파일을 확보한 것처럼 분류하지 않는다. `ubuntu_debug_signature.json`과 `ubuntu_debug_candidates.json` 참조.
- 이 Ubuntu 검색은 noble base universe 인덱스 범위이며 모든 pocket·외부 아카이브의 부재를 증명하지 않는다.

요청별 HTTP/오류/해시/크기는 `official_requests.json`, 검색 범위는 `debug_symbol_search.json`.404와 접근 제한/미확보를 구별한다. 같은 검색을 반복하지 않는다.

## 7. 정확한 Debug 일치 여부

설치 Core/External/Bullet/Gazebo는 모두 **DEBUG_NOT_FOUND**다. Baseline/Trace의 자체 embedded DWARF는 각자의 Build-ID에 대응하지만 설치본과 다르다. `build_id_matches.json`의 EXACT_BUILD_ID_DEBUG_FOUND는 이 로컬 빌드 자체에만 적용된다. 설치 슬롯18 이름 복구에 사용하지 않았다.

설치 debuglink의 CRC32는 추출했다. 실제 후보 파일이 없어 설치본 CRC 대조는 NOT_RUN_NO_CANDIDATE다. 도구의 Build-ID/CRC 정상·오류 동작은 독립 compile-only ELF fixture로 검증했다. 같은 DART 버전만으로 exact match를 선언하지 않는다.

## 8. 확보한 신규 증거

서명된 원본 runtime 패키지와 설치3 ELF 동일성, 서명된 source index 및 소형 dsc/debian.tar.xz를 확보했다. source metadata가 지시한 크기/해시를 확인한 뒤 다운로드했다. packaging rules/control/changelog는 work에만 읽어 추출했다.

rules는 debhelper13, pybuild/cmake, hardening/reproducible/+lfs, shared build, skip install RPATH/FLANN/PAGMO 조건을 제공한다. override_dh_strip는 없다. 이것만으로 원 builder가 dbgsym을 보관/게시했다고 추론하지 않는다. 원본 source archive는 메타데이터만 확인했고 다운로드·재빌드는 하지 않았다.

## 9. 해결한 범위와 재현 빌드 가능성

설치 소유 패키지·아키텍처·공식 원본과 동일성 및 debug 검색 범위를 명확히 했다. 현재 후보 버전과 설치 버전 혼동을 제거했다. 재현 recipe는 확보했으나 historical compiler/dependency versions/buildinfo/changes/원 빌드 환경이 없어 **정확한 Build-ID 재현 가능성은 미확정**이다. 같은 소스를 새로 빌드하는 것은 설치본 debug 확보의 대체가 아니다.

## 10. 남은 불확실성과 추가 정적 분석 가치

설치 슬롯18 실제 symbol/type identity, 전체 class/member layout, nested helper·callback 의미, 객체 수명/allocator interposition, 전체 EH/cleanup, shutdown/concurrency, 계측 중립성은 남는다. V4의 this−144/D0→추론D1/sized-delete1664·48·368/선택된 factory cold cleanup 근거는 유지한다.

새 debug가 없는 상태에서 같은19슬롯·중첩 helper를 반복 추적할 기대 이득은 작다. V5/V6 정적 단계를 추가하지 않는다. 정적 배치/선택된 호출이 실제 소유권·예외·allocator 동작을 증명하지 못하므로 한정된 lifetime probe 계획 검토가 필요한 이유다.

## 11. Runtime Probe A~D 설계

모든 Probe는 **설계만 작성, NOT_RUN, BLOCKED_PENDING_FIXTURE_SAFETY_AND_SEPARATE_APPROVAL**이다. 가설·대상·정확한 arm 경로·사전조건·격리·부작용·중단·성공·증거·보존 계약10개 항목은 `probe_plan.json`, library path/hash/Build-ID는 `probe_library_arms.json`이다.

|Probe|가설·검증 대상|주요 선행조건/성공 계약|
|---|---|---|
|A Loader/Symbol|목적형 fixture의 Core/External/ODE/Bullet closure와 symbol provider|init/fini·dlopen/dlclose 검토 후 mapped real paths/hash·provider 일치. Gazebo plugin은 metadata만 사용|
|B Lifetime|유한 Skeleton→BodyNode→ShapeNode 및 Bullet 객체의 normal ownership/delete|factory·detector owner lifetime과 관측기 검토. 소유 allocation별 정확히1회 해제, 순서/잔여 count 기준 사전 확정|
|C EH|선택한 부분 생성 실패의 storage/owner cleanup|B 정상 경로 이후, scope가 증명된 allocation fault1개만. unwind1회·해제 count 대조. 전역 임의 N번째 allocation 실패 금지|
|D OFF/ON|유한 비물리 metadata/recorder의 추가 동작과 ownership|OFF부터 비교. ON은 World/step 없이 도달하는 reviewed entrypoint 필요. owner/quiescent·overflow·flush 기준과 예상 추가 호출 명시|

A/B/C는 설치대조 A→Baseline B→Trace OFF C 순서로 계획한다. D의 ON은 추가 gate다. B/C도 설치 Bullet을 명시적으로 유지하는 혼합 closure이며 full isolated stack이 아니다. fixture 바이너리는 아직 제작·검증하지 않았다. World destructor/step 연계 trace와 physics/FP/clock 중립성은 이 계획으로 인증할 수 없다.

## 12. 격리·위험·중단·성공 기준

계획은 실행별 전용 cwd/HOME/TMPDIR, env -i의 제한된 환경, child-only loader 경로, timeout10s/TERM 후2s KILL, core dump 금지와 resource limits, 네트워크·run directory 밖 쓰기를 막는 검토된 sandbox/VM을 요구한다. 그 기능의 가용성은 아직 검증하지 않았다. timeout/subprocess만으로 메모리 UB나 파일 접근이 통제됐다고 보지 않는다.

dlopen 자체도 init/fini·registration/IFUNC를 실행할 수 있어 A를 단순 정적 loader 검사로 취급하지 않는다. 예기치 않은 library/provider·callback·write/network·signal/timeout/allocator 오류면 즉시 종료하고 다음 arm/재시도를 하지 않는다. A 대조 실패도 전체 중단이다.

성공은 사전에 정한 **유한 관측 계약**의 통과이며 whole ABI/메모리 안전성 증명이 아니다. source/binary/toolchain/closure 해시, 승인 범위, event counts와 exit/signal·출력 해시를 보존한다. 환경 전체/자격증명은 저장하지 않는다. production·시스템은 read-only, 원본 Evidence는 보존한다. 설치파일 교체·전역 loader 변경·자동 rollback/reset은 없다.

## 13. Host 승인 준비 상태

**NEEDS_ADDITIONAL_EVIDENCE**. 식별·출처는 강화되었지만 debug는 없고 destructor/allocator/EH는 HIGH/UNKNOWN이다. probe fixture safety·init/fini·fault 전략·실제 격리 환경 검증이 남는다. A~D 실행 준비 완료나 READY_FOR_SEPARATE_PROBE_APPROVAL로 올리지 않는다. 별도 사용자 승인 전 어떤 Probe도 실행하지 않는다. Host 및 Stage B 승인도 아니다.

## 14. 신규 테스트와 실패 기록

**22 PASS, failure/error/skip0**. Build-ID 추출/readelf 대조·SHA known vector·package 빈 필드/continuation/오류·실제 debug ELF 매칭/다른 빌드 거부·debuglink CRC 정상/변조·잘못된 ELF section·경로 symlink escape·공식 URL 출처·원본 패키지 실제 hash·계획 금지 상태를 검사했다.

독립 미니 ELF는 g++ shared compile/link와 objcopy만 사용하고 **실행/dlopen하지 않았다**. DART/Native 객체 생성·삭제, 예외 Runtime, loader Probe A~D, Gazebo/World::step/Stage B는 NOT_RUN이다. 과거161/194 등을 더하지 않는다.

운영상 초기 DNS 제한은 승인된 네트워크 조회로 해결했다. Ubuntu debug 서명은 최초 로컬 공개키 부재로 미검증이었으나 인증된 keyring 패키지를 격리 추출해 최종 검증했다. 초기 collector는 HTTP downgrade 응답에서 안전하게 중단했고 redirect 비추종으로 수정했다. source parser는 유효한 빈 checksum 필드를 거부해 수정하고 회귀테스트를 추가했다. scientific test 실패/ABI mismatch로 기록하지 않는다(`failure_analysis.json`).

## 15. 원본·Evidence 무결성

이번 before/after 범위는 이전 V4 보존목록에 V4 자체 및 dpkg/APT-source/loader config 읽기 전용 파일을 추가했다. 파일 수·변경·main HEAD/status 보존의 최종 관측은 `integrity.json`이 권위 원본이다. 이전 목록에서 누락된 파일은 before 시0개였다. 기존 V1~V4/main 기록·소스·build는 수정하지 않았다. 시스템 package/library/config 변경은 없다. 새 다운로드와 debug/ELF fixture는 새 work만 사용했다.

## 16. Git 게시

신규 scripts/tests/경량 reports와 실험 handoff만 명시적으로 선택해 검사·commit·push한다. work/원본 패키지·debug·바이너리·raw manifest는 게시하지 않는다. 최종 commit/push/실시간 원격 SHA 확인은 로컬 `reports/git_publication.json` 영수증에 기록하며, 게시 전 본 보고서가 아직 push 완료를 주장하지 않는다. main/force push/merge/reset/rebase/stash는 없다. 자기 commit SHA를 넣기 위한 재귀 commit을 만들지 않는다.

## 17. 다음 최소 작업과 이식성

우선 OSRF/DART artifact 관리자에게 inventory의 **정확한 Build-ID**에 맞는 retained dbgsym/debug/buildinfo를 요청할 자료를 제공한다. 이번에는 외부 메시지를 보내지 않았다. 대안은 `probe_plan.json`의 fixture·격리·allocator fault 계약 검토다. 그 뒤에도 실제 Probe는 별도 승인 대상이다. 같은 정적 검색을 자동 반복하지 않는다.

`reports/reproduction.md`에 재현·입력 경계를 기록했다. /tmp work/build와 main의 ignored/untracked Evidence는 Git push로 다른 기기/계정에 전달되지 않는다. raw 자료의 장기 외부 백업은 이번 범위에서 수행하지 않았다. **NOT_RUNTIME_VERIFIED / Stage B BLOCKED 유지.**
'''
(ROOT/'reports/final_report.md').write_text(text)
(ROOT/'reports/reproduction.md').write_text('''# 재현과 범위

실험 worktree 루트에서 기존 Python3/readelf/g++/objcopy/gpgv/dpkg-deb/curl만 사용한다. 설치·global config·target ELF 실행은 없다.

1. 먼저 AGENTS/docs rules/handoff와 V4 자료를 읽고 새 복사본 작업 위치를 사용한다. 기존 이번 단계 work/reports를 덮어쓰지 않는다.
2. scripts/preserve.py before → inventory.py. preservation은 기존 V4 work/preservation.json 및 main 로컬 Evidence가 필요하다. 누락 시 중단/UNKNOWN이며 허위 manifest를 만들지 않는다.
3. search_official.py는 명시 공식12 URL만 제한 크기/시간으로 조회하며 HTTP redirect를 따르지 않는다. 외부 네트워크 승인 필요. 최신 메타데이터가 변경될 수 있으므로 과거 hash의 동일 재현을 보장하지 않는다.
4. acquire_reference.py는 OSRF 공개 keyring과 InRelease 검증 후 인덱스/패키지/소형 packaging hash를 검증한다. 3개 ELF exact byte match가 아니면 새 결과로 분류한다. 패키지 설치·source/build 실행은 하지 않는다.
5. summarize.py → python3 -B -m unittest discover -s validation/dart-targeted-evidence-v1/tests -v. 테스트 tiny shared ELF compile/link/objcopy는 하되 실행/로드하지 않는다. Native 또는 과거 runtime fixture를 실행하지 않는다.
6. write_report.py는 이번 22개 결과를 기록하는 역사 보고서 작성 도구다. 재현 시 실제 test count/log/새 요청 결과에 맞게 검토해야 하며 이 파일의 성공 서술을 측정값으로 쓰지 않는다. preserve.py after로 독립 보존 검사한다.

이번 raw logs/metadata/package/source files는 work에만 있고 Git에 게시하지 않는다. 보고서 SHA/URL/크기로 원본을 추적할 수 있으나 해당 work의 자동 백업은 없다. Probe 계획은 실행 스크립트가 아니며 A~D 전부 NOT_RUN이다.
''')
print('final report written')
