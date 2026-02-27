package com.emco.multicamandroid;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.amazonaws.auth.BasicSessionCredentials;
import com.amazonaws.mobileconnectors.s3.transferutility.TransferListener;
import com.amazonaws.mobileconnectors.s3.transferutility.TransferObserver;
import com.amazonaws.mobileconnectors.s3.transferutility.TransferState;
import com.amazonaws.mobileconnectors.s3.transferutility.TransferUtility;
import com.amazonaws.regions.Region;
import com.amazonaws.regions.Regions;
import com.amazonaws.services.s3.AmazonS3Client;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.multicam.common.UploadTypes;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Manages upload queue and handles file uploads to cloud storage.
 * Uploads files to S3 using presigned URLs or IAM credentials.
 */
public class UploadManager {
    private static final String TAG = "UploadManager";
    private static final int MAX_RETRIES = 3;
    private static final String QUEUE_FILE_NAME = "uploadQueue.json";
    
    private final Context context;
    private final Gson gson;
    private final Handler mainHandler;
    private final ExecutorService uploadExecutor;
    
    // Upload queues
    private UploadItemWithCredentials currentUpload;
    private final List<UploadItemWithCredentials> pendingQueue;
    private final List<UploadItemWithCredentials> failedQueue;
    
    // Retry tracking
    private final Map<String, Integer> retryAttempts;
    
    // AWS SDK transfer tracking
    private TransferObserver currentTransferObserver;
    
    // Progress tracking
    private long uploadStartTime;
    private long lastProgressUpdate;
    private long lastBytesUploaded;
    
    // Queue file location
    private final File queueFile;
    
    public UploadManager(Context context) {
        this.context = context.getApplicationContext();
        this.gson = new GsonBuilder().create();
        this.mainHandler = new Handler(Looper.getMainLooper());
        this.uploadExecutor = Executors.newSingleThreadExecutor();
        
        this.pendingQueue = new ArrayList<>();
        this.failedQueue = new ArrayList<>();
        this.retryAttempts = new HashMap<>();
        
        // Set up queue persistence file
        this.queueFile = new File(context.getFilesDir(), QUEUE_FILE_NAME);
        
        // Load persisted queue
        loadQueue();
        
        // Start processing if there are pending items
        if (!pendingQueue.isEmpty()) {
            processNextUpload();
        }
    }
    
    /**
     * Add a file to the upload queue using presigned URL
     */
    public synchronized void queueUpload(String fileName, File file, String uploadUrl) {
        Log.i(TAG, "queueUpload: fileName=" + fileName + ", file=" + file.getAbsolutePath());
        
        // Check if already in queue
        if (isInQueue(fileName)) {
            Log.w(TAG, "File " + fileName + " already in queue");
            return;
        }
        
        // Validate file exists
        if (!file.exists() || !file.isFile()) {
            Log.e(TAG, "File does not exist: " + file.getAbsolutePath());
            return;
        }
        
        UploadTypes.UploadItem uploadItem = new UploadTypes.UploadItem();
        uploadItem.fileName = fileName;
        uploadItem.fileSize = file.length();
        uploadItem.bytesUploaded = 0;
        uploadItem.uploadProgress = 0.0;
        uploadItem.uploadSpeed = 0;
        uploadItem.status = UploadTypes.UploadStatus.QUEUED.getValue();
        uploadItem.uploadUrl = uploadUrl;
        uploadItem.error = null;
        
        UploadItemWithCredentials wrapper = new UploadItemWithCredentials(uploadItem, null);
        
        pendingQueue.add(wrapper);
        saveQueue();
        
        Log.i(TAG, "Added " + fileName + " to queue (presigned URL, " + pendingQueue.size() + " items pending)");
        
        // Start processing if no current upload
        if (currentUpload == null) {
            processNextUpload();
        }
    }
    
