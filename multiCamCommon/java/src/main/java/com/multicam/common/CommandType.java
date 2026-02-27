package com.multicam.common;

import com.google.gson.annotations.SerializedName;

/**
 * Available command types for the MultiCam API.
 */
public enum CommandType {
    /** Start video recording (immediate or scheduled) */
    @SerializedName("START_RECORDING")
    START_RECORDING,

    /** Stop current recording and return file ID */
    @SerializedName("STOP_RECORDING")
    STOP_RECORDING,

    /** Query current device status */
    @SerializedName("DEVICE_STATUS")
    DEVICE_STATUS,

    /** Download video file (binary protocol) */
    @SerializedName("GET_VIDEO")
    GET_VIDEO,

    /** Health check ping */
    @SerializedName("HEARTBEAT")
    HEARTBEAT,

    /** List available video files (may not be supported on all platforms) */
    @SerializedName("LIST_FILES")
    LIST_FILES,

    /** Upload video file to cloud using presigned S3 URL */
    @SerializedName("UPLOAD_TO_CLOUD")
    UPLOAD_TO_CLOUD
}
