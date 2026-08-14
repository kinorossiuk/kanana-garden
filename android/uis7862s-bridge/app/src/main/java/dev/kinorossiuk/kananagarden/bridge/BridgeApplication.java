package dev.kinorossiuk.kananagarden.bridge;

import android.app.Application;

/** Installs crash persistence before the activity UI is created. */
public final class BridgeApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        CrashDiagnostics.install(this);
    }
}
