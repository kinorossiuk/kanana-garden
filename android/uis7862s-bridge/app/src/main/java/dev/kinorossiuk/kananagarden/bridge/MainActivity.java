package dev.kinorossiuk.kananagarden.bridge;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.io.File;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** Bench-only UI: incoming ADB data is displayed and never executed automatically. */
public final class MainActivity extends Activity {
    static final String ACTION_JSON_EXTRA = "action_json";
    private static final String LOG_TAG = "KananaBridge";
    private static final String PREFERENCES_NAME = "stage_zero_results";
    private static final String NOTES_KEY = "tester_notes";
    private static final String HISTORY_KEY = "execution_history";
    private static final String REPORT_FILE_NAME = "stage-zero-report.txt";
    private static final String RECEIVER_URL_KEY = "receiver_url";
    private static final String RECEIVER_TOKEN_KEY = "receiver_token";

    private EditText actionInput;
    private EditText notesInput;
    private EditText receiverUrlInput;
    private EditText receiverTokenInput;
    private LinearLayout receiverSettingsPanel;
    private TextView receiverSettingsStatusView;
    private Button receiverSettingsToggle;
    private TextView resultView;
    private TextView reportView;
    private TextView updateStatusView;
    private ActionExecutor executor;
    private SharedPreferences preferences;
    private String executionHistory;
    private String pendingCrash;
    private String handledDiagnostics;
    private final Map<String, TestSelection> selections = new LinkedHashMap<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        executor = new ActionExecutor(this);
        preferences = getSharedPreferences(PREFERENCES_NAME, MODE_PRIVATE);
        executionHistory = preferences.getString(HISTORY_KEY, "");
        pendingCrash = CrashDiagnostics.readPending(this);
        handledDiagnostics = CrashDiagnostics.readHandled(this);
        setContentView(buildContent());
        loadIntentPayload(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadIntentPayload(intent);
    }

    @Override
    protected void onDestroy() {
        if (executor != null) {
            executor.close();
        }
        super.onDestroy();
    }

    private View buildContent() {
        int padding = dp(18);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);

        TextView title = text("Kanana Garden Bridge " + BuildConfig.VERSION_NAME, 22);
        content.addView(title);

        TextView warning = text(
                "0단계 벤치 테스트 전용 진단 앱입니다. 주행 중 사용하지 마세요. "
                        + "ADB로 받은 JSON도 자동 실행하지 않으며 아래 실행 버튼을 직접 눌러야 합니다.",
                15
        );
        warning.setTextColor(Color.rgb(183, 28, 28));
        warning.setPadding(0, dp(10), 0, dp(14));
        content.addView(warning);

        content.addView(sectionTitle("테스트 순서"));
        content.addView(text(
                "1. 볼륨 올리기와 30% 설정을 실행하고 실제 변화를 확인합니다.\n"
                        + "2. 서울역 길안내를 실행하고 열린 내비 앱과 목적지를 확인합니다.\n"
                        + "3. 음악 앱에서 곡을 한 번 재생한 뒤 알림 접근을 허용합니다.\n"
                        + "4. 재생·일시정지·다음 곡을 실행합니다.\n"
                        + "5. 각 항목을 직접 확인한 후 PASS 또는 FAIL 하나만 체크합니다.\n"
                        + "6. 메모를 적고 결과 제출/공유 버튼을 누릅니다.",
                15
        ));

        content.addView(sectionTitle("기기 정보"));
        TextView device = text(deviceSummary(), 14);
        device.setTextIsSelectable(true);
        content.addView(device);

        content.addView(sectionTitle("PASS / FAIL 체크리스트"));
        addChecklistItem(content, "volume_up", "1. 볼륨 올리기");
        addChecklistItem(content, "volume_set", "2. 볼륨 30% 설정");
        addChecklistItem(content, "navigation_start", "3. 서울역 목적지 전달");
        addChecklistItem(content, "media_play", "4. 음악 재생");
        addChecklistItem(content, "media_pause", "5. 음악 일시정지");
        addChecklistItem(content, "media_next", "6. 다음 곡");

