package dev.kinorossiuk.kananagarden.bridge;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.media.AudioManager;
import android.media.session.MediaController;
import android.media.session.MediaSessionManager;
import android.media.session.PlaybackState;
import android.net.Uri;
import android.provider.Settings;

import java.util.List;

/** Executes only the fixed Android APIs represented by {@link VehicleAction}. */
final class ActionExecutor {
    private final Activity activity;
    private final FytVolumeController fytVolume;

    ActionExecutor(Activity activity) {
        this.activity = activity;
        this.fytVolume = new FytVolumeController(activity);
    }

    String execute(VehicleAction command) {
        switch (command.action) {
            case "volume_up":
                return adjustVolume(AudioManager.ADJUST_RAISE, "볼륨을 올렸습니다.");
            case "volume_down":
                return adjustVolume(AudioManager.ADJUST_LOWER, "볼륨을 내렸습니다.");
            case "volume_set":
                return setVolume(command.levelPercent);
            case "volume_mute":
                return adjustVolume(AudioManager.ADJUST_MUTE, "미디어 볼륨을 음소거했습니다.");
            case "volume_unmute":
                return adjustVolume(AudioManager.ADJUST_UNMUTE, "미디어 음소거를 해제했습니다.");
            case "navigation_start":
                return startNavigation(command.destination);
            case "navigation_stop":
                throw unavailable("Android 공통 길안내 종료 API가 없습니다. 내비 앱별 어댑터가 필요합니다.");
            case "media_play":
                if (command.query != null) {
                    throw unavailable("검색어 재생은 음악 앱별 어댑터가 필요합니다. 빈 slots로 재생을 시험하세요.");
                }
                return controlMedia("play");
            case "media_pause":
                return controlMedia("pause");
            case "media_next":
                return controlMedia("next");
            case "media_previous":
                return controlMedia("previous");
            case "app_open":
                return openAlias(command.appAlias);
            case "unsupported":
                throw unavailable("실행하지 않는 명령입니다: " + command.reason);
            default:
                throw unavailable("구현되지 않은 action입니다.");
        }
    }

    String openNotificationAccessSettings() {
        Intent intent = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS);
        startResolved(intent, "알림 접근 설정 화면을 찾을 수 없습니다.");
        return "Kanana Garden 미디어 제어의 알림 접근을 허용한 뒤 앱으로 돌아오세요.";
    }

    void close() {
        fytVolume.close();
    }

    private String adjustVolume(int direction, String result) {
        int fytCommand;
        if (direction == AudioManager.ADJUST_RAISE) {
            fytCommand = FytVolumeController.VOLUME_UP;
        } else if (direction == AudioManager.ADJUST_LOWER) {
            fytCommand = FytVolumeController.VOLUME_DOWN;
        } else if (direction == AudioManager.ADJUST_MUTE) {
            fytCommand = FytVolumeController.VOLUME_MUTE;
        } else if (direction == AudioManager.ADJUST_UNMUTE) {
            fytCommand = FytVolumeController.VOLUME_UNMUTE;
        } else {
            throw unavailable("지원하지 않는 볼륨 조정입니다.");
        }
        if (fytVolume.adjust(fytCommand)) {
            return result + " (FYT 메인 볼륨)";
        }
        AudioManager audio = audioManager();
        audio.adjustVolume(direction, AudioManager.FLAG_SHOW_UI);
        return result + " (Android 활성 볼륨)";
    }

    private String setVolume(Integer levelPercent) {
        if (levelPercent == null) {
            throw unavailable("볼륨 값이 없습니다.");
        }
        if (fytVolume.setPercent(levelPercent)) {
            return "FYT 메인 볼륨을 " + levelPercent + "%로 설정했습니다.";
        }
        AudioManager audio = audioManager();
        int maximum = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
        int target = Math.round(maximum * (levelPercent / 100.0f));
        audio.setStreamVolume(AudioManager.STREAM_MUSIC, target, AudioManager.FLAG_SHOW_UI);
        return "미디어 볼륨을 " + levelPercent + "%로 설정했습니다.";
    }

    private AudioManager audioManager() {
        AudioManager audio = activity.getSystemService(AudioManager.class);
        if (audio == null) {
            throw unavailable("AudioManager를 사용할 수 없습니다.");
        }
        return audio;
    }

    private String startNavigation(String destination) {
        String encodedDestination = Uri.encode(destination);
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=" + encodedDestination));
        startResolved(intent, "geo Intent를 처리할 지도/내비게이션 앱이 없습니다.");
        return "지도/내비게이션 앱에 목적지를 전달했습니다: " + destination;
    }

    private String openAlias(String alias) {
        Intent intent;
        if ("navigation".equals(alias)) {
            intent = Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MAPS);
        } else if ("music".equals(alias)) {
            intent = Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MUSIC);
        } else if ("settings".equals(alias)) {
            intent = new Intent(Settings.ACTION_SETTINGS);
        } else {
            throw unavailable("허용하지 않는 앱 alias입니다.");
        }
        startResolved(intent, alias + " alias를 처리할 앱이 없습니다.");
        return alias + " 앱을 열었습니다.";
    }

    private String controlMedia(String operation) {
        MediaSessionManager sessions = activity.getSystemService(MediaSessionManager.class);
        if (sessions == null) {
            throw unavailable("MediaSessionManager를 사용할 수 없습니다.");
        }

        ComponentName listener = new ComponentName(
                activity,
                BridgeNotificationListenerService.class
        );
        final List<MediaController> controllers;
        try {
            controllers = sessions.getActiveSessions(listener);
        } catch (SecurityException error) {
            throw unavailable("먼저 '알림 접근 허용'에서 Kanana Garden 미디어 제어를 켜세요.", error);
        }
        if (controllers.isEmpty()) {
            throw unavailable("활성 MediaSession이 없습니다. 음악 앱에서 곡을 한 번 재생한 뒤 다시 시험하세요.");
        }

        MediaController controller = preferredController(controllers);
        MediaController.TransportControls transport = controller.getTransportControls();
        switch (operation) {
            case "play":
                transport.play();
                break;
            case "pause":
                transport.pause();
                break;
            case "next":
                transport.skipToNext();
                break;
            case "previous":
                transport.skipToPrevious();
                break;
            default:
                throw unavailable("지원하지 않는 미디어 동작입니다.");
        }
        return controller.getPackageName() + " MediaSession에 " + operation + " 명령을 보냈습니다.";
    }

    private MediaController preferredController(List<MediaController> controllers) {
        for (MediaController controller : controllers) {
            PlaybackState state = controller.getPlaybackState();
            if (state != null && state.getState() == PlaybackState.STATE_PLAYING) {
                return controller;
            }
        }
        return controllers.get(0);
    }

    private void startResolved(Intent intent, String errorMessage) {
        if (intent.resolveActivity(activity.getPackageManager()) == null) {
            throw unavailable(errorMessage);
        }
        activity.startActivity(intent);
    }

    private static IllegalStateException unavailable(String message) {
        return new IllegalStateException(message);
    }

    private static IllegalStateException unavailable(String message, Throwable cause) {
        return new IllegalStateException(message, cause);
    }
}
