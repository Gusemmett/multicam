package com.emco.multicamandroid;

import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.util.Log;

import com.google.gson.JsonSyntaxException;
import com.multicam.common.CommandMessage;
import com.multicam.common.CommandType;
import com.multicam.common.Constants;
import com.multicam.common.DeviceStatus;
import com.multicam.common.DeviceType;
import com.multicam.common.FileTypes;
import com.multicam.common.StatusResponse;
import com.multicam.common.UploadTypes;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

import javax.jmdns.JmDNS;
import javax.jmdns.ServiceInfo;

public class NetworkController {
    private static final String TAG = "NetworkController";

    private final Context context;
    private final CameraController cameraController;
    private final String deviceId;
    private final UploadManager uploadManager;

    private ServerSocket serverSocket;
    private ExecutorService serverExecutor;
    private final AtomicBoolean isRunning = new AtomicBoolean(false);

    // mDNS service discovery
    private JmDNS jmdns;
    private ServiceInfo serviceInfo;

    // File storage
    private final Map<String, File> recordedFiles = new HashMap<>();
    private String currentRecordingFileId = null; // Track the active recording fileId

    // Upload queue tracking
    private final List<UploadTypes.UploadItem> uploadQueue = new ArrayList<>();
    private final List<UploadTypes.UploadItem> failedUploadQueue = new ArrayList<>();

    // Synchronization for waiting on video processing
    private final Object processingLock = new Object();
    private volatile boolean isProcessingComplete = false;

    public interface NetworkCallback {
        void onServerStarted();
        void onServerStopped();
        void onServerError(String error);
        void onClientConnected(String clientAddress);
        void onClientDisconnected(String clientAddress);
    }

    private NetworkCallback callback;

    public NetworkController(Context context, CameraController cameraController) {
        this.context = context;
        this.cameraController = cameraController;
        this.deviceId = getDeviceId();
        this.serverExecutor = Executors.newCachedThreadPool();
        this.uploadManager = new UploadManager(context);
    }

    private java.net.InetAddress findBestIPv4Address() {
        try {
            java.util.List<java.net.NetworkInterface> interfaces = java.util.Collections.list(java.net.NetworkInterface.getNetworkInterfaces());

            // Look for wlan0 first (WiFi)
            for (java.net.NetworkInterface intf : interfaces) {
                if (intf.isUp() && !intf.isLoopback() && intf.getName().equals("wlan0")) {
                    java.util.List<java.net.InetAddress> addresses = java.util.Collections.list(intf.getInetAddresses());
                    for (java.net.InetAddress addr : addresses) {
                        if (!addr.isLoopbackAddress() && addr.getAddress().length == 4) { // IPv4
                            return addr;
                        }
                    }
                }
            }

            // Fallback: find any IPv4 address
            for (java.net.NetworkInterface intf : interfaces) {
                if (intf.isUp() && !intf.isLoopback()) {
                    java.util.List<java.net.InetAddress> addresses = java.util.Collections.list(intf.getInetAddresses());
                    for (java.net.InetAddress addr : addresses) {
                        if (!addr.isLoopbackAddress() && addr.getAddress().length == 4) { // IPv4
                            return addr;
                        }
                    }
                }
            }

        } catch (java.net.SocketException e) {
            Log.e(TAG, "Error finding IPv4 address", e);
        }

        try {
            return java.net.InetAddress.getLocalHost();
        } catch (java.net.UnknownHostException e) {
            Log.e(TAG, "Error getting localhost", e);
            throw new RuntimeException("Cannot find suitable IP address for mDNS");
        }
    }

    private String getDeviceId() {
        return DeviceIdGenerator.getDeviceId(context);
    }

    public void setCallback(NetworkCallback callback) {
        this.callback = callback;
    }

