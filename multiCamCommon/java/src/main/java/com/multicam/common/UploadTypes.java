package com.multicam.common;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.util.List;
import java.util.ArrayList;

/**
 * Upload-related data types for MultiCam API.
 */
public class UploadTypes {
    private static final Gson gson = new GsonBuilder().create();

    /**
     * Upload item status values.
     */
    public enum UploadStatus {
        /** Upload is queued and waiting */
        QUEUED("queued"),

        /** Upload is currently in progress */
        UPLOADING("uploading"),

        /** Upload completed successfully */
        COMPLETED("completed"),

        /** Upload failed (see error field) */
        FAILED("failed");

        private final String value;

        UploadStatus(String value) {
            this.value = value;
        }

        public String getValue() {
            return value;
        }

        public static UploadStatus fromValue(String value) {
            for (UploadStatus status : values()) {
                if (status.value.equals(value)) {
                    return status;
                }
            }
            return null;
        }
    }

    /**
     * Upload item with progress information.
     * <p>
     * Represents a single file upload in the device's upload queue.
     */
    public static class UploadItem {
        /** Filename */
        public String fileName;

        /** Total file size in bytes */
        public long fileSize;

        /** Bytes uploaded so far */
        public long bytesUploaded;

        /** Upload progress percentage (0-100) */
        public double uploadProgress;

        /** Current upload speed in bytes per second */
        public long uploadSpeed;

        /** Upload status (queued, uploading, completed, failed) */
        public String status;

        /** Presigned S3 URL for upload (only present when using presigned URL auth) */
        public String uploadUrl;

        /** Error message if upload failed */
        public String error;

        public UploadItem() {
        }

        public UploadItem(String fileName, long fileSize, long bytesUploaded,
                         double uploadProgress, long uploadSpeed, String status,
                         String uploadUrl, String error) {
            this.fileName = fileName;
            this.fileSize = fileSize;
            this.bytesUploaded = bytesUploaded;
            this.uploadProgress = uploadProgress;
            this.uploadSpeed = uploadSpeed;
            this.status = status;
            this.uploadUrl = uploadUrl;
            this.error = error;
        }

        /**
         * Get the status as an UploadStatus enum value.
         *
         * @return UploadStatus enum value, or null if unknown
         */
        public UploadStatus getUploadStatus() {
            return UploadStatus.fromValue(status);
        }
    }
}
