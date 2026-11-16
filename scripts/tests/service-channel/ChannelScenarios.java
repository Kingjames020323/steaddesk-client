package com.carriez.flutter_hbb;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.os.Build;

import java.util.Locale;
import java.util.Objects;

public final class ChannelScenarios {
    private final NotificationManager manager = new NotificationManager();
    private final SharedPreferences preferences = new SharedPreferences();
    private final ServiceNotificationChannel receiver = new ServiceNotificationChannel();
    private final FakeContext context = new FakeContext(new Configuration());

    private final class FakeContext extends Context {
        final Configuration config;
        FakeContext(Configuration config) { this.config = config; }
        public SharedPreferences getSharedPreferences(String name, int mode) { return preferences; }
        public <T> T getSystemService(Class<T> type) {
            if (Build.VERSION.SDK_INT < 26) throw new AssertionError("pre-O channel access");
            return type.cast(manager);
        }
        public Resources getResources() { return new Resources(config); }
        public Context createConfigurationContext(Configuration value) { return new FakeContext(value); }
        public String getString(int resource) { return Catalog.get(config.locale.getLanguage(), resource); }
    }

    private static void equal(Object expect, Object value) {
        if (!Objects.equals(expect, value)) throw new AssertionError("expected " + expect + ", got " + value);
    }

    private void checkLocale(String id, String lang) {
        NotificationChannel channel = manager.getNotificationChannel(id);
        String name;
        switch (lang) {
            case "en": name = "SteadDesk service"; break;
            case "zh": name = "SteadDesk 服务"; break;
            case "es": name = "Servicio de SteadDesk"; break;
            default: throw new AssertionError(lang);
        }
        equal(name, channel.getName());
        equal(Catalog.get(lang, R.string.merchant_channel_description), channel.getDescription());
    }

    private void fresh() {
        receiver.onReceive(context, new Intent(Intent.ACTION_MY_PACKAGE_REPLACED));
        equal(0, manager.registrations);
        equal("SteadDesk", ServiceNotificationChannel.builder(context).build().channelId);
        checkLocale("SteadDesk", "en");
        equal(4, manager.channels.get("SteadDesk").getImportance());
        for (String lang : new String[]{"es", "zh-cn", "en"}) {
            equal(true, MerchantLanguage.save(context, lang));
            checkLocale("SteadDesk", Locale.forLanguageTag(lang).getLanguage());
            equal("SteadDesk", ServiceNotificationChannel.builder(context).build().channelId);
        }
        equal(1, manager.channels.size());
    }

    private void upgrade(int importance, String id) {
        NotificationChannel old = new NotificationChannel(id, "RustDesk Service", importance);
        old.setDescription("RustDesk Service Channel");
        old.sound = null;
        old.vibrate = false;
        old.lightColor = 27;
        old.visibility = -1;
        manager.createNotificationChannel(old);
        // The package-update receiver runs even when the service is paused.
        context.config.setLocale(Locale.forLanguageTag("es"));
        receiver.onReceive(context, new Intent(Intent.ACTION_MY_PACKAGE_REPLACED));
        checkLocale(id, "es");
        equal(id, ServiceNotificationChannel.builder(context).build().channelId);
        equal(true, MerchantLanguage.save(context, "zh-cn"));
        checkLocale(id, "zh");
        context.config.setLocale(Locale.ENGLISH);
        receiver.onReceive(context, new Intent(Intent.ACTION_LOCALE_CHANGED));
        checkLocale(id, "zh");
        equal(true, MerchantLanguage.save(context, ""));
        checkLocale(id, "en");
        int writes = manager.registrations;
        receiver.onReceive(context, new Intent(Intent.ACTION_MY_PACKAGE_REPLACED));
        equal(id, ServiceNotificationChannel.builder(context).build().channelId);
        equal(writes, manager.registrations);
        equal(1, manager.channels.size());
        NotificationChannel current = manager.channels.get(id);
        equal(importance, current.importance);
        equal(null, current.sound);
        equal(false, current.vibrate);
        equal(27, current.lightColor);
        equal(-1, current.visibility);
    }

    private void denied() {
        manager.enabled = false;
        manager.createNotificationChannel(new NotificationChannel("RustDesk", "Old", 4));
        receiver.onReceive(context, new Intent(Intent.ACTION_MY_PACKAGE_REPLACED));
        android.app.Notification notification = ServiceNotificationChannel.builder(context).build();
        equal("RustDesk", notification.channelId);
        manager.notify(1, notification);
        equal(0, manager.visible);
        equal(false, manager.enabled);
        equal(1, manager.channels.size());
    }

    private void both() {
        manager.createNotificationChannel(new NotificationChannel("RustDesk", "Old", 0));
        manager.createNotificationChannel(new NotificationChannel("SteadDesk", "New", 4));
        equal("RustDesk", ServiceNotificationChannel.builder(context).build().channelId);
        manager.channels.get("RustDesk").importance = 4;
        manager.channels.get("SteadDesk").importance = 0;
        equal("SteadDesk", ServiceNotificationChannel.builder(context).build().channelId);
    }

    private void support() {
        BuildConfig.MERCHANT_EDITION = false;
        equal("SteadDesk", ServiceNotificationChannel.builder(context).build().channelId);
        for (String lang : new String[]{"zh", "es", "en"}) {
            context.config.setLocale(Locale.forLanguageTag(lang));
            receiver.onReceive(context, new Intent(Intent.ACTION_LOCALE_CHANGED));
            checkLocale("SteadDesk", lang);
        }
        equal(false, MerchantLanguage.save(context, "es"));
    }

    private void preO() {
        Build.VERSION.SDK_INT = 25;
        equal("", ServiceNotificationChannel.builder(context).build().channelId);
        receiver.onReceive(context, new Intent(Intent.ACTION_MY_PACKAGE_REPLACED));
        equal(0, manager.registrations);
    }

    public static void main(String[] args) {
        ChannelScenarios s = new ChannelScenarios();
        switch (args[0]) {
            case "fresh": s.fresh(); break;
            case "muted": s.upgrade(1, "RustDesk"); break;
            case "blocked": s.upgrade(0, "RustDesk"); break;
            case "branded": s.upgrade(0, "SteadDesk"); break;
            case "denied": s.denied(); break;
            case "both": s.both(); break;
            case "support": s.support(); break;
            case "pre-o": s.preO(); break;
            default: throw new AssertionError(args[0]);
        }
    }
}
