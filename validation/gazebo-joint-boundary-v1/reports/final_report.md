# 외부 DSO·종료 접근 차단 경계 확인

**BLOCKED_MISSING_COMPLETE_DENIAL_AND_ATTEMPT_RECORDING. Stage B BLOCKED / 위험 수용 UNDECIDED / 실제 런타임 UNVERIFIED.**

시작 HEAD `5f37e63b81bff8efe22786f6446126fe1fcfb5b1` 일치. tracked/index clean, 기존 dangling symlink만 untracked였다. context-handoff·AGENTS·DEVELOPMENT_RULES·handoff·직전 보고서·기존 봉인 계약을 읽었다. 직전 체크포인트의 증거 해시와 현재 ODE 후보 ELF 해시를 재확인했다. 과거 인계의 prepublication HEAD 차이는 부모와 15개 파일 범위로 대조했다. 기존 전체 계약은 재검증했다.

## 실제로 무엇이 차단되는가

`boundary.json`은 5개 제어 경계, 6개 외부 구성요소/수명 범주, 소스 행과 SHA-256, 재사용 증거 해시를 기록한다. 아래는 **봉인된 명령·코드의 의도와 한계**다. 이번 단계에서 namespace나 native 프로세스가 실제 생성됐다는 관측은 없다.

|경계|접근 제한 장치|차단 시도 기록·최종 실패|시작·종료 및 한계|
|---|---|---|---|
|파일|bwrap 새 root tmpfs, 파일별 `--ro-bind-fd`, root RO remount. host root 디렉터리를 통째로 bind하지 않음.|범위 밖 파일의 ENOENT/EROFS 등 오류가 자동 위반 기록으로 연결되지 않음. 외부 DSO가 오류를 무시하면 수집기가 알 수 없음.|bridge/harness exec 전에 namespace를 준비하는 argv다. 일반적인 namespace 상속은 loader 초기화·thread·종료까지 적용될 의도지만 실제 mount/readback은 실행 증거가 필요함. 승인 파일 재열기·stat/access 탐색, `/scratch`, `/run`, `/proc`, `/dev`, `/dev/shm` 사용은 포괄적으로 금지되지 않음.|
|네트워크|`--unshare-all`의 새 network namespace. 의도된 host socket 전달 없음.|socket/connect/bind/send 등의 전역 요청 기록 장치는 계약에 없음. 단순 실패·fallback은 native fatal이 아님.|외부 host 연결 범위를 제한하지만 로컬 소켓/loopback/abstract UNIX 등의 생성·사용 자체를 금지하는 syscall 정책은 아님. 다른 namespace에서 만들어 상속한 소켓은 namespace 변경만으로 권한이 사라지지 않음.|
|동적 로딩|파일 visibility·환경 초기화. 기존 Sim `CheckLoadRequest`는 seal 후 해당 entrypoint의 lookup/open/LoadLib 전에 실패.|instrumented Sim 경로의 fatal/unexpected packet은 실패 latch로 연결됨. 외부 direct dlopen/dlmopen은 같은 관측을 보장하지 않음.|mounted ELF 또는 procfd alias를 통한 직접 late load를 전역 차단하지 않음. 마지막 mapping은 ACK 전에 찍는 snapshot이며, 이후 생성자/해제 callback·일시 mapping까지 덮지 않음.|
|상속 FD|기존 bridge는 stdin/stdout FIFO 검사 및 `close_range(5,~0U,0)` 성공을 target exec 전에 요구.|기존 bridge 진입 오류는 exit78. 다만 stderr가 소켓/일반 파일인지, 입출력 방향이나 채널 alias는 검사하지 않음.|기존 supervisor는 `Popen(..., stdin=PIPE, stdout=PIPE, stderr=PIPE)`를 요청함. 이것은 정상 caller의 구성 근거이며 bridge 자체의 불변식과 다름. 실제 0..4의 type/mode/device/inode와 동적 FD 생성은 실행에서 확인해야 함.|
|종료 판정|100스텝·마지막 live mapping·EXIT_ACK 뒤에도 양쪽 EOF와 exit, 소유한 정리·무결성을 요구.|관측된 fatal/금지 요청은 latch되어 exit0·EOF·정리 성공으로도 PASS가 되지 않음.|종료 callback이 **보고하지 않은** 거부 요청은 식별할 수 없음. 현재 native collector는 session factory이며 승인된 전체 실행 loop도 없음. ACK가 syscall 차단이나 감사 완료를 뜻하지 않음.|

