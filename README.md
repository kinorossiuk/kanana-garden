# Kanana Garden

**Powered by Kanana**

Kanana Garden은 카나나 LLM으로 만든 한국어 AI 활용법을 작은 JSON
`recipe`로 공유하고, 같은 명령으로 검증·실행할 수 있게 하는 오픈소스
스타터입니다. 첫 목표는 “모델을 실행했다”에서 끝나지 않고, 다른 사람이
재사용할 수 있는 카나나 활용 사례를 꾸준히 쌓는 것입니다.

현재 기본 모델은 2026년 7월 공개된
[`kakaocorp/kanana-2-1.3b-instruct`](https://huggingface.co/kakaocorp/kanana-2-1.3b-instruct)입니다.
1.3B 모델은 온디바이스 배포를 염두에 둔 경량 instruct 모델이며 32K 문맥을
지원합니다. Garden은 모델 가중치를 포함하지 않고, 로컬에서 실행 중인
OpenAI 호환 API에 연결합니다.

> **현재 상태:** 레시피 실행·검증 CLI와 Raspberry Pi 배포·패리티 경로는
> 준비되어 있지만, 실제 Raspberry Pi 5에 모델은 아직 연결하지 않았습니다.
> Pi의 속도·메모리·온도 수치는 첫 실측 전까지 미확정입니다.

## 5분 시작

요구 사항은 Python 3.10 이상과 카나나를 서빙할 수 있는 환경입니다. CLI
자체에는 외부 Python 의존성이 없습니다.

```bash
python3 -m pip install -e .

vllm serve kakaocorp/kanana-2-1.3b-instruct \
  --max-model-len 32768 \
  --trust-remote-code \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
```

다른 터미널에서 서버와 레시피를 확인하고 실행합니다.

```bash
kanana-garden doctor
kanana-garden list
kanana-garden show meeting-action-items-ko
kanana-garden run meeting-action-items-ko \
  --input "민수는 금요일까지 소개 페이지 초안을 만들고, 지연은 다음 주 고객 인터뷰를 잡는다."
```

설치 없이도 저장소 루트에서 같은 기능을 사용할 수 있습니다.

```bash
PYTHONPATH=src python3 -m kanana_garden list
```

기본 서버 주소는 `http://localhost:8000/v1`입니다. 다른 주소나 인증 토큰은
환경 변수로 지정할 수 있습니다.

```bash
export KANANA_BASE_URL=http://localhost:8000/v1
export KANANA_API_KEY=your-token
```

## 할 수 있는 일

```text
list                         내장 레시피 목록
show <slug|file>             레시피 상세 보기
catalog                      레시피와 실행 증빙 카탈로그 생성
validate [file ...]          내장 또는 외부 레시피 검사
suite-validate <slug|file>   패리티 평가 스위트 검사
report-validate [report ...] 저장된 장비·모델·패리티 증빙 재검산
render <slug|file> --input   API 호출 없이 최종 프롬프트 확인
run <slug|file> --input      카나나 서버에서 레시피 실행
check <slug|file>             대표 예제를 실제 모델로 회귀 검사
parity <suite>               공식·온디바이스 런타임 비교
doctor                       서버 연결과 모델 노출 여부 확인
device-doctor                Raspberry Pi 5 8GB 준비 상태 확인
pi5-baseline                 Pi 5 품질·성능·온도 기준선 수집
pi5-compare                  재부팅 전후 Pi 5 기준선 비교
uis7862s-doctor              ADB로 UIS7862S 테스트 장비 점검
uis7862s-capture             재현 로그·상태·화면을 분석 번들로 수집
ota-download                 해시가 고정된 OTA를 로컬 보관소에 다운로드
ota-verify                   보관된 OTA 파일을 다시 검증
serve-local                  공식 모델을 로컬 API로 서빙
new <slug> --output <file>   새 레시피 골격 생성
```

입력이 길거나 셸 기록에 남으면 안 되는 경우 파일 또는 표준 입력을 씁니다.

```bash
kanana-garden run plain-korean-ko --input-file minutes.txt
cat minutes.txt | kanana-garden run plain-korean-ko --input-file -
```

## 생태계에 기여하기

새 활용 사례는 코드 대신 JSON 하나로 시작할 수 있습니다.

```bash
kanana-garden new my-recipe --output my-recipe.json
kanana-garden validate my-recipe.json
kanana-garden run my-recipe.json --input "대표 입력"
kanana-garden check my-recipe.json
```

검증 리포트에는 레시피 해시, 노출·응답 모델 ID, 응답, 지연 시간과 토큰
처리량이 기록됩니다.

```bash
kanana-garden check meeting-action-items-ko \
  --output reports/meeting-action-items-ko.json
kanana-garden report-validate reports/meeting-action-items-ko.json
```

인자를 생략한 `kanana-garden report-validate`는 `reports/*.json`을 모두
검사합니다. 외부 레시피나 평가 스위트의 리포트는
`--asset path/to/asset.json`을 함께 지정합니다.

레시피 규격, 품질 기준, PR 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)에
정리되어 있습니다. 프로젝트가 풀려는 문제와 90일 실행 계획은
[docs/PROJECT.md](docs/PROJECT.md)를 참고하세요.

