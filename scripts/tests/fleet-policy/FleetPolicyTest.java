package com.carriez.flutter_hbb;

import java.time.Instant;
import org.json.JSONObject;

public final class FleetPolicyTest {
  static int checks;

  interface Run {
    void run() throws Exception;
  }

  static void check(boolean ok) {
    checks++;
    if (!ok) throw new AssertionError("check " + checks);
  }

  static void rejected(Run fn) throws Exception {
    boolean failed = false;
    try {
      fn.run();
    } catch (Exception e) {
      failed = true;
    }
    check(failed);
  }

  static JSONObject window(String zone, int start, int end, String day) throws Exception {
    return new JSONObject()
        .put("zone", zone)
        .put("start_min", start)
        .put("end_min", end)
        .put("business_day", day);
  }

  static long time(String at) {
    return Instant.parse(at).getEpochSecond();
  }

  static byte[] release(String id, long issued, long expires) throws Exception {
    String hash = String.join("", java.util.Collections.nCopies(64, "1"));
    JSONObject manifest = new JSONObject()
        .put("schema", 1).put("release_id", "fixture").put("sequence", 2).put("key_id", id)
        .put("issued_at", issued).put("expires_at", expires).put("ring", 0).put("batch", 0)
        .put("bucket_end", 100).put("platform", "android").put("package", "com.steaddesk.remote")
        .put("channel", "merchant").put("architecture", "universal").put("versionCode", 2)
        .put("display_version", "v2").put("min_os", 1).put("size_bytes", 100)
        .put("artifact_path", "fixture.apk").put("sha256", hash).put("signer_cert_sha256", hash)
        .put("previous_release_id", JSONObject.NULL).put("health_policy_id", "c4-v1");
    return manifest.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
  }

  static void overlappingRoots() throws Exception {
    FleetRoot old = new FleetRoot("old", "fixture-old", 10, 30, false);
    FleetRoot next = new FleetRoot("next", "fixture-next", 20, 40, false);
    FleetRoot[] roots = {old, next};
    for (FleetRoot root : roots) {
      FleetRoot selected = FleetRoot.select(roots, root.id, 20);
      check(FleetPolicy.manifest(release(root.id, 20, 30), selected, 20).getString("key_id").equals(root.id));
    }
    rejected(() -> FleetRoot.select(roots, "old", 30));
    rejected(() -> FleetRoot.select(roots, "next", 19));
    rejected(() -> FleetRoot.select(roots, "unknown", 20));
    rejected(() -> FleetPolicy.manifest(release("next", 19, 30), next, 20));
    rejected(() -> FleetPolicy.manifest(release("next", 20, 41), next, 20));
    rejected(() -> FleetPolicy.manifest(release("old", 20, 30), next, 20));
    roots[0] = new FleetRoot("old", old.publicKey, 10, 30, true);
    rejected(() -> FleetRoot.select(roots, "old", 20));
    check(FleetRoot.select(roots, "next", 20) == next);
  }

  public static void main(String[] args) throws Exception {
    overlappingRoots();
    check(
        FleetPolicy.canonical(new JSONObject().put("z", "中文\n").put("a", 1))
            .equals("{\"a\":1,\"z\":\"中文\\n\"}"));
    for (String s :
        new String[] {
          "{\"a\":1,\"a\":2}",
          "{'a':1}",
          "{a:1}",
          "{\"a\":NaN}",
          "{\"a\":1.5}",
          "{\"a\":01}",
          "{\"a\":1,}",
          "{\"a\":{\"x\":1,\"x\":2}}",
          "{\"a\":true} trailing"
        }) rejected(() -> FleetPolicy.Strict.parse(s));
    check(
        FleetPolicy.businessDay(
                window("America/Los_Angeles", 22 * 60, 4 * 60, "2026-11-13"),
                time("2026-11-14T10:00:00Z"))
            .equals("2026-11-13"));
    rejected(
        () ->
            FleetPolicy.businessDay(
                window("America/Los_Angeles", 22 * 60, 4 * 60, "2026-11-13"),
                time("2026-11-14T12:00:00Z")));
    rejected(
        () ->
            FleetPolicy.businessDay(
                window("America/Los_Angeles", 0, 4 * 60, "2026-11-01"),
                time("2026-11-01T08:30:00Z")));
    rejected(
        () ->
            FleetPolicy.businessDay(
                window("America/Los_Angeles", 0, 4 * 60, "2026-03-08"),
                time("2026-03-08T09:00:00Z")));
    rejected(
        () ->
            FleetPolicy.businessDay(
                window("Unknown/Zone", 1, 2, "2026-11-14"), time("2026-11-14T00:00:00Z")));
    rejected(
        () ->
            FleetPolicy.businessDay(
                window("UTC", 0, 1440, "2026-11-14"), time("2026-11-14T00:00:00Z")));
    JSONObject empty = new JSONObject();
    long now = time("2026-11-14T00:00:00Z");
    FleetPolicy.gates(false, false, 0, now, "2026-11-14", empty);
    checks++;
    rejected(() -> FleetPolicy.gates(true, false, 0, now, "day", empty));
    rejected(() -> FleetPolicy.gates(false, true, 0, now, "day", empty));
    rejected(() -> FleetPolicy.gates(false, false, 2, now, "day", empty));
    rejected(() -> FleetPolicy.gates(false, false, 1, now, "day", empty));
    rejected(
        () ->
            FleetPolicy.gates(
                false, false, 0, now, "day", new JSONObject().put("last_day", "day")));
    rejected(
        () ->
            FleetPolicy.gates(
                false, false, 0, now, "day", new JSONObject().put("last_started", now - 86399)));
    rejected(
        () ->
            FleetPolicy.gates(
                false, false, 0, now, "day", new JSONObject().put("last_started", now + 1)));
    rejected(
        () ->
            FleetPolicy.gates(
                false,
                false,
                0,
                now,
                "day",
                new JSONObject().put("transaction", new JSONObject())));
    System.out.println("FleetPolicy checks passed: " + checks);
  }
}
