package com.carriez.flutter_hbb;

import android.content.*;
import android.content.pm.*;
import android.os.*;
import android.provider.Settings;
import java.net.URL;
import javax.net.ssl.HttpsURLConnection;
import org.json.*;

final class FleetHost implements FleetRuntime.Host {
  private final Context context;

  FleetHost(Context context) {
    this.context = context.getApplicationContext();
  }

  private long trustedSeconds;
  private long trustedElapsed;

  public JSONObject proof(String method, String path, String body, long version) throws Exception {
    FleetPolicy.require(
        FleetNative.initialize(io.flutter.util.PathUtils.getDataDirectory(context)), "no_safety");
    String value = FleetNative.proof(method, path, body, version);
    FleetPolicy.require(value != null && !value.isEmpty(), "no_safety");
    return FleetPolicy.Strict.parse(value);
  }

  public boolean verifyRelease(byte[] raw, byte[] sig, byte[] key) {
    return FleetNative.verifyRelease(raw, sig, key);
  }

  public int sessionState() {
    return FleetNative.sessionState();
  }

  public boolean merchantPaused(Context c) {
    return MerchantRecovery.userPaused(c);
  }

  public boolean forceStopped(Context c) {
    try {
      PackageManager pm = c.getPackageManager();
      ApplicationInfo own = pm.getApplicationInfo(c.getPackageName(), 0),
          peer = pm.getApplicationInfo("com.steaddesk.agent", 0);
      return ((own.flags | peer.flags) & ApplicationInfo.FLAG_STOPPED) != 0
          || !"false".equals(MerchantRecovery.peerUserStopped());
    } catch (Exception unknown) {
      return true;
    }
  }

  public boolean healthy(Context c) {
    int sessions = sessionState();
    return MainService.Companion.getRunningInstance() != null
        && !merchantPaused(c)
        && (sessions == 0 || sessions == 2);
  }

  public long trustedNow(Context c) throws Exception {
    FleetPolicy.require(
        Settings.Global.getInt(c.getContentResolver(), Settings.Global.AUTO_TIME, 0) == 1,
        "clock_unknown");
    long elapsed = SystemClock.elapsedRealtime();
    if (trustedSeconds == 0 || elapsed - trustedElapsed > 60_000 || elapsed < trustedElapsed) {
      HttpsURLConnection server = connection(new URL(FleetBuild.OPS_ORIGIN + "/"));
      server.setConnectTimeout(3000);
      server.setReadTimeout(3000);
      server.setInstanceFollowRedirects(false);
      server.setUseCaches(false);
      long before = SystemClock.elapsedRealtime();
      try {
        server.getResponseCode();
        long date = server.getHeaderFieldDate("Date", 0);
        FleetPolicy.require(
            date > 0 && SystemClock.elapsedRealtime() - before < 5000, "clock_unknown");
        trustedSeconds = date / 1000;
        trustedElapsed = SystemClock.elapsedRealtime();
      } finally {
        server.disconnect();
      }
    }
    long network = trustedSeconds + (SystemClock.elapsedRealtime() - trustedElapsed) / 1000;
    FleetPolicy.require(
        Math.abs(System.currentTimeMillis() / 1000 - network) <= 30, "clock_unknown");
    return network;
  }

  public HttpsURLConnection connection(URL url) throws Exception {
    return (HttpsURLConnection) url.openConnection();
  }
}
