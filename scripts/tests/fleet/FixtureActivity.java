package com.carriez.flutter_hbb;

import android.app.Activity;
import android.content.*;
import android.os.Bundle;
import android.util.Base64;
import android.util.Log;
import android.widget.TextView;
import org.json.*;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.*;
import net.i2p.crypto.eddsa.*;
import net.i2p.crypto.eddsa.spec.*;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.net.ssl.HttpsURLConnection;

/** Fixture adapter only. FleetRuntime/FleetPolicy are compiled unchanged. */
public final class FixtureActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView text = new TextView(this);
        try {
            int version = getPackageManager().getPackageInfo(getPackageName(),0).versionCode;
            text.setText("UPD2 isolated fixture version " + version);
            Log.i("UPD2FIXTURE", "start version="+version+" uid="+android.os.Process.myUid()+" canRequestInstalls="+getPackageManager().canRequestPackageInstalls());
        } catch(Exception e) { throw new IllegalStateException(e); }
        setContentView(text);
        String negative=getIntent().getStringExtra("probe_case");
        if(negative!=null) {
            if(!Arrays.asList("equal","lower","manifest","signature","apk_hash","apk_signature","emergency").contains(negative)) throw new IllegalArgumentException("unknown fixture case");
            final Context isolated=new ContextWrapper(getApplicationContext()) {
                @Override public Context getApplicationContext() { return this; }
                @Override public java.io.File getNoBackupFilesDir() {
                    java.io.File dir=new java.io.File(super.getNoBackupFilesDir(),"negative-"+negative);
                    if(!dir.isDirectory()&&!dir.mkdirs()) throw new IllegalStateException("fixture storage");
                    return dir;
                }
            };
            FleetUpdater.WORK.execute(() -> {
                try {
                    new FleetRuntime(isolated,new FixtureHost(isolated)).tick();
                    Log.e("UPD2FIXTURE","negative_probe_unexpected_accept case="+negative);
                } catch(FleetPolicy.Rejected e) {
                    Log.i("UPD2FIXTURE","negative_probe_expected case="+negative+" reason="+e.reason);
                } catch(Exception e) { Log.e("UPD2FIXTURE","negative_probe_failed case="+negative,e); }
            });
        } else if(getIntent().getBooleanExtra("probe_archive",false)) {
            FleetUpdater.WORK.execute(() -> {
                try {
                    FleetArchive.requireCurrent(this);
                    long version=getPackageManager().getPackageInfo(getPackageName(),0).getLongVersionCode();
                    java.io.File base=new java.io.File(getNoBackupFilesDir(),"fleet-update/baselines/version-"+version+"/base.apk");
                    try(java.io.RandomAccessFile file=new java.io.RandomAccessFile(base,"rw")) {
                        file.seek(128);int original=file.read();file.seek(128);file.write(original^1);file.getFD().sync();
                        try {
                            try { FleetArchive.requireCurrent(this); throw new AssertionError("corrupt archive accepted"); }
                            catch(FleetPolicy.Rejected expected) { if(!"artifact_hash".equals(expected.reason)) throw expected; }
                        } finally { file.seek(128);file.write(original);file.getFD().sync(); }
                    }
                    FleetArchive.requireCurrent(this);
                    for(long[] input:new long[][]{{0,1},{Long.MAX_VALUE,Long.MAX_VALUE}}) {
                        try { FleetArchive.requireSpace(input[0],input[1]);throw new AssertionError("insufficient/overflow space accepted"); }
                        catch(FleetPolicy.Rejected expected) { if(!"artifact_size".equals(expected.reason)) throw expected; }
                    }
                    FleetArchive.requireSpace(16L*1024*1024+1,1);
                    Log.i("UPD2FIXTURE","synthetic_archive_corruption_and_space_probe_passed");
                } catch(Exception e) { Log.e("UPD2FIXTURE","synthetic_archive_probe_failed",e); }
            });
        } else if(getIntent().getBooleanExtra("probe_duplicates",false)) {
            FleetUpdater.WORK.execute(() -> {
                try {
                    FleetRuntime runtime=new FleetRuntime(this,new FixtureHost(this));
                    JSONObject before=runtime.load();
                    int session=before.getJSONObject("transaction").getInt("session");
                    String stage=before.getJSONObject("transaction").getString("stage");
                    if(!"observing".equals(stage)) throw new AssertionError("observing baseline required");
                    runtime.result(session,android.content.pm.PackageInstaller.STATUS_PENDING_USER_ACTION);
                    runtime.result(session,android.content.pm.PackageInstaller.STATUS_PENDING_USER_ACTION);
                    runtime.result(session,android.content.pm.PackageInstaller.STATUS_SUCCESS);
                    JSONObject after=runtime.load();
                    if(!stage.equals(after.getJSONObject("transaction").getString("stage"))) throw new AssertionError("late callback changed stage");
                    if(before.getLong("report_seq")!=after.getLong("report_seq")) throw new AssertionError("late callback appended receipt");
                    Log.i("UPD2FIXTURE","synthetic_duplicate_callback_probe_passed");
                } catch(Exception e) { Log.e("UPD2FIXTURE","synthetic_duplicate_callback_probe_failed",e); }
            });
        } else FleetUpdater.run(this, -1, -999);
    }
}

