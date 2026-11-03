# V0.7 검증 보고서

V0.7 CODE COMPLETE / ACTUAL GAZEBO VALIDATION PENDING

GAZEBO ACTUAL INTEGRATION: NOT VERIFIED

2026-10-31, Windows 11 x64 / Python 3.14.3 / PySide6 6.12 / CPU Torch 2.15.0+cpu.
기존 V0.6 프로젝트에서 확장. 실제 Ubuntu/Gazebo 환경이 없어 native 통합 성공 여부를 판단할 수 없다.

## 최종 보고 20항목

1. 변경 파일: contracts/discovery/robot_model/physics_controller, environment/transport/stepping/sensor_provider/world_generator/process_manager, curriculum/trainer, evaluator/safety metrics, Brain/UI, Ubuntu scripts, 검증 도구와 신규 테스트. FILES.txt 및 CHANGES.md 참조.
2. Ubuntu 실제 환경: 없음. wsl.exe는 존재하지만 `wsl --list --quiet` 결과 배포판 없음. Ubuntu를 설치하거나 기존 OS 설정을 바꾸지 않았다.
3. Gazebo version: gz 실행 파일 없음. Harmonic은 대상 버전이며 실제 설치 버전이 아니다.
4. ROS2 version: 미설치/미검증. Jazzy는 선택 대상이다.
5. ros_gz: 미설치/미검증. 기존 bridge 선택 구조 유지, 실제 브리지 smoke 미실행.
6. World launch: 실제 미검증. Physics SDF 생성 및 XML 파싱 PASS는 launch 성공을 뜻하지 않는다.
7. Sensor actual test: 미검증. timestamp, sequence, age, frame 계약 및 stale/timeout 거부는 fixture로 검사했다.
8. Stepping actual test: 미검증. 요청 steps×dt와 실제 simtime 변화 비교 및 paused 확인은 fixture로 검사했다.
9. Physics movement: 미검증. 별도 PHYSICS 제어는 Twist/DiffDrive 사용, 매 action pose teleport 없음. reset pose 이동만 허용. 실제 이동량 검증 코드는 준비되었다.
10. Collision actual test: 미검증. contact topic/history, 지면·자기접촉 제외, source 표시, strict missing-stream 실패 및 명시적 geometric fallback 코드/fixture 검사.
11. Closed Loop: GridWorld 학습/평가 실행. Gazebo Sensor→Agent→Action→Physics→Sensor는 실제 미검증.
12. Brain Map Gazebo: 공통 telemetry/BrainEvent 경로 및 fixture 검사. 실제 Gazebo episode 분석 미검증. 제공 이미지는 GridWorld UI이다.
13. Replay Gazebo: 공통 직렬화/trajectory/replay 경로 보존. 실제 Gazebo episode replay 미검증.
14. Dynamic DQN: 아래3 seed, 각2000 학습, 각조건200 평가. 평균 성공률 OFF20.17%, ON25.67%. 실사용 성공 기준 달성 주장은 하지 않는다.
15. Safety: 평균 충돌률 OFF28.33%, ON15.33%, timeout OFF51.5%, ON59.0%. 개입은 휴리스틱 audit이며 인과적 유익/유해 판정이 아니다.
16. Curriculum: seed7/42/99 모두 complete=true. Hard 노출1500/1550/1200. 단계별 최소 episode/evaluation과 잔여 budget 보장, checkpoint 복원 구현.
17. 전체 unit test: 최종 실행 결과는 아래 최종 검사 항목에 기록.
18. gazebo integration tests: 실제 runtime 부재로3개 SKIPPED. 통과로 계산하지 않는다.
19. 알려진 문제: native Transport API/서비스·토픽 이름, Harmonic rendering, DiffDrive 실제 이동, contact stream, 종료/restart는 실제 Ubuntu에서 확인 필요. PHYSICS 동적 장애물은 정적 검증 전 차단. 저성공률·seed 편차·timeout 잔존. Geo/ENU/Korea 건물·도로는 P0 통과 조건 미충족으로 보류.
20. V0.8 권장: Ubuntu24.04 + Harmonic 실제 설치에서 headless launch→sensor→step→movement→contact→loop→Brain/Replay 순서로 증거 수집. 다음 GUI/Ogre2·ROS2 옵션을 확인하고, 그 후 Geo 기반 기능 착수.