    /**
     * Add a file to the upload queue using IAM credentials
     */
    public synchronized void queueUploadWithIAM(String fileName, File file, 
                                                 String s3Bucket, String s3Key,
                                                 String awsAccessKeyId, String awsSecretAccessKey,
                                                 String awsSessionToken, String awsRegion) {
        Log.i(TAG, "queueUploadWithIAM: fileName=" + fileName + ", bucket=" + s3Bucket + ", key=" + s3Key);
        
        // Check if already in queue
        if (isInQueue(fileName)) {
            Log.w(TAG, "File " + fileName + " already in queue");
            return;
        }
        
        // Validate file exists
        if (!file.exists() || !file.isFile()) {
            Log.e(TAG, "File does not exist: " + file.getAbsolutePath());
            return;
        }
        
        UploadTypes.UploadItem uploadItem = new UploadTypes.UploadItem();
        uploadItem.fileName = fileName;
        uploadItem.fileSize = file.length();
        uploadItem.bytesUploaded = 0;
        uploadItem.uploadProgress = 0.0;
        uploadItem.uploadSpeed = 0;
        uploadItem.status = UploadTypes.UploadStatus.QUEUED.getValue();
        uploadItem.uploadUrl = null; // No uploadUrl for IAM method
        uploadItem.error = null;
        
        IAMCredentials credentials = new IAMCredentials(
            s3Bucket, s3Key, awsAccessKeyId, awsSecretAccessKey, awsSessionToken, awsRegion
        );
        
        UploadItemWithCredentials wrapper = new UploadItemWithCredentials(uploadItem, credentials);
        
        pendingQueue.add(wrapper);
        saveQueue();
        
        Log.i(TAG, "Added " + fileName + " to queue (IAM credentials, " + pendingQueue.size() + " items pending)");
        
        // Start processing if no current upload
        if (currentUpload == null) {
            processNextUpload();
        }
    }
    
    /**
     * Get current upload status
     */
    public synchronized List<UploadTypes.UploadItem>[] getUploadQueues() {
        List<UploadTypes.UploadItem> uploadQueue = new ArrayList<>();
        
        // Add current upload if exists
        if (currentUpload != null) {
            uploadQueue.add(currentUpload.uploadItem);
        }
        
        // Add pending uploads
        for (UploadItemWithCredentials wrapper : pendingQueue) {
            uploadQueue.add(wrapper.uploadItem);
        }
        
        // Add failed uploads
        List<UploadTypes.UploadItem> failedItems = new ArrayList<>();
        for (UploadItemWithCredentials wrapper : failedQueue) {
            failedItems.add(wrapper.uploadItem);
        }
        
        @SuppressWarnings("unchecked")
        List<UploadTypes.UploadItem>[] result = new List[] {uploadQueue, failedItems};
        return result;
    }
    
    /**
     * Retry a failed upload
     */
    public synchronized void retryFailedUpload(String fileName) {
        int index = -1;
        for (int i = 0; i < failedQueue.size(); i++) {
            if (failedQueue.get(i).uploadItem.fileName.equals(fileName)) {
                index = i;
                break;
            }
        }
        
        if (index == -1) {
            Log.w(TAG, "Failed upload not found: " + fileName);
            return;
        }
        
        UploadItemWithCredentials wrapper = failedQueue.remove(index);
        
        // Reset retry count and status
        retryAttempts.put(fileName, 0);
        wrapper.uploadItem.status = UploadTypes.UploadStatus.QUEUED.getValue();
        wrapper.uploadItem.bytesUploaded = 0;
        wrapper.uploadItem.uploadProgress = 0.0;
        wrapper.uploadItem.uploadSpeed = 0;
        wrapper.uploadItem.error = null;
        
        pendingQueue.add(wrapper);
        saveQueue();
        
        Log.i(TAG, "Retrying failed upload: " + fileName);
        
        if (currentUpload == null) {
            processNextUpload();
        }
    }
    
    /**
     * Clear failed queue
     */
    public synchronized void clearFailedQueue() {
        failedQueue.clear();
        saveQueue();
        Log.i(TAG, "Failed queue cleared");
    }
    
    /**
     * Cleanup resources
     */
    public void cleanup() {
        Log.i(TAG, "Cleaning up UploadManager");
        uploadExecutor.shutdownNow();
    }
    
    // Private methods
    
    private synchronized void processNextUpload() {
        if (currentUpload != null || pendingQueue.isEmpty()) {
            return;
        }
        
        UploadItemWithCredentials wrapper = pendingQueue.remove(0);
        currentUpload = wrapper;
        saveQueue();
        
        Log.i(TAG, "Starting upload for " + wrapper.uploadItem.fileName);
        
        // Execute upload on background thread
        uploadExecutor.execute(() -> startUpload(wrapper));
    }
    
