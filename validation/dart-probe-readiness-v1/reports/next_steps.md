# 다음 단계와 개발 로드맵

다음 최소 작업은 **무해한 Fixture로 파일 쓰기·네트워크 강제 차단 환경 검증**이다. 현재 private cwd/timeout/rlimit만으로 안전한 sandbox라고 판단하지 않는다. 시스템 설정 변경 없이 사용할 수 있는 격리 방법을 검토하고, 불가하면 disposable VM 등 별도 환경을 준비한다. 실제 DART는 로드하지 않는다.

그 뒤 exact dependency closure/allocator provider, B/C External 실제 파일, RUNPATH 빈 항목의 영향과 init/fini/TLS/thread shutdown을 검토한다. A 전용 native fixture source/imports/실행 전 limits를 검토한 후에만 A의 별도 실행 승인 요청을 준비한다. B는 owner/deleter source, C는 B 정상경로와 제한 fault window, D는 비물리 entry/owner-quiescent flush 검토가 추가로 필요하다. 현재 A~D 모두 BLOCKED이며 이번 완료는 실행 승인이 아니다.

계획 순서(이번 구현·실행 없음):

1. DART Runtime Probe 준비 검토 및 차단 조건 해소
2. 별도 승인된 제한적 Probe A → B → C → D, 각 실패 시 중단
3. 별도 승인 범위의 Gazebo 실제 물리 연동 검증
4. 기존 DQN 및 Safety Layer 동작 검증
5. A* 경로 계획 추가 검토 — A*는 그래프 탐색, DQN은 학습 정책으로 역할을 구분
6. D* Lite 등 동적 재계획 검토
7. 이동 시간·경로 길이·충돌률·성공률 비교
8. 임무별 시나리오 확장
9. 정찰·정보 수집·자동 복귀 기능 확장
10. 실제 드론 연동 및 안전 검증

각 단계는 앞선 결과 및 해당 실행 권한을 전제로 한다. 소방·재난 정찰은 범용 플랫폼의 응용 후보다. NOT_RUNTIME_VERIFIED / Stage B BLOCKED 유지.
