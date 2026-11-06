# 재현

실험 worktree 루트에서 실행한다. V2의 기존 격리 build/fixtures와 원래 main의 기존 미커밋 offline 테스트가 필요하다. Git clone만으로 해당 입력이 복원되지 않는다. 신규 출력은 이번 단계 디렉터리에만 쓴다. 이전 결과를 보존하려면 새로운 복사본에서 실행한다.

1. `python3 validation/dart-consumer-abi-v1/scripts/analyze.py`
2. `python3 validation/dart-consumer-abi-v1/scripts/check_integrity.py before`
3. `python3 validation/dart-consumer-abi-v1/scripts/abi_review.py`
4. 아래 pytest 명령을 실행한다.
5. `python3 validation/dart-consumer-abi-v1/scripts/finish_analysis.py`
6. `python3 validation/dart-consumer-abi-v1/scripts/check_integrity.py after`

각 pytest는 PYTHONDONTWRITEBYTECODE=1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1을 지정한다. Python은 `/home/jiwon/Projects/AeroAIStudio/.venv-ubuntu/bin/python`이다.

```bash
python -m pytest -q -p no:cacheprovider validation/dart-consumer-abi-v1/tests --junitxml=validation/dart-consumer-abi-v1/work/consumer.xml
python -m pytest -q -p no:cacheprovider validation/dart-capability-abi-v2/tests --basetemp=validation/dart-consumer-abi-v1/work/native-tmp --junitxml=validation/dart-consumer-abi-v1/work/native.xml
```

프로젝트 회귀는 원래 main에서 PYTHONPATH=.:src와 같은 환경 설정으로 실행한다. XML 및 basetemp는 이번 실험 worktree 아래의 절대 경로로 지정한다.

```bash
python -m pytest -q -p no:cacheprovider -p tools.host4_offline_test_guard tests/test_gazebo_action24_one_tick_control.py tests/test_action24_collision_pair_integration.py --junitxml=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-consumer-abi-v1/work/regression.xml --basetemp=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-consumer-abi-v1/work/regression-tmp
```

안전성 전제: 신뢰하는 glibc ldd trace/relocation, 검토된 native fixtures 및 runtime fence를 유지한다. Gazebo/World::step/Stage B/full DART suite를 실행하지 않는다. Loader PASS는 runtime PASS가 아니다.
