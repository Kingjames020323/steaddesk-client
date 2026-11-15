package com.carriez.flutter_hbb;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.StatFs;
import android.util.AtomicFile;
import com.android.apksig.ApkVerifier;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.json.*;

/** Verified private baseline evidence only. This archive never authorizes a rollback. */
public final class FleetArchive {
  static final long RESERVE = 16L * 1024 * 1024;

  static void requireSpace(long available, long bytes) {
    FleetPolicy.require(
        bytes > 0 && bytes <= Long.MAX_VALUE - RESERVE && available >= bytes + RESERVE,
        "artifact_size");
  }

  private static File directory(Context c) {
    File root = new File(c.getNoBackupFilesDir(), "fleet-update/baselines");
    if (!root.isDirectory() && !root.mkdirs()) throw new FleetPolicy.Rejected("artifact_size");
    return root;
  }

  private static PackageInfo installed(Context c) throws Exception {
    return c.getPackageManager()
        .getPackageInfo(c.getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
  }

  private static String signer(PackageInfo p) throws Exception {
    FleetPolicy.require(
        p.signingInfo != null
            && !p.signingInfo.hasMultipleSigners()
            && p.signingInfo.getApkContentsSigners().length == 1,
        "signer_mismatch");
    return FleetRuntime.hex(
        MessageDigest.getInstance("SHA-256")
            .digest(p.signingInfo.getApkContentsSigners()[0].toByteArray()));
  }

  private static List<File> sources(PackageInfo p) throws Exception {
    FleetPolicy.require(
        p.applicationInfo != null && p.applicationInfo.sourceDir != null, "package_mismatch");
    List<File> sources = new ArrayList<>();
    sources.add(new File(p.applicationInfo.sourceDir));
    if (p.applicationInfo.splitSourceDirs != null)
      for (String path : p.applicationInfo.splitSourceDirs) sources.add(new File(path));
    Set<String> distinct = new HashSet<>();
    for (File source : sources)
      FleetPolicy.require(
          source.isFile() && source.length() > 0 && distinct.add(source.getCanonicalPath()),
          "artifact_size");
    return sources;
  }

  private static void verify(File apk, String expected) throws Exception {
    ApkVerifier.Result result =
        new ApkVerifier.Builder(apk)
            .setMinCheckedPlatformVersion(Build.VERSION.SDK_INT)
            .build()
            .verify();
    FleetPolicy.require(
        result.isVerified() && result.getSignerCertificates().size() == 1, "artifact_signature");
    FleetPolicy.require(
        expected.equals(
            FleetRuntime.hex(
                MessageDigest.getInstance("SHA-256")
                    .digest(result.getSignerCertificates().get(0).getEncoded()))),
        "signer_mismatch");
  }

  private static String hash(File path) throws Exception {
    return FleetRuntime.digest(path);
  }

  private static void synced(File target, byte[] bytes) throws Exception {
    try (FileOutputStream out = new FileOutputStream(target)) {
      out.write(bytes);
      out.getFD().sync();
    }
  }

  /** Run before querying an offer, while no one-use safety permit or OS attempt exists. */
  public static synchronized void preserve(Context c) throws Exception {
    File root = directory(c);
    PackageInfo current = installed(c);
    File destination = new File(root, "version-" + current.getLongVersionCode());
    if (destination.exists()) {
      requireCurrent(c);
      return;
    }
    List<File> sources = sources(current);
    long total = 0;
    for (File source : sources) {
      FleetPolicy.require(Long.MAX_VALUE - total >= source.length(), "artifact_size");
      total += source.length();
    }
    requireSpace(new StatFs(root.getAbsolutePath()).getAvailableBytes(), total);
    File temporary = new File(root, "pending-" + UUID.randomUUID());
    FleetPolicy.require(temporary.mkdir(), "artifact_size");
    try {
      String expected = signer(current);
      JSONArray files = new JSONArray();
      for (int i = 0; i < sources.size(); i++) {
        File source = sources.get(i),
            copy = new File(temporary, i == 0 ? "base.apk" : "split-" + i + ".apk");
        try (InputStream in = new FileInputStream(source);
            FileOutputStream out = new FileOutputStream(copy)) {
          byte[] b = new byte[65536];
          int n;
          while ((n = in.read(b)) != -1) out.write(b, 0, n);
          out.getFD().sync();
        }
        String digest = hash(copy);
        FleetPolicy.require(
            copy.length() == source.length() && digest.equals(hash(source)), "artifact_hash");
        verify(copy, expected);
        files.put(
            new JSONObject()
                .put("file", copy.getName())
                .put("source", source.getCanonicalPath())
                .put("size", copy.length())
                .put("sha256", digest));
      }
      PackageInfo after = installed(c);
      FleetPolicy.require(
          after.getLongVersionCode() == current.getLongVersionCode()
              && expected.equals(signer(after))
              && sources(after).equals(sources),
          "package_mismatch");
      JSONObject identity =
          new JSONObject()
              .put("archive_schema", 1)
              .put("package", c.getPackageName())
              .put("version", current.getLongVersionCode())
              .put("signer_cert_sha256", expected)
              .put("files", files)
              .put("automatic_rollback", false)
              .put("data_schema", "undeclared-no-rollback");
      // Only a prior transaction with exactly this installed identity can supply a known manifest.
      File stateFile = new File(c.getNoBackupFilesDir(), "fleet-update/state.json");
      JSONObject prior = null;
      if (stateFile.exists()) {
        JSONObject state =
            FleetPolicy.Strict.parse(
                new String(new AtomicFile(stateFile).readFully(), StandardCharsets.UTF_8));
        for (String field : new String[] {"last_transaction", "transaction"}) {
          JSONObject t = state.optJSONObject(field);
          if (t != null
              && t.optLong("version") == current.getLongVersionCode()
              && expected.equals(t.optString("signer"))
              && t.has("release_envelope")) {
            JSONObject envelope = t.getJSONObject("release_envelope");
            FleetPolicy.require(
                files.getJSONObject(0).getString("sha256").equals(t.getString("sha256")),
                "artifact_hash");
            prior = envelope;
            break;
          }
        }
      }
      identity
          .put("prior_signed_manifest", prior == null ? JSONObject.NULL : prior)
          .put(
              "baseline_manifest_status",
              prior == null
                  ? "unavailable-initial-or-untracked-build"
                  : "previously-verified-release");
      String canonical = FleetPolicy.canonical(identity);
      JSONObject receipt =
          new JSONObject()
              .put("identity", identity)
              .put(
                  "identity_sha256",
                  FleetRuntime.hex(
                      MessageDigest.getInstance("SHA-256")
                          .digest(canonical.getBytes(StandardCharsets.UTF_8))));
      synced(
          new File(temporary, "identity.json"),
          FleetPolicy.canonical(receipt).getBytes(StandardCharsets.UTF_8));
      FleetPolicy.require(temporary.renameTo(destination), "artifact_size");
      requireCurrent(c);
    } catch (Exception e) {
      if (temporary.isDirectory()) {
        File[] files = temporary.listFiles();
        if (files != null) for (File file : files) file.delete();
        temporary.delete();
      }
      throw e;
    }
  }

  /**
   * Never silently replace an equivocal archive or proceed after the installed identity changed.
   */
  public static synchronized void requireCurrent(Context c) throws Exception {
    PackageInfo current = installed(c);
    File baseline = new File(directory(c), "version-" + current.getLongVersionCode());
    File receiptFile = new File(baseline, "identity.json");
    FleetPolicy.require(receiptFile.isFile(), "artifact_hash");
    JSONObject receipt =
        FleetPolicy.Strict.parse(
            new String(
                FleetRuntime.bounded(new FileInputStream(receiptFile), 131072),
                StandardCharsets.UTF_8));
    JSONObject identity = receipt.getJSONObject("identity");
    String digest =
        FleetRuntime.hex(
            MessageDigest.getInstance("SHA-256")
                .digest(FleetPolicy.canonical(identity).getBytes(StandardCharsets.UTF_8)));
    FleetPolicy.require(
        digest.equals(receipt.getString("identity_sha256"))
            && identity.getLong("archive_schema") == 1
            && identity.get("automatic_rollback") == Boolean.FALSE
            && identity.getLong("version") == current.getLongVersionCode()
            && identity.getString("package").equals(c.getPackageName())
            && identity.getString("signer_cert_sha256").equals(signer(current)),
        "artifact_hash");
    List<File> sources = sources(current);
    JSONArray files = identity.getJSONArray("files");
    FleetPolicy.require(files.length() == sources.size(), "artifact_hash");
    for (int i = 0; i < files.length(); i++) {
      JSONObject f = files.getJSONObject(i);
      String name = i == 0 ? "base.apk" : "split-" + i + ".apk";
      FleetPolicy.require(
          name.equals(f.getString("file"))
              && sources.get(i).getCanonicalPath().equals(f.getString("source")),
          "artifact_hash");
      File archived = new File(baseline, name);
      FleetPolicy.require(
          archived.isFile()
              && archived.length() == f.getLong("size")
              && hash(archived).equals(f.getString("sha256")),
          "artifact_hash");
    }
  }

  private FleetArchive() {}
}
