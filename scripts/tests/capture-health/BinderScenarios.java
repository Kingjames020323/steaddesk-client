package com.carriez.flutter_hbb;

import android.content.Context;
import android.os.IBinder;
import android.os.Parcel;

public final class BinderScenarios {
    // Read by the JNI fixture that stands in for the native authorized-connection registry.
    static int session;

    static void probe(IBinder peer, String label, int expected) throws Exception {
        Parcel reply = new Parcel();
        peer.transact(IBinder.FIRST_CALL_TRANSACTION + 1, new Parcel(), reply, 0);
        // Existing companions use zero as their only wakeable state.
        if (reply.value == 0) {
            peer.transact(IBinder.FIRST_CALL_TRANSACTION, new Parcel(), new Parcel(), 0);
        }
        if (reply.value != expected) {
            throw new AssertionError(label + ": expected " + expected + ", received " + reply.value);
        }
    }

    public static void main(String[] args) throws Exception {
        IBinder peer = new AgentWakeService().onBind(null);
        probe(peer, "process without MainService", 5);

        MainService service = new MainService();
        MerchantRecovery.start(service);
        probe(peer, "foreground before consent", 5);
        MainService.ready = true;
        probe(peer, "approved foreground projection", 1);
        session = 2;
        probe(peer, "authorized session", 2);
        session = 3;
        probe(peer, "unknown session registry", 3);
        session = 0;
        MainService.ready = false;
        probe(peer, "revoked projection", 5);

        for (int i = 0; i < 2; i++) {
            try {
                peer.transact(IBinder.FIRST_CALL_TRANSACTION, new Parcel(), new Parcel(), 0);
                throw new AssertionError("A stale WAKE acknowledged capture as available");
            } catch (IllegalStateException unavailable) {
                // The old caller sees the transaction fail. No new grant is requested.
            }
        }
        MerchantPause.paused = true;
        probe(peer, "paused", 4);
        peer.transact(IBinder.FIRST_CALL_TRANSACTION, new Parcel(), new Parcel(), 0);
    }
}

class MainService extends Context {
    static boolean ready;

    static class Companion {
        static boolean isReady() { return ready; }
    }
}

class MerchantPause {
    static boolean paused;
    static boolean isPaused(Context context) { return paused; }
    static boolean setPaused(Context context, boolean value) { paused = value; return true; }
}

class FleetEntry {
    static void start(Context context) { throw new AssertionError("Unexpected fleet start"); }
}

class BootReceiver {
    static boolean resumeService(Context context) { throw new AssertionError("Unexpected service start"); }
}

class MerchantLanguage {
    static String text(Context context, int resourceId) { return "unavailable"; }
}

class MerchantLogs {
    static int collect(Context context) { throw new AssertionError("Unexpected collection"); }
}

class MerchantToday {
    static void append(Context context, Parcel reply) { throw new AssertionError("Unexpected observation"); }
}

class MerchantLogRecords {
    static void recordBoot(Context context, String event) { throw new AssertionError("Unexpected boot"); }
}

class R {
    static class string {
        static int recovery_signature, recovery_uid, recovery_unavailable;
    }
}
