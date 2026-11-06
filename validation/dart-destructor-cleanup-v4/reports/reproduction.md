# 재현 범위

실험 worktree 루트에서 Python3 표준 라이브러리와 기존 g++/readelf/objdump/ldd를 사용한다. 기존 Capability V2 build/source·추출 헤더 및 V3 자료는 읽기 전용 입력이다. 패키지 설치와 target library dlopen/객체 생성·삭제는 하지 않는다. 기존 새 결과도 보존하려면 별도 분석 복사본에서 실행한다.

```bash
python3 validation/dart-destructor-cleanup-v4/scripts/preservation.py before
python3 validation/dart-destructor-cleanup-v4/scripts/analyze.py
python3 validation/dart-destructor-cleanup-v4/scripts/contracts.py
python3 validation/dart-destructor-cleanup-v4/scripts/cold_cleanup.py
python3 validation/dart-destructor-cleanup-v4/scripts/loader_audit.py
```

pytest 환경은 PYTHONDONTWRITEBYTECODE=1/PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, Python은 `/home/jiwon/Projects/AeroAIStudio/.venv-ubuntu/bin/python`이다.

```bash
python -m pytest -q -p no:cacheprovider validation/dart-destructor-cleanup-v4/tests --junitxml=validation/dart-destructor-cleanup-v4/work/new-final.xml
python -m pytest -q -p no:cacheprovider validation/dart-shapenode-boundary-v3/tests --junitxml=validation/dart-destructor-cleanup-v4/work/v3.xml
python -m pytest -q -p no:cacheprovider validation/dart-consumer-abi-v2/tests --junitxml=validation/dart-destructor-cleanup-v4/work/v2.xml
python -m pytest -q -p no:cacheprovider validation/dart-consumer-abi-v1/tests --junitxml=validation/dart-destructor-cleanup-v4/work/v1.xml
```

프로젝트 회귀는 원래 main에서 PYTHONPATH=.:src와 같은 환경으로 실행하며 새 worktree 아래 절대 XML/temp 경로를 쓴다.

```bash
python -m pytest -q -p no:cacheprovider -p tools.host4_offline_test_guard tests/test_gazebo_action24_one_tick_control.py tests/test_action24_collision_pair_integration.py --junitxml=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-destructor-cleanup-v4/work/regression.xml --basetemp=/tmp/AeroAIStudio-dart-internal-trace/validation/dart-destructor-cleanup-v4/work/regression-tmp
```

Native45개는 실제 DART 객체 생성 때문에 이번 범위 NOT_RUN이다. 실행하지 않는다. 테스트 source/가드 검토는 test_safety_review.json 참조.

```bash
python3 validation/dart-destructor-cleanup-v4/scripts/finalize.py
python3 validation/dart-destructor-cleanup-v4/scripts/preservation.py after
```

finalize는 보존된 최초 실패 XML과 당시 V3 handoff snapshot을 읽으므로 새 환경에서 역사 파일을 꾸며 만들지 않는다. 기존 raw work 접근이 없으면 해당 역사 대조는 NOT_RUN/UNKNOWN으로 기록한다. 정상 재현을 위해 과거 실패 테스트를 되살리지 않는다. helper 분석은 한 direct 경계, LP followup은 한 cold FDE로 제한하며 C 종료 이후 반복 확대하지 않는다.

독립적인 parser probe ELF는 compile/link만 하고 실행하지 않는다. trusted glibc trace relocation 외의 target initialization/Gazebo/World::step/Stage B/객체·예외 Runtime은 금지한다. 추가 증거 방법은 targeted_evidence_plan.md이며 별도 승인 전 실행하지 않는다. Git에 게시되는 경량 결과가 기존 ignored build/raw 자료를 자동 전달하지는 않는다.
