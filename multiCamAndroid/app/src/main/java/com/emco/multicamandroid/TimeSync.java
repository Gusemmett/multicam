package com.emco.multicamandroid;

import android.os.SystemClock;
import android.util.Log;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicLong;

public class TimeSync {
    private static final String TAG = "TimeSync";
    private static final int SYNC_ATTEMPTS = 3;
    private static final long SYNC_TIMEOUT_MS = 10000;

    private final NTPClient ntpClient;
    private final AtomicLong timeOffset = new AtomicLong(0);
    private final AtomicLong lastSyncTime = new AtomicLong(0);
    private volatile boolean isSynced = false;

    public interface SyncCallback {
        void onSyncComplete(boolean success, long offsetMs);
        void onSyncError(Exception error);
    }

    public TimeSync() {
        this.ntpClient = new NTPClient();
    }

    public TimeSync(String ntpServer) {
        this.ntpClient = new NTPClient(ntpServer);
    }

    public CompletableFuture<Boolean> synchronizeTime() {
        CompletableFuture<Boolean> future = new CompletableFuture<>();

        synchronizeTime(new SyncCallback() {
            @Override
            public void onSyncComplete(boolean success, long offsetMs) {
                future.complete(success);
            }

            @Override
            public void onSyncError(Exception error) {
                future.complete(false);
            }
        });

        return future;
    }

    public void synchronizeTime(SyncCallback callback) {
        Log.d(TAG, "Starting time synchronization...");

        performMultipleSync(0, 0, 0, callback);
    }

    private void performMultipleSync(int attempt, long totalOffset, int successfulAttempts, SyncCallback callback) {
        if (attempt >= SYNC_ATTEMPTS) {
            if (successfulAttempts > 0) {
                long averageOffset = totalOffset / successfulAttempts;
                timeOffset.set(averageOffset);
                lastSyncTime.set(SystemClock.elapsedRealtime());
                isSynced = true;

                Log.i(TAG, String.format("Time sync complete. Average offset: %dms from %d attempts",
                        averageOffset, successfulAttempts));

                callback.onSyncComplete(true, averageOffset);
            } else {
                Log.e(TAG, "All sync attempts failed");
                callback.onSyncError(new RuntimeException("All sync attempts failed"));
            }
            return;
        }

        long startTime = SystemClock.elapsedRealtime();

        ntpClient.getNTPTime(new NTPClient.TimeCallback() {
            @Override
            public void onTimeReceived(long ntpTime, long roundTripTime) {
                long localTime = System.currentTimeMillis();
                long networkDelay = roundTripTime / 2;
                long adjustedNtpTime = ntpTime + networkDelay;
                long offset = adjustedNtpTime - localTime;

                Log.d(TAG, String.format("Sync attempt %d: offset=%dms, RTT=%dms",
                        attempt + 1, offset, roundTripTime));

                if (roundTripTime < 500) { // Only use results with reasonable RTT
                    performMultipleSync(attempt + 1, totalOffset + offset, successfulAttempts + 1, callback);
                } else {
                    Log.w(TAG, String.format("Ignoring sync attempt %d due to high RTT: %dms",
                            attempt + 1, roundTripTime));
                    performMultipleSync(attempt + 1, totalOffset, successfulAttempts, callback);
                }
            }

            @Override
            public void onError(Exception error) {
                Log.w(TAG, String.format("Sync attempt %d failed", attempt + 1), error);
                performMultipleSync(attempt + 1, totalOffset, successfulAttempts, callback);
            }
        });
    }

    public long getSynchronizedTime() {
        if (!isSynced) {
            Log.w(TAG, "Time not synchronized, using system time");
            return System.currentTimeMillis();
        }

        return System.currentTimeMillis() + timeOffset.get();
    }

    public long getTimeOffsetMs() {
        return timeOffset.get();
    }

    public boolean isSynchronized() {
        return isSynced;
    }

    public long getTimeSinceLastSync() {
        if (!isSynced) {
            return Long.MAX_VALUE;
        }
        return SystemClock.elapsedRealtime() - lastSyncTime.get();
    }

    public boolean shouldResync() {
        return !isSynced || getTimeSinceLastSync() > 300000; // 5 minutes
    }

    public long calculateDelayUntil(long targetSyncTime) {
        long currentSyncTime = getSynchronizedTime();
        long delay = targetSyncTime - currentSyncTime;

        Log.d(TAG, String.format("Target time: %d, Current sync time: %d, Delay: %dms",
                targetSyncTime, currentSyncTime, delay));

        return delay;
    }

    public void shutdown() {
        ntpClient.shutdown();
    }
}