final class FixtureHost implements FleetRuntime.Host {
    final Context context;
    FixtureHost(Context context) { this.context=context; }
    static byte[] decode(String s) { return Base64.decode(s, Base64.NO_WRAP); }
    public JSONObject proof(String method, String path, String canonicalBody, long version) throws Exception {
        if(path.endsWith("/update-assignment")) FleetArchive.preserve(context);
        if(path.endsWith("/update-attempts")) FleetArchive.requireCurrent(context);
        long at = System.currentTimeMillis()/1000;
        byte[] random = new byte[16]; new SecureRandom().nextBytes(random);
        String nonce = FleetRuntime.hex(random);
        JSONArray body = new JSONArray().put(method).put(path).put(new JSONObject(canonicalBody))
            .put(FixtureSecrets.DEVICE).put(version).put(at).put(nonce);
        byte[] message = ("SteadDesk-fleet-v1\0" + FleetPolicy.canonical(body)).getBytes(StandardCharsets.UTF_8);
        byte[] encodedKey = decode(FixtureSecrets.DEVICE_PKCS8);
        PrivateKey key = new EdDSAPrivateKey(new EdDSAPrivateKeySpec(Arrays.copyOfRange(encodedKey, encodedKey.length-32, encodedKey.length), EdDSANamedCurveTable.getByName("Ed25519")));
        Signature signing = new EdDSAEngine(MessageDigest.getInstance("SHA-512")); signing.initSign(key); signing.update(message);
        return new JSONObject().put("X-Fleet-Device", FixtureSecrets.DEVICE).put("X-Fleet-Key-Version", String.valueOf(version))
            .put("X-Fleet-Time", String.valueOf(at)).put("X-Fleet-Nonce", nonce)
            .put("X-Fleet-Signature", Base64.encodeToString(signing.sign(), Base64.NO_WRAP));
    }
    public boolean verifyRelease(byte[] raw, byte[] signature, FleetRoot root) throws Exception {
        PublicKey key = new EdDSAPublicKey(new EdDSAPublicKeySpec(decode(root.publicKey), EdDSANamedCurveTable.getByName("Ed25519")));
        Signature checking = new EdDSAEngine(MessageDigest.getInstance("SHA-512")); checking.initVerify(key); checking.update(raw);
        return checking.verify(signature);
    }
    public int sessionState() { return 0; }
    public boolean merchantPaused(Context c) { return false; }
    public boolean forceStopped(Context c) { return false; }
    public boolean healthy(Context c) { return true; }
    long serverAt, elapsedAt;
    public synchronized long trustedNow(Context c) throws Exception {
        long elapsed = android.os.SystemClock.elapsedRealtime();
        if(serverAt>0 && elapsed-elapsedAt<60000) return serverAt+(elapsed-elapsedAt)/1000;
        HttpsURLConnection clock = connection(new URL(FleetBuild.ARTIFACT_ORIGIN+"/fixed/test.apk"));
        clock.setConnectTimeout(5000); clock.setReadTimeout(5000); clock.setInstanceFollowRedirects(false);
        try {
            if(clock.getResponseCode()!=200) throw new SecurityException("test HTTPS clock unavailable");
            serverAt=clock.getHeaderFieldDate("Date",0)/1000; elapsedAt=android.os.SystemClock.elapsedRealtime();
            if(serverAt<=0 || Math.abs(serverAt-System.currentTimeMillis()/1000)>30) throw new SecurityException("test clock skew");
            return serverAt;
        } finally { clock.disconnect(); }
    }
    public HttpsURLConnection connection(URL url) throws Exception { return (HttpsURLConnection)url.openConnection(); }
}

final class FleetUpdater {
    static final ExecutorService WORK = Executors.newSingleThreadExecutor();
    static void offer(Context c) { Log.i("UPD2FIXTURE", "manual_offer_required"); }
    static void observe(Context c) { Log.i("UPD2FIXTURE", "fixture_heartbeat_only_no_real_remote_service"); }
    static void run(Context context, int session, int status) {
        Context app = context.getApplicationContext();
        WORK.execute(() -> {
            try {
                FleetRuntime runtime = new FleetRuntime(app,new FixtureHost(app));
                if(session>=0) runtime.result(session,status);
                runtime.tick();
                Log.i("UPD2FIXTURE","tick_complete");
            } catch(Exception e) { Log.e("UPD2FIXTURE","tick_failed",e); }
        });
    }
}
