# 빈 Skeleton 승인된 1회 실행 — 실패 기록

**SKELETON_LIFETIME_FAILED_BEFORE_MAIN / Stage B BLOCKED**.

준비 commit0376da864f3e7a57d57e50bb0688c7c8cbb7a422와 clean branch, source/manifest pin, executable/Core16 file identity, fresh marker/output, user manager running 및 cgroup v2 rw 확인 후 사용자가 지정한 launch 명령을 정확히1회 호출했다. 두 one-shot marker와 실패 증거를 보존하고 자동 재시도·설정변경·재빌드하지 않았다.

unit aero-skeleton-v1-runtime-24536f9ed8.service, ELF startup에서 libdart.so.6.13 검색 실패, exit127. stdout 없음, READY/live mapped identity/GO/create/reset/expired 모두 NOT_RUN. main 진입 전 dynamic dependency resolution 실패이므로 객체 수명 판정 불가. 이전 Probe A는 실행하지 않았다.

정적 원인 대조: readiness.aliases는 Core dependency edges에 나온 SONAME alias만 만들고 Core 자체의 SONAME을 추가하지 않는다. 이전 absolute dlopen과 달리 새 직접 링크 ELF는 libdart.so.6.13을 NEEDED로 요구한다. static mount contract에 해당 alias가 없다. 호스트 설치 Core canonical file identity는 PASS였으나 sandbox runtime name resolution을 증명하지 못했다. 이번에는 수정하지 않는다.

systemd stderr: service377ms/CPU108ms/memory peak9.5M/swap0B. 이는 formatted 관측이며 exact memory bytes·최종 memory.events·pids.current/live cpu.max는 UNKNOWN이다. stage가 pinned resource gate 이후 bwrap/ELF에 도달한 간접 근거와 live readback 미수집을 구분한다. GO 이전 host namespace inode gate도 미도달. collected unit의 infinity/default resource properties를 실제 적용값으로 사용하지 않는다.

정리: unit not-found/cgroup removed/temp socket 및 canary 삭제, host listener 수신0, controller 선택설정 전후 변화0. 관측 PID/start는 READY 이전에 수집하지 못했으므로 목록이 비어 있다는 이유로 전체 PID 검사 PASS를 주장하지 않는다. 삭제된 cgroup의 잔여 task는 없지만 외부 이동/관측 밖 process는 UNKNOWN. 원본 보존은 wrapper 완료 후 runtime_integrity.json의 실제 결과를 따른다.

후속 최소 작업(이번 실행 아님): executable NEEDED까지 포함한 alias closure를 비실행 정적으로 보완하고, 기존 실패/marker를 유지하는 새 승인안을 준비한다. 새 런타임은 별도 명시 승인 필요하며 현 one-shot 재사용 금지. Gazebo/World/Stage B 자동진행 없음.

wrapper 최종 exit1. runtime_integrity.json PASS: 변경·누락0/기존범위추가0/main HEAD·status 유지.
