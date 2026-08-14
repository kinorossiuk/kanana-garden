package dev.kinorossiuk.kananagarden.bridge;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

/** Strict, non-executable action data accepted by the bridge. */
final class VehicleAction {
    private static final int MAX_PAYLOAD_LENGTH = 4096;
    private static final int MAX_TEXT_LENGTH = 200;

    private static final Set<String> ACTIONS = setOf(
            "volume_up", "volume_down", "volume_set", "volume_mute", "volume_unmute",
            "navigation_start", "navigation_stop", "media_play", "media_pause",
            "media_next", "media_previous", "app_open", "unsupported"
    );
    private static final Set<String> CONFIDENCE_LEVELS = setOf("high", "medium", "low");
    private static final Set<String> APP_ALIASES = setOf("navigation", "music", "settings");
    private static final Set<String> TOP_LEVEL_FIELDS = setOf(
            "action", "slots", "confidence", "requires_confirmation"
    );
    private static final Set<String> NO_SLOT_ACTIONS = setOf(
            "volume_up", "volume_down", "volume_mute", "volume_unmute",
            "navigation_stop", "media_pause", "media_next", "media_previous"
    );

    final String action;
    final String confidence;
    final boolean requiresConfirmation;
    final Integer levelPercent;
    final String destination;
    final String query;
    final String appAlias;
    final String reason;

    private VehicleAction(
            String action,
            String confidence,
            boolean requiresConfirmation,
            Integer levelPercent,
            String destination,
            String query,
            String appAlias,
            String reason
    ) {
        this.action = action;
        this.confidence = confidence;
        this.requiresConfirmation = requiresConfirmation;
        this.levelPercent = levelPercent;
        this.destination = destination;
        this.query = query;
        this.appAlias = appAlias;
        this.reason = reason;
    }

    static VehicleAction parse(String content) {
        if (content == null || content.trim().isEmpty()) {
            throw invalid("action JSON이 비어 있습니다.");
        }
        if (content.length() > MAX_PAYLOAD_LENGTH) {
            throw invalid("action JSON은 4096자 이하여야 합니다.");
        }

        try {
            JSONObject value = new JSONObject(content);
            requireExactKeys(value, TOP_LEVEL_FIELDS, "최상위");

            String action = requiredString(value, "action");
            if (!ACTIONS.contains(action)) {
                throw invalid("허용하지 않는 action: " + action);
            }
            String confidence = requiredString(value, "confidence");
            if (!CONFIDENCE_LEVELS.contains(confidence)) {
                throw invalid("confidence는 high, medium, low 중 하나여야 합니다.");
            }
            Object confirmation = value.get("requires_confirmation");
            if (!(confirmation instanceof Boolean)) {
                throw invalid("requires_confirmation은 bool이어야 합니다.");
            }
            Object rawSlots = value.get("slots");
            if (!(rawSlots instanceof JSONObject)) {
                throw invalid("slots는 JSON 객체여야 합니다.");
            }
            JSONObject slots = (JSONObject) rawSlots;

            Integer level = null;
            String destination = null;
            String query = null;
            String appAlias = null;
            String reason = null;

            if (NO_SLOT_ACTIONS.contains(action)) {
                requireExactKeys(slots, Collections.emptySet(), action + " slots");
            } else if ("volume_set".equals(action)) {
                requireExactKeys(slots, setOf("level_percent"), "volume_set slots");
                Object rawLevel = slots.get("level_percent");
                if (!(rawLevel instanceof Integer) && !(rawLevel instanceof Long)) {
                    throw invalid("level_percent는 0 이상 100 이하 정수여야 합니다.");
                }
                long parsedLevel = ((Number) rawLevel).longValue();
                if (parsedLevel < 0 || parsedLevel > 100) {
                    throw invalid("level_percent는 0 이상 100 이하 정수여야 합니다.");
                }
                level = (int) parsedLevel;
            } else if ("navigation_start".equals(action)) {
                requireExactKeys(slots, setOf("destination"), "navigation_start slots");
                destination = shortText(slots, "destination");
            } else if ("media_play".equals(action)) {
                Set<String> keys = keys(slots);
                if (!keys.isEmpty() && !keys.equals(setOf("query"))) {
                    throw invalid("media_play slots에는 선택적으로 query만 사용할 수 있습니다.");
                }
                if (!keys.isEmpty()) {
                    query = shortText(slots, "query");
                }
            } else if ("app_open".equals(action)) {
                requireExactKeys(slots, setOf("app"), "app_open slots");
                appAlias = requiredString(slots, "app");
                if (!APP_ALIASES.contains(appAlias)) {
                    throw invalid("app은 navigation, music, settings 중 하나여야 합니다.");
                }
            } else {
                requireExactKeys(slots, setOf("reason"), "unsupported slots");
                reason = shortText(slots, "reason");
            }

            return new VehicleAction(
                    action,
                    confidence,
                    (Boolean) confirmation,
                    level,
                    destination,
                    query,
                    appAlias,
                    reason
            );
        } catch (JSONException error) {
            throw invalid("설명이나 코드 펜스가 없는 올바른 JSON 객체가 필요합니다.", error);
        }
    }

    private static String requiredString(JSONObject object, String name) throws JSONException {
        Object raw = object.get(name);
        if (!(raw instanceof String)) {
            throw invalid(name + "은 문자열이어야 합니다.");
        }
        String value = ((String) raw).trim();
        if (value.isEmpty()) {
            throw invalid(name + "은 비어 있을 수 없습니다.");
        }
        return value;
    }

    private static String shortText(JSONObject object, String name) throws JSONException {
        String value = requiredString(object, name);
        if (value.length() > MAX_TEXT_LENGTH) {
            throw invalid(name + "은 200자 이하여야 합니다.");
        }
        return value;
    }

    private static void requireExactKeys(JSONObject object, Set<String> expected, String name) {
        Set<String> actual = keys(object);
        if (!actual.equals(expected)) {
            Set<String> unknown = new HashSet<>(actual);
            unknown.removeAll(expected);
            Set<String> missing = new HashSet<>(expected);
            missing.removeAll(actual);
            throw invalid(name + " 필드 불일치 (허용 안 됨: " + unknown + ", 누락: " + missing + ")");
        }
    }

    private static Set<String> keys(JSONObject object) {
        Set<String> result = new HashSet<>();
        Iterator<String> iterator = object.keys();
        while (iterator.hasNext()) {
            result.add(iterator.next());
        }
        return result;
    }

    private static Set<String> setOf(String... values) {
        return Collections.unmodifiableSet(new HashSet<>(Arrays.asList(values)));
    }

    private static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException(message);
    }

    private static IllegalArgumentException invalid(String message, Throwable cause) {
        return new IllegalArgumentException(message, cause);
    }
}