    public void startServer() {
        if (isRunning.get()) {
            return;
        }

        serverExecutor.execute(() -> {
            try {
                // Bind to all IPv4 interfaces specifically
                serverSocket = new ServerSocket();
                serverSocket.setReuseAddress(true);
                serverSocket.bind(new java.net.InetSocketAddress("0.0.0.0", Constants.TCP_PORT));
                isRunning.set(true);

                // Start mDNS service advertisement
                startmDNSService();

                if (callback != null) {
                    callback.onServerStarted();
                }

                // Accept client connections
                while (isRunning.get() && !serverSocket.isClosed()) {
                    try {
                        Socket clientSocket = serverSocket.accept();
                        String clientAddress = clientSocket.getRemoteSocketAddress().toString();

                        if (callback != null) {
                            callback.onClientConnected(clientAddress);
                        }

                        // Handle client in separate thread
                        serverExecutor.execute(() -> handleClient(clientSocket));

                    } catch (IOException e) {
                        if (isRunning.get()) {
                            Log.e(TAG, "Error accepting client connection", e);
                        }
                    }
                }

            } catch (IOException e) {
                Log.e(TAG, "Failed to start server", e);
                if (callback != null) {
                    callback.onServerError("Failed to start server: " + e.getMessage());
                }
            } finally {
                stopServer();
            }
        });
    }

    public void stopServer() {
        if (!isRunning.get()) {
            return;
        }

        Log.i(TAG, "Stopping server...");
        isRunning.set(false);

        try {
            if (serverSocket != null && !serverSocket.isClosed()) {
                serverSocket.close();
            }
        } catch (IOException e) {
            Log.e(TAG, "Error closing server socket", e);
        }

        // Stop mDNS service
        stopmDNSService();

        if (callback != null) {
            callback.onServerStopped();
        }

        Log.i(TAG, "Server stopped");
    }

    private void startmDNSService() {
        try {
            // Find the best IPv4 interface
            java.net.InetAddress localAddress = findBestIPv4Address();

            jmdns = JmDNS.create(localAddress);

            String serviceName = "multiCam-" + deviceId;

            serviceInfo = ServiceInfo.create(Constants.SERVICE_TYPE, serviceName, Constants.TCP_PORT,
                "MultiCam Android Device");

            jmdns.registerService(serviceInfo);

            // Wait a moment and check if registration was successful
            Thread.sleep(2000);

            javax.jmdns.ServiceInfo[] services = jmdns.list(Constants.SERVICE_TYPE);
            boolean found = false;
            for (javax.jmdns.ServiceInfo service : services) {
                if (serviceName.equals(service.getName())) {
                    found = true;
                    break;
                }
            }

        } catch (IOException e) {
            Log.e(TAG, "Failed to start mDNS service", e);
        } catch (InterruptedException e) {
            Log.w(TAG, "mDNS registration check interrupted", e);
        }
    }

    private void stopmDNSService() {
        try {
            if (jmdns != null) {
                if (serviceInfo != null) {
                    jmdns.unregisterService(serviceInfo);
                }
                jmdns.close();
            }
        } catch (IOException e) {
            Log.e(TAG, "Error stopping mDNS service", e);
        }
    }

