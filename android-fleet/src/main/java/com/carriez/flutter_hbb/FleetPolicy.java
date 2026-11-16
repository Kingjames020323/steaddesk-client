package com.carriez.flutter_hbb;

import java.nio.charset.StandardCharsets;
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.*;
import org.json.*;

/** Pure policy; no download, process, installation or network side effects. */
public final class FleetPolicy {
  public static void require(boolean ok, String reason) {
    if (!ok) throw new Rejected(reason);
  }

  public static final class Rejected extends RuntimeException {
    public final String reason;

    public Rejected(String reason) {
      super(reason);
      this.reason = reason;
    }
  }

  public static long integer(JSONObject o, String name) throws JSONException {
    Object value = o.get(name);
    require(value instanceof Integer || value instanceof Long, "manifest_signature");
    long n = ((Number) value).longValue();
    require(n >= 0, "manifest_signature");
    return n;
  }

  public static JSONObject manifest(byte[] raw, FleetRoot root, long now) throws Exception {
    require(raw.length > 0 && raw.length <= 32768, "manifest_signature");
    String text = new String(raw, StandardCharsets.UTF_8);
    require(Arrays.equals(raw, text.getBytes(StandardCharsets.UTF_8)), "manifest_signature");
    JSONObject m = Strict.parse(text);
    Set<String> wanted =
        new HashSet<>(
            Arrays.asList(
                ("schema release_id sequence key_id issued_at expires_at ring batch bucket_end"
                     + " platform package channel architecture versionCode display_version min_os"
                     + " size_bytes artifact_path sha256 signer_cert_sha256 previous_release_id"
                     + " health_policy_id")
                    .split(" ")));
    require(keys(m).equals(wanted), "manifest_signature");
    for (String field :
        new String[] {
          "release_id",
          "key_id",
          "platform",
          "package",
          "channel",
          "architecture",
          "display_version",
          "artifact_path",
          "sha256",
          "signer_cert_sha256",
          "health_policy_id"
        }) require(m.get(field) instanceof String, "manifest_signature");
    require(
        integer(m, "schema") == 1
            && integer(m, "sequence") > 0
            && integer(m, "versionCode") > 0
            && integer(m, "min_os") > 0,
        "manifest_signature");
    long issued = integer(m, "issued_at"), expires = integer(m, "expires_at");
    require(root.validFrom <= issued && issued <= now && now < expires && expires <= root.validUntil,
            "manifest_signature");
    require(root.id.equals(m.getString("key_id")), "manifest_signature");
    for (String key : new String[] {"release_id", "key_id", "display_version"})
      require(m.getString(key).matches("[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"), "manifest_signature");
    require("android".equals(m.getString("platform")), "platform_mismatch");
    require(
        "merchant".equals(m.getString("channel"))
            && "c4-v1".equals(m.getString("health_policy_id")),
        "manifest_signature");
    require("com.steaddesk.remote".equals(m.getString("package")), "package_mismatch");
    require(
        Arrays.asList("universal", "arm64-v8a", "armeabi-v7a", "x86_64")
            .contains(m.getString("architecture")),
        "platform_mismatch");
    long ring = integer(m, "ring"), batch = integer(m, "batch"), bucket = integer(m, "bucket_end");
    require(
        ring <= 2
            && bucket > 0
            && bucket <= 100
            && (ring == 2 ? batch > 0 : batch == 0 && bucket == 100),
        "manifest_signature");
    Object previous = m.get("previous_release_id");
    require(
        previous == JSONObject.NULL
            || previous instanceof String
                && ((String) previous).matches("[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
                && !previous.equals(m.getString("release_id")),
        "manifest_signature");
    for (String key : new String[] {"sha256", "signer_cert_sha256"})
      require(m.getString(key).matches("[a-f0-9]{64}"), "manifest_signature");
    long size = integer(m, "size_bytes");
    require(size > 0 && size <= 536870912L, "artifact_size");
    String path = m.getString("artifact_path");
    require(path.length() <= 512 && path.endsWith(".apk"), "manifest_signature");
    for (String part : path.split("/", -1))
      require(
          part.matches("[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}")
              && !part.endsWith(".")
              && !part.matches("(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\..*)?"),
          "manifest_signature");
    return m;
  }

  static Set<String> keys(JSONObject o) {
    Set<String> k = new HashSet<>();
    Iterator<String> it = o.keys();
    while (it.hasNext()) k.add(it.next());
    return k;
  }

  public static String businessDay(JSONObject w, long now) throws Exception {
    ZoneId zone = ZoneId.of(w.getString("zone"));
    int start = (int) integer(w, "start_min"), end = (int) integer(w, "end_min");
    require(start < 1440 && end < 1440 && start != end, "window_unknown");
    ZonedDateTime local = Instant.ofEpochSecond(now).atZone(zone);
    LocalDate day = local.toLocalDate();
    if (end < start && local.toLocalTime().toSecondOfDay() < end * 60) day = day.minusDays(1);
    LocalDateTime a = day.atStartOfDay().plusMinutes(start),
        b = day.plusDays(end < start ? 1 : 0).atStartOfDay().plusMinutes(end);
    ZoneRules rules = zone.getRules();
    require(
        rules.getValidOffsets(a).size() == 1 && rules.getValidOffsets(b).size() == 1,
        "outside_window");
    Instant ai = a.atZone(zone).toInstant(), bi = b.atZone(zone).toInstant();
    // Any DST transition touching the window makes the entire window unavailable.
    java.time.zone.ZoneOffsetTransition transition = rules.nextTransition(ai.minusNanos(1));
    require(transition == null || transition.getInstant().isAfter(bi), "outside_window");
    Instant instant = Instant.ofEpochSecond(now);
    require(!instant.isBefore(ai) && instant.isBefore(bi), "outside_window");
    String business = day.toString();
    require(business.equals(w.getString("business_day")), "window_unknown");
    return business;
  }

  public static void gates(
      boolean paused, boolean stopped, int sessions, long now, String day, JSONObject state)
      throws Exception {
    require(!paused, "merchant_pause");
    require(!stopped, "j23");
    require(sessions == 0, "session_unknown");
    long last = state.optLong("last_started", 0);
    require(
        !day.equals(state.optString("last_day"))
            && (last == 0 || now >= last && now - last >= 86400),
        "outside_window");
    require(state.optJSONObject("transaction") == null, "no_safety");
  }

  public static String canonical(Object value) throws JSONException {
    if (value == null || value == JSONObject.NULL) return "null";
    if (value instanceof JSONObject) {
      JSONObject o = (JSONObject) value;
      List<String> names = new ArrayList<>(keys(o));
      Collections.sort(names);
      List<String> pairs = new ArrayList<>();
      for (String k : names) pairs.add(quote(k) + ":" + canonical(o.get(k)));
      return "{" + String.join(",", pairs) + "}";
    }
    if (value instanceof JSONArray) {
      JSONArray a = (JSONArray) value;
      List<String> parts = new ArrayList<>();
      for (int i = 0; i < a.length(); i++) parts.add(canonical(a.get(i)));
      return "[" + String.join(",", parts) + "]";
    }
    if (value instanceof String) return quote((String) value);
    if (value instanceof Boolean || value instanceof Integer || value instanceof Long)
      return value.toString();
    throw new JSONException("unsupported JSON value");
  }

  static String quote(String s) {
    StringBuilder b = new StringBuilder("\"");
    for (int i = 0; i < s.length(); i++) {
      char c = s.charAt(i);
      switch (c) {
        case '"':
          b.append("\\\"");
          break;
        case '\\':
          b.append("\\\\");
          break;
        case '\n':
          b.append("\\n");
          break;
        case '\r':
          b.append("\\r");
          break;
        case '\t':
          b.append("\\t");
          break;
        case '\b':
          b.append("\\b");
          break;
        case '\f':
          b.append("\\f");
          break;
        default:
          if (c < 32) b.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
          else b.append(c);
      }
    }
    return b.append('"').toString();
  }

  /**
   * Strict RFC 8259 subset: no duplicate keys, permissive JSONTokener syntax or fractional numbers.
   */
  public static final class Strict {
    private final String s;
    private int p;

    Strict(String s) {
      this.s = s;
    }

    public static JSONObject parse(String s) throws JSONException {
      Strict j = new Strict(s);
      Object v = j.value(0);
      j.ws();
      if (j.p != s.length() || !(v instanceof JSONObject))
        throw new JSONException("object required");
      return (JSONObject) v;
    }

    void ws() {
      while (p < s.length() && " \r\n\t".indexOf(s.charAt(p)) >= 0) p++;
    }

    Object value(int depth) throws JSONException {
      if (depth > 32) throw new JSONException("depth");
      ws();
      if (p >= s.length()) throw new JSONException("truncated");
      char c = s.charAt(p);
      if (c == '"') return string();
      if (c == '{') {
        p++;
        JSONObject o = new JSONObject();
        ws();
        if (take('}')) return o;
        do {
          ws();
          String k = string();
          if (o.has(k)) throw new JSONException("duplicate key");
          ws();
          expect(':');
          o.put(k, value(depth + 1));
          ws();
          if (take('}')) return o;
          expect(',');
        } while (true);
      }
      if (c == '[') {
        p++;
        JSONArray a = new JSONArray();
        ws();
        if (take(']')) return a;
        do {
          a.put(value(depth + 1));
          ws();
          if (take(']')) return a;
          expect(',');
        } while (true);
      }
      for (String lit : new String[] {"true", "false", "null"})
        if (s.startsWith(lit, p)) {
          p += lit.length();
          return lit.equals("null") ? JSONObject.NULL : Boolean.valueOf(lit);
        }
      int a = p;
      if (c == '-') p++;
      if (p >= s.length()) throw new JSONException("number");
      if (s.charAt(p) == '0') p++;
      else {
        if (s.charAt(p) < '1' || s.charAt(p) > '9') throw new JSONException("number");
        while (p < s.length() && Character.isDigit(s.charAt(p))) p++;
      }
      try {
        return Long.valueOf(s.substring(a, p));
      } catch (NumberFormatException e) {
        throw new JSONException("integer");
      }
    }

    String string() throws JSONException {
      expect('"');
      StringBuilder b = new StringBuilder();
      while (p < s.length()) {
        char c = s.charAt(p++);
        if (c == '"') return b.toString();
        if (c < 32) throw new JSONException("control");
        if (c == '\\') {
          if (p >= s.length()) break;
          c = s.charAt(p++);
          switch (c) {
            case '"':
            case '\\':
            case '/':
              b.append(c);
              break;
            case 'b':
              b.append('\b');
              break;
            case 'f':
              b.append('\f');
              break;
            case 'n':
              b.append('\n');
              break;
            case 'r':
              b.append('\r');
              break;
            case 't':
              b.append('\t');
              break;
            case 'u':
              if (p + 4 > s.length()) throw new JSONException("escape");
              try {
                b.append((char) Integer.parseInt(s.substring(p, p + 4), 16));
                p += 4;
              } catch (NumberFormatException e) {
                throw new JSONException("escape");
              }
              break;
            default:
              throw new JSONException("escape");
          }
        } else b.append(c);
      }
      throw new JSONException("string");
    }

    boolean take(char c) {
      if (p < s.length() && s.charAt(p) == c) {
        p++;
        return true;
      }
      return false;
    }

    void expect(char c) throws JSONException {
      if (!take(c)) throw new JSONException("syntax");
    }
  }

  private FleetPolicy() {}
}
