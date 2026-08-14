# 변경 이력

이 프로젝트는 Git 태그에는 Semantic Versioning prerelease 표기를, Python
패키지에는 동등한 PEP 440 표기를 사용합니다.

## v0.0.1-alpha.2 — 2026-08-14

UIS7862S 0단계 장비 호환성 시험용 알파 릴리스입니다. Python 패키지 버전은
`0.0.1a2`입니다.

### 포함

- 설치 가능한 UIS7862S Android 제어 브리지 debug APK
- `AudioManager` 기반 미디어 볼륨 올림·내림·설정·음소거
- 인코딩된 `geo:` Intent 기반 목적지 전달
- 활성 `MediaSession`의 재생·일시정지·다음·이전 제어
- 고정 내비게이션·음악·설정 alias만 허용하는 앱 실행
- Python 명령 해석기와 같은 제한형 action JSON 검증
- ADB/외부 Intent 입력의 자동 실행 방지 및 확인 UI
- CI의 Android 빌드·서명 검증·SHA-256 생성
- 태그 생성 시 APK와 SHA-256을 첨부하는 GitHub prerelease 자동화

### 알려진 제한

- APK는 CI의 일회성 debug signing을 사용하므로 다음 빌드에서 덮어쓰기 설치가
  안 될 수 있습니다. 벤치 테스트용이며 주행 중 사용하면 안 됩니다.
- UIS7862S 실장비와 판매사·OTA별 결과는 아직 수집하지 않았습니다.
- 길안내 종료와 검색어 기반 음악 재생은 앱별 어댑터가 필요합니다.
- 미디어 제어에는 사용자가 알림 접근을 직접 허용해야 합니다.
- LLM, 음성 인식, wake word와 TTS는 APK에 포함하지 않습니다.
- UIS7862S 온디바이스 추론 runtime과 양자화 형식은 아직 확정하지 않았습니다.

## v0.0.1-alpha.1 — 2026-08-14

첫 구조 검증용 알파 릴리스입니다. Python 패키지 버전은 `0.0.1a1`입니다.

### 포함

- 한국어 차량 명령을 제한된 action JSON으로 변환하는 `vehicle-command`
- 볼륨·길안내·음악·고정 앱 alias와 `unsupported` action 계약
- 임의 package, shell, URL, 터치 좌표가 포함된 모델 출력 거부
- Ryzen 5 5600G 공식 Transformers 서버 설치·실행 스크립트
- 서버 session UUID, model revision, dtype을 기록하는 반복 baseline
- 서로 다른 서버 session의 재시작 안정성 비교
- 32개 한국어 합성 case의 runtime parity suite
- UIS7862S ADB 사전 점검, 장애 캡처와 OTA 해시 검증
- source-available 사용 제한 라이선스

### 알려진 제한

- 실제 Kanana 모델 품질·성능 baseline은 아직 수집하지 않았습니다.
- UIS7862S Android 제어 브리지 APK는 아직 포함하지 않습니다.
- UIS7862S 온디바이스 추론 runtime과 양자화 형식은 아직 확정하지 않았습니다.
- 음성 인식, wake word와 TTS는 아직 구현하지 않았습니다.
- OTA 자동 flash는 안전상 제공하지 않습니다.