봉인 argv에 `--seccomp`가 없고, 명시적인 service 자원 속성에 SystemCallFilter/RestrictAddressFamilies도 없다. 이는 **현재 계약이 그러한 장치의 설치·범위·위반 전달을 증명하지 않는다**는 뜻이다. 관측하지 않은 host/상위 sandbox의 보안 설정이 전혀 없다고 단정하지 않는다. cgroup·rlimit은 자원 한도이며 경로별 접근 요청을 거부하고 기록하는 장치가 아니다.

## 외부 DSO와 종료 callback별 판정

|대상 / 수명|기존 경계가 제공하는 것|기술 차단으로 남은 것|
|---|---|---|
|ODE/libccd 시작·box·collision·thread cleanup·dCloseODE|일반 파일·네트워크 namespace 제한이 대상 exec 이전부터 적용될 구성|내부·간접 callback의 금지 요청 전역 사전 거부와 보고. initialization 반환 실패를 잡는 직전 ODE 후보는 이 문제와 별개.|
|기본 FCL wrapper·전역 생성자·allocator·해제|동일 namespace 제한. 직전의 bounded 도달 조건 유지|외부 FCL collision API 호출을 단순 mapping/기본 wrapper 생성과 혼동하지 않음. 전역 init/destructor·지원 의존성의 시도 차단/기록은 미확인.|
|crypto provider/config·종료|미마운트 host 설정·모듈 visibility 제한|설정 탐색 실패 후 기본 provider 대체가 가능해도 관측되지 않음. provider 초기화 전에 설치되어 전 수명 유지되는 완전한 요청 정책·기록 없음.|
|transport/ZeroMQ·background·shutdown|별도 network namespace 및 제한된 파일 경로|로컬 socket 허용 범위, inherited socket 예외, 신규 socket와 discovery/설정 탐색 및 thread 종료 시도의 전역 정책·기록 부족.|
|console/logging·해제|승인 RO 입력 변경 불가, 의도된 출력 pipe와 scratch 범위|임의 scratch 로그/설정 탐색의 정책 판정과 실패 latch가 연결되지 않음. record/playback plugin 제외만으로 console 전체를 제외할 수 없음.|
|EXIT_ACK 이후 모든 callback/DSO unload|namespace 제한을 해제하는 새 launcher 코드를 추가하지 않음. 기존 EOF/exit/cleanup 조건 유지|ACK 이후 최종 process death까지 모든 thread·자손 및 일시 syscall을 다루는 차단·인증된 최종 감사 증거 없음.|

파일이 계약에 있다는 사실은 실제 mapping이나 호출 관측이 아니다. syscall import·mapping snapshot은 요청 전 차단이나 전체 감사가 아니다. 현재 제한된 visibility가 있다는 이유만으로 외부 구현의 모든 금지 요청을 감지했다고 보지 않는다.

## 확인된 빈틈의 최소 수정

별도 `inputs/fd_bridge.c` 후보에서 다음만 수정했다.

- 입력 FD 0/1/2를 각각 FIFO·read-only/write-only/write-only로 확인하고 O_PATH를 거부한다.
- GO·관측·stderr pipe의 device/inode가 서로 다른지 확인한다. 기존의 무검사 stderr socket/file을 FD1로 복제하는 경로를 거부한다.
- stdin을 read-only `/dev/null`로 교체하며 char device major1/minor3, O_NOFOLLOW를 검사한다.
- FD 5 이상 닫기 실패, rlimit 적용 실패, 그 외 설정 실패는 subject exec 전에 exit78. GO용 FD3와 관측용 FD4, 기존 CPU/AS/FSIZE/NOFILE/CORE 한도는 유지한다.

새 bridge만 컴파일·링크했다. compiler는 직전 해시와 일치하고, 공통 사용 header는 이전 해시와 대조했다. `build_receipt.json`에 source/ELF SHA-256, Build ID·interpreter·NEEDED·RUNPATH를 포함한 readelf metadata, 의존 header와 컴파일 인자를 기록했다. 의존 ELF는 libc이며 subject DSO를 bridge에 링크하지 않았다. `fd_bridge.patch`는 원본 보존용 zero-context diff다. 원본 bridge·prefix는 수정하지 않았다.

새 C 후보는 **컴파일·정적 검사만** 했다. `fd_policy.py`는 handoff FD 증거의 순수 Python 검사기이며 실제 attestor·launcher에 연결되지 않았다. 이를 native 실행 또는 전 수명 FD 차단 증거로 승격하지 않는다. DSO가 시작 뒤 새 소켓/FD를 만드는 문제도 해결하지 않는다. libc interposition만 새로 넣어 직접 syscall·다른 loader namespace까지 덮었다고 주장하는 수정은 하지 않았다.

## 검사와 조건부 배치

