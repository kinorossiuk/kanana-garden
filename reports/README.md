# 실행 증빙 리포트

이 디렉터리에는 Kanana Garden 명령이 직접 만든 다음 JSON만 저장한다.

- `check --output`: recipe를 실제 Kanana 모델로 실행한 결과
- `server-baseline --output`: 5600G의 반복 품질·성능과 runtime identity
- `parity --output`: 기준 runtime과 온디바이스 후보의 비교 결과

리포트를 커밋하기 전에 다음을 확인한다.

- `kanana-garden report-validate`가 통과한다.
- 내장된 공개 예제만 사용했으며 개인정보·업무 비밀이 없다.
- 모든 `requested_model`과 `response_model`이 일치한다.
- 완료 증빙의 `passed`가 `true`다.
- recipe 또는 eval suite SHA-256이 현재 asset과 일치한다.
- 서버 model revision, dtype과 실행 명령을 PR에 기록했다.
- 차량 제어 sample은 strict action 계약 검증까지 통과한다.

수동 작성 리포트나 mock 서버 결과는 커밋하지 않는다. `report-validate`는
내부 정합성을 재계산하지만 전자서명이나 원격 증명은 아니며 실제 실행 출처를
보증하지 않는다.

현재는 검증된 실모델 리포트가 없다.

`reports/uis7862s/`의 ADB 진단 캡처는 로컬 디버깅 자료이며 Git에서 제외한다.
원본 logcat, 화면, 선택적 bugreport에는 위치·계정·차량 정보가 포함될 수 있다.
GitHub 이슈에는 검토·비식별화한 최소 구간과 manifest 해시만 첨부한다.
