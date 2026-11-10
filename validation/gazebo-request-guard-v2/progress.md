# Request guard v2

- 10de7c4/experiment 상태와 v1 인계/최종 보고서, 봉인 contract/manifest/loader/collector/launcher 확인.
- 기존 main/1442+ 입력·dangling symlink 보존 baseline 작성. 기존 실행 계약과 결과 불변.
- 정상 입력 카탈로그594 alias/429 원본 read-only 매핑. 원본 inode 불변성 증명 부족으로594 모두 거부.
- v1 C journal/supervisor와 Python AuditGate 재사용. ADDFD_SEND broker, task loop, journal 변환 후보 추가.
- 3 TU 별도 compile/link/static ELF 검사 PASS. 새 바이너리 실행 없음.
- 신규70 static/Python mock PASS. 기존 실제 프로토콜을 합성 입력으로 재사용하여 GO/마지막 mapping/ACK/EOF/cleanup 판정 유지.
- PARTIAL/NOT DEPLOYABLE: 정상 입력 불변성, 일반 loader/thread 정책, preexec handoff와 trusted live audit transport 미완료.
- 기존/새 entry는 service/marker 이전78. Stage B BLOCKED / 위험 UNDECIDED / 실제 runtime UNVERIFIED.
- 상세 증거·다음 최소 작업은 reports/final_report.md. 대용량 work/와 기존 로컬 증거는 게시 대상 제외.
