package com.multicam.common;

import com.google.gson.annotations.SerializedName;

/**
 * Device status values used in API responses.
 * <p>
 * All status values use lowercase snake_case for consistency across platforms.
 */
public enum DeviceStatus {
    /** Device is idle and ready for commands */
    @SerializedName("ready")
    READY("ready"),

    /** Currently recording video */
    @SerializedName("recording")
    RECORDING("recording"),

    /** Recording stop in progress */
    @SerializedName("stopping")
    STOPPING("stopping"),

    /** Error state (check message field for details) */
    @SerializedName("error")
    ERROR("error"),

    /** Future recording has been scheduled and accepted */
    @SerializedName("scheduled_recording_accepted")
    SCHEDULED_RECORDING_ACCEPTED("scheduled_recording_accepted"),

    /** Recording completed successfully */
    @SerializedName("recording_stopped")
    RECORDING_STOPPED("recording_stopped"),

    /** Command acknowledged */
    @SerializedName("command_received")
    COMMAND_RECEIVED("command_received"),

    /** Device clock not synchronized via NTP */
    @SerializedName("time_not_synchronized")
    TIME_NOT_SYNCHRONIZED("time_not_synchronized"),

    /** Requested file does not exist */
    @SerializedName("file_not_found")
    FILE_NOT_FOUND("file_not_found"),

    /** Currently uploading file to cloud */
    @SerializedName("uploading")
    UPLOADING("uploading"),

    /** Upload added to queue */
    @SerializedName("upload_queued")
    UPLOAD_QUEUED("upload_queued"),

    /** Upload completed successfully (file auto-deleted) */
    @SerializedName("upload_completed")
    UPLOAD_COMPLETED("upload_completed"),

    /** Upload failed (check message field for error) */
    @SerializedName("upload_failed")
    UPLOAD_FAILED("upload_failed");

    private final String value;

    DeviceStatus(String value) {
        this.value = value;
    }

    /**
     * Get the string value of this status.
     *
     * @return Status string value
     */
    public String getValue() {
        return value;
    }

    /**
     * Check if this status indicates a successful operation.
     *
     * @return true if status indicates success, false otherwise
     */
    public boolean isSuccess() {
        switch (this) {
            case READY:
            case RECORDING:
            case SCHEDULED_RECORDING_ACCEPTED:
            case COMMAND_RECEIVED:
            case RECORDING_STOPPED:
            case STOPPING:
            case UPLOADING:
            case UPLOAD_QUEUED:
            case UPLOAD_COMPLETED:
                return true;
            case ERROR:
            case TIME_NOT_SYNCHRONIZED:
            case FILE_NOT_FOUND:
            case UPLOAD_FAILED:
                return false;
            default:
                return false;
        }
    }

    /**
     * Check if this status indicates an error.
     *
     * @return true if status indicates an error, false otherwise
     */
    public boolean isError() {
        return !isSuccess();
    }

    /**
     * Get DeviceStatus from string value.
     *
     * @param value Status string value
     * @return DeviceStatus enum value, or null if not found
     */
    public static DeviceStatus fromValue(String value) {
        for (DeviceStatus status : values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        return null;
    }
}
