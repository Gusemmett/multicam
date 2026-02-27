package com.emco.multicamandroid;

import android.util.Log;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NTPClient {
    private static final String TAG = "NTPClient";
    private static final String DEFAULT_NTP_SERVER = "pool.ntp.org";
    private static final int NTP_PORT = 123;
    private static final int NTP_PACKET_SIZE = 48;
    private static final int TIMEOUT_MS = 5000;

    private final ExecutorService executor;
    private final String ntpServer;

    public NTPClient() {
        this(DEFAULT_NTP_SERVER);
    }

    public NTPClient(String ntpServer) {
        this.ntpServer = ntpServer;
        this.executor = Executors.newCachedThreadPool();
    }

    public interface TimeCallback {
        void onTimeReceived(long ntpTime, long roundTripTime);
        void onError(Exception error);
    }

    public CompletableFuture<Long> getNTPTime() {
        CompletableFuture<Long> future = new CompletableFuture<>();

        getNTPTime(new TimeCallback() {
            @Override
            public void onTimeReceived(long ntpTime, long roundTripTime) {
                future.complete(ntpTime);
            }

            @Override
            public void onError(Exception error) {
                future.completeExceptionally(error);
            }
        });

        return future;
    }

    public void getNTPTime(TimeCallback callback) {
        executor.execute(() -> {
            DatagramSocket socket = null;
            try {
                long t1 = System.currentTimeMillis();

                socket = new DatagramSocket();
                socket.setSoTimeout(TIMEOUT_MS);

                InetAddress address = InetAddress.getByName(ntpServer);

                byte[] buffer = new NTPMessage().toByteArray();
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length, address, NTP_PORT);

                socket.send(packet);

                DatagramPacket response = new DatagramPacket(new byte[NTP_PACKET_SIZE], NTP_PACKET_SIZE);
                socket.receive(response);

                long t2 = System.currentTimeMillis();

                NTPMessage message = new NTPMessage(response.getData());
                long ntpTime = message.getTransmitTimestamp();
                long roundTripTime = t2 - t1;

                Log.d(TAG, String.format("NTP time received: %d, RTT: %dms", ntpTime, roundTripTime));

                callback.onTimeReceived(ntpTime, roundTripTime);

            } catch (Exception e) {
                Log.e(TAG, "Failed to get NTP time", e);
                callback.onError(e);
            } finally {
                if (socket != null && !socket.isClosed()) {
                    socket.close();
                }
            }
        });
    }

    public void shutdown() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(1, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    private static class NTPMessage {
        private byte[] data = new byte[NTP_PACKET_SIZE];

        public NTPMessage() {
            data[0] = 0x1B;
        }

        public NTPMessage(byte[] data) {
            this.data = data.clone();
        }

        public byte[] toByteArray() {
            return data.clone();
        }

        public long getTransmitTimestamp() {
            long seconds = 0;
            long fraction = 0;

            for (int i = 0; i < 4; i++) {
                seconds = (seconds << 8) | (data[40 + i] & 0xff);
            }

            for (int i = 0; i < 4; i++) {
                fraction = (fraction << 8) | (data[44 + i] & 0xff);
            }

            long ntpTime = ((seconds - 0x83AA7E80L) * 1000) + ((fraction * 1000L) / 0x100000000L);
            return ntpTime;
        }
    }
}