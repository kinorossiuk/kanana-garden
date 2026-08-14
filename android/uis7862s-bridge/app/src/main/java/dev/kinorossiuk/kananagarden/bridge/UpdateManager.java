package dev.kinorossiuk.kananagarden.bridge;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

import javax.net.ssl.HttpsURLConnection;

/** User-initiated updater for release APKs published by the project repository. */
final class UpdateManager {
    private static final String RELEASES_API =
            "https://api.github.com/repos/kinorossiuk/kanana-garden/releases?per_page=20";
    private static final String METADATA_ASSET = "kanana-garden-bridge-update.json";
    private static final int MAX_API_BYTES = 1024 * 1024;
    private static final int MAX_METADATA_BYTES = 16 * 1024;
    private static final long MAX_APK_BYTES = 150L * 1024L * 1024L;
    private static final int MAX_REDIRECTS = 5;

    private UpdateManager() {
    }

    static UpdateInfo findAvailableUpdate() throws IOException {
        final JSONArray releases;
        try {
            releases = new JSONArray(new String(
                    fetchBytes(RELEASES_API, "application/vnd.github+json", MAX_API_BYTES),
                    StandardCharsets.UTF_8
            ));
        } catch (JSONException error) {
            throw new IOException("GitHub 릴리스 응답을 해석할 수 없습니다.", error);
        }
        UpdateInfo best = null;
        for (int index = 0; index < releases.length(); index++) {
            JSONObject release = releases.optJSONObject(index);
            if (release == null) {
                continue;
            }
            if (release.optBoolean("draft", true)) {
                continue;
            }
            JSONArray assets = release.optJSONArray("assets");
            if (assets == null) {
                continue;
            }
            String metadataUrl = assetUrl(assets, METADATA_ASSET);
            if (metadataUrl == null) {
                continue;
            }
            try {
                JSONObject metadata = new JSONObject(new String(
                        fetchBytes(metadataUrl, "application/json", MAX_METADATA_BYTES),
                        StandardCharsets.UTF_8
                ));
                UpdateInfo candidate = parseUpdate(release, assets, metadata);
                if (candidate.versionCode > BuildConfig.VERSION_CODE
                        && (best == null || candidate.versionCode > best.versionCode)) {
                    best = candidate;
                }
            } catch (JSONException | IllegalArgumentException ignored) {
                // Ignore releases that do not carry a valid bridge update contract.
            }
        }
        return best;
    }

    static File downloadAndVerify(Activity activity, UpdateInfo update) throws IOException {
        File destination = UpdateFileProvider.updateFile(activity);
        File directory = destination.getParentFile();
        if (directory == null || (!directory.isDirectory() && !directory.mkdirs())) {
            throw new IOException("업데이트 임시 폴더를 만들 수 없습니다.");
        }
        File partial = new File(directory, destination.getName() + ".part");
        if (partial.exists() && !partial.delete()) {
            throw new IOException("이전 임시 업데이트 파일을 지울 수 없습니다.");
        }

        MessageDigest digest = sha256Digest();
        long total = 0;
        HttpsURLConnection connection = openHttps(update.apkUrl, "application/vnd.android.package-archive");
        try {
            long declaredLength = connection.getContentLengthLong();
            if (declaredLength > MAX_APK_BYTES) {
                throw new IOException("업데이트 APK가 허용 크기를 초과합니다.");
            }
            try (InputStream input = connection.getInputStream();
                 FileOutputStream output = new FileOutputStream(partial)) {
                byte[] buffer = new byte[32 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    total += count;
                    if (total > MAX_APK_BYTES) {
                        throw new IOException("업데이트 APK가 허용 크기를 초과합니다.");
                    }
                    digest.update(buffer, 0, count);
                    output.write(buffer, 0, count);
                }
                output.getFD().sync();
            }
        } catch (IOException error) {
            partial.delete();
            throw error;
        } finally {
            connection.disconnect();
        }
        if (total == 0) {
            partial.delete();
            throw new IOException("빈 업데이트 APK를 받았습니다.");
        }
        String actualSha256 = hex(digest.digest());
        if (!actualSha256.equals(update.sha256)) {
            partial.delete();
            throw new IOException("업데이트 APK SHA-256이 릴리스 메타데이터와 다릅니다.");
        }

        try {
            verifyPackageAndSigner(activity, partial, update);
        } catch (IOException | RuntimeException error) {
            partial.delete();
            throw error;
        }
        if (destination.exists() && !destination.delete()) {
            partial.delete();
            throw new IOException("기존 검증 APK를 교체할 수 없습니다.");
        }
        if (!partial.renameTo(destination)) {
            partial.delete();
            throw new IOException("검증 APK 저장을 완료할 수 없습니다.");
        }
        return destination;
    }

