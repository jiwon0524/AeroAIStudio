# DART Probe A Final Integration V1

**PROBE_A_INTEGRATION_READY / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.

이 판정의 범위는 무해 Fixture로 확인한 통합 실행 기반이다. 실제 DART Core 실행·초기화·종료가 인증되었거나 승인되었다는 뜻이 아니다. 실제 Core loader 분기는 REL object만 컴파일했고 링크·실행하지 않았다. 원본 main과 기존 Evidence는 읽기 전용 입력으로 유지했다.

## 구현

기준 commit `2cb4f524ad1f525f5fa9f966c08b0de656ede161`과 clean 상태를 확인했다. Static Audit, Harness, Runtime Readiness, Hardening V2, Cgroup Integration에서 검증한 Allowlist/identity/alias, Native isolation gate, systemd argv, cgroup readback·PID identity·controller 비교·정리 helper를 재사용했다. 기존 파일은 수정하지 않았다.

신규 `scripts/common.py`는 기존 frozen Core16 manifest와 새 Fixture identity를 pin한다. 라이브러리는 canonical absolute path/O_NOFOLLOW FD에서 SHA-256·Build-ID·device/inode가 일치해야 한다. 동일 ELF의 기존 SONAME/DT_NEEDED를 재사용해 58개 전이 edge를 연결하고 모호한 provider·누락·alias 충돌을 거부한다. `stage.py`는 검증한 FD만 기존 sandbox layout의 canonical/SONAME 경로에 readonly bind한다. Core 경로를 `/usr/lib/x86_64-linux-gnu/libdart.so.6.13.2`로 통일했다. 전체 `/usr`나 원본 프로젝트를 bind하지 않는다.

통합 경로는 **systemd user transient service → Bubblewrap → Native isolation gate → simulated post-open WAIT → Supervisor mapped-file identity → GO → simulated close → 종료·정리**다. 무해 Fixture에는 DART loader를 활성화할 수 없으며 libc/loader만 매핑한다. Core 파일은 readonly 노출하지만 로드하지 않는다. Fixture 모드에서 DART mapping은 unexpected mapping으로 거부한다.

기존 Runtime Readiness의 엄격 Core gate도 `common.gate(require_core=True)`로 연결했다. 이 경로는 Core16 전체 inode 출현을 요구하고 기존 CLOSE permission을 Native의 GO로 변환한다. 실제 서비스 실행은 명시적인 no-loader Fixture 모드만 허용한다. 실제 loader entry의 연결/링크/manifest 생성·실행은 별도 명시 승인 단계에서 수행해야 한다. 실제 Core mapping gate는 이번에 실행하지 않았다.

Native 대기는 monotonic 3초 deadline 안에서 한 바이트씩 읽으므로 partial input 뒤 blocking stdio read로 무한 대기하지 않는다. 검토용 Core 소스도 같은 방식과 canonical 경로/GO 계약을 사용한다. 로딩 중 constructor/IFUNC는 post-open gate 전에 이미 실행되므로 gate로 초기화 부작용을 예방한다고 주장하지 않는다.

## 실행 결과

|case|검증 결과|종료|GO/본문|정리|
|---|---|---|---|---|
|accept|실제 mapped FD identity 일치|0|true/true|PASS|
|reject|host 기대 Fixture SHA만 불일치 주입, 파일 변조 없음|78|false/false|PASS|
|timeout|identity 일치 후 GO 보류, 약3초 native timeout|78|false/false|PASS|

세 own unit의 고유 이름·PID/start·출력·cgroup은 `reports/{accept,reject,timeout}/native_fixture_execution.json`에 있다. 정상 accept0.323419초, reject0.614245초, timeout3.355280초였다. 실제 허용·거부·timeout 통합3 PASS, 신규 unittest12 + 관련 회귀15 =27 PASS / FAIL0 / runner SKIP0. 과거 대규모 회귀·정적 감사를 반복하지 않았다.

각 실행에서 native mnt/net/user/pid 격리, readonly root/dev/fixture/input/limits, private tmp/run4MiB·shm1MiB, canary EROFS, host TCP/UNIX/abstract socket 차단이 PASS다. 실제 cgroup은 memory.max67108864/swap0/pids.max8/cpu.max25000 100000이었다. MemoryMax64M/TasksMax8/CPUQuota25%는 변경하지 않았다. 실제 자원 readback은 resource_readback.json에 있다.

각 unit은 not-found, own cgroup 제거, 관측 PID/start 잔여0, canary/temp 제거를 확인했다. 선택한 controller 설정의 전후 변화0, 수동 복원0. reject는 identity 거부가 먼저 발생해 실행 중 controller snapshot은 미수집으로 기록했다. 정상/timeout의 during 변화는 기존 systemd 자동 CPU 전파 범위였고 종료 후0이다. not-found 상태의 기본 property 값을 실제 실행 제한값으로 해석하지 않는다.

## 실패·SKIP와 한계

초기 compile-only C의 misleading-indentation 경고는 Werror를 유지하며 줄을 분리해 수정했다. 실행 환경의 user manager 접근 거부는 unit 생성 전 발생했고, 환경 실행 승인 후 sandbox 밖에서 무해 service만 검증했다. 보고서 집계가 early-reject의 미수집 during 필드를 요구하던 오류는 NOT_SAMPLED로 정정했다. 초기 기록을 보존하고 서비스 자동 재실행은 하지 않았다.

직접 map_files open은 EPERM/UNAVAILABLE다. proc-root FD에서 maps의 device/inode, SHA-256·Build-ID 및 PID/start/maps 전후 안정성을 검증해 **PASS_FILE_IDENTITY**로만 분류한다. resident COW/relocation 페이지, 검사 이후 변경, host 같은 inode 쓰기, 초기화 안전성은 보장하지 않는다. 시스템 보안 설정·권한을 변경하지 않았다.

실제 DART open/close/init/fini/Core mapping, resource 초과 강제 효과, 강제 Supervisor/systemd timeout·signal은 SKIP/미검증이다. 이번 timeout은 Native 프로토콜 deadline이며 systemd RuntimeMaxSec8s의 강제 효과 검증이 아니다. 64MiB의 실제 DART 충분성도 미확정이다.

## 보존·게시·다음 단계

`integrity.json`은 작업 전 manifest에 대한 기존 파일 전체 비교 및 main HEAD/status 보존 결과다. 이 task와 실험 handoff만 이번 소유이며 기존 evidence는 수정하지 않았다. 원시 manifest·binary/REL·stdout/stderr·attempt·pin은 work에 보존하고 Git에 넣지 않는다. 경량 코드·테스트·보고서·인계문만 실험 브랜치에 게시한다. 실제 SHA/원격 일치는 로컬 git_publication.json 및 최종 응답 참조. `/tmp`와 ignored/untracked 자료는 다른 기기에 자동 전달되지 않는다.

다음 단계는 이번 무해 통합 증거와 FD fallback/64MiB 위험을 검토하고, 실제 Core만 open/close하는 별도 실행 범위를 승인받는 것이다. 실제 loader-enabled artifact는 승인된 별도 준비 절차로 링크·pin한 뒤 엄격 Core gate 모드로 실행해야 한다. DART 객체/World/Gazebo/Stage B로 범위를 확대하지 않는다. 현재 작업 종료 뒤 실제 Runtime을 자동 시작하지 않는다.
