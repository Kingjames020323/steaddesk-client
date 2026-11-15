package com.carriez.flutter_hbb;

import android.content.*;
import android.content.pm.*;
import android.os.*;
import android.util.AtomicFile;
import android.util.Base64;
import com.android.apksig.ApkVerifier;
import java.io.*;
import java.net.URL;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.cert.X509Certificate;
import java.util.*;
import javax.net.ssl.HttpsURLConnection;
import org.json.*;

/** Single durable installation transaction. Only an authenticated *new* commit may install. */
public final class FleetRuntime {
  public interface Host {
    JSONObject proof(String method, String path, String canonicalBody, long keyVersion)
        throws Exception;

    boolean verifyRelease(byte[] raw, byte[] signature, byte[] publicKey) throws Exception;

    int sessionState(); // 0 idle, 2 active, everything else unknown

    boolean merchantPaused(Context context);

    boolean forceStopped(Context context);

    boolean healthy(Context context);

    long trustedNow(Context context) throws Exception;

    HttpsURLConnection connection(URL url) throws Exception;
  }

  final Context context;
  final Host host;
  final File directory;
  final AtomicFile disk;
  JSONObject state;
  JSONObject assignment;
  JSONObject manifest;
  static final String PREFIX = "/ops/v1/device/";

  public FleetRuntime(Context context, Host host) {
    this.context = context.getApplicationContext();
    this.host = host;
    directory = new File(this.context.getNoBackupFilesDir(), "fleet-update");
    if (!directory.isDirectory() && !directory.mkdirs())
      throw new IllegalStateException("private storage unavailable");
    disk = new AtomicFile(new File(directory, "state.json"));
  }

  public void tick() throws Exception {
    try (RandomAccessFile lock =
            new RandomAccessFile(new File(directory, "transaction.lock"), "rw");
        FileChannel channel = lock.getChannel()) {
      FileLock held;
      try {
        held = channel.tryLock();
      } catch (OverlappingFileLockException e) {
        return;
      }
      if (held == null) return;
      try {
        state = load();
        try {
          if (state.optJSONObject("transaction") != null) {
            recover();
            return;
          }
          flush();
          // A crash before durable reservation may leave a staged OS session; never create another.
          FleetPolicy.require(
              context.getPackageManager().getPackageInstaller().getMySessions().isEmpty(),
              "no_safety");
          assignment = request("GET", "update-assignment", new JSONObject(), false);
          if (assignment.isNull("assignment")) {
            log("assignment", "none");
            return;
          }
          prepare();
        } catch (Exception e) {
          String reason =
              e instanceof FleetPolicy.Rejected ? ((FleetPolicy.Rejected) e).reason : "no_safety";
          log("stopped", reason);
          if (assignment != null
              && !assignment.isNull("assignment")
              && state.optJSONObject("transaction") == null)
            report(
                assignment.getString("assignment"),
                reason.matches(
                        "artifact_.*|manifest_signature|signer_mismatch|package_mismatch|platform_mismatch")
                    ? "rejected"
                    : "deferred",
                reason,
                null);
          throw e;
        }
      } finally {
        held.release();
      }
    }
  }

  JSONObject load() throws Exception {
    if (!disk.getBaseFile().exists() && !new File(disk.getBaseFile() + ".bak").exists())
      return new JSONObject();
    return FleetPolicy.Strict.parse(new String(disk.readFully(), StandardCharsets.UTF_8));
  }

  void save() throws Exception {
    FileOutputStream out = null;
    try {
      out = disk.startWrite();
      out.write(FleetPolicy.canonical(state).getBytes(StandardCharsets.UTF_8));
      disk.finishWrite(out);
    } catch (Exception e) {
      if (out != null) disk.failWrite(out);
      throw e;
    }
  }

  long now() throws Exception {
    long t = host.trustedNow(context);
    FleetPolicy.require(t > 0, "clock_unknown");
    return t;
  }

  public static String hex(byte[] bytes) {
    StringBuilder s = new StringBuilder();
    for (byte b : bytes) s.append(String.format(Locale.ROOT, "%02x", b & 255));
    return s.toString();
  }

