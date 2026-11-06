# 재현 범위

실험 worktree 루트에서 실행한다. Python3 표준 라이브러리, 기존 GCC/Clang/readelf/objdump/ldd 및 원래 main의 .venv-ubuntu pytest가 필요하다. 패키지 설치는 하지 않는다. 기존 V1·Capability V2 소스/추출 헤더/build/native fixtures는 읽기 전용 입력이다. 이들 로컬 ignored 자료는 새 clone만으로 복원되지 않는다.

새 결과를 덮어쓰지 않으려면 독립 복사본에서 실행한다. 순서:

```bash
python3 validation/dart-consumer-abi-v2/scripts/preservation.py before
python3 validation/dart-consumer-abi-v2/scripts/compile_boundary.py
python3 validation/dart-consumer-abi-v2/scripts/elf_tables.py
python3 validation/dart-consumer-abi-v2/scripts/disassemble.py
python3 validation/dart-consumer-abi-v2/scripts/contracts.py
python3 validation/dart-consumer-abi-v2/scripts/loader_audit.py
```

네 테스트 묶음은 PYTHONDONTWRITEBYTECODE=1/PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, Python=/home/jiwon/Projects/AeroAIStudio/.venv-ubuntu/bin/python로 실행한다.

```bash
python -m pytest -q -p no:cacheprovider validation/dart-consumer-abi-v2/tests --junitxml=validation/dart-consumer-abi-v2/work/new-final.xml
python -m pytest -q -p no:cacheprovider validation/dart-consumer-abi-v1/tests --junitxml=validation/dart-consumer-abi-v2/work/v1.xml
python -m pytest -q -p no:cacheprovider validation/dart-capability-abi-v2/tests --basetemp=validation/dart-consumer-abi-v2/work/native-tmp --junitxml=validation/dart-consumer-abi-v2/work/native.xml
```

프로젝트 regression은 원래 main에서 PYTHONPATH=.:src와 같은 환경으로 실행하며 새 절대 XML/temp 경로를 사용한다.

```bash
python -m pytest -q -p no:cacheprovider -p tools.host4_offline_test_guard tests/test_gazebo_action24_one_tick_control.py tests/test_action24_collision_pair_integration.py --junitxml=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-consumer-abi-v2/work/regression.xml --basetemp=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-consumer-abi-v2/work/regression-tmp
```

```bash
python3 validation/dart-consumer-abi-v2/scripts/summarize.py
python3 validation/dart-consumer-abi-v2/scripts/preservation.py after
```

summarize의 고정 address/pattern 검사는 이번 hash의 binary 근거에만 해당하며 binary가 달라지면 실패를 조사한다. 기준을 조용히 바꾸지 않는다. handoff reconciliation은 최초 V1 snapshot을 읽은 시점의 관측이며 후속 handoff 갱신 뒤 같은 결과로 재생성되지 않는다. 초기 artifact를 work에 보존한다.

ELF 분석과 compiler는 실행하지만 새 DART/plugin object, dynamic_cast, boundary 함수, fixture shared ELF는 실행하지 않는다. Loader는 trusted glibc trace relocation뿐이며 Gazebo/World::step/Stage B는 금지한다. Native 회귀의 안전한 synthetic algebra 범위와 새 boundary compile-only 범위를 구분한다.
