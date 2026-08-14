# Kanana Garden v0.2.0

UIS7862S에서 설명서를 따로 열거나 USB를 연결하지 않고 0단계 시험과 LTE 결과
제출을 진행하기 위한 Android 제어 브리지 APK입니다.

포함 기능:

- 미디어 볼륨 올림·내림·설정·음소거
- `geo:` Intent를 통한 목적지 전달
- 활성 MediaSession 재생·일시정지·다음·이전
- 고정된 내비게이션·음악·설정 앱 alias
- Python 명령 해석기와 동일한 제한형 action JSON 검증
- 외부 Intent/ADB payload 자동 실행 방지 및 확인 UI
- 앱 내부 6단계 시험 안내와 기기·펌웨어 정보
- 항목별 PASS/FAIL 체크박스, 테스터 메모와 API 실행 이력
- 결과 미리보기·복사·Android 공유
- 사용자 설정 HTTPS 수신기로 LTE 보고서 제출
- loopback 전용 수신기와 `reports/uis7862s/inbox/` SHA-256 증빙 저장
- GitHub Release에서 사용자 버튼으로 확인·다운로드하는 APK OTA
- APK SHA-256·application ID·versionCode·동일 앱 서명자 검증
- 검증 후 Android 설치 화면에서 사용자가 직접 업데이트 승인

알려진 제한:

- 이전 alpha/debug APK와 서명이 다르므로 기존 앱을 한 번 삭제하고 v0.2.0을
  설치해야 합니다. 이후에는 같은 전용 서명키를 사용하는 OTA 업데이트가 가능합니다.
- UIS7862S가 일반 APK의 `알 수 없는 앱 설치` 설정과 package installer를 제공해야
  앱 안에서 업데이트할 수 있습니다.
- 수신 주소와 제출 token은 APK에 포함되지 않으며 사용자가 설정해야 합니다.
- DuckDNS 직접 연결에는 공유기 forwarding과 공개 TLS 인증서가 필요하며,
  불가능하면 Tunnel 구성이 필요합니다.
- 길안내 종료와 검색어 기반 음악 재생은 앱별 어댑터가 없어 지원하지 않습니다.
- 미디어 제어에는 사용자가 Android 알림 접근을 직접 허용해야 합니다.
- UIS7862S 실장비·OTA별 호환성은 이번 APK로 처음 수집합니다.
- LLM과 음성 인식은 APK에 포함하지 않습니다.

저장소 코드는 source-available이며 오픈소스가 아닙니다. 사용 조건은 저장소의
LICENSE가 우선합니다.
