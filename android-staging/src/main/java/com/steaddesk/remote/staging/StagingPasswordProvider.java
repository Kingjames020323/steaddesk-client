package com.steaddesk.remote.staging;

import android.content.ContentProvider;
import android.content.ContentProviderOperation;
import android.content.ContentProviderResult;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructPollfd;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;

public class StagingPasswordProvider extends ContentProvider {
    private static final String BASE = "content://com.steaddesk.remote.staging/";
    private static final Uri PASSWORD = Uri.parse(BASE + "permanent-password");
    private static final Uri STATUS = Uri.parse(BASE + "status");
    private static final String COLUMN = "password_set";
    private static final String ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
    private static final int LENGTH = 20;
    private static final int PIPE_READ_TIMEOUT_MS = 15000;
    private final Object gate = new Object();
    private boolean writing;
    private boolean unconfirmed;

    @Override public boolean onCreate() { return true; }

    private static void requireShell() {
        // Identity must be checked on the Binder thread, before handing off the fd.
        int uid = Binder.getCallingUid();
        if (uid != 2000 && uid != 0) throw new SecurityException("caller");
    }

    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        requireShell();
        if (!PASSWORD.equals(uri) || !"w".equals(mode)) throw new FileNotFoundException("endpoint");
        synchronized (gate) {
            if (writing) throw new FileNotFoundException("busy");
            // Invalidate the previous confirmation before handing the caller an fd.
            // The empty marker keeps an interrupted attempt unconfirmed across restarts.
            unconfirmed = true;
            ParcelFileDescriptor[] pipe;
            try {
                File marker = marker();
                if (!marker.createNewFile() && !marker.isFile()) throw new IOException();
                pipe = ParcelFileDescriptor.createReliablePipe();
            } catch (IOException | RuntimeException e) {
                throw new FileNotFoundException("setup");
            }
            writing = true;
            try {
                new Thread(() -> consume(pipe[0]), "staging-write").start();
                return pipe[1];
            } catch (RuntimeException | Error e) {
                close(pipe[0]);
                close(pipe[1]);
                writing = false;
                throw e;
            }
        }
    }

    private File marker() {
        File dir = getContext().getNoBackupFilesDir();
        if (dir == null || !dir.isDirectory()) throw new IllegalStateException("storage");
        return new File(dir, "staging-unconfirmed");
    }

    private static void close(ParcelFileDescriptor fd) {
        try { fd.close(); } catch (IOException ignored) {}
    }

    private static int readFrame(ParcelFileDescriptor reader, byte[] frame) throws IOException, ErrnoException {
        StructPollfd poll = new StructPollfd();
        poll.fd = reader.getFileDescriptor();
        poll.events = (short) OsConstants.POLLIN;
        StructPollfd[] fds = { poll };
        long end = SystemClock.elapsedRealtime() + PIPE_READ_TIMEOUT_MS;
        int used = 0;
        while (used < frame.length) {
            long left = end - SystemClock.elapsedRealtime();
            if (left <= 0 || Os.poll(fds, (int) left) == 0) throw new IOException();
            int count = Os.read(poll.fd, frame, used, frame.length - used);
            if (count == 0) {
                reader.checkError();
                return used;
            }
            used += count;
        }
        return used; // More than a password plus one LF.
    }

    private void consume(ParcelFileDescriptor reader) {
        byte[] frame = new byte[LENGTH + 2];
        byte[] password = new byte[LENGTH];
        boolean saved = false;
        try {
            int used = readFrame(reader, frame);
            if (used != LENGTH && !(used == LENGTH + 1 && frame[LENGTH] == '\n')) return;
            for (int i = 0; i < LENGTH; i++) {
                if (ALPHABET.indexOf(frame[i]) < 0) return;
            }
            System.arraycopy(frame, 0, password, 0, LENGTH);
            saved = store(password);
        } catch (IOException | ErrnoException | RuntimeException | LinkageError ignored) {
            // Never send input, exception detail or a password-derived value to a peer or log.
        } finally {
            Arrays.fill(frame, (byte) 0);
            Arrays.fill(password, (byte) 0);
            synchronized (gate) {
                try {
                    boolean acknowledged = false;
                    if (saved) {
                        try { acknowledged = marker().delete(); } catch (RuntimeException ignored) {}
                    }
                    if (acknowledged) {
                        unconfirmed = false;
                        close(reader);
                    } else {
                        try { reader.closeWithError("write"); } catch (IOException ignored) { close(reader); }
                    }
                } finally {
                    writing = false;
                }
            }
        }
    }

    boolean store(byte[] value) {
        return StagingPasswords.set(getContext().getDir("flutter", Context.MODE_PRIVATE).getAbsolutePath(), value);
    }

    boolean hasPassword() {
        return StagingPasswords.isSet(getContext().getDir("flutter", Context.MODE_PRIVATE).getAbsolutePath());
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection,
                                  String[] selectionArgs, String sortOrder) {
        requireShell();
        if (!STATUS.equals(uri) || selection != null || selectionArgs != null || sortOrder != null ||
                (projection != null && !(projection.length == 1 && COLUMN.equals(projection[0])))) {
            throw new IllegalArgumentException("endpoint");
        }
        boolean set;
        synchronized (gate) {
            // The shipping tool polls this snapshot; never wait for a pending write.
            try {
                set = !writing && !unconfirmed && !marker().exists() && hasPassword();
            } catch (RuntimeException | LinkageError ignored) {
                set = false;
            }
        }
        MatrixCursor cursor = new MatrixCursor(new String[]{COLUMN}, 1);
        cursor.addRow(new Object[]{set ? "true" : "false"});
        return cursor;
    }

    private static UnsupportedOperationException unsupported() {
        requireShell();
        return new UnsupportedOperationException("endpoint");
    }

    @Override public String getType(Uri uri) { throw unsupported(); }
    @Override public String[] getStreamTypes(Uri uri, String filter) { throw unsupported(); }
    @Override public Uri canonicalize(Uri uri) { throw unsupported(); }
    @Override public Uri uncanonicalize(Uri uri) { throw unsupported(); }
    @Override public Bundle call(String method, String arg, Bundle extras) { throw unsupported(); }
    @Override public Uri insert(Uri uri, ContentValues values) { throw unsupported(); }
    @Override public int bulkInsert(Uri uri, ContentValues[] values) { throw unsupported(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw unsupported(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw unsupported(); }
    @Override public ContentProviderResult[] applyBatch(ArrayList<ContentProviderOperation> ops) { throw unsupported(); }
    @Override public boolean refresh(Uri uri, Bundle args, CancellationSignal signal) { throw unsupported(); }
}
