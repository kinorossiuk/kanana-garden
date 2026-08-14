# Android OTA 서명 운영

Android OTA에는 Google Play 개발자 계정이 필요하지 않지만 모든 업데이트 APK가
같은 키로 서명되어야 한다. 저장소의 자동 생성 스크립트가 키와 비밀번호를 안전한
사용자 설정 폴더에 만든다.

## 1. 키 자동 생성

분석 호스트에서 한 번만 실행한다.

```bash
./ops/android-signing/create.sh
```

다음 세 파일이 `~/.config/kanana-garden/signing/`에 생성된다.

- `kanana-bridge-release.p12`: 장기간 보관할 실제 서명키
- `android-signing-key.base64`: GitHub에 붙여넣을 키 문자열
- `android-signing-password`: 자동 생성된 비밀번호

이 디렉터리를 오프라인 매체에 통째로 백업한다. 키를 잃으면 기존 앱을 이어
업데이트할 수 있고, 키가 유출되면 공격자가 정상 업데이트처럼 보이는 APK를 서명할
수 있으므로 저장소에는 넣지 않는다.

## 2. GitHub Secret 두 개 등록

[저장소 Actions Secrets](https://github.com/kinorossiuk/kanana-garden/settings/secrets/actions)에서
`New repository secret`을 눌러 다음 두 개만 등록한다.

| secret | 값 확인 명령 |
|---|---|
| `ANDROID_SIGNING_KEY_BASE64` | `cat ~/.config/kanana-garden/signing/android-signing-key.base64` |
| `ANDROID_SIGNING_PASSWORD` | `cat ~/.config/kanana-garden/signing/android-signing-password` |

화면의 `Variables`가 아니라 `Repository secrets`에 넣는다. 출력값을 채팅, GitHub
issue 또는 소스 파일에 붙이지 않는다.

## 3. 릴리스 규칙

1. `android/uis7862s-bridge/version.properties`의 `VERSION_CODE`를 높인다.
2. main CI가 통과한 commit에 `vVERSION_NAME` 태그를 만든다.
3. tag workflow가 서명 APK, `.sha256`, `kanana-garden-bridge-update.json`을
   같은 GitHub Release에 첨부했는지 확인한다.

앱은 다운로드 후 SHA-256, application ID, 상향 versionCode와 현재 앱의 signing
certificate를 검사한다. 설치 최종 승인은 항상 Android package installer에서
사용자가 수행한다.
