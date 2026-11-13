package com.steaddesk.remote.spike;

import android.app.PendingIntent;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Build;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.util.Base64;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public final class SelfUpdateProvider extends ContentProvider {
    private static final Uri APK = Uri.parse("content://com.steaddesk.remote.spike/apk");

    @Override public boolean onCreate() { return true; }

    private static void requireShell() {
        int uid = Binder.getCallingUid();
        if (uid != 2000 && uid != 0) throw new SecurityException("shell only");
    }

    private File apk() {
        return new File(getContext().getCacheDir(), "s1-candidate.apk");
    }

    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        requireShell();
        if (!APK.equals(uri) || !"w".equals(mode)) throw new FileNotFoundException("expected /apk for writing");
        return ParcelFileDescriptor.open(apk(), ParcelFileDescriptor.MODE_WRITE_ONLY
                | ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE);
    }

    @Override public Bundle call(String method, String arg, Bundle extras) {
        requireShell();
        if ("lab-key".equals(method)) {
            if (arg == null || !arg.matches("[A-Za-z0-9+/]{43}=") || Base64.decode(arg, Base64.NO_WRAP).length != 32)
                throw new IllegalArgumentException("expected base64 Ed25519 lab public key");
            File dir = getContext().getDir("flutter", Context.MODE_PRIVATE);
            android.util.AtomicFile file = new android.util.AtomicFile(new File(dir, "s1-lab.pub"));
            FileOutputStream out = null;
            try {
                out = file.startWrite();
                out.write(arg.getBytes(StandardCharsets.US_ASCII));
                file.finishWrite(out);
            } catch (IOException e) {
                file.failWrite(out);
                throw new IllegalStateException("lab key not saved", e);
            }
            Bundle reply = new Bundle();
            reply.putBoolean("lab_key_saved", true);
            return reply;
        }
        if (!"update".equals(method) || arg != null || extras != null && !extras.isEmpty())
            throw new IllegalArgumentException("expected update with staged APK");
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) throw new UnsupportedOperationException("requires Android 11+");

        // PackageInstaller must see the merchant's UID, including for installers-of-record checks.
        long identity = Binder.clearCallingIdentity();
        try {
            return commit(getContext(), apk());
        } catch (IOException | RuntimeException e) {
            Log.e("SDSPIKE", "pre-commit failure: " + e.getClass().getSimpleName());
            throw new IllegalStateException("could not submit staged APK", e);
        } finally {
            Binder.restoreCallingIdentity(identity);
        }
    }

    private static Bundle commit(Context context, File apk) throws IOException {
        PackageInfo candidate = context.getPackageManager().getPackageArchiveInfo(apk.getPath(), 0);
        if (candidate == null || !context.getPackageName().equals(candidate.packageName))
            throw new IllegalArgumentException("expected complete merchant APK");
        PackageInstaller installer = context.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(context.getPackageName());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
        }
        int id = installer.createSession(params);
        boolean submitted = false;
        try (PackageInstaller.Session session = installer.openSession(id)) {
            try (FileInputStream in = new FileInputStream(apk);
                 OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
                byte[] buffer = new byte[65536];
                int n;
                while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
                session.fsync(out);
            }
            Intent result = new Intent(context, UpdateReceiver.class).setAction(UpdateReceiver.RESULT);
            PendingIntent callback = PendingIntent.getBroadcast(context, id, result,
                    Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ? PendingIntent.FLAG_MUTABLE : 0);
            Log.i("SDSPIKE", "submit session=" + id + " candidate=" + candidate.versionName
                    + " canRequestInstalls=" + context.getPackageManager().canRequestPackageInstalls());
            session.commit(callback.getIntentSender());
            submitted = true;
            Bundle reply = new Bundle();
            reply.putInt("submitted_session", id);
            return reply;
        } finally {
            if (!submitted) installer.abandonSession(id);
        }
    }

    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { throw unsupported(); }
    @Override public String getType(Uri u) { throw unsupported(); }
    @Override public Uri insert(Uri u, ContentValues v) { throw unsupported(); }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { throw unsupported(); }
    @Override public int delete(Uri u, String s, String[] a) { throw unsupported(); }

    private static UnsupportedOperationException unsupported() {
        requireShell();
        return new UnsupportedOperationException();
    }
}
