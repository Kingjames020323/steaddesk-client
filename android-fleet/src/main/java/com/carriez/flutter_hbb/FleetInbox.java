package com.carriez.flutter_hbb;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import java.util.Iterator;
import org.json.JSONObject;

/** Small receiver-only durable capture; network and installation never run under this lock. */
final class FleetInbox {
  private static SharedPreferences preferences(Context c) {
    return c.getSharedPreferences("fleet-callback-inbox", Context.MODE_PRIVATE);
  }

  static synchronized void capture(Context c, Intent intent) throws Exception {
    int session = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1);
    if (session < 0) return;
    JSONObject inbox = FleetPolicy.Strict.parse(preferences(c).getString("pending", "{}"));
    JSONObject event =
        new JSONObject()
            .put("session", session)
            .put(
                "status",
                intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE));
    Intent confirmation = intent.getParcelableExtra(Intent.EXTRA_INTENT);
    if (confirmation != null)
      event.put("confirmation", confirmation.toUri(Intent.URI_INTENT_SCHEME));
    if (inbox.length() >= 64 && !inbox.has(String.valueOf(session)))
      throw new IllegalStateException("callback inbox full");
    inbox.put(String.valueOf(session), event);
    if (!preferences(c).edit().putString("pending", FleetPolicy.canonical(inbox)).commit())
      throw new IllegalStateException("callback persistence failed");
  }

  static synchronized JSONObject snapshot(Context c) throws Exception {
    return FleetPolicy.Strict.parse(preferences(c).getString("pending", "{}"));
  }

  static synchronized void acknowledge(Context c, String key, JSONObject event) throws Exception {
    JSONObject inbox = snapshot(c);
    JSONObject current = inbox.optJSONObject(key);
    if (current != null && FleetPolicy.canonical(current).equals(FleetPolicy.canonical(event))) {
      inbox.remove(key);
      if (!preferences(c).edit().putString("pending", FleetPolicy.canonical(inbox)).commit())
        throw new IllegalStateException("callback persistence failed");
    }
  }

  static void drain(Context c) throws Exception {
    JSONObject inbox = snapshot(c);
    Iterator<String> keys = inbox.keys();
    while (keys.hasNext()) {
      String key = keys.next();
      JSONObject event = inbox.getJSONObject(key);
      int session = event.getInt("session"), status = event.getInt("status");
      FleetRuntime runtime = FleetUpdater.runtime(c);
      runtime.result(session, status);
      if (status == PackageInstaller.STATUS_PENDING_USER_ACTION && event.has("confirmation")) {
        JSONObject t = runtime.load().optJSONObject("transaction");
        if (t != null
            && t.getInt("session") == session
            && "pending_user_action".equals(t.optString("stage")))
          FleetUpdater.confirm(
              c,
              Intent.parseUri(event.getString("confirmation"), Intent.URI_INTENT_SCHEME),
              session);
      }
      acknowledge(c, key, event);
    }
  }

  private FleetInbox() {}
}
