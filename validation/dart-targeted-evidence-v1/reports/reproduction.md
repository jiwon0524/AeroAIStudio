# 재현과 범위

실험 worktree 루트에서 기존 Python3/readelf/g++/objcopy/gpgv/dpkg-deb/curl만 사용한다. 설치·global config·target ELF 실행은 없다.

1. 먼저 AGENTS/docs rules/handoff와 V4 자료를 읽고 새 복사본 작업 위치를 사용한다. 기존 이번 단계 work/reports를 덮어쓰지 않는다.
2. scripts/preserve.py before → inventory.py. preservation은 기존 V4 work/preservation.json 및 main 로컬 Evidence가 필요하다. 누락 시 중단/UNKNOWN이며 허위 manifest를 만들지 않는다.
3. search_official.py는 명시 공식12 URL만 제한 크기/시간으로 조회하며 HTTP redirect를 따르지 않는다. 외부 네트워크 승인 필요. 최신 메타데이터가 변경될 수 있으므로 과거 hash의 동일 재현을 보장하지 않는다.
4. acquire_reference.py는 OSRF 공개 keyring과 InRelease 검증 후 인덱스/패키지/소형 packaging hash를 검증한다. 3개 ELF exact byte match가 아니면 새 결과로 분류한다. 패키지 설치·source/build 실행은 하지 않는다.
5. summarize.py → python3 -B -m unittest discover -s validation/dart-targeted-evidence-v1/tests -v. 테스트 tiny shared ELF compile/link/objcopy는 하되 실행/로드하지 않는다. Native 또는 과거 runtime fixture를 실행하지 않는다.
6. write_report.py는 이번 22개 결과를 기록하는 역사 보고서 작성 도구다. 재현 시 실제 test count/log/새 요청 결과에 맞게 검토해야 하며 이 파일의 성공 서술을 측정값으로 쓰지 않는다. preserve.py after로 독립 보존 검사한다.

이번 raw logs/metadata/package/source files는 work에만 있고 Git에 게시하지 않는다. 보고서 SHA/URL/크기로 원본을 추적할 수 있으나 해당 work의 자동 백업은 없다. Probe 계획은 실행 스크립트가 아니며 A~D 전부 NOT_RUN이다.