## 학습 및 평가 실측

GridWorld DynamicHard20×20, 정적 밀도18%, moving3, danger0. Double DQN, Sensor, rewardV2, lr.001, warmup256, clipping10, epsilon decay.998/end.05, max150steps. Seed7/42/99 각2000회 학습. 최소 단계(100,100,100,100,400), 최소평가2, interval50, threshold.8. 평가 각200회×2조건×3seed=1200회. 학습 seed와 평가 seed 분리, 각 seed 내 OFF/ON 동일 reset seed. 안전 개입 외 조건 동일. V0.6 20회 평가와 직접 순위 비교하지 않는다.

| Seed | Hard 학습 | Safety | 성공 | 충돌 | Timeout | Overrides | Near samples | 평균 최소 clearance(m) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| 7 | 1500 | OFF | 3.5% | 23.0% | 73.5% | 0 | 15393 | 0.2655 |
| 7 | 1500 | ON | 5.5% | 9.5% | 85.0% | 351 | 17708 | 0.2970 |
| 42 | 1550 | OFF | 21.0% | 32.0% | 47.0% | 0 | 12642 | 0.2355 |
| 42 | 1550 | ON | 26.5% | 20.5% | 53.0% | 74 | 14103 | 0.2730 |
| 99 | 1200 | OFF | 36.0% | 30.0% | 34.0% | 0 | 12029 | 0.2400 |
| 99 | 1200 | ON | 45.0% | 16.0% | 39.0% | 86 | 13564 | 0.2925 |

seed 간 평균±모집단표준편차: 성공 OFF20.17±13.28%, ON25.67±16.14%; 충돌 OFF28.33±3.86%, ON15.33±4.52%; timeout OFF51.50±16.44%, ON59.00±19.25%. 정확한 값은 learning_v07.json이 기준이다. Near는 clearance<0.5m인 step 수이며 episode 충돌 횟수가 아니다. 경계 근처에서도 증가한다. useful/harmful heuristic은 중복 가능하며 counterfactual 비교가 아니다.

## 실행 및 증거

```powershell
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m pytest tests -m gazebo -q
.venv/Scripts/python.exe tools/verify_v07_learning.py --output ../../work/v07-learning
.venv/Scripts/python.exe tools/verify_v07_runtime.py --output ../../work/v07-runtime
```

Linux에서는 `.venv/bin/python`. native 테스트는 `AERO_GAZEBO_INTEGRATION=1`을 명시하고 실제 gz가 있어야 실행된다. 검사 자체를 통과시키려고 fixture를 실제 런타임으로 대체하지 않는다. runtime_v07.json의 NOT AVAILABLE 항목은 모두 미검증이다. 소스ZIP에는 요약/이미지/SDF를 포함하고 대량 학습 모델·episode 로그는 제외한다.

## 최종 검사

전체 pytest: **61 passed, 3 skipped (36.95s)**. Gazebo marker만: **3 skipped, 61 deselected (0.23s)**. compileall PASS. 기본 Grid 회귀1000회 학습/독립100회 평가: 성공100%, 평균38steps, 충돌0, timeout0. 기존 V0.6 ZIP에 포함된 테스트 소스는 byte 단위로 동일하고 기존 파일 삭제 없음. final_checks.json에 검사 결과를 기록했습니다.

UI offscreen1600×1040 캡처7종을 보관했습니다. Diagnostics/Brain/Replay 등은 GridWorld UI 증거이며 Gazebo 실행 화면이 아닙니다. Training 캡처는 실행 전 설정 화면입니다.
