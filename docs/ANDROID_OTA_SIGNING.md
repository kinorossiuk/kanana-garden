# Android OTA 서명 운영

Android는 application ID가 같더라도 APK 서명자가 다르면 업데이트를 거부한다.
`v0.2.0`부터 동일한 전용 키로 모든 release APK를 서명한다. 이 키는 GitHub Public
저장소나 CI artifact에 절대 넣지 않는다.

## 최초 1회 키 준비

인터넷에 공개되지 않는 관리 PC에서 다음 명령을 실행한다. 암호는 명령행에 쓰지
말고 `keytool` prompt에서 입력한다.

```bash
keytool -genkeypair \
  -keystore kanana-bridge-release.jks \
  -alias kanana-bridge \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10950
```

keystore 파일과 두 암호는 별도 오프라인 매체에 백업한다. 키를 잃으면 기존 설치본을
이어 업데이트할 수 없고, 유출되면 공격자가 정상 업데이트처럼 보이는 APK를 서명할
수 있다. `*.jks`와 `*.keystore`는 `.gitignore`에 포함되어 있지만 저장소 안에서
만들지 않는 것이 원칙이다.

## GitHub Actions secrets

GitHub 저장소의 `Settings → Secrets and variables → Actions`에 다음 repository
secret 네 개를 만든다.

| secret | 값 |
|---|---|
| `ANDROID_SIGNING_KEY_BASE64` | `base64 -w 0 kanana-bridge-release.jks` 출력 |
| `ANDROID_STORE_PASSWORD` | keystore 암호 |
| `ANDROID_KEY_ALIAS` | `kanana-bridge` |
| `ANDROID_KEY_PASSWORD` | key 암호 |

Base64 값은 암호화가 아니라 전송 표현일 뿐이므로 keystore와 같은 비밀로 취급한다.
workflow는 이를 runner 임시 디렉터리에만 복원하고 release 빌드 종료 후 보존하지
않는다.

## 릴리스 규칙

1. `android/uis7862s-bridge/version.properties`의 `VERSION_CODE`를 반드시 높인다.
2. `VERSION_NAME`과 Python 패키지·CHANGELOG·README 버전을 맞춘다.
3. main CI가 통과한 commit에 `vVERSION_NAME` 태그를 만든다.
4. tag workflow가 서명 APK, `.sha256`, `kanana-garden-bridge-update.json`을
   같은 GitHub Release에 첨부했는지 확인한다.
5. 별도 기기에서 기존 버전 위에 업데이트 설치해 데이터가 보존되는지 확인한다.

앱은 GitHub의 메타데이터만 신뢰하지 않는다. 다운로드 후 SHA-256, application ID,
상향 versionCode와 현재 앱의 signing certificate를 다시 검사한다. 설치 최종 승인은
항상 Android package installer에서 사용자가 수행한다.
