# Kanana Garden 기여 가이드

> 이 저장소는 source-available이며 오픈소스가 아닙니다. 버그 제보와 기능
> 제안은 GitHub issue로 받을 수 있지만, 코드·recipe pull request는 별도
> 기여자 권리 조건을 마련하기 전까지 받지 않습니다. 사전 합의 없이 제출된
> 코드가 자동으로 프로젝트에 사용되거나 저장소의 사용 권한을 부여하지
> 않습니다.

Kanana Garden의 가장 작은 기여 단위는 “다른 사람이 그대로 재사용할 수 있는
카나나 레시피”입니다. 아이디어만 늘리기보다 대표 입력으로 실제 결과를 확인한
레시피를 받습니다.

## 레시피 추가 절차

1. 골격을 생성합니다.

   ```bash
   PYTHONPATH=src python3 -m kanana_garden new your-recipe \
     --output src/kanana_garden/recipes/your-recipe.json
   ```

2. 사용자 문제 하나만 겨냥하도록 프롬프트와 설명을 고칩니다.
3. `examples`에 개인정보나 비공개 업무 데이터가 아닌 대표 입력을 넣습니다.
4. 검증과 전체 테스트를 실행합니다.

   ```bash
   PYTHONPATH=src python3 -m kanana_garden validate
   PYTHONPATH=src python3 -m kanana_garden report-validate
   PYTHONPATH=src python3 -m kanana_garden catalog --check docs/CATALOG.md
   PYTHONPATH=src python3 -m unittest discover -s tests -v
   ```

5. 가능하면 실제 카나나 서버에서 예제를 실행합니다.

   ```bash
   PYTHONPATH=src python3 -m kanana_garden run your-recipe \
     --input "대표 입력"
   PYTHONPATH=src python3 -m kanana_garden check your-recipe \
     --output reports/your-recipe.json
   PYTHONPATH=src python3 -m kanana_garden report-validate \
     reports/your-recipe.json
   ```

실제 모델을 아직 실행하지 못했다면 리포트를 만들어 내지 말고 PR에서
`미실행`이라고 명시합니다. mock 응답이나 수동 작성 JSON은 실모델 증빙으로
제출할 수 없습니다.

## 레시피 계약

모든 필드는 필수이며 알 수 없는 필드는 거부됩니다.

| 필드 | 의미 |
|---|---|
| `schema_version` | 현재는 `1` |
| `slug` | 소문자·숫자·하이픈으로 된 고유 ID |
| `title` | 사람이 읽는 짧은 이름 |
| `description` | 누구의 어떤 문제를 푸는지 한 문장 |
| `model` | `kakaocorp/kanana-*` 형식의 모델 ID |
| `system_prompt` | 역할, 정확성 경계, 금지할 추측 |
| `prompt_template` | `{input}` 자리표시자를 정확히 한 종류 포함 |
| `generation` | `temperature`, `top_p`, `max_tokens` |
| `tags` | 검색 가능한 태그 한 개 이상 |
| `examples` | `input`과 선택적 `expected_contains` |

## 품질 기준

- 입력에 없는 사실을 만들지 않는 경계가 프롬프트에 있어야 합니다.
- 출력 형식은 사람이 다음 행동을 할 수 있을 만큼 구체적이어야 합니다.
- 특정 조직의 비공개 맥락 없이도 예제가 이해되어야 합니다.
- 한 레시피가 서로 다른 문제를 동시에 풀려고 해서는 안 됩니다.
- “무엇이든 도와주는 챗봇”처럼 범용성만 있는 레시피는 받지 않습니다.
- 건강, 법률, 금융 등 고위험 분야는 전문가 검토와 안전 경계가 없으면 받지
  않습니다.

## 코드 기여

런타임은 Python 표준 라이브러리만 사용하는 원칙을 유지합니다. 새 의존성이
필요하다면 줄이는 설치 비용보다 큰 사용자 가치를 PR 설명에서 입증해 주세요.
오류 메시지와 사용자용 문서는 우선 한국어로 작성하고, 공개 Python API의
이름은 영어를 사용합니다.

## 평가 스위트 기여

런타임 호환성 케이스는 `src/kanana_garden/evals/`에 추가합니다.

- 개인정보나 저작권이 있는 원문 대신 짧은 합성 입력을 사용합니다.
- 외부의 최신 사실이 아니라 입력 안에 답이 있는 과제를 우선합니다.
- 재현성을 위해 `temperature`는 `0`이어야 합니다.
- `contains`, `not_contains`, `regex` 중 하나 이상의 기계 판독 조건을 둡니다.
- 문자열 통과가 의미 품질 전체를 보장한다고 주장하지 않습니다.
- 추가 후 `kanana-garden suite-validate <slug>`를 실행합니다.

## 실행 증빙 기여

`reports/`에는 `check --output`, `server-baseline --output`,
`parity --output`이 직접 만든 JSON만 둡니다.
커밋 전 다음 명령이 통과해야 합니다.

```bash
PYTHONPATH=src python3 -m kanana_garden report-validate
PYTHONPATH=src python3 -m kanana_garden catalog \
  --output docs/CATALOG.md
```

카탈로그를 수동으로 승격하지 않습니다. 현재 recipe와 유효한 실행 증빙만으로
`스키마만 검증 → 실모델 스모크 통과 → 5600G 서버 기준선 통과 → 5600G
재시작 안정성 재현` 순서가 자동 계산됩니다.

검증기는 현재 recipe·suite의 SHA-256, case assertion, 합격률, 임계값과
서버 session·runtime 메타데이터의 내부 정합성을 다시 계산합니다. 다만
전자서명이나 원격 증명은 아니므로
응답이 실제 장비·모델에서 생성됐다는 사실 자체를 암호학적으로 보증하지
않습니다. PR 설명에는 장비, OS, 런타임, 모델 revision, dtype·양자화 방식과
실행 명령을 적어 사람이 출처를 검토할 수 있게 합니다.

리포트의 입력·출력에는 개인정보, API 키, 사내 호스트의 query token이나
비공개 업무 데이터를 넣지 않습니다.

## 차량 제어 기여

`vehicle-control-ko`의 모델 출력은 `vehicle_control.py`의 action 계약을
통과해야 합니다. 새 action을 추가할 때는 다음을 지킵니다.

- 모델 출력에는 실행 코드 대신 의미와 제한된 slot만 둡니다.
- package 이름, shell, URL, 화면 좌표를 모델이 정하지 못하게 합니다.
- Android adapter는 action별 허용 API 또는 명시적 Intent만 호출합니다.
- 낮은 confidence나 안전 영향이 있는 동작은 확인 없이 실행하지 않습니다.
- 실제 차량 주행 중이 아니라 벤치 전원과 테스트 장비에서 검증합니다.

## 모델 및 상표

이 저장소에 모델 가중치나 카카오의 자산을 복사하지 마세요. 카나나 모델 사용
시 모델별 라이선스 원문을 확인하고 사용자에게 `Powered by Kanana`를
명확히 표시해야 합니다. Kanana Garden이 카카오의 공식 또는 보증 프로젝트인
것처럼 표현해서는 안 됩니다.
