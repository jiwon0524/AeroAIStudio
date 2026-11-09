# External resource review

- 시작: HEAD 2ee5c8a 일치, 기존 symlink 외 clean. 현재 지침/인계/계약 읽음.
- 소스 237 built bindings 및 sealed 입력 재검증. ODE/FCL/crypto/transport/logging/종료 경로를 단계·도달 조건별로 기록.
- NDEBUG ODE 초기화 반환 검사 누락 발견. 별도 TU 1개/DSO 1개 후보 빌드, native 실패 latch 연결. 공개 export 불변. 기존 ELF/manifest는 그대로 보존, 후보 미배치.
- 기존 31 static/mock + 새 25 negative 검사. 결과 reports/tests.json 참조. 대상 실행 없음.
- 외부 사전 접근 차단 미완성. exit78 유지. Stage B BLOCKED / 위험 미결정 / 런타임 미검증.
- 다음 최소 작업: 외부 실제 구현·callback과 종료의 source/binary closure 또는 정확한 pre-access guard 확보. 후보 통합 및 실행 검토안은 그 이후.
