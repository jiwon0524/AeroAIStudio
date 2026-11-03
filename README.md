# Aero AI Studio V0.7

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

기존 V0.6 PC 전용 PySide6 앱을 그대로 확장했습니다. Windows GridWorld 학습·평가·Brain Map·Replay를 유지하면서 Gazebo 센서 동기화/접촉/물리 제어/진단 계약을 강화했습니다. 실제 Ubuntu/Gazebo 환경이 없어 native 작동을 검증하지 못했습니다. V0.7 전체 통합 완료를 의미하지 않습니다.

Windows 시작: `./Setup.ps1` 후 `./Start.ps1`. 기존 프로젝트 데이터/모델을 앱에서 열어 계속 사용합니다. 새 프로젝트 생성은 필요하지 않습니다. Python3.11 이상, 현재 검사는3.14 CPU Torch 환경입니다. 기본 UI의 학습 backend는 GridWorld이며 Gazebo는 실제 설치가 필요한 선택 기능입니다.

주요 변경: KINEMATIC/PHYSICS 분리, timestamp/sequence/age 유효성, contact 기반 충돌 source, simstep 검증, actual scene pose telemetry, lifecycle 오류/timeout/정리, 단계별 curriculum 최소 노출, Safety 휴리스틱 audit. PHYSICS는 지상 DiffDrive agent만 대상으로 하며 UAV 비행 검증이 아닙니다. 실제 검증 전 PHYSICS 동적 장애물 및 Geo/Korea 확장은 보류했습니다.

3 seed×2000회 Double DQN 학습 및 각 조건200회 평가를 실행했습니다. Safety ON 평균 성공25.7%, 충돌15.3%, timeout59.0%로 성능 한계가 남습니다. [상세 검증](VALIDATION.md), [Gazebo 절차](GAZEBO_INTEGRATION.md), [변경 목록](CHANGES.md), [이전 V0.6 안내](docs/V0.6-README.md)를 참고하세요.

Ubuntu24.04에서는 `bash scripts/setup_ubuntu_dev.sh`로 먼저 읽기 전용 진단을 실행합니다. `--install`은 출력 명령을 확인하고 INSTALL을 입력해야만 설치합니다. native 검증 도구 `tools/verify_v07_runtime.py`는 headless 우선으로 실제 증거를 기록하며 runtime가 없으면 NOT VERIFIED를 반환합니다. ROS2 Jazzy/ros_gz는 선택 사항입니다.
