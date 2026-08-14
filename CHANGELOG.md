# 변경 이력

이 프로젝트는 Git 태그에는 Semantic Versioning prerelease 표기를, Python
패키지에는 동등한 PEP 440 표기를 사용합니다.

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
