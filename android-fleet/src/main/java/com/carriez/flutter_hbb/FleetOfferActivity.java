package com.carriez.flutter_hbb;

import android.app.*;
import android.os.Bundle;

/** Explicit merchant consent; a notification or wake never represents acceptance. */
public final class FleetOfferActivity extends Activity {
  @Override
  public void onCreate(Bundle saved) {
    super.onCreate(saved);
    new AlertDialog.Builder(this)
        .setTitle(R.string.fleet_title)
        .setMessage(R.string.fleet_consent)
        .setPositiveButton(
            R.string.fleet_accept,
            (dialog, which) -> {
              FleetUpdater.respond(this, true);
              finish();
            })
        .setNegativeButton(
            R.string.fleet_decline,
            (dialog, which) -> {
              FleetUpdater.respond(this, false);
              finish();
            })
        .setOnCancelListener(dialog -> finish())
        .show();
  }
}
