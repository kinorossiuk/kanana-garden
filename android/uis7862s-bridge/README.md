# UIS7862S 0단계 제어 브리지

LLM을 탑재하기 전에 UIS7862S Android 펌웨어가 차량 제어 API를 허용하는지
확인하는 벤치 테스트용 디버그 APK입니다. 앱은 네트워크 권한, 임의 package 실행,
shell 실행, 접근성 서비스와 화면 좌표 조작을 사용하지 않습니다.

## 설치

GitHub Release에서 다음 두 파일을 같은 디렉터리에 받습니다.

- `kanana-garden-bridge-0.0.1-alpha.2-debug.apk`
- `kanana-garden-bridge-0.0.1-alpha.2-debug.apk.sha256`

PC에서 해시를 확인하고 UIS7862S에 설치합니다.

```bash
sha256sum -c kanana-garden-bridge-0.0.1-alpha.2-debug.apk.sha256
adb install -r kanana-garden-bridge-0.0.1-alpha.2-debug.apk
adb shell am start -n \
  dev.kinorossiuk.kananagarden.bridge/.MainActivity
```

이 APK는 공개 배포용 release signing이 아닌 CI의 일회성 debug signing을
사용합니다. 다른 CI 빌드나 다음 알파와 서명이 달라지면 `adb install -r`이
거부될 수 있으며, 그때는 기존 테스트 앱을 삭제한 뒤 설치해야 합니다. 앱에는
보존할 사용자 데이터가 없습니다. 주행 중에는 설치하거나 조작하지 마세요.

## 시험 순서

1. 앱의 빠른 입력에서 볼륨 action을 불러오고 `검증 후 실행`을 누릅니다.
2. 지도/내비 앱이 설치된 상태에서 `서울역 길안내`를 실행합니다.
3. 음악 앱에서 곡을 한 번 재생합니다.
4. 브리지의 `미디어 제어용 알림 접근 설정 열기`를 눌러 접근을 허용합니다.
5. 재생·일시정지·다음 곡 action을 각각 시험합니다.
6. 실패하면 루트 도구의 `uis7862s-capture`로 OTA·logcat 증빙을 수집합니다.

ADB는 JSON을 입력 칸에 미리 채우는 용도로만 사용할 수 있습니다. 앱은 외부
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
