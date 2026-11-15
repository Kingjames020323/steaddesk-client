package com.carriez.flutter_hbb;

/** Space reservation is tested without allocating a huge file or touching device storage. */
public final class FleetArchivePolicyTest {
  private static void rejected(long available, long size) {
    try {
      FleetArchive.requireSpace(available, size);
      throw new AssertionError("expected rejection");
    } catch (FleetPolicy.Rejected expected) {
    }
  }

  public static void main(String[] args) {
    FleetArchive.requireSpace(FleetArchive.RESERVE + 1, 1);
    FleetArchive.requireSpace(FleetArchive.RESERVE + 100_000_000, 100_000_000);
    rejected(FleetArchive.RESERVE, 1);
    rejected(0, 1);
    rejected(Long.MAX_VALUE, Long.MAX_VALUE);
    rejected(Long.MAX_VALUE, 0);
    rejected(Long.MAX_VALUE, -1);
    System.out.println("FleetArchive space checks passed: 7");
  }
}
