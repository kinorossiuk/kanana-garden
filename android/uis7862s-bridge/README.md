# UIS7862S 0단계 제어 브리지

LLM을 탑재하기 전에 UIS7862S Android 펌웨어가 차량 제어 API를 허용하는지
확인하는 벤치 테스트용 디버그 APK입니다. 앱은 네트워크 권한, 임의 package 실행,
shell 실행, 접근성 서비스와 화면 좌표 조작을 사용하지 않습니다.

## 설치

GitHub Release에서 다음 두 파일을 같은 디렉터리에 받습니다.

- `kanana-garden-bridge-0.0.1-alpha.3-debug.apk`
- `kanana-garden-bridge-0.0.1-alpha.3-debug.apk.sha256`

PC에서 해시를 확인하고 UIS7862S에 설치합니다.

```bash
sha256sum -c kanana-garden-bridge-0.0.1-alpha.3-debug.apk.sha256
adb install -r kanana-garden-bridge-0.0.1-alpha.3-debug.apk
adb shell am start -n \
  dev.kinorossiuk.kananagarden.bridge/.MainActivity
```

이 APK는 공개 배포용 release signing이 아닌 CI의 일회성 debug signing을
사용합니다. 다른 CI 빌드나 다음 알파와 서명이 달라지면 `adb install -r`이
거부될 수 있으며, 그때는 기존 테스트 앱을 삭제한 뒤 설치해야 합니다. 앱에는
보존할 사용자 데이터가 없습니다. 주행 중에는 설치하거나 조작하지 마세요.

## 시험 순서

시험 순서는 APK 화면에 포함되어 있습니다. 볼륨 올리기·30% 설정, 서울역
목적지 전달, 음악 재생·일시정지·다음 곡을 실행하고 실제 장비 동작을 확인한
뒤 각 항목의 PASS 또는 FAIL 하나만 체크합니다. 앱은 다음 정보를 보고서로
계속 보존합니다.

- 앱 버전, 기기 제조사·모델, Android SDK와 펌웨어 표시
- 사용자가 직접 확인한 PASS/FAIL
- 테스터 메모
- Android API 호출 시각과 성공·실패 메시지

`결과 보고서 복사`와 `다른 앱으로 결과 공유`는 보조 기능입니다. 현재 저장소로
바로 제출하려면 아래 LTE 수신기 구성을 사용합니다.

## LTE로 현재 저장소에 제출

```text
UIS7862S LTE
  └─ HTTPS + 제출 전용 token
       └─ DuckDNS + nginx 또는 Cloudflare Tunnel
            └─ 127.0.0.1:8762 report-receiver
                 └─ reports/uis7862s/inbox/*.txt + *.json
```

수신 서버에서 32-byte 무작위 토큰을 만들고 사용자 환경 파일에 설정합니다.
명령의 출력은 비밀이므로 공개 저장소나 이슈에 올리지 마세요.

```bash
openssl rand -hex 32

# 출력값을 ~/.config/kanana-garden/report-receiver.env의
# KANANA_REPORT_TOKEN에 설정
systemctl --user enable --now kanana-report-receiver
curl -fsS http://127.0.0.1:8762/health
```

이미 DuckDNS와 공인 IP를 사용한다면 nginx가 TLS를 종료하고
`127.0.0.1:8762`로 reverse proxy하도록 설정합니다. 예제는
`ops/5600g/nginx-report-receiver.conf.example`, 전체 절차는
[LTE 보고서 수신](../../docs/LTE_REPORTING.md)에 있습니다. 공유기 WAN 8443을
수신 PC의 8443으로 전달해야 합니다. 포트 forwarding이 불가능할 때만
Cloudflare Tunnel을 사용합니다.

APK의 `LTE 제출 설정`에 다음 값을 넣습니다.

```text
HTTPS 수신 주소: https://YOUR_SUBDOMAIN.duckdns.org:8443
제출 토큰: 서버의 KANANA_REPORT_TOKEN 값
```

`LTE 제출 설정 저장` 후 `LTE로 현재 저장소에 결과 제출`을 누릅니다. 성공하면
화면에 서버의 report ID와 SHA-256이 표시되고, 서버 checkout의
`reports/uis7862s/inbox/`에 `.txt` 원문과 `.json` 메타데이터가 생성됩니다.
앱은 HTTP, redirect, 32자 미만 token과 64 KiB 초과 보고서를 거부합니다.

공개 hostname은 누구나 접속을 시도할 수 있으므로 제출 token을 충분히 무작위로
만들고 유출 시 즉시 교체해야 합니다. 수신기는 반드시 loopback에만 바인딩하고
nginx/Tunnel을 통해서만 접근시킵니다.

USB/ADB 수집은 LTE 장애 시에만 사용합니다.

```bash
kanana-garden uis7862s-report-pull
```

ADB는 action JSON을 입력 칸에 미리 채우는 용도로도 사용할 수 있습니다. 앱은 외부
입력을 자동 실행하지 않으며 사용자가 화면에서 실행 버튼을 눌러야 합니다.

```bash
adb shell am start -n \
  dev.kinorossiuk.kananagarden.bridge/.MainActivity \
  --es action_json '{"action":"volume_set","slots":{"level_percent":30},"confidence":"high","requires_confirmation":false}'
```

`requires_confirmation`이 `true`이면 실행 버튼 이후에도 확인 대화상자를 한 번
더 표시합니다.

## 현재 범위

| action | 0단계 구현 | 비고 |
|---|---:|---|
| 볼륨 올림·내림·설정·음소거 | 예 | `STREAM_MUSIC` 대상 |
| 길안내 시작 | 부분 | 검증된 `geo:` Intent로 설치된 앱에 목적지 전달 |
| 길안내 종료 | 아니오 | Android 공통 API가 없어 앱별 어댑터 필요 |
| 재생·정지·다음·이전 | 예 | 활성 `MediaSession`과 알림 접근 필요 |
| 검색어로 음악 재생 | 아니오 | 음악 앱별 어댑터 필요 |
| 내비·음악·설정 앱 열기 | 예 | 고정 Android category/설정 action만 허용 |

## 로컬 빌드

JDK 17, Android SDK 36/build-tools 36.0.0, Gradle 9.4.1이 필요합니다.

```bash
gradle -p android/uis7862s-bridge --no-daemon :app:assembleDebug
```

저장소 CI도 같은 조합으로 APK를 빌드하고 `apksigner` 검증과 SHA-256 생성을
수행합니다.
