package com.carriez.flutter_hbb;

import android.app.*;
import android.app.job.*;
import android.content.*;
import android.os.*;
import java.util.concurrent.*;

/** Normal launch, six-hour job, package-replaced/boot and local wake all share this entry. */
public final class FleetUpdater {
  static final int POLL_JOB = 67021, OBSERVE_JOB = 67022, OFFER = 67023;
  static final ExecutorService WORK = Executors.newSingleThreadExecutor();

  static FleetRuntime runtime(Context context) {
    return new FleetRuntime(context, new FleetHost(context));
  }

  public static void start(Context context) {
    if (Build.VERSION.SDK_INT < 28) return;
    Context app = context.getApplicationContext();
    JobScheduler scheduler = app.getSystemService(JobScheduler.class);
    scheduler.schedule(
        new JobInfo.Builder(POLL_JOB, new ComponentName(app, FleetJobService.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPersisted(true)
            .setPeriodic(6 * 60 * 60 * 1000L)
            .build());
    tick(app);
  }

  public static void tick(Context context) {
    Context app = context.getApplicationContext();
    WORK.execute(
        () -> {
          try {
            runtime(app).tick();
          } catch (Exception | LinkageError ignored) {
            /* durable fixed-code evidence is written by runtime */
          }
        });
  }

  public static void observe(Context context) {
    long delay = 60_000;
    try {
      org.json.JSONObject transaction = runtime(context).load().optJSONObject("transaction");
      if (transaction != null && transaction.has("deadline")) {
        // One scheduled wake near the four-hour observation boundary avoids exhausting job quota.
        delay =
            Math.max(
                60_000,
                transaction.getLong("deadline") * 1000 - System.currentTimeMillis() - 240_000);
      }
    } catch (Exception unavailable) {
      return;
    }
    context
        .getSystemService(JobScheduler.class)
        .schedule(
            new JobInfo.Builder(OBSERVE_JOB, new ComponentName(context, FleetJobService.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setMinimumLatency(delay)
                .setOverrideDeadline(delay + 90_000)
                .setPersisted(true)
                .build());
  }

  static void offer(Context c) {
    NotificationManager manager = c.getSystemService(NotificationManager.class);
    FleetPolicy.require(manager.areNotificationsEnabled(), "no_safety");
    manager.createNotificationChannel(
        new NotificationChannel(
            "fleet-update",
            c.getString(R.string.fleet_channel),
            NotificationManager.IMPORTANCE_DEFAULT));
    PendingIntent action =
        PendingIntent.getActivity(
            c,
            OFFER,
            new Intent(c, FleetOfferActivity.class),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    manager.notify(
        OFFER,
        new Notification.Builder(c, "fleet-update")
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(c.getString(R.string.fleet_ready))
            .setContentText(c.getString(R.string.fleet_notification))
            .setContentIntent(action)
            .setAutoCancel(true)
            .build());
  }

  static void confirm(Context c, Intent confirmation, int session) throws Exception {
    android.content.pm.PackageManager pm = c.getPackageManager();
    android.content.pm.ResolveInfo target = pm.resolveActivity(confirmation, 0);
    FleetPolicy.require(
        target != null
            && target.activityInfo != null
            && (target.activityInfo.applicationInfo.flags
                    & android.content.pm.ApplicationInfo.FLAG_SYSTEM)
                != 0,
        "no_safety");
    confirmation.setComponent(
        new ComponentName(target.activityInfo.packageName, target.activityInfo.name));
    confirmation.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    PendingIntent action =
        PendingIntent.getActivity(
            c,
            session,
            confirmation,
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    NotificationManager manager = c.getSystemService(NotificationManager.class);
    manager.createNotificationChannel(
        new NotificationChannel(
            "fleet-update",
            c.getString(R.string.fleet_channel),
            NotificationManager.IMPORTANCE_DEFAULT));
    manager.notify(
        OFFER,
        new Notification.Builder(c, "fleet-update")
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(c.getString(R.string.fleet_title))
            .setContentText(c.getString(R.string.fleet_system_confirm))
            .setContentIntent(action)
            .setAutoCancel(true)
            .build());
  }

  static void respond(Context c, boolean accepted) {
    Context app = c.getApplicationContext();
    WORK.execute(
        () -> {
          try {
            runtime(app).respond(accepted);
            if (accepted) runtime(app).tick();
          } catch (Exception | LinkageError ignored) {
          }
        });
  }

  private FleetUpdater() {}
}
