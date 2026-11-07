# B1 이후 최소 Subject notification 준비 — 결과

**SUBJECT_NOTIFICATION_PREPARED_NOT_EXECUTED / NOT_RUNTIME_VERIFIED / Stage B BLOCKED**.
시작 HEAD5f5a496dce3acf3f777a816308c1d0d018f30ff3/experiment/dart-internal-trace clean 확인. 필수 지침·B1 실행·기존 Gazebo 승인안·Probe B/C/D 계획과 V4 위험 수용 문구를 대조했다. prerequisite_review.md에 기본 필수 게이트와 항목별 명시적 위험 수용의 적용 가능성을 구분했으며, 이번에 어떤 위험도 수용/면제하지 않았다.

선택은 Probe B destroy/notify 요구의 가장 작은 하위 사례: 설치 Core의 정상 Skeleton/BodyNode/ShapeNode에서 BodyNode와 ShapeNode Subject destruction notification 각1개를 직접 callback으로 관측하도록 준비. 기존 B1의 weak/exit-only 근거에 callback count/identity/window/order/unregistration이라는 독립 신호를 추가하는 목적이다. Bullet 새 closure/allocator interposition/exception/trace scope를 동시에 넓히지 않는다. 단, Subject는 destructor 외에서도 notification을 보낼 수 있어 개별 destructor entry/order/D0/provider/free·allocator balance는 이 사례 성공 후에도 NOT_OBSERVED/NOT_MEASURED다. 이 미충족 항목을 우회하거나 Probe B 전체를 완료한 것으로 처리하지 않는다.

fixtures/notification.cpp: GO 뒤만 객체를 생성하며 observer가 owner보다 오래 산다. 등록2개·통지0, 외부 Shape reset뒤에도0, Skeleton owner reset중 node1/body1/ID순서[node,body], unknown/중복/overflow없음·등록잔여0을 요구한다. callback은 noexcept 고정2slot/scalar만 쓰고 할당/출력/등록변경 없음. std::set 등록/해제는 라이브러리에서 발생하므로 관측기 전체가 무할당이라는 주장은 하지 않는다. native에서 weak_ptr를 판정에 사용하지 않는다. 정상 종료만으로 callback이나 destructor 증거를 대체하지 않는다.

컴파일·링크 PASS, 실행 ELF SHA256453d44703cbe423976aebe721311d22e959fc2ab5613539d7584381593749e9d, Build-ID5413820f21ad247eeac0a1048667b334aeb1344d,86944bytes. 실제 target 실행/로딩0, 서비스0, 새 runtime marker0. 기존 B1/V2/Probe A source·evidence·marker는 그대로 보존했다. build command와 identity는 build_result.json/manifest.json, raw log는 work/build.*.

B1의 Bubblewrap/systemd/strict identity GO/cleanup helper를 task-local 코드로 재사용. readonly Core SONAME alias/actual mount argv 유지. readelf와 열린 FD hash/Build-ID/device/inode로 Core16+fixture 검증,62dependency edges/29ROmount PASS. runtime_contract.json은 source/manifest/pin·정확한1회 argv·한도를 고정한다. 별도 task output/두 one-shot marker와 default contract-only 동작, source/환경/branch/freshpaths/resolution/manager 사전검사를 유지한다. 실제 격리/GO/service lifecycle은 이번 재실행하지 않았다.

비실행 검사26PASS/0FAIL/0ERROR. source/manifest hash/AST,actual resolution 및 잘못된 alias/provider/FD/metadata/interpreter거부,marker전 static/manager 실패mock,합성 callback contract 누락/중복/역순/window외/미해제등록/weak대체/소멸자증명주장 거부. 테스트 로그 work/static_tests.log. 이 수치를 실제 notification/runtime 횟수로 해석하지 않는다. 추가 native/서비스/패키지 테스트 없음.

preservation before/after54,971원본파일 changed/missing0,existing-scope additions0,main HEAD/status동일 PASS. 기존 uncommitted/ignored파일과 이전 marker 포함. runtime/,runtime_integrity.json,새두attempt/before/stdout/stderr/canary 모두 부재. no sudo/install/system/production/main/Clock/Capture 변경. build/test jobs ended; external-CWD/remote/container 상태 UNKNOWN.

한도64MiB/swap0/tasks8/CPU25%/service8s/stop2s 유지. B1의 같은 closure/구조와 추가2개 등록 범위를 근거로 선제상향하지 않았으나 실제 충분성은 미검증이다. 실패 시 자동retry/상향 없음. 정확한 별도 실행안 approval_plan.md에 ELF 경로/SHA256/출력/one-shot/통과·중단·정리·무결성 기준을 고정했다. 별도 명시 승인 전 실행 금지.

필수 잔여: B의 개별 destructor/allocator/provider/Bullet factory·deleter·cast/비교arms, C의 부분생성 fault·unwind·해제, D의 비물리 recorder OFF/ON metadata·owner/quiescent/capacity/overflow/flush, Gazebo payload/backend/step gate/dynamicclosure. 문서가 허용하는 항목별 위험 수용은 사용자가 범위·미관측 위험·주장 제외를 명시할 때의 별도 경로이며 이번 결정 없음. Stage B BLOCKED 유지. 이 단계의 새 소스/scripts/tests/경량reports/인계만 실험 브랜치에 게시 후 멈춘다. 원본/공통skill 변경 없음. local /tmp work ELF/pin/snapshot/로그/이전marker는 Git만으로 다른기기에 이동되지 않는다.
