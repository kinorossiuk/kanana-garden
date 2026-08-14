# Raspberry Pi 5 8GB 온디바이스 배포

## 현재 결정

첫 대상 장비는 **Raspberry Pi 5 8GB + 64-bit Raspberry Pi OS**다. 모델은
`kakaocorp/kanana-2-1.3b-instruct`를 사용한다. 아직 실제 장비에 모델을
연결하거나 성능을 측정하지 않았으므로 이 문서의 수치는 요구 조건이며 실측
결과가 아니다.

정확성 기준 경로는 공식 Hugging Face 모델의 Transformers 구현이다. 모델은
커스텀 `Kanana2TinyForCausalLM` 코드와 3:1 sliding-window/full-attention
구조를 사용하므로 `trust_remote_code=True`가 필요하다. Garden은 검토한
모델 커밋 `c10f59f16af7e3e3a9b2801f528a98c1e4ff6171`을 기본으로 고정한다.

- [공식 Kanana-2 1.3B 모델 카드](https://huggingface.co/kakaocorp/kanana-2-1.3b-instruct)
- [고정한 모델 커밋](https://huggingface.co/kakaocorp/kanana-2-1.3b-instruct/tree/c10f59f16af7e3e3a9b2801f528a98c1e4ff6171)
- [Transformers 커스텀 모델 보안 안내](https://huggingface.co/docs/transformers/models#custom-models)

## 하드웨어 준비

필수:

- Raspberry Pi 5 8GB
- 64-bit Raspberry Pi OS
- 모델·가상환경 위치에 여유 공간 8 GiB 이상
- Python 3.10 이상

권장:

- 공식 Active Cooler 또는 팬 케이스
- 공식 27 W USB-C 전원 공급 장치
- microSD 대신 충분한 공간의 USB 3/NVMe SSD에 모델 캐시 저장

Raspberry Pi 공식 문서는 지속적인 고부하에서 열 스로틀링이 발생할 수 있다고
설명하며, Pi 5에 능동 냉각을 권장한다. 전원은 27 W USB-C 공급 장치가
권장된다.

- [Raspberry Pi 열·전원 문서](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#frequency-management-and-thermal-control)
- [Raspberry Pi Active Cooler](https://www.raspberrypi.com/products/active-cooler/)

## 1. 사전 점검

저장소를 Raspberry Pi에 받은 뒤 실행한다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .

kanana-garden device-doctor --model-dir /mnt/ssd/kanana-hf
```

모든 필수 항목이 `PASS`여야 다음 단계로 진행한다. `/mnt/ssd/kanana-hf`는
실제 SSD 경로로 바꾼다.

기계 판독 가능한 장비 증빙도 남길 수 있다.

```bash
mkdir -p reports
kanana-garden device-doctor \
  --model-dir /mnt/ssd/kanana-hf \
  --json > reports/pi5-device.json
```

장비 리포트는 원본 `/etc/machine-id`와 Linux boot ID를 저장하지 않고 각각의
SHA-256만 기록합니다. `device_id_sha256`은 재부팅 전후가 같은 장치인지,
`boot_id_sha256`은 서로 다른 부팅 세션인지 확인하는 데 사용됩니다.
안정 장치 해시는 공개 리포트 사이에서 연결 가능한 가명 식별자입니다.
machine-id를 사용하고 싶지 않다면 기준선 실행 전마다 같은 비밀값을
`KANANA_DEVICE_ID`로 설정하고 원문은 공개하지 않습니다. 공개 제출 사이의
연결을 피하려면 재부팅 전후 비교 한 쌍마다 새로운 고엔트로피 값을 사용합니다.

## 2. 정확성 기준 런타임 설치

모델 캐시와 pip 캐시를 SSD에 둔다.

```bash
export HF_HOME=/mnt/ssd/kanana-hf
export PIP_CACHE_DIR=/mnt/ssd/pip-cache

python3 -m pip install -e '.[pi]'
```

`pi` extra는 `transformers>=4.57`과 ARM CPU용 PyTorch 경로를 설치한다.
PyTorch 2.11부터 일반 Linux aarch64 wheel의 성격이 바뀌었기 때문에 Pi
프로필은 현재 `torch<2.11`로 제한한다. 이 제한은 실제 Pi 검증 후 조정한다.

첫 모델 로드는 수 GB를 내려받으므로 네트워크와 저장공간을 다시 확인한다.
Hugging Face의 커스텀 모델 코드를 실행하므로 고정한 커밋을 임의로
`main`으로 바꾸지 않는다.

Pi 5의 Cortex-A76은 네이티브 BF16 명령을 제공하지 않는다. 로컬 서버는
모델을 내려받기 전에 설치된 PyTorch가 BF16 행렬 연산을 수행할 수 있는지
작은 연산으로 검사하고, 지원하지 않으면 즉시 중단한다. 소프트웨어 폴백으로
실행되더라도 속도가 충분하다는 뜻은 아니므로 첫 실측이 필수다.

## 3. 로컬 API 시작

Pi의 터미널 A:

```bash
source .venv/bin/activate
export HF_HOME=/mnt/ssd/kanana-hf

kanana-garden serve-local \
  --host 127.0.0.1 \
  --port 8000 \
  --threads 4 \
  --max-input-tokens 2048 \
  --max-output-tokens 512
```

기본적으로 루프백에서만 접속할 수 있다. LAN에 공개하려면 반드시 API 키를
설정하고 방화벽으로 접근 대상을 제한한다.

```bash
read -s KANANA_API_KEY
export KANANA_API_KEY

kanana-garden serve-local \
  --host 0.0.0.0 \
  --api-key "$KANANA_API_KEY"
```

## 4. 첫 실모델 검증

Pi의 터미널 B:

```bash
source .venv/bin/activate
export KANANA_BASE_URL=http://127.0.0.1:8000/v1

kanana-garden doctor
kanana-garden check meeting-action-items-ko \
  --output reports/pi5-meeting-action-items-ko.json
kanana-garden report-validate

kanana-garden pi5-compare \
  reports/pi5-baseline-boot-1.json \
  reports/pi5-baseline-boot-2.json
```

`pi5-compare`는 두 baseline 자체가 모두 유효하고 통과했는지, 모델·recipe
revision이 같은지, `device_id_sha256`은 같고 `boot_id_sha256`은 다른지
확인합니다. 지연 시간·tok/s·최고 온도의 두 번째 실행 변화도 함께 보여
주지만, 현재는 성능 변화에 별도 합격 임계값을 두지 않습니다.

리포트는 다음을 증명한다.

- 서버 `/v1/models`가 정확한 카나나 모델 ID를 노출했는가
- 실제 응답의 모델 ID가 요청 모델과 같은가
- 레시피의 최소 기대 문자열을 만족했는가
- 레시피 내용의 SHA-256이 무엇인가
- 응답 지연 시간과 생성 토큰/초가 얼마인가

## 5. 반복 기준선 수집

단일 스모크 검사가 통과하면 내장 레시피 전체를 각각 3회 반복합니다.
`pi5-baseline`은 실행 전후 장비 상태, 각 응답의 품질·지연·tok/s, 매 생성
직후 온도와 `vcgencmd get_throttled` 결과를 하나의 리포트에 기록합니다.

```bash
kanana-garden pi5-baseline \
  --model-dir /mnt/ssd/kanana-hf \
  --output reports/pi5-baseline-boot-1.json

kanana-garden report-validate reports/pi5-baseline-boot-1.json
```

기본 제한 시간은 요청당 600초입니다. 더 느린 환경에서는 `--timeout`을
명시합니다. 반복 횟수는 기본 3회이며 `--repetitions`로 3~20회 사이에서
늘릴 수 있습니다.

온도가 80°C 이상이거나 스로틀링 값이 `throttled=0x0`이 아니면 남은 생성을
즉시 중단합니다. 이때도 리포트는 저장되지만 `complete`와 `passed`는
`false`입니다. 냉각·전원 문제를 해결하기 전에는 재시도하지 않습니다.

재부팅 재현성은 한 프로세스에서 증명할 수 없으므로 첫 리포트를 보존한 뒤
Pi를 재부팅하고 다른 파일명으로 같은 명령을 다시 실행합니다.

```bash
sudo reboot

# 재부팅 후 서버를 다시 시작한 다음
kanana-garden pi5-baseline \
  --model-dir /mnt/ssd/kanana-hf \
  --output reports/pi5-baseline-boot-2.json

kanana-garden report-validate
```

## 6. 합격 기준

첫 온디바이스 마일스톤은 아래 조건을 모두 만족해야 완료다.

1. `device-doctor` 필수 검사 전체 통과
2. `doctor`가 `kakaocorp/kanana-2-1.3b-instruct` 확인
3. 두 `pi5-baseline` 리포트에서 내장 레시피 3개가 각각 3회 연속 통과
4. 모든 sample에 응답 모델, 지연 시간, tok/s 기록
5. 추론 중 온도가 80°C 미만이고 `vcgencmd get_throttled`가 문제를 보고하지 않음
6. `pi5-compare`가 같은 장치·다른 boot의 두 통과 리포트를 확인

성능 기준은 첫 실측 후 정한다. 측정 전에는 Raspberry Pi에서의 tok/s나 응답
시간을 보장하지 않는다.

## GGUF/llama.cpp 상태

1.3B의 제3자 Q8 GGUF가 존재하지만 현재 기본 경로로 채택하지 않는다.

- GGUF 메타데이터는 아키텍처를 일반 `qwen3`로 기록한다.
- 공식 모델은 레이어마다 다른 RoPE를 쓰는 3:1
  sliding-window/full-attention 구조다.
- 현재 `llama.cpp`의 일반 Qwen3 실행 경로가 이 차이를 동일하게 처리한다는
  증거가 없다.
- Q8 파일은 약 1.38 GB로 메모리상 유리하지만, 작동 여부와 모델 출력
  동등성은 별개의 문제다.

따라서 GGUF는 Transformers 기준 출력과 다음 항목을 비교한 뒤에만 승격한다.

1. 같은 채팅 템플릿과 greedy decoding 사용
2. 한국어 대표 케이스 최소 30개
3. 핵심 사실·형식 통과율 비교
4. 토큰화 결과 비교
5. 2K 문맥과 8K 문맥에서 회귀 확인

이 호환성 검증과 필요한 `llama.cpp` 아키텍처 지원 자체가 Kanana Garden의
중요한 생태계 기여 과제다.

## 두 런타임 패리티 실행

`pi5-parity-ko-v1`은 다음 다섯 범주의 합성 한국어 케이스 32개를 포함한다.

- 입력 근거 추출 10개
- 출력 형식과 지시 이행 8개
- 정보 없음 처리 2개
- 날짜·숫자·URL 등 재작성 보존 6개
- 한국어 커뮤니케이션 6개

공식 Transformers 서버를 `reference`, Pi의 GGUF 등 후보 서버를
`candidate`로 둔다. 두 서버는 서로 다른 URL이어야 한다.

먼저 세 케이스로 연결만 확인한다.

```bash
kanana-garden parity pi5-parity-ko-v1 \
  --reference-url http://reference-host:8000/v1 \
  --candidate-url http://raspberrypi.local:8080/v1 \
  --limit 3
```

`--limit` 또는 `--case-id`를 쓴 리포트는 `complete: false`, `passed: null`로
기록되어 전체 스위트 합격 증거로 오인되지 않는다.

연결이 확인되면 전체 비교와 증빙 저장을 실행한다.

```bash
kanana-garden parity pi5-parity-ko-v1 \
  --reference-url http://reference-host:8000/v1 \
  --candidate-url http://raspberrypi.local:8080/v1 \
  --output reports/pi5-parity.json
```

후보 서버가 GGUF 파일명 같은 다른 모델 ID를 노출하면
`--candidate-model`에 `/v1/models`가 반환한 정확한 ID를 지정한다. 인증이
필요한 서버는 `KANANA_REFERENCE_API_KEY`와 `KANANA_CANDIDATE_API_KEY`
환경 변수를 사용한다.

전체 합격 조건은 다음 두 가지다.

- 공식 기준 런타임 자체가 전체 케이스의 90% 이상 통과
- 기준 런타임이 통과한 케이스 중 후보 런타임이 90% 이상 통과

문자열·정규식 기반 스모크 검사는 의미 품질 전체를 증명하지 않는다. 이
단계를 통과한 뒤 `kanana-garden report-validate reports/pi5-parity.json`로
저장 내용의 정합성을 재검산하고 사람이 응답 차이를 검토해야 한다.
