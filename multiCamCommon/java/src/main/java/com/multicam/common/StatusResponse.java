package com.multicam.common;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.util.List;
import java.util.ArrayList;
import com.multicam.common.UploadTypes.UploadItem;

/**
 * Status response from a MultiCam device.
 */
public class StatusResponse {
    private static final Gson gson = new GsonBuilder().create();

    /** Unique identifier of the responding device */
    public String deviceId;

    /** Device status (see DeviceStatus enum for standard values) */
    public String status;

    /** Unix timestamp when response was generated */
    public double timestamp;

    /** Battery percentage (0.0-100.0), null if unavailable */
    public Double batteryLevel;

    /** Type of device (e.g., "iOS", "Android", "Desktop"), null if unavailable */
    public String deviceType;

    /** Upload queue (includes in-progress and queued uploads) */
    public List<UploadItem> uploadQueue;

    /** Failed upload queue */
    public List<UploadItem> failedUploadQueue;

    public StatusResponse() {
        this.uploadQueue = new ArrayList<>();
        this.failedUploadQueue = new ArrayList<>();
    }

    public StatusResponse(String deviceId, String status, double timestamp) {
        this.deviceId = deviceId;
        this.status = status;
        this.timestamp = timestamp;
        this.uploadQueue = new ArrayList<>();
        this.failedUploadQueue = new ArrayList<>();
    }

    /**
     * Get the status as a DeviceStatus enum value.
     *
     * @return DeviceStatus enum value, or null if unknown
     */
    public DeviceStatus getDeviceStatus() {
        return DeviceStatus.fromValue(status);
    }

    /**
     * Serialize response to JSON string.
     *
     * @return JSON string representation
     */
    public String toJson() {
        return gson.toJson(this);
    }

    /**
     * Deserialize response from JSON string.
     *
     * @param json JSON string to parse
     * @return StatusResponse instance
     */
    public static StatusResponse fromJson(String json) {
        return gson.fromJson(json, StatusResponse.class);
    }
}