  static String digest(File f) throws Exception {
    MessageDigest d = MessageDigest.getInstance("SHA-256");
    try (InputStream in = new FileInputStream(f)) {
      byte[] b = new byte[65536];
      int n;
      while ((n = in.read(b)) != -1) d.update(b, 0, n);
    }
    return hex(d.digest());
  }

  static byte[] unbase(String v, int limit) {
    FleetPolicy.require(v.length() <= limit * 2, "manifest_signature");
    byte[] b = Base64.decode(v, Base64.NO_WRAP);
    FleetPolicy.require(
        b.length <= limit && Base64.encodeToString(b, Base64.NO_WRAP).equals(v),
        "manifest_signature");
    return b;
  }

  JSONObject request(String method, String route, JSONObject body, boolean discovery)
      throws Exception {
    long version = discovery ? 0 : state.optLong("key_version", 0);
    if (!discovery && version == 0) {
      JSONObject v = request("GET", "update-identity", new JSONObject(), true);
      version = FleetPolicy.integer(v, "key_version");
      FleetPolicy.require(version > 0, "no_safety");
      state.put("key_version", version);
      save();
    }
    String path = PREFIX + route, encoded = FleetPolicy.canonical(body);
    JSONObject headers = host.proof(method, path, encoded, version);
    URL url = new URL(FleetBuild.OPS_ORIGIN + path);
    FleetPolicy.require(
        "https".equals(url.getProtocol()) && url.getUserInfo() == null, "no_safety");
    HttpsURLConnection connection = host.connection(url);
    connection.setConnectTimeout(5000);
    connection.setReadTimeout(5000);
    connection.setInstanceFollowRedirects(false);
    connection.setUseCaches(false);
    connection.setRequestMethod(method);
    for (String h :
        new String[] {
          "X-Fleet-Device",
          "X-Fleet-Key-Version",
          "X-Fleet-Time",
          "X-Fleet-Nonce",
          "X-Fleet-Signature"
        }) connection.setRequestProperty(h, headers.getString(h));
    try {
      if (!method.equals("GET")) {
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json");
        try (OutputStream out = connection.getOutputStream()) {
          out.write(encoded.getBytes(StandardCharsets.UTF_8));
        }
      }
      int code = connection.getResponseCode();
      if (code == 403) {
        state.remove("key_version");
        save();
      }
      FleetPolicy.require(code == 200, "no_safety");
      byte[] bytes = bounded(connection.getInputStream(), 131072);
      return FleetPolicy.Strict.parse(new String(bytes, StandardCharsets.UTF_8));
    } finally {
      connection.disconnect();
    }
  }

