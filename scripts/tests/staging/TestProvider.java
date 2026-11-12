package com.steaddesk.remote.staging;

import android.os.SystemClock;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.util.Arrays;

/** Replace only the native settings call. Record a fixture label and count, never the bytes. */
public class TestProvider extends StagingPasswordProvider {
    private File file(String name) {
        return new File(getContext().getFilesDir(), name);
    }

    @Override
    boolean hasPassword() {
        return file("state").exists();
    }

    @Override
    boolean store(byte[] value) {
        try {
            if (file("hold").exists()) {
                file("entered").createNewFile();
                long deadline = SystemClock.elapsedRealtime() + 15000;
                while (file("hold").exists() && SystemClock.elapsedRealtime() < deadline) {
                    SystemClock.sleep(20);
                }
                if (file("hold").exists()) {
                    return false;
                }
            }
            if (file("fail").exists()) {
                return false;
            }
            // A single letter identifies each of the two synthetic fixtures.
            int tag = -1;
            for (int symbol : new int[] {'A', 'z'}) {
                byte[] fixture = new byte[20];
                Arrays.fill(fixture, (byte) symbol);
                if (Arrays.equals(value, fixture)) {
                    tag = symbol;
                }
            }
            Files.write(file("state").toPath(), new byte[] {(byte) tag},
                    java.nio.file.StandardOpenOption.CREATE,
                    java.nio.file.StandardOpenOption.APPEND);
            return true;
        } catch (IOException e) {
            throw new AssertionError(e);
        }
    }
}
