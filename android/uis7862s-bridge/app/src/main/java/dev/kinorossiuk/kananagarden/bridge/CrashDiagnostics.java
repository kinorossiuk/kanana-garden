package dev.kinorossiuk.kananagarden.bridge;

import android.content.Context;
import android.os.Process;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Pattern;

/** Stores bounded crash and handled-error diagnostics in the app-private files directory. */
final class CrashDiagnostics {
    private static final String CRASH_FILE_NAME = "last-crash.txt";
    private static final String HANDLED_FILE_NAME = "handled-errors.txt";
    private static final int MAX_CRASH_BYTES = 12 * 1024;
    private static final int MAX_HANDLED_BYTES = 16 * 1024;
    private static final Pattern SECRET_ASSIGNMENT = Pattern.compile(
            "(?i)((?:token|authorization|password)\\s*[:=]\\s*)[^\\s,;]+"
    );
    private static final Pattern BEARER_VALUE = Pattern.compile("(?i)(bearer\\s+)[^\\s,;]+");
    private static boolean installed;

    private CrashDiagnostics() {
    }

    static synchronized void install(Context context) {
        if (installed) {
            return;
        }
        Thread.UncaughtExceptionHandler delegate = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(new RecordingHandler(
                context.getApplicationContext(),
                delegate
        ));
        installed = true;
    }

    static String readPending(Context context) {
        return readPrivateFile(context, CRASH_FILE_NAME, MAX_CRASH_BYTES);
    }

    static String readHandled(Context context) {
        return readPrivateFile(context, HANDLED_FILE_NAME, MAX_HANDLED_BYTES);
    }

    static synchronized void recordHandled(Context context, String category, Throwable error) {
        String previous = readHandled(context);
        String entry = formatThrowable("처리된 내부 오류", category, Thread.currentThread(), error);
        String combined = previous.isEmpty() ? entry : previous + "\n---\n" + entry;
        writePrivateFile(
                context,
                HANDLED_FILE_NAME,
                keepUtf8Tail(combined, MAX_HANDLED_BYTES)
        );
    }

    static String summary(Throwable error) {
        if (error == null) {
            return "UnknownError";
        }
        String message = safeLine(error.getMessage());
        String result = error.getClass().getSimpleName();
        if (!"unknown".equals(message)) {
            result += ": " + message;
        }
        return keepUtf8Head(redactSecrets(result), 600);
    }

    static void clearAll(Context context) {
        context.deleteFile(CRASH_FILE_NAME);
        context.deleteFile(HANDLED_FILE_NAME);
    }

    private static void writePending(Context context, Thread thread, Throwable error) {
        String diagnostic = formatThrowable("미처리 예외", "process_crash", thread, error);
        writePrivateFile(
                context,
                CRASH_FILE_NAME,
                keepUtf8Head(diagnostic, MAX_CRASH_BYTES)
        );
    }

    private static String formatThrowable(
            String heading,
            String category,
            Thread thread,
            Throwable error
    ) {
        StringWriter traceBuffer = new StringWriter();
        try (PrintWriter traceWriter = new PrintWriter(traceBuffer)) {
            if (error == null) {
                traceWriter.println("UnknownError");
            } else {
                error.printStackTrace(traceWriter);
            }
        }
        String timestamp = new SimpleDateFormat(
                "yyyy-MM-dd HH:mm:ss Z",
                Locale.KOREA
        ).format(new Date());
        String threadName = thread == null ? "unknown" : safeLine(thread.getName());
        return redactSecrets(
                heading
                        + "\n발생 시각: " + timestamp
                        + "\n앱 버전: " + BuildConfig.VERSION_NAME
                        + "\n분류: " + safeLine(category)
                        + "\n스레드: " + threadName
                        + "\n예외:\n" + traceBuffer
        ).replace('\u0000', ' ');
    }

