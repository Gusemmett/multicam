package com.multicam.common;

/**
 * Network and protocol constants for MultiCam API.
 */
public class Constants {
    // Network Configuration

    /** TCP port for device server */
    public static final int TCP_PORT = 8080;

    /** mDNS service type for device discovery */
    public static final String SERVICE_TYPE = "_multicam._tcp.local.";

    // NTP Configuration

    /** NTP server for time synchronization */
    public static final String NTP_SERVER = "pool.ntp.org";

    /** NTP protocol port */
    public static final int NTP_PORT = 123;

    /** Maximum acceptable NTP round-trip time in seconds */
    public static final double MAX_ACCEPTABLE_RTT = 0.5;

    // Synchronization

    /** Default delay for synchronized recording start (seconds) */
    public static final double SYNC_DELAY = 3.0;

    // Timeouts

    /** Command timeout in seconds */
    public static final double COMMAND_TIMEOUT = 60.0;

    /** Download stall timeout in seconds (10 minutes) */
    public static final double DOWNLOAD_STALL_TIMEOUT = 600.0;

    // Transfer Configuration

    /** Chunk size for file downloads (bytes) */
    public static final int DOWNLOAD_CHUNK_SIZE = 8192;

    // File ID Format

    /**
     * File ID format pattern.
     * <p>
     * Example: Mountain-A1B2C3D4_1729000000123
     */
    public static final String FILE_ID_FORMAT = "{deviceId}_{timestamp}";

    /**
     * Generate a file ID for the current device and time.
     *
     * @param deviceId Device identifier
     * @return File ID string
     */
    public static String generateFileId(String deviceId) {
        long timestamp = System.currentTimeMillis();
        return String.format("%s_%d", deviceId, timestamp);
    }

    private Constants() {
        // Prevent instantiation
    }
}