    private void startUpload(UploadItemWithCredentials wrapper) {
        UploadTypes.UploadItem item = wrapper.uploadItem;
        
        try {
            // Get file
            // We assume the file is in the external files dir with the given filename
            // Or we could store the full path in the UploadItem, but UploadItem is from common lib
            // So we'll reconstruct the path.
            // Note: In queueUpload we verified existence, but it might have changed.
            
            // Remove .mp4 extension to get fileId if needed, but here we expect fileName to be the full name
            File file = new File(context.getExternalFilesDir(null), item.fileName);
            
            if (!file.exists()) {
                handleUploadFailure(wrapper, "File not found: " + item.fileName);
                return;
            }
            
            // Update item with status
            synchronized (this) {
                if (currentUpload != null && currentUpload.uploadItem.fileName.equals(item.fileName)) {
                    currentUpload.uploadItem.status = UploadTypes.UploadStatus.UPLOADING.getValue();
                }
            }
            
            // Perform upload using appropriate method
            if (wrapper.iamCredentials != null) {
                // Use AWS SDK with IAM credentials
                uploadToS3WithSDK(wrapper, file);
            } else {
                // Use presigned URL
                uploadToS3WithPresignedUrl(wrapper, file);
            }
            
        } catch (Exception e) {
            Log.e(TAG, "Error during upload", e);
            handleUploadFailure(wrapper, "Upload error: " + e.getMessage());
        }
    }
    
