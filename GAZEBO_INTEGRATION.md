# V0.7 Gazebo 실제 검증 절차

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

현재 Windows에는 gz/ROS2/ros_gz/Docker가 없고 WSL 배포판도 없습니다. 실제 launch/sensor/step/physics/contact/loop/render를 확인하지 못했습니다. fixture PASS를 native PASS로 간주하지 않습니다. 이전 설계 설명은 docs/V0.6-GAZEBO_INTEGRATION.md에 보존했습니다.

1. Ubuntu24.04에서 `bash scripts/setup_ubuntu_dev.sh`로 OS, Python, gz, ROS, display, GPU 상태부터 확인합니다. 설치 옵션은 명시적 INSTALL 확인 뒤에만 사용합니다. 저장소 keyring/CUDA/ROS를 무단 설치하지 않습니다.
2. Gazebo Harmonic 및 gz.transport13/gz.msgs10 Python bindings를 설치한 Python 환경에서 패키지를 editable 설치합니다. OS Python bindings 경로와 venv 접근을 확인합니다. ROS2 Jazzy/ros_gz는 optional입니다.
3. `bash scripts/verify_ubuntu_dev.sh` 후 `python tools/verify_v07_runtime.py --output validation/native-headless`를 실행합니다. CLI flag는 실제 gz sim --help에서 탐색합니다. gz topic/service discovery 결과와 world namespace를 기록합니다.
4. SDF parse→서버 alive→world/agent/goal/obstacles→sensor topic/message→scene pose→step progress→physics movement→contact→closed loop→shutdown 순으로 확인합니다. 실패 단계에서 로그와 last_error를 보존합니다. NOT AVAILABLE은 PASS가 아닙니다.
5. `AERO_GAZEBO_INTEGRATION=1 python -m pytest tests -m gazebo -q`로 native integration을 실행합니다. 실제 episode 로그를 앱 Replay/Brain Map에서 열어 동일 timestamp·pose·action을 대조합니다. headless 성공 뒤 GUI 옵션을 실행하고 rendering을 별도로 기록합니다.

KINEMATIC은 기존 위치 제어입니다. PHYSICS는 질량/관성/마찰/wheel joints/DiffDrive 및 contact sensor를 가진 simple_agent입니다. up/down은 선속도, left/right는 yaw 각속도, stop은0입니다. 매 action set_pose를 쓰지 않으며 reset에만 사용합니다. 물리 mode는 Sensor observation이 필요하고 동적 장애물은 실제 정적 검증 전 차단합니다.

ObservationFrame은 simtime, timestamp, sequence, source, four clearances, goal/agent pose, age를 기록합니다. stale/미래/역순 sample과 timeout은 오류입니다. stepper는 실제 simtime 증가량을 비교합니다. collision은 contact가 우선이며 지면/자기접촉을 필터링합니다. strict contact 검사에서는 missing stream을 실패 처리합니다. fallback을 사용할 경우 geometric_fallback source를 명시합니다. 실제 토픽/API 호환성은 여전히 native 확인 대상입니다.

telemetry에는 actual_world, sensor age, step delta, command, collision source, wall latency/throughput/RTF가 포함됩니다. Brain/Replay는 공통 로그를 사용합니다. process group은 소유 프로세스만 종료하고 grace 뒤 강제 정리합니다. lifecycle은 STARTING/RUNNING/PAUSED/ERROR/STOPPING/STOPPED이며 오류를 조용히 synthetic으로 바꾸지 않습니다.

Ogre2/EGL/X11/Wayland 렌더링과 PyTorch CUDA 사용 여부는 별개입니다. 현재 RTX5070 드라이버610.88은 확인했지만 CPU Torch이므로 CUDA 학습은 검증하지 않았습니다.

공식 참고: [Harmonic DiffDrive](https://gazebosim.org/docs/harmonic/moving_robot/), [Sensors](https://gazebosim.org/docs/harmonic/sensors/), [Gazebo Transport](https://gazebosim.org/api/transport/13/python.html).
