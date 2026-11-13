package com.steaddesk.remote.spike;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.util.Log;

import com.carriez.flutter_hbb.BootReceiver;

public final class UpdateReceiver extends BroadcastReceiver {
    static final String RESULT = "com.steaddesk.remote.spike.INSTALL_RESULT";

    @Override public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction())) {
            Log.i("SDSPIKE", "MY_PACKAGE_REPLACED; entering merchant boot recovery");
            // Reuse the boot receiver in-process, with all of its existing permission checks.
            new BootReceiver().onReceive(context, new Intent(Intent.ACTION_BOOT_COMPLETED));
            return;
        }
        if (!RESULT.equals(intent.getAction()) || !intent.hasExtra(PackageInstaller.EXTRA_STATUS)) return;
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        int id = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1);
        String label = status == PackageInstaller.STATUS_SUCCESS ? "STATUS_SUCCESS"
                : status == PackageInstaller.STATUS_PENDING_USER_ACTION ? "STATUS_PENDING_USER_ACTION" : "FAILURE";
        Log.i("SDSPIKE", "session=" + id + " status=" + status + " " + label);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent prompt = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (prompt != null) {
                try {
                    context.startActivity(prompt.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                } catch (RuntimeException e) {
                    Log.w("SDSPIKE", "confirmation UI launch failed: " + e.getClass().getSimpleName());
                }
            }
        }
    }
}