        content.addView(sectionTitle("동작 실행"));
        addPresetButton(content, "볼륨 올리기", json("volume_up", "{}", false));
        addPresetButton(content, "볼륨 30%", json("volume_set", "{\"level_percent\":30}", false));
        addPresetButton(content, "서울역 길안내", json(
                "navigation_start",
                "{\"destination\":\"서울역\"}",
                true
        ));
        addPresetButton(content, "음악 재생", json("media_play", "{}", false));
        addPresetButton(content, "음악 일시정지", json("media_pause", "{}", false));
        addPresetButton(content, "다음 곡", json("media_next", "{}", false));

        Button notificationAccess = button("미디어 제어용 알림 접근 설정 열기");
        notificationAccess.setOnClickListener(view -> {
            try {
                showResult(executor.openNotificationAccessSettings(), false);
            } catch (RuntimeException error) {
                recordDetailedError("notification_settings", error);
                showResult(CrashDiagnostics.summary(error), true);
            }
        });
        content.addView(notificationAccess);

        TextView inputLabel = text("action JSON", 17);
        inputLabel.setPadding(0, dp(14), 0, dp(6));
        content.addView(inputLabel);

        actionInput = new EditText(this);
        actionInput.setMinLines(7);
        actionInput.setGravity(android.view.Gravity.TOP | android.view.Gravity.START);
        actionInput.setText(json("volume_up", "{}", false));
        content.addView(actionInput, matchWidthWrapHeight());

        Button execute = button("검증 후 실행");
        execute.setOnClickListener(view -> validateAndExecute());
        content.addView(execute);

        resultView = text("대기 중", 15);
        resultView.setTextIsSelectable(true);
        resultView.setPadding(0, dp(14), 0, dp(24));
        content.addView(resultView);

