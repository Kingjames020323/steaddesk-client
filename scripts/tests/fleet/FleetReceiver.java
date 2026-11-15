package com.carriez.flutter_hbb;

import android.content.*;
import android.content.pm.PackageInstaller;
import android.util.Log;

/** Test adapter replacing only production native/service wiring. */
public final class FleetReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        int session = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID,-1);
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS,-999);
        Log.i("UPD2FIXTURE","callback action="+intent.getAction()+" session="+session+" status="+status);
        FleetUpdater.run(context,session,status);
    }
}
