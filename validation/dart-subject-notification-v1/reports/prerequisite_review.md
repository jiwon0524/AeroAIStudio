# B1 이후 진입 조건 대조와 최소 사례 선택

기준 HEAD5f5a496dce3acf3f777a816308c1d0d018f30ff3 / experiment/dart-internal-trace clean. 이번은 준비·컴파일·비실행 검사만이다. **Stage B BLOCKED**, 위험 수용 결정 없음.

## 문서 근거와 현재 증거

1. `validation/dart-probe-readiness-v1/reports/next_steps.md` 계획 순서2→3은 제한된 A→B→C→D 이후 별도 Gazebo 실제 물리 연동 검증이다. 각 단계는 앞선 결과와 실행 권한을 전제로 한다.
2. `validation/dart-targeted-evidence-v1/reports/probe_plan.json` B는 정상 소유 경로/정확한 destroy-notify/잔여 allocation, Bullet detector가 group/object/deleter보다 오래 생존, 설치·baseline·trace OFF의 유한 계약 비교를 요구한다. C는 정상 B 이후 검토된 부분 생성 fault1개, D는 비물리 recorder entry·metadata·owner/quiescent·capacity/overflow/flush를 요구한다. 원 보고서의 all_not_run은 그 시점의 역사이며 최신 B1을 덮어쓰지 않는다.
3. `validation/dart-destructor-cleanup-v4/reports/targeted_evidence_plan.md` 마지막 문단은 “이 증거 또는 항목별 잔여 위험의 명시적 수용 전에는 READY_FOR_SEPARATE_HOST_APPROVAL로 올리지 않는다.”라고 명시한다. 정확한 원 Build-ID debug/symbol map·배포 빌드 자료와 비물리 runtime probe는 대체 입력 경로로 제시돼 있다. debug 자료가 모든 runtime 위험을 없앤다는 뜻은 아니다.
4. `validation/dart-body-shape-lifetime-v1/reports/execution_report.md`는 설치본 정상 생성 관계·owner-release와 weak 만료를 관측했으나 개별 destructor·순서/allocator balance/Bullet/cast/비교 arm/C/D는 미관측이라고 명시한다. B1 성공은 설치본 유한 사례에만 적용된다.
5. `validation/gazebo-minimal-approval-v1/reports/approval_plan.md` §1/3/5는 진입 조건을 넘지 않는 준비 초안이며 아직 world/observer/step GO/dynamic closure가 미완성이다. 문서의 NOT_IMPLEMENTED B1은 역사적 준비 당시 상태이며 최신 B1 결과가 우선한다. 미래 Gazebo한도512MiB 등은 제안이지 승인값이 아니다.

## 필수 게이트와 기술적 잔여 위험의 수용 가능성

|항목|기본 경로에서 필요한 증거/상태|항목별 위험 수용 경로와 한계|
|---|---|---|
|실행 권한/원본 보존/Stage B 제한|실제 대상·명령·commit별 명시 승인, 기존 evidence/marker 보존|기술적 위험 수용과 별개. 이번 준비 승인을 runtime 승인으로 전환 불가; 기존 금지 변경에는 이후 명시 범위 변경 필요|
|고정 ELF/actual mount/GO/한도/cleanup|새 payload의 완전 closure·readelf/FD identity·runtime backend proof·수집·정리 계약|알 수 없는 provider를 PASS 처리하는 식의 생략 불가. 범위/게이트 변경 시 새 준비와 명시 승인 필요|
|B 정상 소유·destroy/notify·allocator|B1 정상 owner-release는 부분 근거, 실제 destruction callback/개별D0/provider/해제 balance는 남음|V4가 허용한 잔여 위험의 항목별 명시 수용 대상. 유한 callback만으로 allocator/개별 destructor 증명 대체 불가|
|B Bullet/group/object/cast|factory/deleter와 detector outlive, provider/identity/해제의 별도 증거|선택할 Gazebo 플러그인과 closure에서 비사용 입증 또는 구체적인 미검증 경계 수용이 필요. world에 접촉이 없다는 가정만으로 면제하지 않음|
|B 설치/baseline/trace OFF 비교|원 프로토콜은 대조 arm 비교 요구; B1은 설치 arm만|설치본 smoke만으로 한정할 때 비교/계측 중립성 주장을 제외하고 해당 생략 위험을 명시 수용할 수 있는지 사용자가 결정해야 함. 결정 전 기존 gate 유지|
|C 예외/부분 생성 해제|정상 B 선행, 입증된 allocation fault window와 callback/해제 count·unwind|정상 종료 사례가 대신하지 못함. 예외 미시험의 범위·ABI/allocator 잔여 위험을 별도 수용하지 않으면 미충족|
|D trace OFF/ON|nonphysics entry/metadata lifetime/quiescent Configure/GetStatus/Flush/capacity/overflow|uninstrumented 설치본만 사용하는 smoke의 비적용 가능성은 범위 판단+사용자 명시 수용 사항. local trace가 섞이면 그대로 남음. 자동 N/A 처리 금지|
|Gazebo 최소물리 결과|실제로 선택된 DART provider, fixed step/time/state, 출구/정리/무결성|준비 또는 B 성공으로 runtime 검증 대체 불가. 별도 실행 승인과 별도 결과가 필요|

