# 실행 증빙 리포트

이 디렉터리에는 Kanana Garden 명령이 직접 만든 다음 JSON만 저장한다.

- `device-doctor --json`: Raspberry Pi 5 8GB 장비 사전 점검
- `check --output`: 레시피를 실제 카나나 모델로 실행한 결과
- `pi5-baseline --output`: 내장 레시피 반복 실행과 Pi 열·성능 기준선
- `parity --output`: 기준 런타임과 온디바이스 후보의 비교 결과

리포트를 커밋하기 전에 확인할 것:

- `kanana-garden report-validate`가 통과한다.
- 내장된 공개 예제만 사용했으며 개인정보·업무 비밀이 없다.
- 모델·패리티 리포트는 `requested_model`과 모든 `response_model`이 일치한다.
- 완료 증빙으로 제출하는 모델·패리티 리포트의 `passed`가 `true`다.
- 레시피 또는 평가 스위트 SHA-256이 현재 asset과 일치한다.
- 장비·런타임·양자화 방식을 PR 설명에 기록했다.

실제 모델을 실행하지 않은 수동 작성 리포트나 mock 서버 결과는 커밋하지
않는다. `report-validate`는 내용의 내부 정합성을 재계산하지만 전자서명이나
원격 증명이 아니며, 실행 출처 자체를 보증하지는 않는다.

Pi 리포트의 `device_id_sha256`은 원본 machine-id가 아닌 Garden 전용
SHA-256이지만 여러 공개 리포트에서 같은 장치를 연결할 수 있는 가명
식별자다. 이 연결을 원하지 않으면 공개용 비밀값을 정해 모든 실행에
`KANANA_DEVICE_ID`로 제공한다. 비교하는 재부팅 전후 한 쌍에는 같은 값을
쓰되, 별도 제출에는 새 값을 사용하고 원문은 커밋하지 않는다.

현재는 검증된 실모델 리포트가 없다.

`reports/uis7862s/`의 ADB 진단 캡처는 로컬 디버깅 자료이며 Git에서 제외한다.
원본 logcat, 화면, 선택적 bugreport에는 위치·계정·차량 정보가 포함될 수 있다.
Gitea 이슈에는 원본 전체 대신 검토·비식별화한 최소 구간과 manifest 해시를
첨부한다.