기존 31+25=56개 static/mock case를 원본 source에서 재사용했고, 결과·임시 디렉터리만 이번 단계로 돌렸다. 과거 보고서를 덮어쓰지 않았다. 추가 **34개** 검사로 정상 FD evidence, stdin/stdout/stderr의 socket/file/device·O_RDWR·O_PATH·alias·방향 오류, handoff 잔여 FD·null identity·GO/관측 identity, close_range/rlimit의 사전 실패 분기, 초기화 및 EXIT_ACK 뒤 위반 packet의 실패 latch, 서비스/marker 전 exit78을 확인했다. 합계 **90개 PASS_STATIC_MOCK_ONLY**다.

추가로 **관측 packet이 없는 금지 요청을 기존 collector가 구별할 수 없다는 모의 반례**를 기록했다. 같은 정상 packet trace에 외부 요청을 보고하는 채널이 없으면 collector는 정상 PASS를 반환한다. 실제 파일/네트워크 접근을 수행한 검사가 아니며, 이 반례는 기술 준비를 BLOCKED로 유지해야 하는 근거다. 반대로 위반 packet이 실제 전달되면 종료가 exit0이어도 전체 실패한다.

차단 경계 확인 조건이 충족되지 않아 ODE 후보·bridge 후보의 새 prefix 배치와 전체 재봉인을 **진행하지 않았다**. 직전 ODE 후보 ELF는 해시로 검증해 재사용 가능 상태로 보존했다. 기존 manifest `789737d947f8c0ebd1466300792667fc9c838adba5834168e5c82bc6e4846aae`와 모든 mount/allowlist/provider/attestor 입력은 그대로다. 후보 일부만 섞는 거부 검사는 재사용했다. 현재 실제 선택은 여전히 원래 bridge/ODE 입력이며, 어떤 후보도 배치 완료로 표시하지 않는다.

## 해소에 필요한 최소 증거와 중단점

현재 차단을 풀려면 다음 연결 증거가 필요하다.

1. 허용 파일·출력·FD·로컬 통신·동적 로딩 범위와 금지 요청을 정확히 정의하고, 기존 namespace 정책이 제한하는 범위와 동일하게 고정한다. 필수 정상 초기화까지 무조건 socket/open 금지로 바꾸지 않는다.
2. 외부 DSO의 최초 loader 초기화 이전부터 모든 thread/자손과 최종 process death까지, 금지 요청을 접근 전에 거부하는 경계 및 직접 syscall/간접 경로/상속 FD 예외가 없다는 검토 근거를 갖춘다. 또는 각 외부 구현의 matching source/binary/build/callback closure로 그 범위를 증명해야 한다.
3. 거부를 삼키고 exit0 하는 경우에도 누락·유실·조기 EOF·위조를 실패로 취급하는 신뢰 가능한 외부 거부 기록과 최종 수집 완료 조건을 연결한다. 단순 stderr 문자열 검색·maps polling·ENOENT·빈 namespace는 이 증거를 대체하지 않는다.
4. 정적·모의 검토를 통과한 뒤에만 ODE/bridge 후보와 영향을 받는 산출물을 별도 prefix에 배치하고, 전체 파일/mount/SONAME/allowlist/native/provider/attestor 계약을 함께 재봉인한다. 현재는 이 조건 전이다.

실제 namespace/mount/readback, 정확한 FD 전달과 신규 FD 생성, 실제 provider/maps, 실제 위반 거부·감사 전달/유실 처리, timing·자원·100스텝·최종 ACK/EOF/exit/소유한 정리·무결성은 별도 실행에서만 확인된다. 이번에는 실행 검토 명령을 제출하지 않는다. 기존 launcher는 service/marker뿐 아니라 manager 조회 전 exit78이다.

원본 main HEAD/status·dirty/untracked 일반 파일 hash, 기존 dangling symlink inode/target, 과거 보고서와 봉인 입력 보존 검사를 재사용·재확인했다. 실제 native/bridge/harness/harmless/Gazebo/DART 실행, step, service, marker 소비, sudo/install/system 변경은 없었다. 알려진 compiler/검사 작업은 완료됐고 외부 CWD/remote/container 가시성은 UNKNOWN이다. /tmp의 후보 ELF/object/header·원시 로그와 원래 ignored/untracked 증거는 Git 게시로 기기에 전달되지 않는다.

재현: 이 phase 아래 `scripts/build.py`, `scripts/audit.py`, `tests/check_boundary.py`를 Python으로 실행한다. 전자는 compile/link만 하며, 후자는 정적·Python 모의 검사만 한다. runtime 실행 진입점은 추가하지 않았다.
