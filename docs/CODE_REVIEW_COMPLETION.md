# 작업지시서 완료 리뷰

검토일: 2026-10-27 KST. 대상: `main`, HEAD `dcf4896`과 검토 시작 시점의
미커밋·미추적 구현 및 테스트. 기준: 루트 `CODE_REVIEW_TASK.md`.

## 판정

**작업 완료 승인 보류.** 로컬 검증은 통과했지만 차량 action 입력 검증과
Android 확인 절차에 미해결 결함 3건이 있다. 기존 결함도 지시서의 전체 리뷰
범위에 포함했다. 실모델·실기기 결과와 운영 서버 배포 상태는 확인되지 않았다.

이번 작업은 완료 리뷰다. 구현 코드는 수정하지 않았으며, 배포·서버 설정 변경·
기기 설치·릴리스 발행을 수행하지 않았다. 아래 결함의 수정 여부는 모두 미수정이다.

## 미해결 결함

### R1 — P2: 잘못된 action 필드가 평가 전체를 예외로 중단시킴

- 영향: 모델이 잘못된 필드 타입을 반환하면 정상적인 검증 거부나 실패 case
  기록 대신 `vehicle-command`, `check`, 기준선 및 보고서 재검산이 중단될 수 있다.
- 근거: `src/kanana_garden/vehicle_control.py:90-95`에서 타입 검사 없이
  `action not in ACTIONS`, `confidence not in CONFIDENCE_LEVELS`를 실행한다.
  `app_open`의 `slots.app`도 같은 문제가 있다(`:125`).
- 재현: 정상 action 객체의 `action` 또는 `confidence`를 `{}`나 `[]`로
  바꾸어 `parse_vehicle_action(json.dumps(value))`를 호출하면 `RecipeError`
  대신 `TypeError: unhashable type`이 발생한다. 모델 응답을 mock으로 주입한
  공개 CLI의 `vehicle-command`와 `check vehicle-control-ko`에서도 미처리
  `TypeError`를 확인했다. 실제 모델 오류 응답을 관찰한 결과는 아니다.
- 수정 여부: 미수정. 문자열 타입을 먼저 확인하고 계약 오류로 변환해야 한다.
  파서뿐 아니라 CLI·기준선·보고서 재검산의 실패 처리를 회귀 검사해야 한다.

### R2 — P2: Android의 strict JSON 검증이 비표준 문법을 허용함

- 영향: Python이 거부하는 입력을 브리지에서 허용하므로 동일 action 계약의
  거부 기준이 일치하지 않는다.
- 근거: `VehicleAction.java:70-78,154-175`의 사전 검사는 일부 문자만
  차단하고 나머지 문법 검증을 기본 `JSONTokener`에 맡긴다.
- 재현: 현재 `VehicleAction.java`를 단위 테스트와 같은
  `org.json:json:20240303`으로 컴파일했다. 정상 `volume_up` 객체에서
  `"action"`을 `action`으로, `"volume_up"`을 `volume_up`으로 바꾼 두 입력과
  마지막 필드 뒤에 쉼표를 추가한 입력 모두 파싱에 성공했다. 동일 문자열은
  Python의 JSON 파서에서 거부된다. Android 실기기 실행은 하지 않았다.
- 수정 여부: 미수정. JSON 문법 자체를 엄격하게 검사하고, 따옴표 없는 키·값과
  후행 쉼표를 거부하는 양쪽 파서의 회귀 테스트가 필요하다. 현재 Java 테스트
  6개에는 이 조건들이 없다.

### R3 — P2: 낮은 confidence의 추가 확인을 모델 플래그에 의존함

- 영향: `confidence="low"`인데 `requires_confirmation=false`인 응답도
  실행 버튼 이후 추가 확인 대화상자 없이 실행 경로로 넘어간다. 지시서의
  낮은 confidence 확인 절차가 결정론적으로 보장되지 않는다.
- 근거: `VehicleAction.parse()`는 위 조합을 허용한다. 실제 분기인
  `MainActivity.java:310-318`은 `requiresConfirmation`만 확인하며,
  `ActionExecutor`도 confidence를 검사하지 않는다.
- 재현: 정상 `volume_up` 객체의 confidence만 `low`로 바꾸면 Java 파서 결과는
  `confidence=low`, `confirmation=false`다. 이후 실행 경로는 코드로 확인했다.
  앱은 모든 입력에 대해 사용자의 실행 버튼 클릭을 요구하며 자동 실행하지
  않는다. 이번 지적은 실행 버튼 이후의 추가 확인 누락에 해당한다.
- 수정 여부: 미수정. 브리지에서 낮은 confidence를 독립적으로 확인 대상으로
  처리하고, 확인·취소 분기를 동작 테스트로 검증해야 한다.

## 반영 확인 항목과 완료 기록의 부족