    private void handleClient(Socket clientSocket) {
        String clientAddress = clientSocket.getRemoteSocketAddress().toString();

        try (InputStream inputStream = clientSocket.getInputStream();
             OutputStream outputStream = clientSocket.getOutputStream()) {

            byte[] buffer = new byte[4096];
            int bytesRead;
            while ((bytesRead = inputStream.read(buffer)) != -1 && isRunning.get()) {
                String jsonCommand = new String(buffer, 0, bytesRead, "UTF-8");

                try {
                    CommandMessage request = CommandMessage.fromJson(jsonCommand);

                    Object response = processCommand(request);

                    // Handle GET_VIDEO file transfer (binary protocol)
                    if (request.command == CommandType.GET_VIDEO &&
                        response instanceof StatusResponse &&
                        ((StatusResponse) response).getDeviceStatus() == DeviceStatus.READY) {

                        // For GET_VIDEO, send the file directly using binary protocol (no JSON response first)
                        try {
                            sendFile(outputStream, request.fileName);
                        } catch (IOException fileError) {
                            // Send error response if file transfer fails
                            StatusResponse errorResponse = createStatusResponse(DeviceStatus.ERROR);
                            outputStream.write(errorResponse.toJson().getBytes());
                            outputStream.flush();
                        }

                    } else {
                        // Normal JSON response - serialize based on type
                        String responseJson;
                        if (response instanceof StatusResponse) {
                            responseJson = ((StatusResponse) response).toJson();
                        } else if (response instanceof FileTypes.StopRecordingResponse) {
                            responseJson = ((FileTypes.StopRecordingResponse) response).toJson();
                        } else if (response instanceof FileTypes.ListFilesResponse) {
                            responseJson = ((FileTypes.ListFilesResponse) response).toJson();
                        } else if (response instanceof FileTypes.ErrorResponse) {
                            responseJson = ((FileTypes.ErrorResponse) response).toJson();
                        } else {
                            // Fallback error
                            responseJson = createStatusResponse(DeviceStatus.ERROR).toJson();
                        }

                        outputStream.write(responseJson.getBytes());
                        outputStream.flush();
                    }

                } catch (JsonSyntaxException e) {
                    Log.e(TAG, "Invalid JSON command", e);
                    StatusResponse errorResponse = createStatusResponse(DeviceStatus.ERROR);

                    String responseJson = errorResponse.toJson();
                    outputStream.write(responseJson.getBytes());
                    outputStream.flush();
                }
            }

        } catch (IOException e) {
            // Client disconnected - this is normal
        } finally {
            try {
                clientSocket.close();
                if (callback != null) {
                    callback.onClientDisconnected(clientAddress);
                }
            } catch (IOException e) {
                Log.e(TAG, "Error closing client socket", e);
            }
        }
    }

    private Object processCommand(CommandMessage request) {
        try {
            CommandType commandType = request.command;

            switch (commandType) {
                case START_RECORDING:
                    return handleStartRecording(request);
                case STOP_RECORDING:
                    return handleStopRecording(request);
                case DEVICE_STATUS:
                    return handleDeviceStatus(request);
                case GET_VIDEO:
                    return handleGetVideo(request);
                case HEARTBEAT:
                    return handleHeartbeat(request);
                case LIST_FILES:
                    return handleListFiles(request);
                case UPLOAD_TO_CLOUD:
                    return handleUploadToCloud(request);
                default:
                    return createStatusResponse(DeviceStatus.ERROR);
            }

        } catch (IllegalArgumentException e) {
            Log.e(TAG, "Invalid command type", e);
            return createStatusResponse(DeviceStatus.ERROR);
        } catch (Exception e) {
            Log.e(TAG, "Error processing command", e);
            return createStatusResponse(DeviceStatus.ERROR);
        }
    }

    private StatusResponse createStatusResponse(DeviceStatus status) {
        double timestamp = System.currentTimeMillis() / 1000.0;
        double batteryLevel = getBatteryLevel();
        StatusResponse response = new StatusResponse(deviceId, status.getValue(), timestamp);
        response.batteryLevel = batteryLevel;
        
        // Set device type
        response.deviceType = DeviceType.ANDROID_QUEST.getValue();

        // Get upload queues from upload manager
        if (uploadManager != null) {
            List<UploadTypes.UploadItem>[] queues = uploadManager.getUploadQueues();
            response.uploadQueue = queues[0];
            response.failedUploadQueue = queues[1];
        } else {
            response.uploadQueue = new ArrayList<>();
            response.failedUploadQueue = new ArrayList<>();
        }
        
        return response;
    }

