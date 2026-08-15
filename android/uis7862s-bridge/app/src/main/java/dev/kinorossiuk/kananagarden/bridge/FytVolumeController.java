package dev.kinorossiuk.kananagarden.bridge;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.IBinder;
import android.os.Parcel;
import android.os.RemoteException;

/**
 * Minimal client for the fixed FYT sound module exposed by UIS7862(S) firmware.
 *
 * <p>FYT keeps the MCU amplifier volume outside Android's STREAM_MUSIC value. The stock
 * {@code com.syu.ms} service exposes that value through a Binder module, so normal
 * AudioManager calls can report success without changing audible volume. This client contains
 * only the two Binder transactions needed to obtain sound module 4 and send its fixed volume
 * command 0. It never discovers or invokes an arbitrary package.</p>
 */
final class FytVolumeController implements ServiceConnection, AutoCloseable {
    private static final ComponentName TOOLKIT_SERVICE = new ComponentName(
            "com.syu.ms",
            "app.ToolkitService"
    );
    private static final String TOOLKIT_ACTION = "com.syu.ms.toolkit";
    private static final String TOOLKIT_DESCRIPTOR = "com.syu.ipc.IRemoteToolkit";
    private static final String MODULE_DESCRIPTOR = "com.syu.ipc.IRemoteModule";

    private static final int TRANSACTION_GET_REMOTE_MODULE = 1;
    private static final int TRANSACTION_MODULE_COMMAND = 1;
    private static final int SOUND_MODULE = 4;
    private static final int SOUND_VOLUME_COMMAND = 0;

    static final int VOLUME_UP = -1;
    static final int VOLUME_DOWN = -2;
    static final int VOLUME_MUTE = -3;
    static final int VOLUME_UNMUTE = -4;
    static final int MAX_VOLUME = 36;

    private final Context context;
    private volatile IBinder soundModule;
    private boolean bound;

    FytVolumeController(Context context) {
        this.context = context.getApplicationContext();
        connect();
    }

    private void connect() {
        Intent intent = new Intent(TOOLKIT_ACTION);
        intent.setComponent(TOOLKIT_SERVICE);
        try {
            bound = context.bindService(intent, this, Context.BIND_AUTO_CREATE);
        } catch (RuntimeException ignored) {
            bound = false;
        }
    }

    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        soundModule = getRemoteModule(service, SOUND_MODULE);
    }

    @Override
    public void onServiceDisconnected(ComponentName name) {
        soundModule = null;
    }

    @Override
    public void onBindingDied(ComponentName name) {
        soundModule = null;
        if (bound) {
            try {
                context.unbindService(this);
            } catch (RuntimeException ignored) {
                // Continue with a clean rebind below.
            }
            bound = false;
        }
        connect();
    }

    boolean adjust(int command) {
        if (command != VOLUME_UP && command != VOLUME_DOWN
                && command != VOLUME_MUTE && command != VOLUME_UNMUTE) {
            throw new IllegalArgumentException("허용하지 않는 FYT 볼륨 명령입니다.");
        }
        return sendVolumeCommand(command);
    }

    boolean setPercent(int levelPercent) {
        if (levelPercent < 0 || levelPercent > 100) {
            throw new IllegalArgumentException("볼륨은 0~100 범위여야 합니다.");
        }
        int target = Math.round(MAX_VOLUME * (levelPercent / 100.0f));
        return sendVolumeCommand(target);
    }

    private boolean sendVolumeCommand(int value) {
        IBinder module = soundModule;
        if (module == null || !module.isBinderAlive()) {
            return false;
        }
        Parcel data = Parcel.obtain();
        try {
            data.writeInterfaceToken(MODULE_DESCRIPTOR);
            data.writeInt(SOUND_VOLUME_COMMAND);
            data.writeIntArray(new int[]{value});
            data.writeFloatArray(null);
            data.writeStringArray(null);
            boolean accepted = module.transact(
                    TRANSACTION_MODULE_COMMAND,
                    data,
                    null,
                    IBinder.FLAG_ONEWAY
            );
            if (!accepted) {
                soundModule = null;
            }
            return accepted;
        } catch (RemoteException | RuntimeException error) {
            soundModule = null;
            return false;
        } finally {
            data.recycle();
        }
    }

    private static IBinder getRemoteModule(IBinder toolkit, int moduleCode) {
        Parcel data = Parcel.obtain();
        Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(TOOLKIT_DESCRIPTOR);
            data.writeInt(moduleCode);
            if (!toolkit.transact(TRANSACTION_GET_REMOTE_MODULE, data, reply, 0)) {
                return null;
            }
            reply.readException();
            return reply.readStrongBinder();
        } catch (RemoteException | RuntimeException error) {
            return null;
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    @Override
    public void close() {
        soundModule = null;
        if (!bound) {
            return;
        }
        try {
            context.unbindService(this);
        } catch (RuntimeException ignored) {
            // The vendor service may have died between the callback and Activity shutdown.
        }
        bound = false;
    }
}
