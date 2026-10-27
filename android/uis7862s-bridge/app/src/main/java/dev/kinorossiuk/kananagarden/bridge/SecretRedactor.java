package dev.kinorossiuk.kananagarden.bridge;

import java.util.regex.Pattern;

/** Removes common credential forms before diagnostics leave the process. */
final class SecretRedactor {
    private static final Pattern SECRET_ASSIGNMENT = Pattern.compile(
            "(?i)((?:token|authorization|password)\\s*[:=]\\s*)[^\\s,;]+"
    );
    private static final Pattern BEARER_VALUE = Pattern.compile("(?i)(bearer\\s+)[^\\s,;]+");

    private SecretRedactor() {
    }

    static String redact(String value) {
        String redacted = BEARER_VALUE.matcher(value).replaceAll("$1[REDACTED]");
        return SECRET_ASSIGNMENT.matcher(redacted).replaceAll("$1[REDACTED]");
    }
}
