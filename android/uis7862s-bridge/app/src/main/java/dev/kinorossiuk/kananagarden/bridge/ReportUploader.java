package dev.kinorossiuk.kananagarden.bridge;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;

import javax.net.ssl.HttpsURLConnection;

/** Sends a bounded report only to a user-configured HTTPS receiver. */
final class ReportUploader {
    private static final int MAX_REPORT_BYTES = 64 * 1024;
    private static final int MAX_RESPONSE_BYTES = 8 * 1024;

    private ReportUploader() {
    }

    static String validateBaseUrl(String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("HTTPS 수신 주소를 입력하세요.");
        }
        try {
            URI parsed = new URI(value.trim());
            String path = parsed.getPath();
            if (!"https".equalsIgnoreCase(parsed.getScheme())
                    || parsed.getHost() == null
                    || parsed.getUserInfo() != null
                    || parsed.getQuery() != null
                    || parsed.getFragment() != null
                    || (path != null && !path.isEmpty() && !"/".equals(path))) {
                throw new IllegalArgumentException(
                        "수신 주소는 경로·계정·query가 없는 https://호스트 형식이어야 합니다."
                );
            }
            return new URI(
                    "https",
                    null,
                    parsed.getHost(),
                    parsed.getPort(),
                    null,
                    null,
                    null
            ).toString();
        } catch (URISyntaxException error) {
            throw new IllegalArgumentException("올바른 HTTPS 수신 주소가 아닙니다.", error);
        }
    }

    static String validateToken(String value) {
        if (value == null || value.length() < 32 || value.length() > 512
                || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0) {
            throw new IllegalArgumentException("제출 토큰은 줄바꿈 없는 32~512자여야 합니다.");
        }
        return value;
    }

    static String submit(String baseUrl, String token, String report, String version)
            throws IOException {
        String normalizedBase = validateBaseUrl(baseUrl);
        String normalizedToken = validateToken(token);
        byte[] payload = report.getBytes(StandardCharsets.UTF_8);
        if (payload.length == 0 || payload.length > MAX_REPORT_BYTES) {
            throw new IllegalArgumentException("보고서는 1 byte 이상 64 KiB 이하여야 합니다.");
        }

        HttpsURLConnection connection = null;
        try {
            URI endpoint = new URI(normalizedBase + "/v1/uis7862s/reports");
            connection = (HttpsURLConnection) endpoint.toURL().openConnection();
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(20_000);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("POST");
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(payload.length);
            connection.setRequestProperty("Authorization", "Bearer " + normalizedToken);
            connection.setRequestProperty("Content-Type", "text/plain; charset=utf-8");
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("User-Agent", "kanana-garden-bridge/" + version);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(payload);
            }

            int status = connection.getResponseCode();
            InputStream responseStream = status >= 200 && status < 300
                    ? connection.getInputStream() : connection.getErrorStream();
            String response = readBounded(responseStream);
            if (status < 200 || status >= 300) {
                throw new IOException("수신기 HTTP " + status + ": " + response);
            }
            return response.isEmpty() ? "HTTP " + status : response;
        } catch (URISyntaxException error) {
            throw new IllegalArgumentException("수신 endpoint를 만들 수 없습니다.", error);
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private static String readBounded(InputStream input) throws IOException {
        if (input == null) {
            return "";
        }
        try (InputStream stream = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[1024];
            int total = 0;
            int read;
            while ((read = stream.read(buffer)) != -1) {
                total += read;
                if (total > MAX_RESPONSE_BYTES) {
                    throw new IOException("수신기 응답이 8 KiB를 초과했습니다.");
                }
                output.write(buffer, 0, read);
            }
            return output.toString(StandardCharsets.UTF_8.name());
        }
    }
}
