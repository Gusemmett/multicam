package com.multicam.common;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.util.List;
import java.util.ArrayList;

/**
 * File-related data types for MultiCam API.
 */
public class FileTypes {
    private static final Gson gson = new GsonBuilder().create();

    /**
     * Metadata for a single video file.
     */
    public static class FileMetadata {
        /** Filename */
        public String fileName;

        /** File size in bytes */
        public long fileSize;

        /** File creation time (Unix timestamp) */
        public double creationDate;

        /** File modification time (Unix timestamp) */
        public double modificationDate;

        public FileMetadata() {
        }

        public FileMetadata(String fileName, long fileSize,
                          double creationDate, double modificationDate) {
            this.fileName = fileName;
            this.fileSize = fileSize;
            this.creationDate = creationDate;
            this.modificationDate = modificationDate;
        }
    }

    /**
     * Header for binary file transfer.
     * <p>
     * This is sent as JSON before the binary file data in GET_VIDEO responses.
     * <p>
     * Binary protocol:
     * <ol>
     *   <li>Header size (4 bytes, big-endian uint32)</li>
     *   <li>JSON FileResponse header</li>
     *   <li>Binary file data</li>
     * </ol>
     */
    public static class FileResponse {
        /** Device that owns the file */
        public String deviceId;

        /** Filename */
        public String fileName;

        /** File size in bytes */
        public long fileSize;

        /** Status (typically "ready") */
        public String status;

        public FileResponse() {
        }

        public FileResponse(String deviceId, String fileName,
                          long fileSize, String status) {
            this.deviceId = deviceId;
            this.fileName = fileName;
            this.fileSize = fileSize;
            this.status = status;
        }

        /**
         * Serialize file response to JSON string.
         *
         * @return JSON string representation
         */
        public String toJson() {
            return gson.toJson(this);
        }

        /**
         * Deserialize file response from JSON string.
         *
         * @param json JSON string to parse
         * @return FileResponse instance
         */
        public static FileResponse fromJson(String json) {
            return gson.fromJson(json, FileResponse.class);
        }
    }

    /**
     * Response to LIST_FILES command.
     * <p>
     * Note: This command may not be supported on all platforms.
     */
    public static class ListFilesResponse {
        /** Device ID */
        public String deviceId;

        /** Status (see DeviceStatus enum) */
        public String status;

        /** Response timestamp */
        public double timestamp;

        /** List of available files */
        public List<FileMetadata> files;

        public ListFilesResponse() {
            this.files = new ArrayList<>();
        }

        public ListFilesResponse(String deviceId, String status, double timestamp,
                               List<FileMetadata> files) {
            this.deviceId = deviceId;
            this.status = status;
            this.timestamp = timestamp;
            this.files = files != null ? files : new ArrayList<>();
        }

        /**
         * Serialize list files response to JSON string.
         *
         * @return JSON string representation
         */
        public String toJson() {
            return gson.toJson(this);
        }

        /**
         * Deserialize list files response from JSON string.
         *
         * @param json JSON string to parse
         * @return ListFilesResponse instance
         */
        public static ListFilesResponse fromJson(String json) {
            return gson.fromJson(json, ListFilesResponse.class);
        }
    }

    /**
     * Response to STOP_RECORDING command.
     */
    public static class StopRecordingResponse {
        /** Device ID */
        public String deviceId;

        /** Device status (typically "recording_stopped") */
        public String status;

        /** Response timestamp */
        public double timestamp;

        /** File name of the recorded video */
        public String fileName;

        /** File size in bytes */
        public long fileSize;

        public StopRecordingResponse() {
        }

        public StopRecordingResponse(String deviceId, String status, double timestamp,
                                    String fileName, long fileSize) {
            this.deviceId = deviceId;
            this.status = status;
            this.timestamp = timestamp;
            this.fileName = fileName;
            this.fileSize = fileSize;
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
         * @return StopRecordingResponse instance
         */
        public static StopRecordingResponse fromJson(String json) {
            return gson.fromJson(json, StopRecordingResponse.class);
        }
    }

    /**
     * Error response from a MultiCam device.
     */
    public static class ErrorResponse {
        /** Device ID */
        public String deviceId;

        /** Error status (e.g., "file_not_found", "error") */
        public String status;

        /** Response timestamp */
        public double timestamp;

        /** Human-readable error message */
        public String message;

        public ErrorResponse() {
        }

        public ErrorResponse(String deviceId, String status, double timestamp, String message) {
            this.deviceId = deviceId;
            this.status = status;
            this.timestamp = timestamp;
            this.message = message;
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
         * @return ErrorResponse instance
         */
        public static ErrorResponse fromJson(String json) {
            return gson.fromJson(json, ErrorResponse.class);
        }
    }
}