    /**
     * Upload to S3 using presigned URL (legacy method)
     */
    private void uploadToS3WithPresignedUrl(UploadItemWithCredentials wrapper, File file) {
        UploadTypes.UploadItem item = wrapper.uploadItem;
        HttpURLConnection connection = null;
        
        try {
            URL url = new URL(item.uploadUrl);
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("PUT");
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(file.length());
            
            // CRITICAL: HttpURLConnection automatically adds "Content-Type: application/x-www-form-urlencoded"
            // when setDoOutput(true) is called. This breaks S3 presigned URLs that don't include Content-Type.
            // We must explicitly set it to empty string to prevent the default.
            connection.setRequestProperty("Content-Type", "");
            
            Log.i(TAG, "Uploading to S3 with presigned URL: " + item.fileName);
            
            // Initialize progress tracking
            uploadStartTime = System.currentTimeMillis();
            lastProgressUpdate = uploadStartTime;
            lastBytesUploaded = 0;
            
            // Upload file
            try (FileInputStream fis = new FileInputStream(file);
                 OutputStream os = connection.getOutputStream()) {
                
                byte[] buffer = new byte[8192];
                int bytesRead;
                long totalUploaded = 0;
                
                while ((bytesRead = fis.read(buffer)) != -1) {
                    os.write(buffer, 0, bytesRead);
                    totalUploaded += bytesRead;
                    
                    // Update progress
                    updateProgress(item, totalUploaded, file.length());
                }
                
                os.flush();
            }
            
            // Get response code
            int responseCode = connection.getResponseCode();
            Log.i(TAG, "Upload response code: " + responseCode);
            
            if (responseCode >= 200 && responseCode < 300) {
                handleUploadSuccess(wrapper);
            } else {
                String errorMsg = "HTTP " + responseCode;
                try {
                    String responseMessage = connection.getResponseMessage();
                    if (responseMessage != null) {
                        errorMsg += " - " + responseMessage;
                    }
                    
                    // Try to read error response body for more details
                    java.io.InputStream errorStream = connection.getErrorStream();
                    if (errorStream != null) {
                        java.io.BufferedReader reader = new java.io.BufferedReader(
                            new java.io.InputStreamReader(errorStream));
                        StringBuilder errorBody = new StringBuilder();
                        String line;
                        while ((line = reader.readLine()) != null) {
                            errorBody.append(line);
                        }
                        reader.close();
                        Log.e(TAG, "S3 Error Response: " + errorBody.toString());
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Error reading error response", e);
                }
                handleUploadFailure(wrapper, errorMsg);
            }
            
        } catch (IOException e) {
            Log.e(TAG, "Upload failed", e);
            handleUploadFailure(wrapper, "Network error: " + e.getMessage());
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }
    
    /**
     * Upload to S3 using AWS SDK with IAM credentials (supports multipart uploads)
     */
    private void uploadToS3WithSDK(UploadItemWithCredentials wrapper, File file) {
        UploadTypes.UploadItem item = wrapper.uploadItem;
        IAMCredentials creds = wrapper.iamCredentials;
        
        try {
            Log.i(TAG, "Uploading to S3 with IAM credentials: " + item.fileName + 
                  " to s3://" + creds.s3Bucket + "/" + creds.s3Key);
            
            // Create AWS credentials from IAM temporary credentials
            BasicSessionCredentials awsCredentials = new BasicSessionCredentials(
                creds.awsAccessKeyId,
                creds.awsSecretAccessKey,
                creds.awsSessionToken
            );
            
            // Create S3 client with credentials and region
            AmazonS3Client s3Client = new AmazonS3Client(awsCredentials);
            s3Client.setRegion(Region.getRegion(Regions.fromName(creds.awsRegion)));
            
            // Create TransferUtility for managed uploads (handles multipart automatically)
            TransferUtility transferUtility = TransferUtility.builder()
                .context(context)
                .s3Client(s3Client)
                .build();
            
            // Initialize progress tracking
            uploadStartTime = System.currentTimeMillis();
            lastProgressUpdate = uploadStartTime;
            lastBytesUploaded = 0;
            
            // Start upload
            TransferObserver observer = transferUtility.upload(
                creds.s3Bucket,
                creds.s3Key,
                file
            );
            
            currentTransferObserver = observer;
            
            // Set up transfer listener for progress tracking
            observer.setTransferListener(new TransferListener() {
                @Override
                public void onStateChanged(int id, TransferState state) {
                    Log.i(TAG, "Transfer state changed: " + state);
                    
                    if (state == TransferState.COMPLETED) {
                        // Upload succeeded
                        currentTransferObserver = null;
                        handleUploadSuccess(wrapper);
                        
                    } else if (state == TransferState.FAILED || state == TransferState.CANCELED) {
                        // Upload failed
                        currentTransferObserver = null;
                        handleUploadFailure(wrapper, "Transfer " + state.toString().toLowerCase());
                    }
                }
                
                @Override
                public void onProgressChanged(int id, long bytesCurrent, long bytesTotal) {
                    // Update progress
                    updateProgress(item, bytesCurrent, bytesTotal);
                }
                
                @Override
                public void onError(int id, Exception ex) {
                    Log.e(TAG, "Transfer error", ex);
                    currentTransferObserver = null;
                    handleUploadFailure(wrapper, "Transfer error: " + ex.getMessage());
                }
            });
            
        } catch (Exception e) {
            Log.e(TAG, "AWS SDK upload failed", e);
            currentTransferObserver = null;
            handleUploadFailure(wrapper, "AWS SDK error: " + e.getMessage());
        }
    }
    
    private void updateProgress(UploadTypes.UploadItem item, long totalUploaded, long totalSize) {
        long now = System.currentTimeMillis();
        
        // Calculate progress percentage
        double progress = (double) totalUploaded / totalSize * 100.0;
        
        // Calculate upload speed
        long speed = 0;
        long timeDelta = now - lastProgressUpdate;
        if (timeDelta > 0) {
            long bytesDelta = totalUploaded - lastBytesUploaded;
            speed = bytesDelta * 1000 / timeDelta; // bytes per second
        }
        
        // Update tracking
        lastProgressUpdate = now;
        lastBytesUploaded = totalUploaded;
        
        // Update current upload item
        synchronized (this) {
            if (currentUpload != null && currentUpload.uploadItem.fileName.equals(item.fileName)) {
                currentUpload.uploadItem.bytesUploaded = totalUploaded;
                currentUpload.uploadItem.uploadProgress = progress;
                currentUpload.uploadItem.uploadSpeed = speed;
            }
        }
    }
    
    private synchronized void handleUploadSuccess(UploadItemWithCredentials wrapper) {
        UploadTypes.UploadItem item = wrapper.uploadItem;
        Log.i(TAG, "Upload succeeded for " + item.fileName);
        
        // We do NOT delete the file after upload in this implementation
        // The file management is handled by NetworkController/User
        
        // Clear retry count
        retryAttempts.remove(item.fileName);
        
        // Clear current upload
        currentUpload = null;
        saveQueue();
        
        // Process next upload
        mainHandler.post(this::processNextUpload);
    }
    
    private synchronized void handleUploadFailure(UploadItemWithCredentials wrapper, String error) {
        UploadTypes.UploadItem item = wrapper.uploadItem;
        Log.w(TAG, "Upload failed for " + item.fileName + ": " + error);
        
        int attempts = retryAttempts.getOrDefault(item.fileName, 0) + 1;
        retryAttempts.put(item.fileName, attempts);
        
        if (attempts < MAX_RETRIES) {
            // Retry with exponential backoff
            long delay = (long) Math.pow(2, attempts) * 1000; // 2s, 4s, 8s
            Log.i(TAG, "Retrying " + item.fileName + " in " + delay + "ms (attempt " + 
                  attempts + "/" + MAX_RETRIES + ")");
            
            // Re-add to front of queue
            item.status = UploadTypes.UploadStatus.QUEUED.getValue();
            item.error = error;
            pendingQueue.add(0, wrapper);
            currentUpload = null;
            saveQueue();
            
            // Schedule retry
            mainHandler.postDelayed(this::processNextUpload, delay);
            
        } else {
            // Move to failed queue
            Log.e(TAG, "Max retries reached for " + item.fileName + ", moving to failed queue");
            
            item.status = UploadTypes.UploadStatus.FAILED.getValue();
            item.error = error;
            failedQueue.add(wrapper);
            retryAttempts.remove(item.fileName);
            currentUpload = null;
            saveQueue();
            
            // Process next upload
            mainHandler.post(this::processNextUpload);
        }
    }
    
    // Helper methods
    
    private boolean isInQueue(String fileName) {
        if (currentUpload != null && currentUpload.uploadItem.fileName.equals(fileName)) {
            return true;
        }
        
        for (UploadItemWithCredentials wrapper : pendingQueue) {
            if (wrapper.uploadItem.fileName.equals(fileName)) {
                return true;
            }
        }
        
        return false;
    }
    
    // Queue persistence
    
    private synchronized void saveQueue() {
        try {
            QueueData queueData = new QueueData(
                pendingQueue,
                failedQueue,
                retryAttempts
            );
            
            String json = gson.toJson(queueData);
            try (FileOutputStream fos = new FileOutputStream(queueFile)) {
                fos.write(json.getBytes("UTF-8"));
            }
            
        } catch (IOException e) {
            Log.e(TAG, "Failed to save queue", e);
        }
    }
    
    private synchronized void loadQueue() {
        if (!queueFile.exists()) {
            return;
        }
        
        try {
            StringBuilder json = new StringBuilder();
            try (FileInputStream fis = new FileInputStream(queueFile)) {
                byte[] buffer = new byte[8192];
                int length;
                while ((length = fis.read(buffer)) != -1) {
                    json.append(new String(buffer, 0, length, "UTF-8"));
                }
            }
            
            QueueData queueData = gson.fromJson(json.toString(), QueueData.class);
            
            if (queueData != null) {
                pendingQueue.clear();
                pendingQueue.addAll(queueData.pending);
                
                failedQueue.clear();
                failedQueue.addAll(queueData.failed);
                
                retryAttempts.clear();
                retryAttempts.putAll(queueData.retryAttempts);
                
                Log.i(TAG, "Queue loaded (" + pendingQueue.size() + " pending, " + 
                      failedQueue.size() + " failed)");
            }
            
        } catch (Exception e) {
            Log.e(TAG, "Failed to load queue", e);
        }
    }
    
    // Supporting classes
    
    /**
     * Wrapper class to store UploadItem with optional IAM credentials
     */
    private static class UploadItemWithCredentials {
        UploadTypes.UploadItem uploadItem;
        IAMCredentials iamCredentials;  // null if using presigned URL
        
        UploadItemWithCredentials() {
            // For Gson deserialization
        }
        
        UploadItemWithCredentials(UploadTypes.UploadItem uploadItem, IAMCredentials iamCredentials) {
            this.uploadItem = uploadItem;
            this.iamCredentials = iamCredentials;
        }
    }
    
    /**
     * IAM credentials for S3 upload
     */
    private static class IAMCredentials {
        String s3Bucket;
        String s3Key;
        String awsAccessKeyId;
        String awsSecretAccessKey;
        String awsSessionToken;
        String awsRegion;
        
        IAMCredentials() {
            // For Gson deserialization
        }
        
        IAMCredentials(String s3Bucket, String s3Key, String awsAccessKeyId, 
                      String awsSecretAccessKey, String awsSessionToken, String awsRegion) {
            this.s3Bucket = s3Bucket;
            this.s3Key = s3Key;
            this.awsAccessKeyId = awsAccessKeyId;
            this.awsSecretAccessKey = awsSecretAccessKey;
            this.awsSessionToken = awsSessionToken;
            this.awsRegion = awsRegion;
        }
    }
    
    /**
     * Queue data for persistence
     */
    private static class QueueData {
        List<UploadItemWithCredentials> pending;
        List<UploadItemWithCredentials> failed;
        Map<String, Integer> retryAttempts;
        
        QueueData(List<UploadItemWithCredentials> pending, 
                  List<UploadItemWithCredentials> failed,
                  Map<String, Integer> retryAttempts) {
            this.pending = pending;
            this.failed = failed;
            this.retryAttempts = retryAttempts;
        }
    }
}