    private double getBatteryLevel() {
        try {
            IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
            Intent batteryStatus = context.registerReceiver(null, ifilter);
            if (batteryStatus != null) {
                int level = batteryStatus.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int scale = batteryStatus.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
                return (level / (float) scale) * 100.0;
            }
        } catch (Exception e) {
            Log.w(TAG, "Failed to get battery level", e);
        }
        return -1.0;
    }

    private boolean isCurrentlyRecording() {
        return cameraController.isRecording();
    }

    public void shutdown() {
        stopServer();
        if (serverExecutor != null) {
            serverExecutor.shutdown();
        }
    }

    private StatusResponse handleStartRecording(CommandMessage request) {
        if (isCurrentlyRecording()) {
            return createStatusResponse(DeviceStatus.RECORDING);
        }

        long targetTimestamp = (long)(request.timestamp * 1000);

        // First ensure time is synchronized
        if (!cameraController.isTimeSynchronized()) {
            return createStatusResponse(DeviceStatus.TIME_NOT_SYNCHRONIZED);
        }

        // Generate file ID and output file using Constants.generateFileId()
        String fileId = Constants.generateFileId(deviceId);
        File outputFile = new File(context.getExternalFilesDir(null), fileId + ".mp4");

        try {
            currentRecordingFileId = fileId; // Track this recording

            // Use immediate recording for frame-perfect sync
            cameraController.startRecordingImmediately(targetTimestamp, outputFile, new CameraController.RecordingCallback() {
                @Override
                public void onRecordingStarted(String filePath) {
                    // Store final file path in recorded files map
                    recordedFiles.put(fileId, new File(filePath));
                }

                @Override
                public void onRecordingStopped(String filePath, long durationMs) {
                    // Recording stopped and processing complete - signal waiting thread
                    synchronized (processingLock) {
                        isProcessingComplete = true;
                        processingLock.notifyAll();
                    }
                    Log.i(TAG, "Video processing complete, file ready: " + filePath);
                }

                @Override
                public void onRecordingError(String error) {
                    Log.e(TAG, "Recording error: " + error);
                    recordedFiles.remove(fileId);
                    currentRecordingFileId = null; // Clear tracking on error

                    // Signal processing complete even on error to unblock waiting thread
                    synchronized (processingLock) {
                        isProcessingComplete = true;
                        processingLock.notifyAll();
                    }
                }

                @Override
                public void onRecordingPreparing() {
                    // Recording preparing
                }

                @Override
                public void onRecordingWaitingForTime(long delayMs) {
                    // Waiting for time
                }
            });

            return createStatusResponse(DeviceStatus.SCHEDULED_RECORDING_ACCEPTED);

        } catch (Exception e) {
            Log.e(TAG, "Failed to start immediate recording", e);
            return createStatusResponse(DeviceStatus.ERROR);
        }
    }

