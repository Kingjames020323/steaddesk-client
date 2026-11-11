package com.steaddesk.remote.staging;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ContentResolver;
import android.net.Uri;
import android.os.Bundle;

/** The remote provider process sees this ordinary application UID across a real Binder call. */
public class AppCaller extends Instrumentation {
    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        try {
            ContentResolver resolver = getTargetContext().getContentResolver();
            String prefix = "content://com.steaddesk.remote.staging/";
            for (String operation : new String[] {"query", "write"}) {
                try {
                    if (operation.equals("query")) {
                        resolver.query(Uri.parse(prefix + "status"), null, null, null, null);
                    } else {
                        resolver.openFileDescriptor(Uri.parse(prefix + "permanent-password"), "w");
                    }
                    throw new AssertionError("Provider allowed app " + operation);
                } catch (SecurityException e) {
                    if (!"caller".equals(e.getMessage())) {
                        throw new AssertionError("Unexpected denial for app " + operation, e);
                    }
                }
            }
            finish(Activity.RESULT_OK, result);
        } catch (Throwable failure) {
            result.putString("failure", android.util.Log.getStackTraceString(failure));
            finish(Activity.RESULT_CANCELED, result);
        }
    }
}
