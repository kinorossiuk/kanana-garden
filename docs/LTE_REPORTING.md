# UIS7862S LTE 테스트 보고서 수신

## 권장 구성

UIS7862S는 LTE 외부망에 있으므로 APK는 공개 HTTPS hostname으로 제출해야 한다.
이미 DuckDNS와 공인 IP·포트 forwarding을 사용할 수 있으면 nginx reverse proxy가
가장 단순하다. CGNAT이거나 공유기 포트를 열 수 없을 때만 Cloudflare Tunnel을
대체 경로로 사용한다.

```text
UIS7862S LTE
  └─ POST https://YOUR_SUBDOMAIN.duckdns.org:8443/v1/uis7862s/reports
       └─ 공유기 WAN 8443 → 192.168.0.40:8443
            └─ nginx TLS → http://127.0.0.1:8762
                 └─ reports/uis7862s/inbox/
```

현재 테스트 랩에서 두 호스트의 역할은 분리한다.

| 주소 | 역할 | LTE 보고서 수신 |
|---|---|---:|
| `192.168.0.50` | Ryzen 5600G 로컬 LLM 서버 | 아니요 |
| `192.168.0.40` | Codex 분석·디버깅 및 현재 저장소 checkout | 예 |

따라서 공유기의 포트 forwarding 대상은 5600G가 아니라 `192.168.0.40`이다.

필요 조건:

- 이 저장소 checkout과 Python 환경이 있는 `192.168.0.40` 분석 호스트
- 현재 공인 IP를 가리키는 DuckDNS subdomain
- 공유기에서 수신 PC로 전달할 외부 HTTPS 포트
- APK에 한 번 입력할 64자 무작위 제출 token

DuckDNS는 DNS 주소를 갱신할 뿐 NAT를 통과시키지 않는다. LTE에서 실제로 받으려면
공인 IP와 포트 forwarding이 필요하다. 외부에서 공유기 관리 페이지가 보인다면
같은 포트를 사용하지 말고 관리 기능을 끄거나 8443 같은 별도 포트를 사용한다.

## 1. 로컬 수신기 준비

```bash
./ops/report-host/install.sh
openssl rand -hex 32
```

`openssl` 출력은 비밀이다. 다음 파일에서 placeholder를 그 값으로 교체한다.

```text
~/.config/kanana-garden/report-receiver.env
```

서비스를 시작하고 loopback 상태를 확인한다.

```bash
systemctl --user enable --now kanana-report-receiver
systemctl --user status kanana-report-receiver
curl -fsS http://127.0.0.1:8762/health
```

수신기는 loopback 이외 주소로 실행하는 것을 거부한다. 공유기에서 8762 포트를
열지 않는다.

## 2. DuckDNS와 nginx 연결

1. DuckDNS subdomain이 현재 공유기 공인 IPv4로 해석되는지 확인한다.
2. 유효한 공개 TLS 인증서를 준비한다. 저장소에는 인증서와 DuckDNS token을
   넣지 않는다.
3. `ops/report-host/nginx-report-receiver.conf.example`을 복사하고
   `YOUR_SUBDOMAIN`을 실제 값으로 바꾼다.
4. nginx 설정을 검사하고 reload한다.
5. 공유기에서 WAN 8443을 `192.168.0.40:8443`으로 전달한다.
6. LTE 휴대전화처럼 내부 Wi-Fi가 아닌 망에서 `/health`를 확인한다.

```bash
sudo cp ops/report-host/nginx-report-receiver.conf.example \
  /etc/nginx/sites-available/kanana-report-receiver
sudoedit /etc/nginx/sites-available/kanana-report-receiver
sudo ln -s /etc/nginx/sites-available/kanana-report-receiver \
  /etc/nginx/sites-enabled/kanana-report-receiver
sudo nginx -t
sudo systemctl reload nginx
```

직접 포트를 열 수 없다면 [Cloudflare remotely-managed Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)을
사용하고 Service URL만 `http://localhost:8762`로 설정한다. 두 방식 모두 수신기는
loopback에만 둔다.

## 3. APK 설정과 제출

APK의 `LTE 제출 설정`에 다음 두 값을 입력한다.

```text
HTTPS 수신 주소: https://YOUR_SUBDOMAIN.duckdns.org:8443
제출 토큰: ~/.config/kanana-garden/report-receiver.env에 설정한 값
```

`LTE 제출 설정 저장`을 누른 뒤 시험을 진행하고 `LTE로 현재 저장소에 결과 제출`을
누른다. APK는 다음을 강제한다.

- `https://` scheme과 경로 없는 base hostname만 허용
- redirect 거부
- 15초 연결·20초 응답 제한 시간
- 32~512자 token
- 64 KiB 이하 UTF-8 보고서
- 사용자 버튼 없이 자동 제출하지 않음

성공 응답에는 `report_id`와 SHA-256이 표시된다. 수신 PC에서 확인한다.

```bash
find reports/uis7862s/inbox -maxdepth 1 -type f -printf '%f\n'
```

같은 report ID의 `.txt`는 사람이 읽는 원문, `.json`은 수신 시각·byte 수와
SHA-256 메타데이터다. 이 디렉터리는 Git에서 제외된다.

## 장애 처리와 token 교체

- 분석 호스트, `kanana-report-receiver`, `cloudflared` 중 하나가 꺼져 있으면
  제출은 실패한다. APK 내부 보고서는 유지되므로 복구 후 다시 누른다.
- 401이면 APK와 서버 token이 다른 것이다.
- 404이면 nginx hostname/location 또는 Tunnel route가 잘못된 것이다.
- 502/503이면 reverse proxy는 도달했지만 로컬 수신기가 꺼졌을 가능성이 높다.
- token 유출·기기 분실 시 서버 env에 새 token을 설정하고 서비스를 재시작한
  뒤 APK에도 새 값을 저장한다.
- DuckDNS API token이 유출되면 DuckDNS에서 교체하고 DDNS 갱신·인증서 DNS
  challenge 설정도 새 값으로 갱신한다.

```bash
systemctl --user restart kanana-report-receiver
journalctl --user -u kanana-report-receiver -n 100 --no-pager
```

USB가 가능한 예외 상황에는 다음 보조 경로를 사용할 수 있다.

```bash
kanana-garden uis7862s-report-pull
```
