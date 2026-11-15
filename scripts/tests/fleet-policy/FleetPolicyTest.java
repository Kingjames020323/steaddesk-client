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

  public static void main(String[] args) throws Exception {
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
