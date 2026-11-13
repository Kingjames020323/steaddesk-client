package com.steaddesk.remote.s6;

import android.app.ActivityManager;
import android.content.ComponentName;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;
import android.util.AtomicFile;
import android.util.Base64;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class SelfHealProvider extends ContentProvider {
    private static final String TAG = "S6SelfHeal";

    @Override public boolean onCreate() { return true; }

    @Override public Bundle call(String method, String arg, Bundle extras) {
        if (Binder.getCallingUid() != 2000) throw new SecurityException("adb shell only");
        Context context = getContext().getApplicationContext();
        Bundle result = new Bundle();
        if ("lab-key".equals(method)) {
            saveLabKey(context, arg);
            result.putBoolean("saved", true);
            return result;
        }
        if (arg != null || extras != null && !extras.isEmpty())
            throw new IllegalArgumentException("unexpected arguments");
        boolean kill = "kill-self".equals(method);
        if (!kill && !"launch".equals(method)) throw new IllegalArgumentException("unknown S6 method");
        long id = SystemClock.elapsedRealtime();
        // Return the shell's provider transaction before measuring process importance or calling AMS.
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            if (kill) {
                Log.i(TAG, "SIGKILL id=" + id + " package=" + context.getPackageName() + " pid=" + Process.myPid());
                Process.killProcess(Process.myPid());
            } else {
                launch(context, id);
            }
        }, kill ? 1000 : 15000);
        result.putLong("queued", id);
        return result;
    }

    private static void launch(Context context, long id) {
        ActivityManager.RunningAppProcessInfo info = new ActivityManager.RunningAppProcessInfo();
        ActivityManager.getMyMemoryState(info);
        Intent intent = new Intent().setComponent(new ComponentName(
                "com.steaddesk.agent", "com.meshcentral.agent.ScreenCaptureService"));
        // Correlate receipt without supplying any MediaProjection result or token.
        intent.putExtra("s6_id", id);
        Log.i(TAG, "launch id=" + id + " from=" + context.getPackageName() + " uid=" + Process.myUid()
                + " binderUid=" + Binder.getCallingUid() + " pid=" + Process.myPid()
                + " importance=" + info.importance + " to=" + intent.getComponent());
        try {
            ComponentName result = context.startForegroundService(intent);
            Log.i(TAG, "startForegroundService id=" + id + " returned=" + result);
        } catch (RuntimeException failure) {
            Log.e(TAG, "startForegroundService id=" + id + " failed", failure);
        }
    }

    private static void saveLabKey(Context context, String key) {
        if (key == null || !key.matches("[A-Za-z0-9+/]{43}=") || Base64.decode(key, Base64.NO_WRAP).length != 32)
            throw new IllegalArgumentException("expected base64 Ed25519 lab public key");
        AtomicFile file = new AtomicFile(new File(context.getDir("flutter", Context.MODE_PRIVATE), "s6-lab.pub"));
        FileOutputStream stream = null;
        try {
            stream = file.startWrite();
            stream.write(key.getBytes(StandardCharsets.US_ASCII));
            file.finishWrite(stream);
        } catch (IOException error) {
            file.failWrite(stream);
            throw new IllegalStateException("could not save lab public key", error);
        }
    }

    @Override public Cursor query(Uri uri, String[] fields, String selection, String[] args, String order) { throw new UnsupportedOperationException(); }
    @Override public String getType(Uri uri) { return null; }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