  static byte[] bounded(InputStream input, int maximum) throws Exception {
    try (InputStream in = input;
        ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] b = new byte[8192];
      int n;
      while ((n = in.read(b)) != -1) {
        FleetPolicy.require(out.size() + n <= maximum, "artifact_size");
        out.write(b, 0, n);
      }
      return out.toByteArray();
    }
  }

  void prepare() throws Exception {
    long at = now();
    FleetPolicy.require(FleetPolicy.integer(assignment, "expires_at") > at, "no_safety");
    String key = assignment.getString("key_id");
    FleetPolicy.require(
        key.equals(FleetBuild.KEY_ID)
            && at >= FleetBuild.KEY_VALID_FROM
            && at < FleetBuild.KEY_VALID_UNTIL,
        "manifest_signature");
    byte[] raw = unbase(assignment.getString("manifest"), 32768),
        sig = unbase(assignment.getString("signature"), 64),
        pub = unbase(FleetBuild.PUBLIC_KEY, 32);
    FleetPolicy.require(
        sig.length == 64 && pub.length == 32 && host.verifyRelease(raw, sig, pub),
        "manifest_signature");
    manifest = FleetPolicy.manifest(raw, key, at);
    FleetPolicy.require(
        manifest.getLong("issued_at") >= FleetBuild.KEY_VALID_FROM
            && manifest.getLong("expires_at") <= FleetBuild.KEY_VALID_UNTIL,
        "manifest_signature");
    FleetPolicy.require(
        FleetPolicy.integer(assignment, "ring") == manifest.getLong("ring"), "manifest_signature");
    FleetPolicy.require(
        manifest.getLong("sequence") > state.optLong("highest_sequence", 0), "low_sequence");
    FleetPolicy.require(manifest.getLong("min_os") <= Build.VERSION.SDK_INT, "platform_mismatch");
    String architecture = manifest.getString("architecture");
    FleetPolicy.require(
        architecture.equals("universal")
            || Arrays.asList(Build.SUPPORTED_ABIS).contains(architecture),
        "platform_mismatch");
    FleetPolicy.require(
        installed().getLongVersionCode() < manifest.getLong("versionCode"), "same_version");
    String day = FleetPolicy.businessDay(assignment.getJSONObject("window"), at);
    FleetPolicy.gates(
        host.merchantPaused(context),
        host.forceStopped(context),
        host.sessionState(),
        at,
        day,
        state);
    log("manifest", "verified");
    File apk = download();
    verifyApk(apk);
    log("artifact", "verified");
    // Unproven firmware remains an interactive, explicitly accepted offer. No silent fallback.
    boolean silent =
        Build.VERSION.SDK_INT >= 31
            && !FleetBuild.SILENT_PROFILE.isEmpty()
            && FleetBuild.SILENT_PROFILE.equals(
                hex(
                    MessageDigest.getInstance("SHA-256")
                        .digest(Build.FINGERPRINT.getBytes(StandardCharsets.UTF_8))))
            && FleetBuild.SILENT_PROFILE.equals(assignment.optString("silent_profile", ""));
    boolean accepted =
        assignment.getString("assignment").equals(state.optString("accepted_assignment", ""));
    if (!silent && !accepted) {
      String aid = assignment.getString("assignment");
      if (!aid.equals(state.optString("offer_assignment", ""))) {
        state.put("offer_assignment", aid).put("offer_expires", assignment.getLong("expires_at"));
        save();
        FleetUpdater.offer(context);
        report(aid, "offer_shown", null, null);
      }
      log("offer", "manual_required");
      return;
    }
    install(apk, day, architecture, !silent, accepted);
  }

  PackageInfo installed() throws Exception {
    return context
        .getPackageManager()
        .getPackageInfo(context.getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
  }

  File download() throws Exception {
    URL url = new URL(FleetBuild.ARTIFACT_ORIGIN + "/" + manifest.getString("artifact_path"));
    FleetPolicy.require(
        url.getProtocol().equals("https") && url.getUserInfo() == null, "artifact_hash");
    File apk = new File(directory, "candidate.apk");
    HttpsURLConnection connection = host.connection(url);
    connection.setConnectTimeout(5000);
    connection.setReadTimeout(15000);
    connection.setInstanceFollowRedirects(false);
    connection.setUseCaches(false);
    try {
      FleetPolicy.require(connection.getResponseCode() == 200, "artifact_hash");
      long size = manifest.getLong("size_bytes"), count = 0;
      try (InputStream in = connection.getInputStream();
          FileOutputStream out = new FileOutputStream(apk)) {
        byte[] b = new byte[65536];
        int n;
        while ((n = in.read(b)) != -1) {
          count += n;
          FleetPolicy.require(count <= size, "artifact_size");
          out.write(b, 0, n);
        }
        out.getFD().sync();
      }
      FleetPolicy.require(count == size, "artifact_size");
      FleetPolicy.require(digest(apk).equals(manifest.getString("sha256")), "artifact_hash");
    } catch (Exception e) {
      apk.delete();
      throw e;
    } finally {
      connection.disconnect();
    }
    return apk;
  }

  void verifyApk(File apk) throws Exception {
    ApkVerifier.Result result =
        new ApkVerifier.Builder(apk)
            .setMinCheckedPlatformVersion(Build.VERSION.SDK_INT)
            .build()
            .verify();
    FleetPolicy.require(
        result.isVerified() && result.getSignerCertificates().size() == 1, "artifact_signature");
    X509Certificate signer = result.getSignerCertificates().get(0);
    String expected = manifest.getString("signer_cert_sha256");
    FleetPolicy.require(
        expected.equals(hex(MessageDigest.getInstance("SHA-256").digest(signer.getEncoded()))),
        "signer_mismatch");
    PackageInfo current = installed();
    FleetPolicy.require(
        current.signingInfo != null
            && !current.signingInfo.hasMultipleSigners()
            && current.signingInfo.getApkContentsSigners().length == 1,
        "signer_mismatch");
    FleetPolicy.require(
        expected.equals(
            hex(
                MessageDigest.getInstance("SHA-256")
                    .digest(current.signingInfo.getApkContentsSigners()[0].toByteArray()))),
        "signer_mismatch");
    PackageInfo archive =
        context
            .getPackageManager()
            .getPackageArchiveInfo(apk.getAbsolutePath(), PackageManager.GET_SIGNING_CERTIFICATES);
    FleetPolicy.require(
        archive != null
            && context.getPackageName().equals(archive.packageName)
            && manifest.getString("package").equals(archive.packageName),
        "package_mismatch");
    FleetPolicy.require(
        archive.applicationInfo != null
            && archive.applicationInfo.minSdkVersion <= Build.VERSION.SDK_INT,
        "platform_mismatch");
    FleetPolicy.require(
        archive.getLongVersionCode() == manifest.getLong("versionCode")
            && archive.getLongVersionCode() > current.getLongVersionCode(),
        "same_version");
  }

  void install(File apk, String day, String architecture, boolean interactive, boolean accepted)
      throws Exception {
    android.content.pm.PackageInstaller installer =
        context.getPackageManager().getPackageInstaller();
    android.content.pm.PackageInstaller.SessionParams params =
        new android.content.pm.PackageInstaller.SessionParams(
            android.content.pm.PackageInstaller.SessionParams.MODE_FULL_INSTALL);
    params.setAppPackageName(context.getPackageName());
    params.setSize(apk.length());
    if (Build.VERSION.SDK_INT >= 31)
      params.setRequireUserAction(
          interactive
              ? android.content.pm.PackageInstaller.SessionParams.USER_ACTION_REQUIRED
              : android.content.pm.PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
    int id = installer.createSession(params);
    boolean reserved = false;
    try (android.content.pm.PackageInstaller.Session session = installer.openSession(id)) {
      try (InputStream in = new FileInputStream(apk);
          OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
        byte[] bytes = new byte[65536];
        int n;
        while ((n = in.read(bytes)) != -1) out.write(bytes, 0, n);
        session.fsync(out);
      }
      verifyApk(apk);
      long at = now();
      String currentDay = FleetPolicy.businessDay(assignment.getJSONObject("window"), at);
      FleetPolicy.gates(
          host.merchantPaused(context),
          host.forceStopped(context),
          host.sessionState(),
          at,
          currentDay,
          state);
      FleetPolicy.require(
          day.equals(currentDay) && at < assignment.getLong("expires_at"), "outside_window");
      byte[] random = new byte[16];
      new SecureRandom().nextBytes(random);
      String nonce = hex(random);
      JSONObject safety =
          request(
              "POST",
              "update-safety",
              new JSONObject()
                  .put("nonce", nonce)
                  .put("purpose", "install")
                  .put("assignment", assignment.getString("assignment"))
                  .put("min_generation", state.optLong("generation", 0)),
              false);
      long generation = FleetPolicy.integer(safety, "generation"),
          issued = FleetPolicy.integer(safety, "issued_at"),
          expiry = FleetPolicy.integer(safety, "expires_at");
      long fresh = now();
      FleetPolicy.require(
          safety.get("enabled") == Boolean.TRUE
              && generation >= state.optLong("generation", 0)
              && nonce.equals(safety.getString("nonce"))
              && "install".equals(safety.getString("purpose"))
              && issued <= fresh
              && fresh < expiry
              && expiry - issued <= 15,
          "no_safety");
      state.put("generation", generation);
      save();
      JSONObject facts =
          new JSONObject()
              .put("installed", installed().getLongVersionCode())
              .put("platform", "android")
              .put("package", context.getPackageName())
              .put(
                  "architecture",
                  architecture.equals("universal") ? Build.SUPPORTED_ABIS[0] : architecture)
              .put("os", Build.VERSION.SDK_INT)
              .put("artifact_sha256", manifest.getString("sha256"))
              .put("signer_cert_sha256", manifest.getString("signer_cert_sha256"))
              .put("size_bytes", apk.length())
              .put("signature_verified", true)
              .put("local_window", true)
              .put("remote_session", false)
              .put("merchant_paused", false)
              .put("force_stopped", false)
              .put("highest_sequence", state.optLong("highest_sequence", 0))
              .put("interactive", interactive)
              .put("accepted", accepted)
              .put("profile", FleetBuild.SILENT_PROFILE);
      // Repeat volatile checks immediately before reserving the unique local transaction.
      FleetPolicy.gates(
          host.merchantPaused(context),
          host.forceStopped(context),
          host.sessionState(),
          now(),
          FleetPolicy.businessDay(assignment.getJSONObject("window"), now()),
          state);
      JSONObject transaction =
          new JSONObject()
              .put("assignment", assignment.getString("assignment"))
              .put("session", id)
              .put("stage", "committing")
              .put("version", manifest.getLong("versionCode"))
              .put("build", manifest.getString("display_version"))
              .put("sha256", manifest.getString("sha256"))
              .put("signer", manifest.getString("signer_cert_sha256"))
              .put("started", at)
              .put("sequence", manifest.getLong("sequence"));
      state.put("transaction", transaction).put("last_day", day).put("last_started", at);
      save();
      reserved = true;
      log("committing", "reserved");
      JSONObject authorization =
          request(
              "POST",
              "update-attempts",
              new JSONObject()
                  .put("assignment", assignment.getString("assignment"))
                  .put("permit", safety.getString("permit"))
                  .put("nonce", nonce)
                  .put("generation", generation)
                  .put("facts", facts),
              false);
      FleetPolicy.require(
          authorization.get("install_authorized") == Boolean.TRUE
              && authorization.getLong("generation") == generation,
          "no_safety");
      transaction.put("attempt", authorization.getString("attempt")).put("stage", "authorized");
      save();
      // Authorization is one use. Never submit again after process death or an ambiguous response.
      FleetPolicy.require(now() < expiry && now() < assignment.getLong("expires_at"), "no_safety");
      FleetPolicy.require(
          !host.merchantPaused(context) && !host.forceStopped(context) && host.sessionState() == 0,
          "j23");
      FleetPolicy.businessDay(assignment.getJSONObject("window"), now());
      Intent callback =
          new Intent(context, FleetReceiver.class)
              .setAction("com.steaddesk.remote.FLEET_RESULT")
              .setData(android.net.Uri.parse("steaddesk-fleet:" + id));
      int flags =
          android.app.PendingIntent.FLAG_UPDATE_CURRENT | android.app.PendingIntent.FLAG_MUTABLE;
      android.app.PendingIntent pending =
          android.app.PendingIntent.getBroadcast(context, id, callback, flags);
      transaction.put("stage", "submitted");
      save();
      session.commit(pending.getIntentSender());
      log("submitted", "os_pending");
    } finally {
      if (!reserved) installer.abandonSession(id);
    }
  }

  void recover() throws Exception {
    JSONObject t = state.getJSONObject("transaction");
    int id = t.getInt("session");
    // OS session lookup always precedes any reconciliation; recovery never commits an install.
    android.content.pm.PackageInstaller.SessionInfo info =
        context.getPackageManager().getPackageInstaller().getSessionInfo(id);
    log("recovery", info == null ? "session_absent" : "session_present");
    JSONObject lookup = request("GET", "update-assignment", new JSONObject(), false);
    JSONObject previous = lookup.optJSONObject("reconcile_only");
    boolean matching =
        previous != null && t.getString("assignment").equals(previous.optString("assignment"));
    if (matching && !t.has("attempt")) {
      t.put("attempt", previous.getString("attempt"));
      state.put("report_seq", Math.max(state.optLong("report_seq", 0), previous.optLong("seq", 0)));
      save();
    }
    if (previous != null
        && t.getString("assignment").equals(previous.optString("assignment"))
        && "healthy".equals(previous.optString("state"))) {
      FleetPolicy.require(installed().getLongVersionCode() == t.getLong("version"), "same_version");
      retireReports(t.getString("attempt"));
      log("health", "server_observation_complete");
      state.put("last_transaction", t);
      state.remove("transaction");
      save();
      new File(directory, "candidate.apk").delete();
      return;
    }
    if (previous != null
        && t.getString("assignment").equals(previous.optString("assignment"))
        && "failed".equals(previous.optString("state"))) {
      retireReports(t.getString("attempt"));
      t.put("stage", "failed");
      save();
      log("health", "frozen");
      if (info == null) {
        state.put("last_transaction", t);
        state.remove("transaction");
        save();
      }
      return;
    }
    if (previous != null
        && t.getString("assignment").equals(previous.optString("assignment"))
        && previous.has("deadline")) {
      t.put("deadline", previous.getLong("deadline"));
      save();
    }
    flush();
    if (!t.has("attempt")) {
      if (previous != null && t.getString("assignment").equals(previous.optString("assignment"))) {
        t.put("attempt", previous.getString("attempt"));
        state.put(
            "report_seq", Math.max(state.optLong("report_seq", 0), previous.optLong("seq", 0)));
        save();
      } else {
        log("recovery", "manual_required");
        return;
      }
    }
    long current = installed().getLongVersionCode();
    if (current == t.getLong("version")) {
      String actual = digest(new File(context.getApplicationInfo().sourceDir));
      PackageInfo identity = installed();
      boolean signer =
          identity.signingInfo != null
              && identity.signingInfo.getApkContentsSigners().length == 1
              && t.getString("signer")
                  .equals(
                      hex(
                          MessageDigest.getInstance("SHA-256")
                              .digest(
                                  identity.signingInfo.getApkContentsSigners()[0].toByteArray())));
      FleetPolicy.require(actual.equals(t.getString("sha256")) && signer, "signer_mismatch");
      state.put(
          "highest_sequence",
          Math.max(state.optLong("highest_sequence", 0), t.getLong("sequence")));
      t.put("stage", "observing");
      save();
      if (host.merchantPaused(context) || host.forceStopped(context)) {
        report(t.getString("attempt"), "paused", "merchant_pause", t);
        return;
      }
      if (host.healthy(context)) report(t.getString("attempt"), "observing", null, t);
      else log("health", "service_unverified");
      FleetUpdater.observe(context);
    } else if (t.optString("stage").equals("failed")) {
      log("recovery", "frozen");
    } else if (t.optString("stage").equals("pending_user_action")) {
      log("recovery", "manual_required");
    } else if (info == null) {
      report(t.getString("attempt"), "failed", "install_failed", t);
      t.put("stage", "failed");
      save();
    } else {
      log("recovery", "manual_required");
    }
  }

  public void respond(boolean accepted) throws Exception {
    try (RandomAccessFile file =
            new RandomAccessFile(new File(directory, "transaction.lock"), "rw");
        FileChannel channel = file.getChannel();
        FileLock lock = channel.lock()) {
      state = load();
      String id = state.optString("offer_assignment", "");
      if (id.isEmpty() || state.optJSONObject("transaction") != null) return;
      if (id.equals(state.optString("answered_assignment", ""))) {
        flush();
        return;
      }
      if (now() >= state.getLong("offer_expires")) {
        state.put("answered_assignment", id);
        report(id, "expired", "offer_expired", null);
        state.remove("offer_assignment");
        save();
        return;
      }
      state.put("answered_assignment", id);
      if (accepted) state.put("accepted_assignment", id);
      else state.remove("offer_assignment");
      report(id, accepted ? "accepted" : "declined", accepted ? null : "user_declined", null);
      save();
    }
  }

  public void result(int session, int status) throws Exception {
    // Callback carries no authority; the ordinary tick verifies OS/installed identity again.
    try (RandomAccessFile file =
            new RandomAccessFile(new File(directory, "transaction.lock"), "rw");
        FileChannel channel = file.getChannel();
        FileLock lock = channel.lock()) {
      state = load();
      JSONObject t = state.optJSONObject("transaction");
      if (t == null || t.getInt("session") != session) return;
      log(
          "installer",
          status == android.content.pm.PackageInstaller.STATUS_SUCCESS
              ? "os_success"
              : status == android.content.pm.PackageInstaller.STATUS_PENDING_USER_ACTION
                  ? "manual_required"
                  : "failed");
      if (status == android.content.pm.PackageInstaller.STATUS_PENDING_USER_ACTION) {
        String stage = t.optString("stage");
        if (stage.equals("pending_user_action")
            || stage.equals("observing")
            || stage.equals("failed")) {
          log("installer", "duplicate_or_stale");
          return;
        }
        t.put("stage", "pending_user_action");
        if (t.has("attempt")) report(t.getString("attempt"), "pending_user_action", null, t);
        else save();
      } else if (status != android.content.pm.PackageInstaller.STATUS_SUCCESS) {
        if (t.optString("stage").equals("failed")) {
          log("installer", "duplicate_or_stale");
          return;
        }
        t.put("stage", "failed");
        if (t.has("attempt")) report(t.getString("attempt"), "failed", "install_failed", t);
        else save();
      }
    }
  }

  void report(String subject, String status, String reason, JSONObject transaction)
      throws Exception {
    long observed = now();
    JSONObject report =
        new JSONObject()
            .put("id", subject)
            .put("seq", state.optLong("report_seq", 0) + 1)
            .put("state", status)
            .put("observed_at", observed);
    state.put("report_seq", report.getLong("seq"));
    if (reason != null) report.put("reason", reason);
    if (transaction != null)
      report.put("os_session", String.valueOf(transaction.getInt("session")));
    if (status.equals("observing"))
      report
          .put("heartbeat_at", observed)
          .put("build", transaction.getLong("version"))
          .put("artifact_sha256", transaction.getString("sha256"))
          .put("service_verified", true)
          .put("identity_verified", true);
    JSONArray pending = state.optJSONArray("reports");
    if (pending == null) {
      pending = new JSONArray();
      state.put("reports", pending);
    }
    FleetPolicy.require(pending.length() < 256, "no_safety");
    pending.put(report);
    save();
    log("report", status);
    flush();
  }

  void retireReports(String subject) throws Exception {
    JSONArray queue = state.optJSONArray("reports");
    if (queue == null) return;
    JSONArray keep = new JSONArray();
    for (int i = 0; i < queue.length(); i++) {
      JSONObject report = queue.getJSONObject(i);
      if (subject.equals(report.getString("id"))) {
        try (FileOutputStream out =
            new FileOutputStream(new File(directory, "terminal-reports.jsonl"), true)) {
          out.write((FleetPolicy.canonical(report) + "\n").getBytes(StandardCharsets.UTF_8));
          out.getFD().sync();
        }
      } else keep.put(report);
    }
    state.put("reports", keep);
    save();
  }

  void flush() throws Exception {
    JSONArray queue = state.optJSONArray("reports");
    while (queue != null && queue.length() > 0) {
      JSONObject r = queue.getJSONObject(0);
      request("POST", "update-reports", r, false);
      queue.remove(0);
      save();
    }
  }

  void log(String event, String reason) throws Exception {
    JSONObject line =
        new JSONObject()
            .put("time", System.currentTimeMillis() / 1000)
            .put("event", event)
            .put("reason", reason);
    JSONObject t = state == null ? null : state.optJSONObject("transaction");
    if (t != null)
      line.put("session", t.optInt("session"))
          .put("assignment", t.optString("assignment"))
          .put("target_version", t.optLong("version"))
          .put("sequence", t.optLong("sequence"));
    else if (assignment != null && !assignment.isNull("assignment"))
      line.put("assignment", assignment.optString("assignment"));
    try (FileOutputStream out = new FileOutputStream(new File(directory, "events.jsonl"), true)) {
      out.write((line.toString() + "\n").getBytes(StandardCharsets.UTF_8));
      out.getFD().sync();
    }
  }
}
