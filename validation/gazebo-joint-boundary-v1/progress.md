# Isolation boundary review

- HEAD5f37e63 및 기존 지침/보고서/봉인 계약 대조. 기존 symlink 외 clean.
- 기존 namespace/RO mount/FD bridge와 시도 기록·실패 latch를 분리해 5 controls /6 external lifetime categories 기록.
- stderr type/mode 미검사 및 채널 alias 빈틈 수정 후보: bridge1개 compile/link, 실행·배치 없음.
- 기존56 + 새34 static/mock PASS. Silent foreign denial에 대한 collector 관측 공백도 모의 반례로 확인.
- ODE 후보 유효 hash 재확인. 경계 미확인으로 별도 prefix 배치/전체 재봉인 조건 미충족. exit78 유지.
- Stage B BLOCKED / 위험 UNDECIDED / runtime UNVERIFIED. 다음 최소: 전 수명 사전 거부 + 신뢰 가능한 최종 시도 기록 연결 증거, 그 후 후보 통합.
