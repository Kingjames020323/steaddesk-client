package com.carriez.flutter_hbb;

/** Build-time release authority for one ID. Time bounds are Unix seconds. */
final class FleetRoot {
  final String id, publicKey;
  final long validFrom, validUntil;
  final boolean revoked;

  FleetRoot(String id, String publicKey, long validFrom, long validUntil, boolean revoked) {
    this.id = id;
    this.publicKey = publicKey;
    this.validFrom = validFrom;
    this.validUntil = validUntil;
    this.revoked = revoked;
  }

  static FleetRoot select(FleetRoot[] roots, String id, long now) {
    for (FleetRoot root : roots) {
      if (root.id.equals(id) && !root.revoked && root.validFrom <= now && now < root.validUntil)
        return root;
    }
    throw new FleetPolicy.Rejected("manifest_signature");
  }
}