    private static String readPrivateFile(Context context, String name, int maxBytes) {
        File file = context.getFileStreamPath(name);
        if (!file.isFile()) {
            return "";
        }
        try (InputStream input = context.openFileInput(name);
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[2048];
            int total = 0;
            while (total < maxBytes) {
                int count = input.read(buffer, 0, Math.min(buffer.length, maxBytes - total));
                if (count < 0) {
                    break;
                }
                output.write(buffer, 0, count);
                total += count;
            }
            String result = new String(output.toByteArray(), StandardCharsets.UTF_8).trim();
            if (input.read() >= 0) {
                result += "\n[진단 기록이 제한 크기에서 잘렸습니다.]";
            }
            return result;
        } catch (IOException | RuntimeException error) {
            return "진단 기록 읽기 실패: " + error.getClass().getSimpleName();
        }
    }

    private static void writePrivateFile(Context context, String name, String value) {
        try (OutputStream output = context.openFileOutput(name, Context.MODE_PRIVATE)) {
            output.write(value.getBytes(StandardCharsets.UTF_8));
        } catch (IOException | RuntimeException ignored) {
            // Diagnostics must never trigger another app failure.
        }
    }

    private static String keepUtf8Head(String value, int maxBytes) {
        if (value.getBytes(StandardCharsets.UTF_8).length <= maxBytes) {
            return value;
        }
        String marker = "\n[진단 기록이 제한 크기에서 잘렸습니다.]\n";
        int markerBytes = marker.getBytes(StandardCharsets.UTF_8).length;
        StringBuilder result = new StringBuilder();
        int used = 0;
        for (int offset = 0; offset < value.length();) {
            int codePoint = value.codePointAt(offset);
            String character = new String(Character.toChars(codePoint));
            int bytes = character.getBytes(StandardCharsets.UTF_8).length;
            if (used + bytes + markerBytes > maxBytes) {
                break;
            }
            result.append(character);
            used += bytes;
            offset += Character.charCount(codePoint);
        }
        return result + marker;
    }

    private static String keepUtf8Tail(String value, int maxBytes) {
        if (value.getBytes(StandardCharsets.UTF_8).length <= maxBytes) {
            return value;
        }
        String marker = "[이전 진단 일부가 제한 크기로 제거됐습니다.]\n";
        int markerBytes = marker.getBytes(StandardCharsets.UTF_8).length;
        StringBuilder reversed = new StringBuilder();
        int used = 0;
        for (int offset = value.length(); offset > 0;) {
            int codePoint = value.codePointBefore(offset);
            String character = new String(Character.toChars(codePoint));
            int bytes = character.getBytes(StandardCharsets.UTF_8).length;
            if (used + bytes + markerBytes > maxBytes) {
                break;
            }
            reversed.appendCodePoint(codePoint);
            used += bytes;
            offset -= Character.charCount(codePoint);
        }
        return marker + reversed.reverse();
    }

    private static String redactSecrets(String value) {
        String redacted = SECRET_ASSIGNMENT.matcher(value).replaceAll("$1[REDACTED]");
        return BEARER_VALUE.matcher(redacted).replaceAll("$1[REDACTED]");
    }

    private static String safeLine(String value) {
        if (value == null) {
            return "unknown";
        }
        String cleaned = value.replace('\n', ' ').replace('\r', ' ').trim();
        return cleaned.isEmpty() ? "unknown" : cleaned;
    }

    private static final class RecordingHandler implements Thread.UncaughtExceptionHandler {
        private final Context context;
        private final Thread.UncaughtExceptionHandler delegate;
        private final AtomicBoolean handling = new AtomicBoolean(false);

        RecordingHandler(Context context, Thread.UncaughtExceptionHandler delegate) {
            this.context = context;
            this.delegate = delegate;
        }

        @Override
        public void uncaughtException(Thread thread, Throwable error) {
            if (handling.compareAndSet(false, true)) {
                try {
                    writePending(context, thread, error);
                } catch (Throwable ignored) {
                    // Never replace the original crash with a diagnostics failure.
                }
            }
            if (delegate != null) {
                delegate.uncaughtException(thread, error);
                return;
            }
            Process.killProcess(Process.myPid());
            System.exit(10);
        }
    }
}
