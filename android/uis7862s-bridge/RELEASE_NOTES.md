# Kanana Garden v0.2.2

UIS7862S 실장비에서 확인된 볼륨 무반응을 수정하고 LTE 제출 설정을 단순화한
Android 제어 브리지 APK입니다.

포함 기능:

- FYT `com.syu.ms` 메인 사운드 모듈을 통한 실제 앰프 볼륨 올림·내림·설정·음소거
- FYT 사운드 모듈이 없는 일반 Android 장비의 활성 볼륨 API 폴백
- `geo:` Intent를 통한 목적지 전달
- 활성 MediaSession 재생·일시정지·다음·이전
- 고정된 내비게이션·음악·설정 앱 alias
- Python 명령 해석기와 동일한 제한형 action JSON 검증
- 외부 Intent/ADB payload 자동 실행 방지 및 확인 UI
- 앱 내부 6단계 시험 안내와 board·hardware·ABI·build fingerprint 진단
- 항목별 PASS/FAIL 체크박스, 테스터 메모와 API 실행 이력
- 앱 비공개 저장소에 미처리 예외·stack trace를 최대 12KB로 보존
- 앱이 처리한 API·OTA·LTE 내부 오류의 stack trace를 최대 16KB로 누적
- 다음 실행 보고서에 직전 crash 진단 자동 첨부 및 인증 문자열 마스킹
- 결과 미리보기·복사·Android 공유
- 사용자 설정 HTTPS 수신기로 LTE 보고서 제출
- 저장된 LTE 주소·코드를 기본적으로 숨기고 전송 버튼만 표시
- 앱 업데이트 뒤에도 기존 LTE 연결 설정 유지
- loopback 전용 수신기와 `reports/uis7862s/inbox/` SHA-256 증빙 저장
- GitHub Release에서 사용자 버튼으로 확인·다운로드하는 APK OTA
- APK SHA-256·application ID·versionCode·동일 앱 서명자 검증
- 검증 후 Android 설치 화면에서 사용자가 직접 업데이트 승인

알려진 제한:

- 이전 alpha/debug APK와 서명이 다르므로 기존 앱을 한 번 삭제하고 v0.2.2를
  설치해야 합니다. v0.2.0 이상은 같은 전용 서명키를 사용해 OTA 업데이트가 가능합니다.
- release APK는 `debuggable`이 아니며 전체 system logcat은 수집하지 않습니다.
  앱 프로세스의 미처리 예외만 다음 실행 보고서에 포함합니다.
- UIS7862S가 일반 APK의 `알 수 없는 앱 설치` 설정과 package installer를 제공해야
  앱 안에서 업데이트할 수 있습니다.
- 수신 주소와 제출 token은 APK에 포함되지 않으며 최초 설치 때 한 번 설정해야 합니다.
- v0.2.1에서 저장한 LTE 설정은 v0.2.2 OTA 업데이트 뒤에도 유지됩니다.
- DuckDNS 직접 연결에는 공유기 forwarding과 공개 TLS 인증서가 필요하며,
  불가능하면 Tunnel 구성이 필요합니다.
- 길안내 종료와 검색어 기반 음악 재생은 앱별 어댑터가 없어 지원하지 않습니다.
- 미디어 제어에는 사용자가 Android 알림 접근을 직접 허용해야 합니다.
- FYT 메인 사운드 모듈 명령은 보고된 UIS7862S에서 업데이트 후 재확인이 필요합니다.
- LLM과 음성 인식은 APK에 포함하지 않습니다.

저장소 코드는 source-available이며 오픈소스가 아닙니다. 사용 조건은 저장소의
LICENSE가 우선합니다.
