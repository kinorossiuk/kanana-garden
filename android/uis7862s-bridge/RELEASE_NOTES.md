# Kanana Garden v0.0.1-alpha.2

UIS7862S 0단계 장비 호환성 시험을 위한 첫 Android 제어 브리지 APK입니다.

포함 기능:

- 미디어 볼륨 올림·내림·설정·음소거
- `geo:` Intent를 통한 목적지 전달
- 활성 MediaSession 재생·일시정지·다음·이전
- 고정된 내비게이션·음악·설정 앱 alias
- Python 명령 해석기와 동일한 제한형 action JSON 검증
- 외부 Intent/ADB payload 자동 실행 방지 및 확인 UI

알려진 제한:

- CI의 일회성 debug signing을 사용하므로 다음 빌드에서 덮어쓰기 설치가 안 될 수
  있습니다. 벤치 테스트 APK이며 주행 중 사용하면 안 됩니다.
- 길안내 종료와 검색어 기반 음악 재생은 앱별 어댑터가 없어 지원하지 않습니다.
- 미디어 제어에는 사용자가 Android 알림 접근을 직접 허용해야 합니다.
- UIS7862S 실장비·OTA별 호환성은 이번 APK로 처음 수집합니다.
- LLM과 음성 인식은 APK에 포함하지 않습니다.

저장소 코드는 source-available이며 오픈소스가 아닙니다. 사용 조건은 저장소의
LICENSE가 우선합니다.