    private FileTypes.StopRecordingResponse handleStopRecording(CommandMessage request) {
        if (!isCurrentlyRecording()) {
            double timestamp = System.currentTimeMillis() / 1000.0;
            return new FileTypes.StopRecordingResponse(deviceId, DeviceStatus.ERROR.getValue(),
                timestamp, null, 0);
        }

        try {
            // Reset processing flag before stopping
            synchronized (processingLock) {
                isProcessingComplete = false;
            }

            cameraController.stopRecording();

            // Use the tracked current recording file ID
            String fileIdToReturn = currentRecordingFileId;

            if (fileIdToReturn == null) {
                for (Map.Entry<String, File> entry : recordedFiles.entrySet()) {
                    // Use the most recent file we can find
                    if (entry.getValue() != null) {
                        fileIdToReturn = entry.getKey();
                        break;
                    }
                }
            }

            if (fileIdToReturn == null) {
                // Generate file ID from current time if none found
                fileIdToReturn = Constants.generateFileId(deviceId);
            }

            // Wait for video processing to complete (trimming or file move)
            Log.i(TAG, "Waiting for video processing to complete...");
            synchronized (processingLock) {
                long waitStartTime = System.currentTimeMillis();
                while (!isProcessingComplete) {
                    try {
                        // Wait up to 60 seconds for processing to complete
                        processingLock.wait((long)(Constants.COMMAND_TIMEOUT * 1000));

                        if (!isProcessingComplete) {
                            long waitDuration = System.currentTimeMillis() - waitStartTime;
                            Log.w(TAG, "Video processing timeout after " + waitDuration + "ms");
                            break;
                        }
                    } catch (InterruptedException e) {
                        Log.e(TAG, "Wait for processing interrupted", e);
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            }

            Log.i(TAG, "Video processing complete, sending response");

            // Get file size
            File recordedFile = recordedFiles.get(fileIdToReturn);
            long fileSize = recordedFile != null ? recordedFile.length() : 0;

            // Clear the current recording tracking
            currentRecordingFileId = null;

            double timestamp = System.currentTimeMillis() / 1000.0;
            return new FileTypes.StopRecordingResponse(deviceId, DeviceStatus.RECORDING_STOPPED.getValue(),
                timestamp, fileIdToReturn + ".mp4", fileSize);

        } catch (Exception e) {
            Log.e(TAG, "Failed to stop recording", e);
            double timestamp = System.currentTimeMillis() / 1000.0;
            return new FileTypes.StopRecordingResponse(deviceId, DeviceStatus.ERROR.getValue(),
                timestamp, null, 0);
        }
    }

    private StatusResponse handleDeviceStatus(CommandMessage request) {
        DeviceStatus status;

        if (isCurrentlyRecording()) {
            status = DeviceStatus.RECORDING;
        } else {
            CameraController.RecordingState state = cameraController.getRecordingState();
            switch (state) {
                case PREPARING:
                    status = DeviceStatus.COMMAND_RECEIVED;
                    break;
                case WAITING_FOR_TIME:
                    status = DeviceStatus.COMMAND_RECEIVED;
                    break;
                case STOPPING:
                    status = DeviceStatus.STOPPING;
                    break;
                default:
                    status = DeviceStatus.READY;
            }
        }

        return createStatusResponse(status);
    }

    private StatusResponse handleGetVideo(CommandMessage request) {
        String fileName = request.fileName;
        if (fileName == null || fileName.trim().isEmpty()) {
            return createStatusResponse(DeviceStatus.FILE_NOT_FOUND);
        }

        // Remove .mp4 extension to get the fileId for lookup
        String fileId = fileName.replace(".mp4", "");
        File videoFile = recordedFiles.get(fileId);

        if (videoFile == null) {
            return createStatusResponse(DeviceStatus.FILE_NOT_FOUND);
        }

        if (!videoFile.exists()) {
            return createStatusResponse(DeviceStatus.FILE_NOT_FOUND);
        }

        // For GET_VIDEO, we signal ready status which triggers binary file transfer
        return createStatusResponse(DeviceStatus.READY);
    }

    private StatusResponse handleHeartbeat(CommandMessage request) {
        return createStatusResponse(DeviceStatus.COMMAND_RECEIVED);
    }

    private FileTypes.ListFilesResponse handleListFiles(CommandMessage request) {
        double timestamp = System.currentTimeMillis() / 1000.0;
        List<FileTypes.FileMetadata> files = new ArrayList<>();

        // Iterate through recorded files and create metadata
        for (Map.Entry<String, File> entry : recordedFiles.entrySet()) {
            File file = entry.getValue();
            if (file != null && file.exists()) {
                String fileName = entry.getKey() + ".mp4";
                long fileSize = file.length();
                double creationDate = file.lastModified() / 1000.0;
                double modificationDate = file.lastModified() / 1000.0;

                FileTypes.FileMetadata metadata = new FileTypes.FileMetadata(
                    fileName, fileSize, creationDate, modificationDate);
                files.add(metadata);
            }
        }

        return new FileTypes.ListFilesResponse(deviceId, DeviceStatus.READY.getValue(), timestamp, files);
    }

    private StatusResponse handleUploadToCloud(CommandMessage request) {
        String fileName = request.fileName;
        
        if (fileName == null || fileName.trim().isEmpty()) {
            return createStatusResponse(DeviceStatus.FILE_NOT_FOUND);
        }

        // Remove .mp4 extension to get the fileId for lookup
        String fileId = fileName.replace(".mp4", "");
        File videoFile = recordedFiles.get(fileId);

        if (videoFile == null || !videoFile.exists()) {
            // Try to find it in the external files dir directly if not in map
            videoFile = new File(context.getExternalFilesDir(null), fileName);
            if (!videoFile.exists()) {
                return createStatusResponse(DeviceStatus.FILE_NOT_FOUND);
            }
        }

        // Determine authentication method: presigned URL or IAM credentials
        boolean usePresignedUrl = request.uploadUrl != null && !request.uploadUrl.isEmpty();
        boolean useIAMCredentials = request.awsAccessKeyId != null && !request.awsAccessKeyId.isEmpty();
        
        if (!usePresignedUrl && !useIAMCredentials) {
            return createStatusResponse(DeviceStatus.ERROR);
        }
        
        // Validate IAM credentials if using that method
        if (useIAMCredentials) {
            if (request.s3Bucket == null || request.s3Bucket.isEmpty() ||
                request.s3Key == null || request.s3Key.isEmpty() ||
                request.awsSecretAccessKey == null || request.awsSecretAccessKey.isEmpty() ||
                request.awsSessionToken == null || request.awsSessionToken.isEmpty() ||
                request.awsRegion == null || request.awsRegion.isEmpty()) {
                return createStatusResponse(DeviceStatus.ERROR);
            }
        }

        // Queue the upload with the appropriate authentication method
        if (usePresignedUrl) {
            uploadManager.queueUpload(fileName, videoFile, request.uploadUrl);
        } else {
            uploadManager.queueUploadWithIAM(
                fileName,
                videoFile,
                request.s3Bucket,
                request.s3Key,
                request.awsAccessKeyId,
                request.awsSecretAccessKey,
                request.awsSessionToken,
                request.awsRegion
            );
        }

        return createStatusResponse(DeviceStatus.UPLOAD_QUEUED);
    }

    // Helper method to handle file download after GET_VIDEO response
    public void sendFile(OutputStream outputStream, String fileName) throws IOException {
        // Remove .mp4 extension to get the fileId for lookup
        String fileId = fileName.replace(".mp4", "");
        File videoFile = recordedFiles.get(fileId);
        if (videoFile == null || !videoFile.exists()) {
            throw new IOException("File not found: " + fileName);
        }

        // Create file response header using FileTypes.FileResponse
        FileTypes.FileResponse fileResponse = new FileTypes.FileResponse(
            deviceId, fileName, videoFile.length(), DeviceStatus.READY.getValue());

        byte[] headerJson = fileResponse.toJson().getBytes("UTF-8");

        // Send header size (4 bytes, big-endian)
        ByteBuffer headerSizeBuffer = ByteBuffer.allocate(4);
        headerSizeBuffer.putInt(headerJson.length);
        outputStream.write(headerSizeBuffer.array());

        // Send JSON header
        outputStream.write(headerJson);

        // Send file data using chunk size from Constants
        try (FileInputStream fileInputStream = new FileInputStream(videoFile)) {
            byte[] buffer = new byte[Constants.DOWNLOAD_CHUNK_SIZE];
            int bytesRead;
            while ((bytesRead = fileInputStream.read(buffer)) != -1) {
                outputStream.write(buffer, 0, bytesRead);
            }
        }

        outputStream.flush();
        Log.d(TAG, String.format("File sent: %s (%d bytes)", fileName, videoFile.length()));
    }
}