        content.addView(sectionTitle("테스터 메모"));
        notesInput = new EditText(this);
        notesInput.setHint("예: 볼륨은 성공, 내비 앱 선택창이 반복 표시됨");
        notesInput.setMinLines(3);
        notesInput.setGravity(android.view.Gravity.TOP | android.view.Gravity.START);
        notesInput.setText(preferences.getString(NOTES_KEY, ""));
        notesInput.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence value, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence value, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable value) {
                preferences.edit().putString(NOTES_KEY, value.toString()).apply();
                refreshReport();
            }
        });
        content.addView(notesInput, matchWidthWrapHeight());

        Button copyReport = button("결과 보고서 복사");
        copyReport.setOnClickListener(view -> copyReport());
        content.addView(copyReport);

        Button shareReport = button("다른 앱으로 결과 공유");
        shareReport.setOnClickListener(view -> shareReport());
        content.addView(shareReport);

        content.addView(sectionTitle("앱 OTA 업데이트"));
        content.addView(text(
                "GitHub 공식 릴리스에서 더 높은 versionCode를 확인합니다. APK의 SHA-256, "
                        + "application ID와 현재 앱의 서명자를 모두 검증한 뒤 Android 설치 "
                        + "화면을 엽니다. 자동 설치는 하지 않습니다.",
                13
        ));
        Button updateButton = button("업데이트 확인");
        updateButton.setOnClickListener(view -> checkForAppUpdate(updateButton));
        content.addView(updateButton);
        updateStatusView = text("현재 버전: " + BuildConfig.VERSION_NAME, 13);
        updateStatusView.setTextIsSelectable(true);
        content.addView(updateStatusView);

        content.addView(sectionTitle("LTE 제출 설정"));

        boolean receiverConfigured = hasSavedReceiverSettings();
        receiverSettingsStatusView = text("", 13);
        content.addView(receiverSettingsStatusView);

        receiverSettingsToggle = button("");
        receiverSettingsToggle.setOnClickListener(
                view -> showReceiverSettings(receiverSettingsPanel.getVisibility() != View.VISIBLE)
        );
        content.addView(receiverSettingsToggle);

        receiverSettingsPanel = new LinearLayout(this);
        receiverSettingsPanel.setOrientation(LinearLayout.VERTICAL);

        TextView submitGuide = text(
                "최초 연결 때만 HTTPS 수신 주소와 제출 코드를 저장합니다. 저장된 값은 "
                        + "앱 업데이트 후에도 유지되며 평소에는 전송 버튼만 누르면 됩니다.",
                13
        );
        receiverSettingsPanel.addView(submitGuide);

        receiverUrlInput = new EditText(this);
        receiverUrlInput.setHint("https://reports.example.com");
        receiverUrlInput.setSingleLine(true);
        receiverUrlInput.setInputType(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI
        );
        receiverUrlInput.setText(preferences.getString(RECEIVER_URL_KEY, ""));
        receiverSettingsPanel.addView(receiverUrlInput, matchWidthWrapHeight());

        receiverTokenInput = new EditText(this);
        receiverTokenInput.setHint("제출 전용 토큰 (32자 이상)");
        receiverTokenInput.setSingleLine(true);
        receiverTokenInput.setInputType(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
        );
        receiverTokenInput.setText(preferences.getString(RECEIVER_TOKEN_KEY, ""));
        receiverSettingsPanel.addView(receiverTokenInput, matchWidthWrapHeight());

        Button saveReceiver = button("LTE 제출 설정 저장");
        saveReceiver.setOnClickListener(view -> saveReceiverSettings());
        receiverSettingsPanel.addView(saveReceiver);
        content.addView(receiverSettingsPanel);
        showReceiverSettings(!receiverConfigured);

        Button submitReport = button("LTE로 현재 저장소에 결과 제출");
        submitReport.setOnClickListener(view -> submitReportOverLte(submitReport));
        content.addView(submitReport);

        TextView storageGuide = text(
                "체크 결과는 APK 내부에도 자동 저장됩니다. LTE 제출이 안 될 때만 USB/ADB "
                        + "수집을 보조 경로로 사용합니다.",
                13
        );
        storageGuide.setPadding(0, dp(6), 0, dp(6));
        content.addView(storageGuide);

        Button resetReport = button("체크와 기록 초기화");
        resetReport.setOnClickListener(view -> confirmReset());
        content.addView(resetReport);

        content.addView(sectionTitle("제출될 보고서 미리보기"));
        reportView = text("", 13);
        reportView.setTextIsSelectable(true);
        reportView.setPadding(0, 0, 0, dp(24));
        content.addView(reportView);
        refreshReport();

        TextView copyright = text(
                "Copyright (c) 2026 Kanana Garden contributors. 사용 조건은 저장소 LICENSE를 따릅니다.",
                12
        );
        content.addView(copyright);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content, matchWidthWrapHeight());
        return scroll;
    }

    private void validateAndExecute() {
        final VehicleAction command;
        try {
            command = VehicleAction.parse(actionInput.getText().toString());
        } catch (RuntimeException error) {
            showResult("검증 거부: " + error.getMessage(), true);
            recordExecution("validation", false, error.getMessage());
            return;
        }

        if (command.requiresConfirmation) {
            new AlertDialog.Builder(this)
                    .setTitle("실행 확인")
                    .setMessage(command.action + " 명령을 실행할까요?")
                    .setNegativeButton("취소", null)
                    .setPositiveButton("실행", (dialog, which) -> execute(command))
                    .show();
        } else {
            execute(command);
        }
    }

    private void execute(VehicleAction command) {
        try {
            String result = executor.execute(command);
            showResult("성공: " + result, false);
            recordExecution(command.action, true, result);
            Log.i(LOG_TAG, "action=" + command.action + " result=success");
        } catch (RuntimeException error) {
            recordDetailedError("action_" + command.action, error);
            showResult("실행 실패: " + error.getMessage(), true);
            recordExecution(command.action, false, error.getMessage());
            Log.w(LOG_TAG, "action=" + command.action + " result=failure", error);
        }
    }

    private void loadIntentPayload(Intent intent) {
        if (intent == null || actionInput == null || !intent.hasExtra(ACTION_JSON_EXTRA)) {
            return;
        }
        String payload = intent.getStringExtra(ACTION_JSON_EXTRA);
        if (payload != null) {
            actionInput.setText(payload);
            showResult("ADB/Intent 입력을 불러왔습니다. 내용 확인 후 실행 버튼을 누르세요.", false);
        }
    }

    private void addPresetButton(LinearLayout parent, String label, String payload) {
        Button preset = button(label + " JSON 불러오기");
        preset.setOnClickListener(view -> {
            actionInput.setText(payload);
            showResult("빠른 입력을 불러왔습니다. 실행 버튼을 누르세요.", false);
        });
        parent.addView(preset);
    }

    private void addChecklistItem(LinearLayout parent, String id, String label) {
        LinearLayout block = new LinearLayout(this);
        block.setOrientation(LinearLayout.VERTICAL);
        block.setPadding(0, dp(4), 0, dp(4));
        block.addView(text(label, 15));

        LinearLayout choices = new LinearLayout(this);
        choices.setOrientation(LinearLayout.HORIZONTAL);
        CheckBox pass = new CheckBox(this);
        pass.setText("PASS");
        CheckBox fail = new CheckBox(this);
        fail.setText("FAIL");
        choices.addView(pass);
        choices.addView(fail);
        block.addView(choices);
        parent.addView(block);

        TestSelection selection = new TestSelection(id, label, pass, fail);
        selections.put(id, selection);
        setSelection(selection, preferences.getString("result_" + id, ""), false);

        pass.setOnCheckedChangeListener((button, checked) -> {
            if (selection.updating) {
                return;
            }
            if (checked) {
                setSelection(selection, "PASS", true);
            } else if (!fail.isChecked()) {
                setSelection(selection, "", true);
            }
        });
        fail.setOnCheckedChangeListener((button, checked) -> {
            if (selection.updating) {
                return;
            }
            if (checked) {
                setSelection(selection, "FAIL", true);
            } else if (!pass.isChecked()) {
                setSelection(selection, "", true);
            }
        });
    }

    private void setSelection(TestSelection selection, String status, boolean save) {
        String normalized = "PASS".equals(status) || "FAIL".equals(status) ? status : "";
        selection.updating = true;
        selection.pass.setChecked("PASS".equals(normalized));
        selection.fail.setChecked("FAIL".equals(normalized));
        selection.updating = false;
        if (save) {
            preferences.edit().putString("result_" + selection.id, normalized).apply();
        }
        refreshReport();
    }

    private void recordExecution(String action, boolean success, String message) {
        String timestamp = new SimpleDateFormat("HH:mm:ss", Locale.KOREA).format(new Date());
        String cleaned = cleanReportText(message);
        String entry = timestamp + " " + action + " API " + (success ? "SUCCESS" : "FAIL")
                + " - " + cleaned + "\n";
        executionHistory = executionHistory + entry;
        if (executionHistory.length() > 6000) {
            executionHistory = executionHistory.substring(executionHistory.length() - 6000);
        }
        preferences.edit().putString(HISTORY_KEY, executionHistory).apply();
        refreshReport();
    }

    private void copyReport() {
        ClipboardManager clipboard = getSystemService(ClipboardManager.class);
        if (clipboard == null) {
            showResult("클립보드를 사용할 수 없습니다.", true);
            return;
        }
        clipboard.setPrimaryClip(ClipData.newPlainText("Kanana Garden 테스트 결과", buildReport()));
        showResult("결과 보고서를 클립보드에 복사했습니다.", false);
    }

    private void shareReport() {
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType("text/plain");
        send.putExtra(Intent.EXTRA_SUBJECT, "Kanana Garden UIS7862S 0단계 테스트 결과");
        send.putExtra(Intent.EXTRA_TEXT, buildReport());
        try {
            startActivity(Intent.createChooser(send, "테스트 결과 제출 / 공유"));
            showResult("공유할 앱을 직접 선택하세요. 자동 전송되지는 않습니다.", false);
        } catch (RuntimeException error) {
            recordDetailedError("report_share", error);
            showResult("결과를 공유할 앱을 열 수 없습니다: " + error.getMessage(), true);
        }
    }

    private void saveReceiverSettings() {
        try {
            String url = ReportUploader.validateBaseUrl(receiverUrlInput.getText().toString());
            String token = ReportUploader.validateToken(receiverTokenInput.getText().toString());
            preferences.edit()
                    .putString(RECEIVER_URL_KEY, url)
                    .putString(RECEIVER_TOKEN_KEY, token)
                    .apply();
            receiverUrlInput.setText(url);
            showReceiverSettings(false);
            showResult("LTE 제출 설정을 이 앱의 비공개 저장소에 저장했습니다.", false);
        } catch (RuntimeException error) {
            showResult("제출 설정 거부: " + error.getMessage(), true);
        }
    }

    private boolean hasSavedReceiverSettings() {
        try {
            ReportUploader.validateBaseUrl(preferences.getString(RECEIVER_URL_KEY, ""));
            ReportUploader.validateToken(preferences.getString(RECEIVER_TOKEN_KEY, ""));
            return true;
        } catch (RuntimeException error) {
            return false;
        }
    }

    private void showReceiverSettings(boolean show) {
        if (receiverSettingsPanel == null || receiverSettingsStatusView == null
                || receiverSettingsToggle == null) {
            return;
        }
        receiverSettingsPanel.setVisibility(show ? View.VISIBLE : View.GONE);
        boolean configured = hasSavedReceiverSettings();
        receiverSettingsStatusView.setText(
                configured
                        ? "LTE 전송 준비됨 · 앱 업데이트 뒤에도 연결 설정이 유지됩니다."
                        : "LTE 전송을 사용하려면 최초 한 번만 연결 설정을 저장하세요."
        );
        receiverSettingsToggle.setText(show ? "연결 설정 닫기" : "연결 설정 변경");
    }

    private void submitReportOverLte(Button submitButton) {
        final String url;
        final String token;
        try {
            url = ReportUploader.validateBaseUrl(receiverUrlInput.getText().toString());
            token = ReportUploader.validateToken(receiverTokenInput.getText().toString());
        } catch (RuntimeException error) {
            showResult("제출 설정 거부: " + error.getMessage(), true);
            return;
        }
        preferences.edit()
                .putString(RECEIVER_URL_KEY, url)
                .putString(RECEIVER_TOKEN_KEY, token)
                .apply();
        String report = buildReport();
        persistInternalReport(report);
        submitButton.setEnabled(false);
        showResult("LTE로 보고서를 제출하는 중입니다...", false);

        new Thread(() -> {
            try {
                String response = ReportUploader.submit(
                        url,
                        token,
                        report,
                        BuildConfig.VERSION_NAME
                );
                runOnUiThread(() -> {
                    submitButton.setEnabled(true);
                    showResult("제출 성공: " + response, false);
                });
            } catch (RuntimeException | IOException error) {
                runOnUiThread(() -> {
                    recordDetailedError("report_submit", error);
                    submitButton.setEnabled(true);
                    showResult("LTE 제출 실패: " + error.getMessage(), true);
                });
            }
        }, "kanana-report-upload").start();
    }

    private void checkForAppUpdate(Button updateButton) {
        updateButton.setEnabled(false);
        showUpdateStatus("GitHub 릴리스에서 업데이트를 확인하는 중입니다...", false);
        new Thread(() -> {
            try {
                UpdateManager.UpdateInfo update = UpdateManager.findAvailableUpdate();
                runOnUiThread(() -> {
                    updateButton.setEnabled(true);
                    if (update == null) {
                        showUpdateStatus("현재 설치본이 최신입니다: " + BuildConfig.VERSION_NAME, false);
                        return;
                    }
                    showUpdateDownloadConfirmation(update, updateButton);
                });
            } catch (IOException | RuntimeException error) {
                runOnUiThread(() -> {
                    recordDetailedError("update_check", error);
                    updateButton.setEnabled(true);
                    showUpdateStatus("업데이트 확인 실패: " + error.getMessage(), true);
                });
            }
        }, "kanana-update-check").start();
    }

    private void showUpdateDownloadConfirmation(
            UpdateManager.UpdateInfo update,
            Button updateButton
    ) {
        showUpdateStatus("새 버전 발견: " + update.versionName, false);
        new AlertDialog.Builder(this)
                .setTitle("앱 업데이트 " + update.versionName)
                .setMessage("LTE 데이터로 APK를 다운로드하고 검증할까요? 설치는 Android 확인 화면에서 직접 승인합니다.")
                .setNegativeButton("취소", null)
                .setPositiveButton("다운로드", (dialog, which) -> downloadAppUpdate(update, updateButton))
                .show();
    }

    private void downloadAppUpdate(UpdateManager.UpdateInfo update, Button updateButton) {
        updateButton.setEnabled(false);
        showUpdateStatus("APK 다운로드 및 SHA-256·서명 검증 중입니다...", false);
        new Thread(() -> {
            try {
                File apk = UpdateManager.downloadAndVerify(this, update);
                runOnUiThread(() -> {
                    updateButton.setEnabled(true);
                    offerVerifiedUpdateInstall(update, apk);
                });
            } catch (IOException | RuntimeException error) {
                runOnUiThread(() -> {
                    recordDetailedError("update_download", error);
                    updateButton.setEnabled(true);
                    showUpdateStatus("업데이트 검증 실패: " + error.getMessage(), true);
                });
            }
        }, "kanana-update-download").start();
    }

    private void offerVerifiedUpdateInstall(UpdateManager.UpdateInfo update, File apk) {
        if (!UpdateManager.canRequestInstall(this)) {
            showUpdateStatus(
                    "APK 검증 완료. 이 앱의 '알 수 없는 앱 설치'를 허용한 뒤 업데이트 확인을 다시 누르세요.",
                    true
            );
            new AlertDialog.Builder(this)
                    .setTitle("설치 권한 필요")
                    .setMessage("UIS7862S 설정에서 이 앱의 APK 설치 요청을 허용해야 합니다.")
                    .setNegativeButton("나중에", null)
                    .setPositiveButton("설정 열기", (dialog, which) -> {
                        try {
                            UpdateManager.openUnknownSourcesSettings(this);
                        } catch (RuntimeException error) {
                            recordDetailedError("update_permission_settings", error);
                            showUpdateStatus("설치 권한 화면을 열 수 없습니다: " + error.getMessage(), true);
                        }
                    })
                    .show();
            return;
        }
        try {
            UpdateManager.launchInstaller(this, apk);
            showUpdateStatus(
                    update.versionName + " 설치 화면을 열었습니다. Android 화면에서 업데이트를 승인하세요.",
                    false
            );
        } catch (RuntimeException error) {
            recordDetailedError("update_installer", error);
            showUpdateStatus("APK 설치 화면을 열 수 없습니다: " + error.getMessage(), true);
        }
    }

    private void confirmReset() {
        new AlertDialog.Builder(this)
                .setTitle("테스트 기록 초기화")
                .setMessage("PASS/FAIL, 메모, API 실행 이력과 crash 진단을 모두 지울까요?")
                .setNegativeButton("취소", null)
                .setPositiveButton("초기화", (dialog, which) -> resetReport())
                .show();
    }

    private void resetReport() {
        SharedPreferences.Editor editor = preferences.edit();
        for (TestSelection selection : selections.values()) {
            editor.remove("result_" + selection.id);
            setSelection(selection, "", false);
        }
        editor.remove(NOTES_KEY);
        editor.remove(HISTORY_KEY);
        editor.apply();
        executionHistory = "";
        CrashDiagnostics.clearAll(this);
        pendingCrash = "";
        handledDiagnostics = "";
        notesInput.setText("");
        refreshReport();
        showResult("테스트 기록을 초기화했습니다.", false);
    }

    private void refreshReport() {
        if (reportView != null) {
            String report = buildReport();
            reportView.setText(report);
            persistInternalReport(report);
        }
    }

    private void persistInternalReport(String report) {
        try (OutputStreamWriter writer = new OutputStreamWriter(
                openFileOutput(REPORT_FILE_NAME, MODE_PRIVATE),
                StandardCharsets.UTF_8
        )) {
            writer.write(report);
        } catch (IOException error) {
            Log.e(LOG_TAG, "test report save failed", error);
            showResult("내부 보고서 저장 실패: " + error.getMessage(), true);
        }
    }

    private String buildReport() {
        StringBuilder report = new StringBuilder();
        report.append("Kanana Garden UIS7862S 0단계 테스트\n");
        report.append("앱 버전: ").append(BuildConfig.VERSION_NAME).append("\n");
        report.append(deviceSummary()).append("\n");
        report.append("작성 시각: ")
                .append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss Z", Locale.KOREA).format(new Date()))
                .append("\n\n사용자 확인 결과:\n");
        for (TestSelection selection : selections.values()) {
            report.append("- [")
                    .append(selection.status().isEmpty() ? "미실행" : selection.status())
                    .append("] ")
                    .append(selection.label)
                    .append("\n");
        }
        String notes = notesInput == null ? preferences.getString(NOTES_KEY, "")
                : notesInput.getText().toString();
        report.append("\n테스터 메모:\n")
                .append(notes.trim().isEmpty() ? "없음" : notes.trim())
                .append("\n\nAPI 실행 이력:\n")
                .append(executionHistory == null || executionHistory.trim().isEmpty()
                        ? "없음\n" : executionHistory)
                .append("\n이전 앱 비정상 종료 진단:\n")
                .append(pendingCrash == null || pendingCrash.trim().isEmpty()
                        ? "없음\n" : pendingCrash + "\n")
                .append("\n처리된 내부 오류 상세:\n")
                .append(handledDiagnostics == null || handledDiagnostics.trim().isEmpty()
                        ? "없음\n" : handledDiagnostics + "\n");
        return report.toString();
    }

    private void recordDetailedError(String category, Throwable error) {
        CrashDiagnostics.recordHandled(this, category, error);
        handledDiagnostics = CrashDiagnostics.readHandled(this);
        refreshReport();
    }

    private String deviceSummary() {
        return "제조사/모델: " + cleanReportText(Build.MANUFACTURER) + " / "
                + cleanReportText(Build.MODEL) + "\nAndroid: "
                + cleanReportText(Build.VERSION.RELEASE) + " (SDK " + Build.VERSION.SDK_INT + ")"
                + "\n보안 패치: " + cleanReportText(Build.VERSION.SECURITY_PATCH)
                + "\n브랜드/기기/제품: " + cleanReportText(Build.BRAND) + " / "
                + cleanReportText(Build.DEVICE) + " / " + cleanReportText(Build.PRODUCT)
                + "\n하드웨어/보드: " + cleanReportText(Build.HARDWARE) + " / "
                + cleanReportText(Build.BOARD)
                + "\nABI: " + cleanReportText(Arrays.toString(Build.SUPPORTED_ABIS))
                + "\n펌웨어 표시: " + cleanReportText(Build.DISPLAY)
                + "\nBuild fingerprint: " + cleanReportText(Build.FINGERPRINT);
    }

    private String cleanReportText(String value) {
        if (value == null) {
            return "unknown";
        }
        String cleaned = value.replace('\n', ' ').replace('\r', ' ').trim();
        if (cleaned.length() > 300) {
            return cleaned.substring(0, 300);
        }
        return cleaned.isEmpty() ? "unknown" : cleaned;
    }

    private void showResult(String message, boolean error) {
        if (resultView == null) {
            return;
        }
        resultView.setText(message == null ? "알 수 없는 오류" : message);
        resultView.setTextColor(error ? Color.rgb(183, 28, 28) : Color.rgb(27, 94, 32));
    }

    private void showUpdateStatus(String message, boolean error) {
        if (updateStatusView == null) {
            return;
        }
        updateStatusView.setText(message == null ? "알 수 없는 업데이트 오류" : message);
        updateStatusView.setTextColor(error ? Color.rgb(183, 28, 28) : Color.rgb(27, 94, 32));
    }

    private Button button(String label) {
        Button result = new Button(this);
        result.setText(label);
        result.setAllCaps(false);
        result.setLayoutParams(matchWidthWrapHeight());
        return result;
    }

    private TextView text(String value, int sizeSp) {
        TextView result = new TextView(this);
        result.setText(value);
        result.setTextSize(sizeSp);
        return result;
    }

    private TextView sectionTitle(String value) {
        TextView result = text(value, 17);
        result.setPadding(0, dp(16), 0, dp(6));
        return result;
    }

    private LinearLayout.LayoutParams matchWidthWrapHeight() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String json(String action, String slots, boolean confirmation) {
        return "{\"action\":\"" + action + "\",\"slots\":" + slots
                + ",\"confidence\":\"high\",\"requires_confirmation\":"
                + confirmation + "}";
    }

    private static final class TestSelection {
        final String id;
        final String label;
        final CheckBox pass;
        final CheckBox fail;
        boolean updating;

        TestSelection(String id, String label, CheckBox pass, CheckBox fail) {
            this.id = id;
            this.label = label;
            this.pass = pass;
            this.fail = fail;
        }

        String status() {
            if (pass.isChecked()) {
                return "PASS";
            }
            if (fail.isChecked()) {
                return "FAIL";
            }
            return "";
        }
    }
}
