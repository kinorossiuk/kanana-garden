package dev.kinorossiuk.kananagarden.bridge;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Bench-only UI: incoming ADB data is displayed and never executed automatically. */
public final class MainActivity extends Activity {
    static final String ACTION_JSON_EXTRA = "action_json";
    private static final String LOG_TAG = "KananaBridge";

    private EditText actionInput;
    private TextView resultView;
    private ActionExecutor executor;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        executor = new ActionExecutor(this);
        setContentView(buildContent());
        loadIntentPayload(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadIntentPayload(intent);
    }

    private View buildContent() {
        int padding = dp(18);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);

        TextView title = text("Kanana Garden Bridge " + BuildConfig.VERSION_NAME, 22);
        content.addView(title);

        TextView warning = text(
                "0단계 벤치 테스트 전용 디버그 앱입니다. 주행 중 사용하지 마세요. "
                        + "ADB로 받은 JSON도 자동 실행하지 않으며 아래 실행 버튼을 직접 눌러야 합니다.",
                15
        );
        warning.setTextColor(Color.rgb(183, 28, 28));
        warning.setPadding(0, dp(10), 0, dp(14));
        content.addView(warning);

        content.addView(text("빠른 입력", 17));
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
                showResult(error.getMessage(), true);
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
            Log.i(LOG_TAG, "action=" + command.action + " result=success");
        } catch (RuntimeException error) {
            showResult("실행 실패: " + error.getMessage(), true);
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

    private void showResult(String message, boolean error) {
        if (resultView == null) {
            return;
        }
        resultView.setText(message == null ? "알 수 없는 오류" : message);
        resultView.setTextColor(error ? Color.rgb(183, 28, 28) : Color.rgb(27, 94, 32));
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
}
