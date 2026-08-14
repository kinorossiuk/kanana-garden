# Kanana Garden

**Powered by Kanana**

현재 테스트 릴리스: **v0.0.1-alpha.2** (`0.0.1a2`)

Kanana Garden은 한국어 LLM을 반복 시험하고, 같은 모델 설정이 서버 재시작
후에도 같은 품질과 성능을 내는지 증빙한 뒤 온디바이스 배포로 넘기기 위한
테스트·분석 저장소입니다.

현재 기본 모델은 `kakaocorp/kanana-2-1.3b-instruct`이며 모델 가중치는 이
저장소에 포함하지 않습니다.

> **현재 단계:** Ryzen 5 5600G에서 명령 해석 모델을 안정화하는 동시에,
> UIS7862S에서는 LLM 없이 고정 action을 실행할 Android 제어 브리지의
> 호환성을 먼저 확인합니다. 완성 LLM의 설치·양자화·성능 시험만 안정화
> 게이트 통과 후 진행합니다.

이 버전은 UIS7862S 0단계 장비 호환성 시험용 알파입니다. 차량 action 계약,
5600G 테스트 도구와 설치 가능한 Android 제어 브리지 APK를 포함합니다. LLM은
APK에 포함하지 않으며 온디바이스 모델 변환은 안정화 게이트 통과 후 진행합니다.

## 시스템 구성

```text
GitHub Public
  └─ source, tests, issue
          │
          ▼
음성/텍스트 ─▶ Ryzen 5 5600G LLM ─▶ 허용 action JSON ─▶ UIS7862S 제어 브리지
                 ▲                                      └─ 볼륨·길안내·음악
                 │
현재 작업 폴더 + Codex
  └─ 로그 분석·디버깅·버전 관리

안정화 게이트 통과 후에는 LLM 추론 위치만 5600G에서 UIS7862S 내부로 이동
```

다른 SBC 경로는 운영 범위에 포함하지 않습니다.

## 0단계: UIS7862S 제어 가능성 확인

완성 LLM을 올리기 전에 작은 Android 제어 브리지로 다음 동작을 먼저 확인합니다.

- `AudioManager` 기반 미디어 볼륨 올림·내림·설정
- 설치된 내비게이션 앱의 명시적/검증된 Intent 실행
- 활성 `MediaSession`의 재생·정지·다음·이전 곡 제어 가능 여부
- 일반 APK, 접근성 서비스, 공급사 서명 시스템 앱 중 필요한 권한 수준

초기 브리지는 LLM을 포함하지 않습니다. ADB 또는 로컬 테스트 입력으로 고정된
action JSON을 받아 실행하고, 기기·펌웨어별 실패를 먼저 분리합니다.

`v0.0.1-alpha.2` GitHub Release에는 테스트용 debug APK와 SHA-256 파일을 함께
첨부합니다. 설치·권한 설정·시험 순서는
[UIS7862S 0단계 제어 브리지](android/uis7862s-bridge/README.md)를 따릅니다.

## 1단계: 5600G 명령 해석 모델 안정화

5600G 호스트에서 저장소를 clone하고 서버 환경을 준비합니다.

```bash
./ops/5600g/install.sh

# ~/.config/kanana-garden/server.env에서 API 키와 HF_HOME 확인
./ops/5600g/run.sh
```

초기 기준 설정은 CPU `float32`, 물리 코어 6개입니다. 모델 revision은 검토한
커밋으로 고정됩니다. `serve-local`은 시작할 때마다 새 서버 세션 UUID를
발급하고 `/v1/models`에 revision·dtype과 함께 노출합니다.

분석 PC 또는 현재 작업 폴더에서 연결과 대표 출력을 확인합니다.

```bash
python3 -m pip install -e .

kanana-garden doctor
kanana-garden check vehicle-control-ko \
  --output reports/5600g-vehicle-control.json

kanana-garden vehicle-command --input "볼륨 올려줘"
```

첫 서버 세션에서 내장 레시피 전체를 각각 3회 실행합니다.

```bash
kanana-garden server-baseline \
  --output reports/5600g-session-1.json

kanana-garden report-validate reports/5600g-session-1.json
```

서버를 완전히 재시작한 뒤 두 번째 기준선을 만듭니다.

```bash
systemctl --user restart kanana-garden

kanana-garden server-baseline \
  --output reports/5600g-session-2.json

kanana-garden server-compare \
  reports/5600g-session-1.json \
  reports/5600g-session-2.json
```

`server-compare`는 두 리포트가 모두 재검산을 통과하는지, 서버 세션 UUID가
실제로 다른지, 모델·revision·dtype·recipe 해시가 같은지 확인합니다. 단순히
같은 서버 프로세스에서 파일만 두 개 만든 결과는 재시작 안정성으로 인정하지
않습니다.

`vehicle-command`는 모델 출력을 바로 실행하지 않습니다. action, slots,
confidence, requires_confirmation 네 필드만 허용하며, package 이름·shell 명령·
화면 좌표·임의 URL이 섞이면 거부합니다.

### UIS7862S에 LLM을 탑재하는 조건

- 내장 레시피 전체가 한 서버 세션에서 각각 3회 연속 통과
- 서버 재시작 후 두 번째 기준선도 전부 통과
- `server-compare`의 모든 동일성·세션 분리 검사가 통과
- `vehicle-control-ko`의 action JSON 계약 검증이 반복 실행마다 통과
- model revision, dtype, prompt, generation 설정이 고정
- 반복 실행 중 미해결 crash, OOM, 응답 모델 불일치가 없음
- 0단계 제어 브리지가 대상 펌웨어에서 볼륨·길안내·음악 동작을 실행

