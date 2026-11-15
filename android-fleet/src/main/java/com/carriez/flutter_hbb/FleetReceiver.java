package com.carriez.flutter_hbb;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Not exported. Capture only; JobScheduler owns all long work and network calls. */
public final class FleetReceiver extends BroadcastReceiver {
  @Override
  public void onReceive(Context context, Intent intent) {
    Context app = context.getApplicationContext();
    try {
      if ("com.steaddesk.remote.FLEET_RESULT".equals(intent.getAction()))
        FleetInbox.capture(app, intent);
    } catch (Exception unavailable) {
      // The persisted transaction is still authoritative. The scheduled job reconciles the OS
      // first.
    } finally {
      FleetUpdater.schedule(app);
    }
  }
}
