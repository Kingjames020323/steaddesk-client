package com.steaddesk.remote.staging;

final class StagingPasswords {
    static { System.loadLibrary("rustdesk"); }
    private StagingPasswords() {}

    static native boolean set(String configDir, byte[] password);
    static native boolean isSet(String configDir);
}
