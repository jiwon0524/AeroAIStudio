# 정적 분석 종료 후 필요한 최소 증거

현재 Host 판단은 NEEDS_TARGETED_EVIDENCE다. 이 문서는 실행 계획의 검토 초안이며 실행 승인이 아니다. 객체 생성·삭제/예외/Host/Gazebo/World::step/Stage B는 이번에 실행하지 않는다. 같은19개 슬롯을 다시 훑는 새 정적 단계를 자동 추가하지 않는다.

가능한 두 입력 중 하나를 우선 선택한다.

1. 원 설치 core/Bullet Build ID와 정확히 대응하는 debug/symbol map·원 배포 빌드 자료. V4 slot18_analysis.json의 SHA/Build ID와 대조해야 한다. 다른 빌드의 함수명을 설치본 사실로 전파하지 않는다.
2. 별도 승인된 **비물리 객체 수명 probe**. 별도 subprocess와 고정한 A/B/C closure에서 synthetic Skeleton→BodyNode→ShapeNode의 소유·해제, CollisionObject/Group/Detector factory/deleter 및 cast 경계를 최소 사례로 관측한다. World/Gazebo/step 없이도 실제 DART 객체 생성·삭제가 필요하므로 V4 권한으로 실행할 수 없다.

probe 검토 시 최소 계약:

- production/시스템 파일 교체 없이 자식 loader 경로를 고정하고 실제 mapped libraries·해시·allocator/deallocator provider를 기록한다.
- 설치 A를 대조로 하고 baseline B, trace OFF를 먼저 비교한다. ON은 owner/quiescent·capacity·flush와 추가 metadata 영향 계획을 별도로 정의한다.
- 생성/소멸 및 allocator callback 횟수·주소 소유권을 최소 단위로 검증하며 실패 후 자동 재시도하지 않는다. 잘못된 포인터/UB를 일부러 production에 주입하지 않는다.
- 예외 주입은 검토된 allocation-failure 경계에 한정하고 정상/실패 부분 생성의 해제 계약·누수·이중 해제 관측 기준을 사전에 정한다. 기존 설치 binary가 sanitizer 미계측일 수 있어 sanitizer 성공만으로 ABI 전체를 인증하지 않는다.
- 유한 timeout·격리 출력·종료 기준과 fixture safety audit를 사전에 확정한다. subprocess 제한만으로 UB/계측 오염이 해소됐다고 하지 않는다.

이 증거 또는 항목별 잔여 위험의 명시적 수용 전에는 READY_FOR_SEPARATE_HOST_APPROVAL로 올리지 않는다. 실제 Host 실행은 그 후에도 별도 승인이 필요하다. NOT_RUNTIME_VERIFIED / Stage B BLOCKED 유지.