    static boolean canRequestInstall(Activity activity) {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O
                || activity.getPackageManager().canRequestPackageInstalls();
    }

    static void openUnknownSourcesSettings(Activity activity) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        Intent settings = new Intent(
                android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + activity.getPackageName())
        );
        activity.startActivity(settings);
    }

    static void launchInstaller(Activity activity, File apk) {
        if (!apk.equals(UpdateFileProvider.updateFile(activity)) || !apk.isFile()) {
            throw new IllegalArgumentException("검증된 업데이트 APK가 없습니다.");
        }
        Intent install = new Intent(Intent.ACTION_INSTALL_PACKAGE);
        install.setData(UpdateFileProvider.updateUri(activity));
        install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        if (install.resolveActivity(activity.getPackageManager()) == null) {
            throw new IllegalStateException("이 펌웨어에서 APK 설치 화면을 찾을 수 없습니다.");
        }
        activity.startActivity(install);
    }

    private static UpdateInfo parseUpdate(
            JSONObject release,
            JSONArray assets,
            JSONObject metadata
    ) {
        if (metadata.optInt("schemaVersion", 0) != 1) {
            throw new IllegalArgumentException("unknown update schema");
        }
        String packageName = metadata.optString("packageName", "");
        String versionName = metadata.optString("versionName", "");
        int versionCode = metadata.optInt("versionCode", 0);
        String apkAsset = metadata.optString("apkAsset", "");
        String sha256 = metadata.optString("sha256", "").toLowerCase(Locale.ROOT);
        String tagName = release.optString("tag_name", "");
        if (!BuildConfig.APPLICATION_ID.equals(packageName)
                || !versionName.matches("[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z.-]+)?")
                || versionCode <= 0
                || !tagName.equals("v" + versionName)
                || !apkAsset.matches("kanana-garden-bridge-[0-9A-Za-z.-]+-release\\.apk")
                || !sha256.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("invalid update metadata");
        }
        String apkUrl = assetUrl(assets, apkAsset);
        if (apkUrl == null) {
            throw new IllegalArgumentException("update APK asset missing");
        }
        return new UpdateInfo(versionName, versionCode, apkUrl, sha256);
    }

    private static String assetUrl(JSONArray assets, String expectedName) {
        for (int index = 0; index < assets.length(); index++) {
            JSONObject asset = assets.optJSONObject(index);
            if (asset != null && expectedName.equals(asset.optString("name", ""))) {
                String url = asset.optString("browser_download_url", "");
                requireAllowedHttps(url);
                return url;
            }
        }
        return null;
    }

    private static byte[] fetchBytes(String url, String accept, int maxBytes) throws IOException {
        HttpsURLConnection connection = openHttps(url, accept);
        try (InputStream input = connection.getInputStream()) {
            return readBounded(input, maxBytes);
        } finally {
            connection.disconnect();
        }
    }

    private static HttpsURLConnection openHttps(String initialUrl, String accept)
            throws IOException {
        URL current = new URL(initialUrl);
        for (int redirect = 0; redirect <= MAX_REDIRECTS; redirect++) {
            requireAllowedHttps(current.toString());
            HttpURLConnection raw = (HttpURLConnection) current.openConnection();
            if (!(raw instanceof HttpsURLConnection)) {
                raw.disconnect();
                throw new IOException("HTTPS가 아닌 업데이트 연결을 거부했습니다.");
            }
            HttpsURLConnection connection = (HttpsURLConnection) raw;
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(30_000);
            connection.setRequestProperty("Accept", accept);
            connection.setRequestProperty("User-Agent", "kanana-garden-bridge/" + BuildConfig.VERSION_NAME);
            int status = connection.getResponseCode();
            if (status >= 300 && status < 400) {
                String location = connection.getHeaderField("Location");
                connection.disconnect();
                if (location == null || location.trim().isEmpty()) {
                    throw new IOException("업데이트 redirect 주소가 없습니다.");
                }
                current = new URL(current, location);
                continue;
            }
            if (status != HttpURLConnection.HTTP_OK) {
                connection.disconnect();
                throw new IOException("업데이트 서버 HTTP " + status);
            }
            return connection;
        }
        throw new IOException("업데이트 redirect가 너무 많습니다.");
    }

    private static void requireAllowedHttps(String value) {
        try {
            URL url = new URL(value);
            String host = url.getHost().toLowerCase(Locale.ROOT);
            boolean allowedHost = host.equals("api.github.com")
                    || host.equals("github.com")
                    || host.endsWith(".githubusercontent.com");
            if (!"https".equalsIgnoreCase(url.getProtocol())
                    || url.getUserInfo() != null
                    || !allowedHost) {
                throw new IllegalArgumentException("untrusted update URL");
            }
        } catch (IOException error) {
            throw new IllegalArgumentException("invalid update URL", error);
        }
    }

    private static byte[] readBounded(InputStream input, int maxBytes) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            total += count;
            if (total > maxBytes) {
                throw new IOException("업데이트 응답이 허용 크기를 초과합니다.");
            }
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private static void verifyPackageAndSigner(
            Activity activity,
            File apk,
            UpdateInfo update
    ) throws IOException {
        PackageManager manager = activity.getPackageManager();
        int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
        PackageInfo candidate = manager.getPackageArchiveInfo(apk.getAbsolutePath(), flags);
        if (candidate == null || !activity.getPackageName().equals(candidate.packageName)) {
            throw new IOException("업데이트 APK의 application ID가 다릅니다.");
        }
        long candidateVersion = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                ? candidate.getLongVersionCode() : candidate.versionCode;
        if (candidateVersion != update.versionCode || candidateVersion <= BuildConfig.VERSION_CODE) {
            throw new IOException("업데이트 APK의 versionCode가 올바르지 않습니다.");
        }
        try {
            PackageInfo installed = manager.getPackageInfo(activity.getPackageName(), flags);
            if (!signatureSet(installed).equals(signatureSet(candidate))) {
                throw new IOException("업데이트 APK의 앱 서명자가 현재 앱과 다릅니다.");
            }
        } catch (PackageManager.NameNotFoundException error) {
            throw new IOException("현재 설치 앱의 서명을 확인할 수 없습니다.", error);
        }
    }

    private static Set<String> signatureSet(PackageInfo info) throws IOException {
        Signature[] signatures;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            if (info.signingInfo == null) {
                throw new IOException("APK 서명 정보가 없습니다.");
            }
            signatures = info.signingInfo.getApkContentsSigners();
        } else {
            signatures = info.signatures;
        }
        if (signatures == null || signatures.length == 0) {
            throw new IOException("APK 서명 인증서가 없습니다.");
        }
        Set<String> result = new HashSet<>();
        for (Signature signature : signatures) {
            result.add(hex(sha256Digest().digest(signature.toByteArray())));
        }
        return result;
    }

    private static MessageDigest sha256Digest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder(bytes.length * 2);
        for (byte item : bytes) {
            value.append(String.format(Locale.ROOT, "%02x", item & 0xff));
        }
        return value.toString();
    }

    static final class UpdateInfo {
        final String versionName;
        final int versionCode;
        final String apkUrl;
        final String sha256;

        UpdateInfo(String versionName, int versionCode, String apkUrl, String sha256) {
            this.versionName = versionName;
            this.versionCode = versionCode;
            this.apkUrl = apkUrl;
            this.sha256 = sha256;
        }
    }
}