| 지시서 항목 | 현재 확인 결과 |
|---|---|
| 차량 action·slot 정확성 | `expected_action`, `expected_slots` 비교가 CLI·기준선·리포트 재검산에 반영됨. 잘못된 볼륨 slot의 회귀 테스트 통과 |
| release APK의 보고서 수집 | `run-as` 실패 안내에 debuggable 제한과 공유·LTE 대안 반영. Android README와 LTE 문서도 보완됨 |
| Android 호환성·생명주기 | API 호환성 및 버전별 스타일, 비동기 UI 콜백 가드 반영. 빌드·lint 통과. 실기기 동작 미확인 |
| 진단·FYT 실패 처리 | Bearer 마스킹 보완과 FYT 연결·명령 실패 처리 변경 확인. 실제 펌웨어 통신·볼륨 변화 미검증 |
| 성능 보고서 | 지연·토큰 처리량 재계산 및 변조 회귀 테스트 통과 |
| OTA·서명 | manifest 파일명 충돌 및 manifest 저장 실패 정리 보완. Python 서명 검증 테스트와 Android 빌드 통과. 정식 서명·설치 흐름 미검증 |
| 운영 스크립트 | 예제 인증 값 거부, 환경 파일 권한, Jenkins 설정 노드 보존 및 롤백 코드 확인. 관련 로컬 테스트 통과. 운영 반영·장애 복구 미검증 |

README의 진행 현황도 현재 작업 트리와 맞춰 갱신해야 한다. `README.md:28`은
테스트 105개를, `:32`는 빌드·lint 결과 미확인을 기록하고 있다. `:54-55`의
slot 검증 한계 설명은 이번에 추가된 정확 일치 검사와 구분이 필요하다.
전체 리뷰·수정 완료 표시는 아래 결함을 수정하고 재검증한 뒤 갱신해야 한다.

## 실행한 검증

| 검증 | 결과와 한계 |
|---|---|
| `make test` | Python 테스트 122개 통과. Android 소스에 대한 정적 검사와 mock 서버 시험 포함 |
| `make validate` | recipe 4개, 평가 suite 32 case 유효. 저장된 모델 JSON 리포트가 없어 실행 증빙 재검산은 0건 |
| `catalog --check docs/CATALOG.md` | 통과. 실모델 증빙이 생겼다는 의미는 아님 |
| `git diff --check` | 통과 |
| `bash -n` | 운영 shell 스크립트 7개 통과. 운영 실행·롤백 시험을 대신하지 않음 |
| Android debug | `testDebugUnitTest`, `assembleDebug`, `lintDebug`를 `--rerun-tasks`로 실행해 통과. Java 테스트 7개, 실패·오류 0개 |
| Android release | `assembleRelease`, `lintRelease` 통과. `app-release-unsigned.apk` 생성. 정식 릴리스 서명은 사용하지 않음 |
| Android lint | debug·release 각각 Error 0개, Warning 6개. SDK 버전, 데이터 추출 규칙, 아이콘, 문자열 관련 경고 |

Android 검증에는 Gradle 9.4.1, Android SDK 36 및 로컬 의존성 캐시를 사용했다.
캐시·Android 사용자 디렉터리를 `/tmp/kanana-completion-review`로 분리했다.
최초 캐시 사용 빌드 뒤 강제 재실행에서 기본 debug keystore 디렉터리의 쓰기
제한을 만났고, 쓰기 가능한 `ANDROID_USER_HOME`을 지정한 재실행이 통과했다.
기존 사용자 서명키는 변경하지 않았다. 현재 구성에는 `testReleaseUnitTest`
task가 없어 release 전용 Java 단위 테스트는 실행하지 못했다.

## 실환경 확인과 미검증 사유

- 5600G로 문서화된 `192.168.0.50:8000`의 `/health`는 HTTP 200과 `OK` 텍스트를
  반환했지만, `/v1/models`는 HTTP 404였다. Kanana 모델 서버의 모델·revision·
  session 식별을 확인하지 못했으며 실제 추론·기준선·재시작·패리티 시험을 하지 않았다.
- 보고서 호스트로 문서화된 `192.168.0.40:8762/health`는 4초 제한 내 응답하지
  않았다. 수신기는 loopback 전용이므로 이 결과만으로 서비스 중단을 판단할 수 없다.
  로컬 `127.0.0.1:8762` 연결도 실패했고, sandbox의 사용자 systemd bus에는
  접근하지 못했다. SSH 운영 상태 확인 및 외부 LTE/HTTPS 시험은 수행하지 않았다.
- `adb devices -l` 결과 연결된 장치가 없었다. 정차·기기 준비도 확인되지 않아
  차량 제어, 보고서 공유·제출, FYT Binder, 실제 볼륨·내비·미디어 및 OTA 설치는
  시험하지 않았다.
- CI workflow는 로컬에서 검토했으며 GitHub Actions 실행 결과를 조회하지 않았다.

## 완료 재검토 조건

1. R1~R3 수정 및 해당 실패 조건에 대한 회귀 테스트 통과.
2. Python 전체 검사와 Android debug 검사 및 release 빌드·lint 재실행.
3. README와 완료 보고를 실제 결과로 갱신하고, 실모델·실기기·정식 서명·운영
   검증의 미실행 항목과 사유를 유지.