이 표의 수용 경로는 V4 문구에 대한 범위별 적용 제안이며 이미 수용됐다는 사실이 아니다. 사용자가 미관측 항목·관련 경로·주장 제외 범위·해당 실행 사례를 명시적으로 결정해야 한다. 이번에는 어느 항목도 수용·면제하지 않는다. 승인된 빈 Skeleton/V2/B1의 제한된 성공을 전 범위 A/B/C/D PASS로 올리지 않는다. Gazebo 준비 중 검토할 잔여 자료와 설치 Core 전체 ABI는 UNKNOWN 유지다.

추가 직접 정적 확인: 설치 `/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-dartsim-plugin.so.7.8.0`의 readelf DT_NEEDED에 libdart-collision-bullet.so.6.13, libLinearMath.so.3.24, libdart-collision-ode.so.6.13 등이 있다. 이는 target 로딩 없이 확인했으며 실제 선택 detector를 증명하지 않는다. 향후 Gazebo closure에는 Core16만으로 부족하다.

## 선택: B2의 작은 하위 사례, Subject 소멸 통지2개

B의 destroy/notify 관측 중 가장 작은 **BodyNode·ShapeNode Subject/Observer callback** 사례를 준비한다. 기존 B1과 동일한 설치 Core16 closure·같은 정상 구조만 사용해 새 Bullet/Fault/trace 경계를 추가하지 않는다. normal owner-release 관측에 callback 증거를 하나씩 추가할 수 있고, collector가 stack 고정2slot/scalar여서 global allocator interposition보다 검토 범위가 작다. Bullet group/object까지 한꺼번에 확장하면 추가 ELF/factory/cast/소유권 경계가 늘어난다. C는 해당 정상경로가 먼저이고 D도 별도 entry 검토가 필요해 이번 최소 사례로 선택하지 않았다.

신호: DART Observer::receiveDestructionNotification 경유 `Recorder::handleDestructionNotification(subject)` callback. live 등록한 BodyNode/ShapeNode의 Subject base 주소 두 개와 callback 인자를 비교해 ID1(shape node),ID2(body node)를 기록한다. raw 저장값을 reset 후 역참조하지 않는다. callback은 noexcept이며 logging/할당/등록변경을 하지 않는다. Observer의 등록·해제 std::set 동작은 라이브러리에서 수행하므로 전체 관측기가 allocation-free라고 주장하지 않는다.

통과 신호: 등록2개·callback0, 외부 Shape 참조 해제 뒤에도0, Skeleton owner.reset 구간 안에서 node1회/body1회, 모르는 대상/중복/overflow 없음, callback ID 순서1→2, 구간 종료 후 Observer 등록0. expected 순서는 보존된 source의 BodyNode node-map 해제 후 Subject base teardown에서 도출한 **검증할 가설**이며 실제 설치본 관측 사실이 아니다. 범위 불일치/역순은 실패 증거이지 자동 기준 완화 사유가 아니다.

**NOT_OBSERVED 유지:** protected Subject notification은 destructor 외에서도 보낼 수 있으므로 이 신호는 각 derived destructor 진입/D0 호출/return·최종 free를 직접 입증하지 않는다. 통지 순서는 개별 소멸자 호출 순서가 아니다. Skeleton/Joint destructor와 allocator/deallocator 주소·provider·balance/누수도 미측정이다. weak 만료와 exit0을 callback 또는 이 미관측 항목의 대체 증거로 사용하지 않는다. 이 사례가 성공해도 B 전체를 완료하지 않으며 직접 destructor/allocator 관측은 별도 설계·증거 또는 위험 수용 항목으로 남는다.

현재 상태: 준비·compile/link·비실행 검사만 완료. 실제 callback0, 실제 target loading0, service0, marker소비0. 다음은 새 승인안의 정확한 명령에 대한 별도1회 승인 여부 검토이며, 이번 종료 뒤 자동 실행하지 않는다.
