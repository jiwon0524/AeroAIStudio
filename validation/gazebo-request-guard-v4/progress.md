# Integrated request guard v4

- HEAD fb6723e/experiment 및 최신 v3 인계/보고서·봉인 계약 확인. 기존 main/evidence/symlink baseline 보존.
- v3 유효 receipt 재사용. ODE ELF+SONAME 대표부터578경로 전체로 같은 mock router 적용;452경로는 정적 필수. 실제 runtime 입력0/target 허용0.
- 429원본=424준비+5차단,594경로=578+16 대조.5개 모두 정적 root/SONAME 도달 필수. 한도/allowlist 변경 없음.
- native preexec wait/options/동기 journal API, child eventmsg/task/pending/actual ECHILD API와 기존 broker callback 연결. 실제 wait owner/listener/단발 exec/정상 thread 정책은 미완료.
- bounded private framing+수명 adapter+원 Gate/NativeSession 모의 결합. 불확실 reply·journal 예외·PID 세대 등 검토 수정 및 재검사.
- 필요한3 TU compile/link/static PASS, 신규686 static/Python mock PASS. 기존 결과 합산/재실행·새 kernel 입력 준비·native 실행 없음.
- 네 구성요소 모두 PARTIAL/BLOCKED; 비실행 준비 미완료. 서비스/marker 이전78, Stage B BLOCKED / 위험 UNDECIDED / runtime UNVERIFIED.
- 최초 실패/다음 구현 및 조건부 첫 runtime 최소 제안은 reports/final_report.md 하나에 통합. 후보 배치·계약 재봉인 없음.
