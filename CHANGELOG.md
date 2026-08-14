# 변경 이력

이 프로젝트는 Git 태그에는 Semantic Versioning prerelease 표기를, Python
패키지에는 동등한 PEP 440 표기를 사용합니다.

## v0.2.1 — 2026-08-14

UIS7862S에서 USB/ADB 없이 앱 crash를 회수하기 위한 진단 보강 릴리스입니다.
Python 패키지 버전은 `0.2.1`입니다.

### 포함

- `Application` 생성 시 전역 미처리 예외 기록기 설치
- UI 생성과 백그라운드 스레드 crash를 앱 비공개 파일에 최대 12KB로 보존
- 앱에서 처리한 API·OTA·LTE 내부 오류도 stack trace와 함께 최대 16KB로 누적
- 다음 실행 보고서의 `이전 앱 비정상 종료 진단`에 시각·스레드·stack trace 첨부
- token·authorization·password 형태의 인증 문자열을 저장 전에 마스킹
- 기록 실패와 관계없이 Android의 기존 crash 처리기로 원래 예외 전달
- PASS/FAIL·메모·API 이력 초기화 시 보존된 crash 진단도 함께 삭제
- board·hardware·ABI·보안 패치·build fingerprint 추가(serial은 미수집)

### 알려진 제한

- release APK는 `debuggable`이 아니며 system 전체 logcat을 수집하지 않습니다.
- 프로세스가 재실행되지 않으면 저장된 crash 보고서를 LTE로 제출할 수 없습니다.
- 네이티브 프로세스 강제 종료, 전원 차단과 OS 수준 ANR은 Java 미처리 예외 기록에
  포함되지 않을 수 있습니다.

## v0.2.0 — 2026-08-14

UIS7862S에서 별도 설명서나 USB 없이 0단계 시험과 결과 제출을 진행하기 위한
첫 고정 서명 OTA 기준 릴리스입니다. Python 패키지 버전은 `0.2.0`입니다.

### 포함

- APK 화면에 6단계 시험 순서와 기기·Android·펌웨어 정보 표시
- 볼륨·길안내·음악 항목별 상호 배타적 PASS/FAIL 체크박스
- 테스터 메모와 API 실행 성공·실패 이력 자동 보존
- 보고서 미리보기, 클립보드 복사와 사용자 주도 Android 공유
- LTE에서 사용자 설정 HTTPS 수신기로 보고서를 직접 제출
- HTTPS 강제, redirect 차단, 64 KiB 제한과 32자 이상 제출 토큰 검증
- loopback 전용 분석 호스트 보고서 수신기와 SHA-256 메타데이터 저장
- DuckDNS·nginx HTTPS와 Cloudflare Tunnel 대체 배포 절차
- USB/ADB 보고서 수집은 장애 시 보조 경로로 유지
- GitHub Release 메타데이터 기반 사용자 주도 APK OTA 업데이트
- APK SHA-256·application ID·상향 versionCode·동일 서명자 검증
- GitHub Actions secret의 전용 키로 release APK 서명

### 알려진 제한

- DuckDNS 직접 연결에는 공유기 포트 forwarding, Tunnel 연결에는 관리 도메인이
  필요하며 외부 HTTPS 경로 설정은 사용자가 완료해야 합니다.
- v0.2.0 APK에는 수신 주소나 제출 토큰이 포함되지 않으며 최초 1회 입력해야 합니다.
- 제출 토큰은 Android 앱 sandbox의 비공개 preferences에 저장되며 장비를 양도하거나
  분실하면 서버에서 즉시 교체해야 합니다.
- 실제 UIS7862S LTE 망과 판매사 OTA에서의 제출 결과는 아직 수집하지 않았습니다.
- alpha.2와 이전 CI debug APK는 서명자가 다르므로 삭제 후 v0.2.0을 한 번 새로
  설치해야 합니다. 이후 OTA 릴리스는 같은 전용 서명키를 사용해야 합니다.
- UIS7862S 펌웨어가 일반 APK의 `알 수 없는 앱 설치` 화면을 제공하지 않으면
  OTA 다운로드는 검증되더라도 설치 화면을 열 수 없습니다.

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