현재 recipe별 검증 수준은 자동 생성된
[레시피 카탈로그](docs/CATALOG.md)에서 확인할 수 있습니다. 실제 리포트가
없는 지금은 세 recipe 모두 `스키마만 검증`으로 표시됩니다.

## Raspberry Pi 5 8GB

온디바이스 첫 목표 장비는 Raspberry Pi 5 8GB입니다. 공식 Transformers
모델을 정확성 기준 경로로 사용하며, 현재 공개된 GGUF는 모델 구조 동등성이
입증되기 전까지 실험용으로 취급합니다. 설치, 냉각·저장공간 요구 사항,
실행과 합격 기준은 [Raspberry Pi 5 배포 가이드](docs/RASPBERRY_PI.md)에
정리되어 있습니다.

내장 `pi5-parity-ko-v1` 스위트는 외부 지식이나 개인정보가 필요 없는 한국어
합성 케이스 32개로 공식 Transformers 런타임과 후보 런타임을 비교합니다.

```bash
kanana-garden suite-validate pi5-parity-ko-v1

kanana-garden parity pi5-parity-ko-v1 \
  --reference-url http://reference-host:8000/v1 \
  --candidate-url http://raspberrypi.local:8000/v1 \
  --output reports/pi5-parity.json
```

실제 Pi에서 모델을 연결한 뒤에는 내장 레시피 3개를 각각 3회 실행하는 기준선을
한 명령으로 수집합니다. 각 응답의 품질, 지연 시간, tok/s와 실행 직후 온도·
스로틀링 상태가 같은 JSON에 기록됩니다.

```bash
kanana-garden pi5-baseline \
  --model-dir /mnt/ssd/kanana-hf \
  --output reports/pi5-baseline-boot-1.json

kanana-garden report-validate reports/pi5-baseline-boot-1.json
```

실행 중 80°C 이상 또는 스로틀링이 감지되면 남은 생성을 중단하고
`complete: false`, `passed: false`인 안전 중단 리포트를 저장합니다.
재부팅 후 두 번째 기준선을 만든 다음에는 같은 장치의 서로 다른 부팅인지
확인하고 결과를 비교할 수 있습니다.

```bash
kanana-garden pi5-compare \
  reports/pi5-baseline-boot-1.json \
  reports/pi5-baseline-boot-2.json
```

## 5600G 서버 + UIS7862S 테스트 랩

운영 역할은 5600G 모델 서버, 현재 작업 폴더의 Codex 로그 분석·디버깅,
Gitea 소스/이슈 관리, UIS7862S OTA 테스트 장비로 분리할 수 있습니다. 준비와
일상적인 재현 루프는 [5600G · Codex · UIS7862S 테스트 랩](docs/LAB_5600G_UIS7862S.md)에
정리되어 있습니다.

```bash
kanana-garden uis7862s-doctor
kanana-garden uis7862s-capture \
  --label issue-12 \
  --package com.example.app \
  --ota-version 2026.08.1
```

캡처는 기본적으로 `reports/uis7862s/` 아래에 저장되고 Git에서 제외됩니다.
OTA도 `var/ota/`에 해시 검증 후 저장하며 자동으로 장비에 적용하지 않습니다.

## 모델 라이선스

이 저장소의 코드는 MIT 라이선스입니다. 카나나 모델과 가중치는 별도의
[Kanana Open License Agreement](https://huggingface.co/kakaocorp/kanana-2-1.3b-instruct/blob/main/LICENSE)를
따릅니다. 특히 카나나 또는 파생 모델에 대한 제3자 API·클라우드·SI·온디바이스
접근을 판매하는 경우 별도 상업 라이선스가 필요할 수 있습니다. 자신의
서비스에서 모델을 사용하기 전에 원문을 확인하세요. 자세한 적용 경계는
[docs/MODEL_LICENSE.md](docs/MODEL_LICENSE.md)에 기록했습니다.

Kanana Garden은 Kakao Corp.의 공식 프로젝트가 아닙니다.