위 조건을 통과하기 전에는 UIS7862S용 모델 변환을 확정하지 않습니다. 제어
브리지와 장비 호환성 시험은 처음부터 병행합니다.

## 2단계: UIS7862S 완전 온디바이스

UIS7862S는 유일한 최종 온디바이스 대상입니다. 2단계에서 다음 순서로
진행합니다.

1. 0단계에서 확인한 ABI·권한·제어 브리지를 고정
2. 안정화된 5600G 출력을 기준으로 양자화 후보의 한국어 정합성 비교
3. 5600G API 대신 UIS7862S 내부 추론 backend를 같은 action 계약에 연결
4. 설치가 쉬운 APK 또는 APK+모델 팩 형태로 패키징
5. cold start, 메모리, 지연, 장시간 실행과 재부팅·OTA 회귀 시험

현재 저장소의 ADB/OTA 명령은 최종 단계의 장비 식별과 장애 분석을 위한
도구입니다. 모델 설치를 자동으로 수행하지 않습니다.

```bash
kanana-garden uis7862s-doctor

kanana-garden uis7862s-capture \
  --label issue-12 \
  --package com.example.app \
  --ota-version 2026.08.1
```

OTA는 공급사 SHA-256을 확인한 뒤 로컬 `var/ota/`에만 보관합니다. 보드·MCU·
판매사마다 복구 절차가 달라 자동 플래시는 제공하지 않습니다.

자세한 운영 절차는 [5600G·UIS7862S 테스트 랩](docs/LAB_5600G_UIS7862S.md)에
정리되어 있습니다.

## 주요 명령

```text
list                         내장 레시피 목록
show <slug|file>             레시피 상세 보기
catalog                      recipe와 실행 증빙 카탈로그 생성
validate [file ...]          내장 또는 외부 recipe 검사
suite-validate <slug|file>   런타임 평가 스위트 검사
report-validate [report ...] 저장된 모델·기준선·패리티 증빙 재검산
render <slug|file> --input   API 호출 없이 최종 프롬프트 확인
run <slug|file> --input      카나나 서버에서 recipe 실행
check <slug|file>            대표 예제를 실제 모델로 회귀 검사
vehicle-command --input      차량 명령을 검증된 action JSON으로 해석
doctor                       서버 연결과 모델 노출 여부 확인
serve-local                  5600G에서 공식 모델을 로컬 API로 서빙
server-baseline              5600G 반복 품질·성능 기준선 수집
server-compare               서로 다른 서버 세션의 안정성 비교
parity <suite>               기준·후보 런타임의 한국어 출력 비교
uis7862s-doctor              ADB로 최종 장비 식별·준비 상태 확인
uis7862s-capture             재현 로그·상태·화면을 분석 번들로 수집
ota-download                 해시가 고정된 OTA를 로컬에 다운로드
ota-verify                   보관된 OTA 파일을 재검증
new <slug> --output <file>   새 recipe 골격 생성
```

내장 `runtime-stability-ko-v1`은 외부 최신 지식이나 개인정보가 필요 없는
한국어 합성 케이스 32개를 포함합니다. 최종 단계에서 5600G 기준 런타임과
UIS7862S 후보 런타임을 비교할 때 사용합니다.

```bash
kanana-garden suite-validate runtime-stability-ko-v1

kanana-garden parity runtime-stability-ko-v1 \
  --reference-url http://5600g.local:8000/v1 \
  --candidate-url http://uis7862s.local:8080/v1 \
  --output reports/uis7862s-parity.json
```

## 개발과 검증

```bash
make test
make validate
PYTHONPATH=src python3 -m kanana_garden catalog --check docs/CATALOG.md
```

특정 알파 버전을 다시 확인하려면 태그를 checkout합니다.

```bash
git checkout v0.0.1-alpha.2
kanana-garden --version  # 0.0.1a2
```

새 recipe 기여 절차와 리포트 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md), 현재
검증 수준은 [카탈로그](docs/CATALOG.md)를 참고하세요.
릴리스별 변경사항과 알려진 제한은 [CHANGELOG.md](CHANGELOG.md)에 기록합니다.

## 이번 구조 변경

- 기존 SBC 전용 코드·명령·문서·테스트 제거
- 5600G `server-baseline`과 서버 세션 기반 `server-compare` 추가
- 서버 리포트에 session UUID, 모델 revision, dtype 저장
- 평가 스위트를 장비 비종속 `runtime-stability-ko-v1`으로 변경
- UIS7862S 0단계 제어 브리지 APK와 자동 빌드·Release 첨부 추가
- 완성 LLM 탑재는 0단계 장비 검증과 5600G 안정화 이후로 분리

## 라이선스

이 저장소는 **source-available이며 오픈소스가 아닙니다.** 공개 열람 외에
코드를 사용·복제·수정·배포·서비스에 배포하려면 저작권자의 사전 서면 허가가
필요합니다. 상업·비상업 사용 모두 같은 제한을 받습니다. 정확한 조건은 루트
[LICENSE](LICENSE) 원문이 우선하며, 사용 허가는 GitHub issue로 문의할 수
있습니다.

Kanana 모델과 가중치는 별도의 Kanana License Agreement를 따릅니다. 저장소
코드에 대한 허가가 모델 사용 권한을 포함하지 않으며, 제3자 대상 API·SI·
온디바이스 판매에는 Kakao의 별도 상업 라이선스가 추가로 필요할 수 있습니다.

Kanana Garden은 Kakao Corp.의 공식 프로젝트가 아닙니다.
