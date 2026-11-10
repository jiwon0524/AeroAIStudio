# Sealed copy request guard v3

- HEAD b54c3f6/experiment 확인. 기존 dirty/main/evidence/symlink 보존 baseline 작성.
- 원 계약 불변. 입력 preparation만 실제 수행:424/429 immutable 사본 객체,578/594 alias의 seal 후 해시 PASS.5객체/16alias는64MiB 준비 한도로 차단. 모두 닫음. target permit0.
- alias 동일 객체, 원본/사본 identity 분리, executable intent/seal, PT_INTERP3개와1793 SONAME edge 정적 대조.
- v2 broker를 copy seal+delivery proof 조건으로 확장. v2 tree/v1 supervisor journal와 감사 adapter 재사용.
- 정상 metadata/read/mapping/thread, preexec handoff, live audit integration 차단을 구분. 기존 canonical mapping/native identity 기준 유지.
- 새3 TU compile/link/static PASS; ELF 실행/로드 없음. 초기 feature macro 빌드 오류 보존·수정.
- 신규101 static/Python mock PASS. 원 GO/마지막 mapping/ACK/EOF/cleanup 조건 유지.
- PARTIAL/NOT DEPLOYABLE. 서비스·marker 이전78 / Stage B BLOCKED / 위험 UNDECIDED / 실제 runtime UNVERIFIED.
- 상세 증거와 다음 최소 구현/실행 전용 검증은 reports/final_report.md. 새 실행 계약 배치·재봉인 없음.
