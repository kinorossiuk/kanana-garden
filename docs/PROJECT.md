# Kanana Garden 프로젝트 브리프

## 목표

UIS7862S Android 헤드유닛에서 “볼륨 올려줘”, “강남역으로 길 안내해”,
“다음 음악 틀어줘” 같은 한국어 음성 명령으로 화면과 앱을 제어한다. 최종
제품은 네트워크 없이 동작하는 온디바이스 명령 해석기와 Android 제어
브리지다.

## 핵심 원칙

1. LLM은 사용자 의도를 허용된 action JSON으로만 변환한다.
2. Android 제어는 action별 결정론적 API/Intent adapter가 실행한다.
3. LLM이 shell, package, URL, 화면 좌표를 직접 만들거나 실행하지 않는다.
4. 명령 해석 버그와 장비·권한·펌웨어 버그를 별도로 재현한다.
5. 5600G 기준 출력이 안정화된 뒤 같은 계약을 UIS7862S 내부 추론으로 옮긴다.
6. 차량이 움직이는 동안 개발·파괴적 OTA 시험을 하지 않는다.

## 단계별 산출물

### 0단계: UIS7862S 제어 가능성

- 대상 장비의 Android, ABI, RAM, build fingerprint, 설치 앱을 고정한다.
- LLM이 없는 작은 제어 브리지로 볼륨, 길안내, 미디어 세션을 시험한다.
- 일반 APK로 가능한 동작과 공급사 서명/특권이 필요한 동작을 구분한다.
- OTA별 성공·실패와 ADB 진단 번들을 남긴다.

통과 조건: 목표 OTA에서 고정 action으로 볼륨·길안내·음악의 최소 한 동작씩
재현된다.

### 1단계: 5600G 명령 해석 안정화

- 공식 Kanana Transformers 모델과 revision, dtype을 고정한다.
- `vehicle-control-ko`가 한국어 표현을 strict action JSON으로 변환한다.
- 알 수 없는 기능, 임의 package/shell/좌표 필드를 거부한다.
- 두 개의 서로 다른 서버 session에서 전체 recipe를 각각 3회 반복한다.
- `server-compare`로 재시작 후 품질·설정 동일성을 확인한다.

통과 조건: 두 서버 session의 모든 차량 action 예제가 계약 검증까지 통과하고
미해결 crash/OOM이 없다.

### 2단계: 하이브리드 통합

- 음성 또는 텍스트를 5600G 명령 해석기에 전달한다.
- 검증된 action JSON만 UIS7862S 제어 브리지로 전달한다.
- confidence가 낮거나 확인이 필요한 동작은 사용자 확인 후 실행한다.
- 명령부터 실제 동작까지 end-to-end 지연과 실패 원인을 기록한다.

통과 조건: 볼륨·길안내·음악 대표 명령이 목표 OTA에서 반복 재현된다.

### 3단계: 완전 온디바이스

- UIS7862S에서 가능한 추론 runtime과 양자화를 선택한다.
- 5600G 기준과 한국어 패리티를 비교한다.
- APK 또는 APK+서명된 모델 팩으로 설치를 단순화한다.
- cold start, 메모리 peak, 장시간 반복, 재부팅, OTA 회귀를 측정한다.

통과 조건: 네트워크 없이 대표 명령이 목표 지연·메모리 한도 안에서 동작하고
재부팅·OTA 후에도 회귀하지 않는다. 수치 한도는 첫 실측 후 고정한다.

## 초기 action 범위

| 범주 | action |
|---|---|
| 볼륨 | `volume_up`, `volume_down`, `volume_set`, `volume_mute`, `volume_unmute` |
| 길안내 | `navigation_start`, `navigation_stop` |
| 음악 | `media_play`, `media_pause`, `media_next`, `media_previous` |
| 앱 | `app_open`의 `navigation`, `music`, `settings` alias |
| 거부 | `unsupported` |

창문, 공조, 주행 기능, 임의 앱 조작은 초기 범위가 아니다. CAN/MCU 제어는
안전·권한·차종별 계약이 별도로 확정되기 전에는 추가하지 않는다.

## 사업 검증

범용 recipe 저장소보다 헤드유닛 공급사·펌웨어 업체를 위한 포팅, 호환성 시험,
회귀 리포트와 장애 대응이 더 명확한 유료 가치다. 다만 제3자용 Kanana
온디바이스 제품은 모델 상업 라이선스 협의가 필요할 수 있으므로, 유료 파일럿과
Kakao 라이선스 가능성을 제품 확대 전에 확인한다.

저장소 코드는 source-available로 공개하되 사용·복제·수정·배포는 사전 서면
허가가 필요하다. 별도 기여자 권리 조건을 마련하기 전에는 외부 코드 pull
request를 받지 않는다.

## 지금 의도적으로 하지 않는 것

- 다른 SBC 지원
- LLM이 직접 수행하는 화면 좌표 자동화나 shell 실행
- 차량 주행·안전 기능 제어
- 자동 OTA flash
- 모델 가중치의 Git 재배포
- 실제 장비 증빙 없는 성능 주장
