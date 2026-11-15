package com.carriez.flutter_hbb;

import android.content.*;
import android.content.pm.PackageInstaller;

/** Not exported; system PendingIntent is the only installer-result entry. */
public final class FleetReceiver extends BroadcastReceiver {
  @Override
  public void onReceive(Context context, Intent intent) {
    PendingResult pending = goAsync();
    Context app = context.getApplicationContext();
    FleetUpdater.WORK.execute(
        () -> {
          try {
            if ("com.steaddesk.remote.FLEET_RESULT".equals(intent.getAction())) {
              int id = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1);
              FleetUpdater.runtime(app)
                  .result(
                      id,
                      intent.getIntExtra(
                          PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE));
              if (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
                  == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                org.json.JSONObject t =
                    FleetUpdater.runtime(app).load().optJSONObject("transaction");
                Intent confirmation = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                if (t != null && t.getInt("session") == id && confirmation != null)
                  FleetUpdater.confirm(app, confirmation, id);
              }
            }
            FleetUpdater.start(app);
          } catch (Exception | LinkageError ignored) {
          } finally {
            pending.finish();
          }
        });
  }
}
