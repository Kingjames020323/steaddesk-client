package com.carriez.flutter_hbb;

import android.app.job.*;

public final class FleetJobService extends JobService {
  @Override
  public boolean onStartJob(JobParameters parameters) {
    FleetUpdater.WORK.execute(
        () -> {
          try {
            FleetUpdater.runtime(this).tick();
          } catch (Exception | LinkageError ignored) {
          } finally {
            jobFinished(parameters, false);
          }
        });
    return true;
  }

  @Override
  public boolean onStopJob(JobParameters parameters) {
    return false;
  }
}
