package com.carriez.flutter_hbb;

/** Same Config-held Ed25519 identity as HELP-2. No key export or identity injection. */
public final class FleetNative {
  static {
    System.loadLibrary("rustdesk");
  }

  public static native boolean initialize(String appPrivateDir);

  public static native String proof(
      String method, String path, String canonicalBody, long keyVersion);

  public static native boolean verifyRelease(byte[] raw, byte[] signature, byte[] publicKey);

  public static native int sessionState();

  private FleetNative() {}
}
