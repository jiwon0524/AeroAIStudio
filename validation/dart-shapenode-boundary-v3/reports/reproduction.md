# 재현

실험 worktree 루트, Python3 표준 라이브러리와 기존 g++/readelf/objdump/addr2line/ldd, 원래 main .venv-ubuntu pytest를 사용한다. 패키지 설치는 없다. V2/Capability V2 source/build/추출 헤더 및 원래 main의 offline regression 파일이 필요하다. 기존 원본은 읽기 전용이며 새 결과가 덮어써지지 않도록 복사된 분석 위치에서 실행한다.

```bash
python3 validation/dart-shapenode-boundary-v3/scripts/preservation.py before
python3 validation/dart-shapenode-boundary-v3/scripts/map_slots.py
python3 validation/dart-shapenode-boundary-v3/scripts/refine_identity.py
python3 validation/dart-shapenode-boundary-v3/scripts/exception_tables.py
python3 validation/dart-shapenode-boundary-v3/scripts/lifetimes.py
python3 validation/dart-shapenode-boundary-v3/scripts/dispatch.py
python3 validation/dart-shapenode-boundary-v3/scripts/evidence.py
python3 validation/dart-shapenode-boundary-v3/scripts/loader_audit.py
```

pytest는 PYTHONDONTWRITEBYTECODE=1/PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 및 `/home/jiwon/Projects/AeroAIStudio/.venv-ubuntu/bin/python`으로 실행한다.

```bash
python -m pytest -q -p no:cacheprovider validation/dart-shapenode-boundary-v3/tests --junitxml=validation/dart-shapenode-boundary-v3/work/new-final.xml
python -m pytest -q -p no:cacheprovider validation/dart-consumer-abi-v2/tests --junitxml=validation/dart-shapenode-boundary-v3/work/v2.xml
python -m pytest -q -p no:cacheprovider validation/dart-consumer-abi-v1/tests --junitxml=validation/dart-shapenode-boundary-v3/work/v1.xml
python -m pytest -q -p no:cacheprovider validation/dart-capability-abi-v2/tests --basetemp=validation/dart-shapenode-boundary-v3/work/native-tmp --junitxml=validation/dart-shapenode-boundary-v3/work/native.xml
```

프로젝트 regression은 main에서 PYTHONPATH=.:src와 같은 환경으로 실행한다. XML/temp 경로는 새 worktree 아래 절대 경로다.

```bash
python -m pytest -q -p no:cacheprovider -p tools.host4_offline_test_guard tests/test_gazebo_action24_one_tick_control.py tests/test_action24_collision_pair_integration.py --junitxml=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-shapenode-boundary-v3/work/regression.xml --basetemp=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-shapenode-boundary-v3/work/regression-tmp
python3 validation/dart-shapenode-boundary-v3/scripts/summarize.py
python3 validation/dart-shapenode-boundary-v3/scripts/preservation.py after
```

summarize는 보존한 최초 실패 XML도 입력으로 쓴다. 새 재현에서는 기존 `work/new-initial.xml`에 접근하거나 그 역사 입력을 보존한 위치를 연결한다. 최초 실패를 다시 만들기 위해 테스트를 과거 버전으로 바꾸지 않는다. handoff reconciliation은 최초 V2 snapshot을 읽은 관측이며 게시 뒤 같은 결과가 생성되지 않을 수 있다.

Fixture는 object/shared ELF를 compile/link만 하고 실행/dlopen하지 않는다. delete/cast 표현이 코드에 있더라도 실제 호출은 금지다. trusted glibc trace relocation 외의 plugin initialization/Gazebo/World::step/Stage B/throw/catch runtime을 수행하지 않는다. Native의 기존 synthetic algebra와 새 boundary compile-only를 구분한다.
