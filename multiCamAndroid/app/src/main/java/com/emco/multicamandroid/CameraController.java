package com.emco.multicamandroid;

import android.content.Context;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.camera.core.Camera;
import androidx.camera.core.CameraInfo;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.video.FileOutputOptions;
import androidx.camera.video.Quality;
import androidx.camera.video.QualitySelector;
import androidx.camera.video.Recorder;
import androidx.camera.video.Recording;
import androidx.camera.video.VideoCapture;
import androidx.camera.video.VideoRecordEvent;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;
import androidx.lifecycle.LifecycleOwner;

import com.google.common.util.concurrent.ListenableFuture;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class CameraController {

    private static final String TAG = "CameraController";

    private final Context context;
    private final LifecycleOwner lifecycleOwner;
    private ExecutorService cameraExecutor;
    private ProcessCameraProvider cameraProvider;
    private Camera camera;

    // Recording components
    private VideoCapture<Recorder> videoCapture;
    private Recording currentRecording;
    private final AtomicBoolean isRecording = new AtomicBoolean(false);
    private final AtomicBoolean isPreparingToRecord = new AtomicBoolean(false);

    // Timing components
    private final TimeSync timeSync;
    private HandlerThread timingThread;
    private Handler timingHandler;

    // Recording state
    private final AtomicReference<RecordingState> recordingState = new AtomicReference<>(RecordingState.IDLE);

    // Immediate recording timing properties
    private long scheduledStartTime = 0;
    private long actualRecordingStartTime = 0;
    private long recordingStopTime = 0;
    private String currentRecordingFilePath = null;
    private boolean useImmediateRecording = true;
    private String tempRecordingFilePath = null;
    private String finalRecordingFilePath = null;

    public enum RecordingState {
        IDLE, PREPARING, WAITING_FOR_TIME, RECORDING, STOPPING, PROCESSING
    }

    public interface CameraCallback {
        void onCameraReady();
        void onCameraError(String message);
    }

    public interface RecordingCallback {
        void onRecordingStarted(String filePath);
        void onRecordingStopped(String filePath, long durationMs);
        void onRecordingError(String error);
        void onRecordingPreparing();
        void onRecordingWaitingForTime(long delayMs);
    }

    public CameraController(Context context, LifecycleOwner lifecycleOwner) {
        this.context = context;
        this.lifecycleOwner = lifecycleOwner;
        this.cameraExecutor = Executors.newSingleThreadExecutor();
        this.timeSync = new TimeSync();

        // Initialize high-priority timing thread
        this.timingThread = new HandlerThread("CameraTimingThread", -8); // TIME_CRITICAL priority
        this.timingThread.start();
        this.timingHandler = new Handler(this.timingThread.getLooper());
    }

    public void startCamera(PreviewView previewView, CameraCallback callback) {
        Log.d(TAG, "Starting camera...");

        ListenableFuture<ProcessCameraProvider> cameraProviderFuture =
                ProcessCameraProvider.getInstance(context);

        cameraProviderFuture.addListener(() -> {
            try {
                cameraProvider = cameraProviderFuture.get();
                bindPreview(previewView, callback);
            } catch (ExecutionException | InterruptedException e) {
                Log.e(TAG, "Error starting camera", e);
                callback.onCameraError("Error starting camera: " + e.getMessage());
            }
        }, ContextCompat.getMainExecutor(context));
    }

    private void bindPreview(PreviewView previewView, CameraCallback callback) {
        Log.d(TAG, "Binding camera preview...");

        Preview preview = new Preview.Builder().build();
        preview.setSurfaceProvider(previewView.getSurfaceProvider());

        // Setup video capture
        setupVideoCapture();

        CameraSelector cameraSelector = getWidestAngleCameraSelector();
        Log.d(TAG, "Using camera selector: " + cameraSelector);

        try {
            cameraProvider.unbindAll();
            camera = cameraProvider.bindToLifecycle(lifecycleOwner, cameraSelector, preview, videoCapture);
            Log.d(TAG, "Camera bound successfully: " + (camera != null ? "Camera found" : "Camera is null"));

            if (camera == null) {
                throw new IllegalStateException("Camera binding returned null");
            }

            callback.onCameraReady();

        } catch (Exception e) {
            Log.e(TAG, "Error binding camera", e);

            // Try fallback to default camera
            try {
                Log.d(TAG, "Trying fallback to default back camera...");
                cameraProvider.unbindAll();
                Camera fallbackCamera = cameraProvider.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, videoCapture);
                Log.d(TAG, "Fallback camera bound: " + (fallbackCamera != null ? "Success" : "Failed"));

                if (fallbackCamera != null) {
                    camera = fallbackCamera;
                    callback.onCameraReady();
                } else {
                    callback.onCameraError("No cameras available");
                }
            } catch (Exception fallbackException) {
                Log.e(TAG, "Fallback camera also failed", fallbackException);
                callback.onCameraError("No cameras available");
            }
        }
    }

    private void setupVideoCapture() {
        Log.d(TAG, "Setting up video capture...");

        // Create quality selector to match iOS: 1080p with fallback options
        QualitySelector qualitySelector = QualitySelector.fromOrderedList(
                Arrays.asList(
                        Quality.HD,    // 1080p (1920x1080) - primary choice to match iOS
                        Quality.FHD,   // 1080p alternative naming
                        Quality.SD     // 720p fallback if 1080p not available
                )
        );

        Recorder recorder = new Recorder.Builder()
                .setQualitySelector(qualitySelector)
                .build();

        videoCapture = VideoCapture.withOutput(recorder);

        Log.d(TAG, "Video capture configured for 1080p@30fps to match iOS settings");
        Log.d(TAG, "Quality priority: HD (1080p) > FHD (1080p alt) > SD (720p fallback)");
    }

    private CameraSelector getWidestAngleCameraSelector() {
        Log.d(TAG, "Finding widest angle camera...");

        if (cameraProvider == null) {
            Log.w(TAG, "Camera provider is null, using default back camera");
            return CameraSelector.DEFAULT_BACK_CAMERA;
        }

        // Try ultra-wide lens first (typically 0.5x - 0.7x)
        CameraSelector ultraWideSelector = new CameraSelector.Builder()
                .requireLensFacing(CameraSelector.LENS_FACING_BACK)
                .addCameraFilter(cameras -> {
                    Log.d(TAG, "Available cameras: " + cameras.size());

                    CameraInfo bestCamera = null;
                    float lowestZoomRatio = Float.MAX_VALUE;

                    for (CameraInfo cameraInfo : cameras) {
                        try {
                            float zoomRatio = cameraInfo.getIntrinsicZoomRatio();
                            Log.d(TAG, "Camera zoom ratio: " + zoomRatio);

                            if (zoomRatio < lowestZoomRatio) {
                                lowestZoomRatio = zoomRatio;
                                bestCamera = cameraInfo;
                            }
                        } catch (Exception e) {
                            Log.w(TAG, "Could not get zoom ratio for camera", e);
                        }
                    }

                    if (bestCamera != null) {
                        Log.d(TAG, "Selected camera with zoom ratio: " + lowestZoomRatio);
                        List<CameraInfo> result = new ArrayList<>();
                        result.add(bestCamera);
                        return result;
                    }

                    Log.d(TAG, "No suitable camera found, returning all");
                    return new ArrayList<>(cameras);
                })
                .build();

        // Test if the selector can find a camera
        try {
            if (cameraProvider.hasCamera(ultraWideSelector)) {
                Log.d(TAG, "Ultra-wide camera selector is valid");
                return ultraWideSelector;
            }
        } catch (Exception e) {
            Log.w(TAG, "Ultra-wide camera selector failed", e);
        }

        // Fallback to default back camera
        Log.d(TAG, "Falling back to default back camera");
        return CameraSelector.DEFAULT_BACK_CAMERA;
    }

    public Camera getCamera() {
        return camera;
    }

    public void stopCamera() {
        if (cameraProvider != null) {
            cameraProvider.unbindAll();
        }
    }

    public void synchronizeTime(TimeSync.SyncCallback callback) {
        timeSync.synchronizeTime(callback);
    }

    public void startRecordingAtTime(long targetSyncTimestamp, File outputFile, RecordingCallback callback) {
        Log.d(TAG, String.format("Scheduled recording for timestamp: %d", targetSyncTimestamp));

        if (!recordingState.compareAndSet(RecordingState.IDLE, RecordingState.PREPARING)) {
            callback.onRecordingError("Recording already in progress or preparing");
            return;
        }

        callback.onRecordingPreparing();

        cameraExecutor.execute(() -> {
            try {
                // Warm up camera and prepare recording
                prepareForRecording(outputFile, callback);

                // Calculate delay until target time
                long delayMs = timeSync.calculateDelayUntil(targetSyncTimestamp);

                if (delayMs < 0) {
                    Log.w(TAG, String.format("Target time has passed by %dms", -delayMs));
                    recordingState.set(RecordingState.IDLE);
                    callback.onRecordingError("Target recording time has already passed");
                    return;
                }

                if (delayMs > 300000) { // 5 minutes
                    Log.w(TAG, String.format("Target time is too far in future: %dms", delayMs));
                    recordingState.set(RecordingState.IDLE);
                    callback.onRecordingError("Target recording time is too far in the future");
                    return;
                }

                recordingState.set(RecordingState.WAITING_FOR_TIME);
                callback.onRecordingWaitingForTime(delayMs);

                // Use high-priority timing thread for precise timing
                timingHandler.postDelayed(() -> {
                    if (recordingState.get() == RecordingState.WAITING_FOR_TIME) {
                        startRecordingNow(outputFile, callback);
                    }
                }, delayMs);

            } catch (Exception e) {
                Log.e(TAG, "Failed to prepare recording", e);
                recordingState.set(RecordingState.IDLE);
                callback.onRecordingError("Failed to prepare recording: " + e.getMessage());
            }
        });
    }

    private void prepareForRecording(File outputFile, RecordingCallback callback) {
        Log.d(TAG, "Preparing for recording...");

        if (videoCapture == null) {
            throw new RuntimeException("Video capture not initialized");
        }

        // Pre-warm the camera by accessing its properties
        if (camera != null) {
            try {
                camera.getCameraInfo().getIntrinsicZoomRatio();
                Thread.sleep(100); // Small delay to ensure camera is fully warmed up
            } catch (Exception e) {
                Log.w(TAG, "Camera warm-up failed", e);
            }
        }

        Log.d(TAG, "Recording preparation complete");
    }

    private void startRecordingNow(File outputFile, RecordingCallback callback) {
        Log.d(TAG, "Starting recording NOW");

        if (!recordingState.compareAndSet(RecordingState.WAITING_FOR_TIME, RecordingState.RECORDING)) {
            callback.onRecordingError("Invalid recording state for starting");
            return;
        }

        try {
            // Create FileOutputOptions to save directly to app storage
            FileOutputOptions outputOptions = new FileOutputOptions.Builder(outputFile).build();

            currentRecording = videoCapture.getOutput()
                    .prepareRecording(context, outputOptions)
                    .start(ContextCompat.getMainExecutor(context), videoRecordEvent -> {
                        handleRecordingEvent(videoRecordEvent, outputFile.getAbsolutePath(), callback);
                    });

            isRecording.set(true);
            Log.i(TAG, "Recording started successfully");

        } catch (Exception e) {
            Log.e(TAG, "Failed to start recording", e);
            recordingState.set(RecordingState.IDLE);
            isRecording.set(false);
            callback.onRecordingError("Failed to start recording: " + e.getMessage());
        }
    }

    private void handleRecordingEvent(VideoRecordEvent event, String filePath, RecordingCallback callback) {
        if (event instanceof VideoRecordEvent.Start) {
            Log.d(TAG, "Recording event: Started");
            callback.onRecordingStarted(filePath);
        } else if (event instanceof VideoRecordEvent.Finalize) {
            VideoRecordEvent.Finalize finalizeEvent = (VideoRecordEvent.Finalize) event;
            Log.d(TAG, "Recording event: Finalized");

            recordingState.set(RecordingState.IDLE);
            isRecording.set(false);

            if (finalizeEvent.hasError()) {
                callback.onRecordingError("Recording finalized with error: " + finalizeEvent.getCause());
            } else {
                // Duration calculation - simplified for now
                long durationMs = 0; // TODO: Implement proper duration tracking
                callback.onRecordingStopped(filePath, durationMs);
            }
        } else if (event instanceof VideoRecordEvent.Status) {
            // Recording is ongoing
            Log.v(TAG, "Recording status update");
        }
    }

    public void stopRecording() {
        if (useImmediateRecording) {
            stopRecordingImmediate();
        } else {
            stopRecordingTraditional();
        }
    }

    private void stopRecordingImmediate() {
        Log.d(TAG, "[IMMEDIATE] Stopping immediate recording...");

        if (!isRecording.get()) {
            Log.w(TAG, "[IMMEDIATE] No recording in progress");
            return;
        }

        if (recordingState.compareAndSet(RecordingState.RECORDING, RecordingState.STOPPING)) {
            if (currentRecording != null) {
                Log.d(TAG, "[IMMEDIATE] Stopping current recording for processing");
                currentRecording.stop();
                currentRecording = null;
            }
        }
    }

    private void stopRecordingTraditional() {
        Log.d(TAG, "Stopping recording (traditional mode)...");

        if (!isRecording.get()) {
            Log.w(TAG, "No recording in progress");
            return;
        }

        if (recordingState.compareAndSet(RecordingState.RECORDING, RecordingState.STOPPING)) {
            if (currentRecording != null) {
                currentRecording.stop();
                currentRecording = null;
            }
        }
    }

    public boolean isRecording() {
        return isRecording.get();
    }

    public RecordingState getRecordingState() {
        return recordingState.get();
    }

    public boolean isTimeSynchronized() {
        return timeSync.isSynchronized();
    }

    public long getSynchronizedTime() {
        return timeSync.getSynchronizedTime();
    }

    public void shutdown() {
        stopRecording();
        stopCamera();

        if (timingThread != null) {
            timingThread.quitSafely();
        }

        if (cameraExecutor != null) {
            cameraExecutor.shutdown();
        }

        timeSync.shutdown();
    }

    // Immediate recording implementation
    public void startRecordingImmediately(long scheduledTime, File outputFile, RecordingCallback callback) {
        Log.d(TAG, String.format("[IMMEDIATE] Starting immediate recording for scheduled time: %d", scheduledTime));
        Log.d(TAG, String.format("[IMMEDIATE] Current synchronized time: %d", timeSync.getSynchronizedTime()));
        Log.d(TAG, String.format("[IMMEDIATE] Time difference: %d ms", scheduledTime - timeSync.getSynchronizedTime()));

        if (!recordingState.compareAndSet(RecordingState.IDLE, RecordingState.PREPARING)) {
            Log.e(TAG, "[IMMEDIATE] Recording already in progress or preparing");
            callback.onRecordingError("Recording already in progress or preparing");
            return;
        }

        // Store timing information
        this.scheduledStartTime = scheduledTime;
        this.finalRecordingFilePath = outputFile.getAbsolutePath();

        // Create temporary file for initial recording
        File tempFile = new File(outputFile.getParent(), "temp_" + outputFile.getName());
        this.tempRecordingFilePath = tempFile.getAbsolutePath();

        Log.d(TAG, String.format("[IMMEDIATE] Final file: %s", finalRecordingFilePath));
        Log.d(TAG, String.format("[IMMEDIATE] Temp file: %s", tempRecordingFilePath));

        callback.onRecordingPreparing();

        cameraExecutor.execute(() -> {
            try {
                // Prepare recording immediately
                prepareForRecording(tempFile, callback);

                // Start recording immediately
                recordingState.set(RecordingState.RECORDING);
                startRecordingNowImmediate(tempFile, callback);

            } catch (Exception e) {
                Log.e(TAG, "[IMMEDIATE] Failed to start immediate recording", e);
                recordingState.set(RecordingState.IDLE);
                callback.onRecordingError("Failed to start immediate recording: " + e.getMessage());
            }
        });
    }

    private void startRecordingNowImmediate(File outputFile, RecordingCallback callback) {
        Log.d(TAG, "[IMMEDIATE] Starting recording NOW (immediate mode)");

        try {
            // Create FileOutputOptions to save to temp file
            FileOutputOptions outputOptions = new FileOutputOptions.Builder(outputFile).build();

            currentRecording = videoCapture.getOutput()
                    .prepareRecording(context, outputOptions)
                    .start(ContextCompat.getMainExecutor(context), videoRecordEvent -> {
                        handleRecordingEventImmediate(videoRecordEvent, outputFile.getAbsolutePath(), callback);
                    });

            isRecording.set(true);
            Log.i(TAG, "[IMMEDIATE] Recording started successfully in immediate mode");

        } catch (Exception e) {
            Log.e(TAG, "[IMMEDIATE] Failed to start immediate recording", e);
            recordingState.set(RecordingState.IDLE);
            isRecording.set(false);
            callback.onRecordingError("Failed to start immediate recording: " + e.getMessage());
        }
    }

    private void handleRecordingEventImmediate(VideoRecordEvent event, String filePath, RecordingCallback callback) {
        if (event instanceof VideoRecordEvent.Start) {
            // Capture the actual recording start time with high precision
            actualRecordingStartTime = timeSync.getSynchronizedTime();

            Log.d(TAG, String.format("[IMMEDIATE] Recording event: Started at synchronized time %d", actualRecordingStartTime));
            Log.d(TAG, String.format("[IMMEDIATE] Scheduled for: %d", scheduledStartTime));

            long timeDifference = actualRecordingStartTime - scheduledStartTime;
            Log.d(TAG, String.format("[IMMEDIATE] Time difference (actual vs scheduled): %d ms", timeDifference));

            if (timeDifference > 0) {
                Log.i(TAG, String.format("[IMMEDIATE] Recording started %d ms after scheduled time - will need trimming", timeDifference));
            } else {
                Log.i(TAG, String.format("[IMMEDIATE] Recording started %d ms before scheduled time - no trimming needed", -timeDifference));
            }

            callback.onRecordingStarted(finalRecordingFilePath); // Report final file path to callback

        } else if (event instanceof VideoRecordEvent.Finalize) {
            VideoRecordEvent.Finalize finalizeEvent = (VideoRecordEvent.Finalize) event;
            Log.d(TAG, "[IMMEDIATE] Recording event: Finalized");

            recordingState.set(RecordingState.PROCESSING);
            isRecording.set(false);

            if (finalizeEvent.hasError()) {
                Log.e(TAG, "[IMMEDIATE] Recording finalized with error: " + finalizeEvent.getCause());
                callback.onRecordingError("Recording finalized with error: " + finalizeEvent.getCause());
            } else {
                // Process the recorded video (trim if needed)
                processRecordedVideo(callback);
            }
        } else if (event instanceof VideoRecordEvent.Status) {
            // Recording is ongoing
            Log.v(TAG, "[IMMEDIATE] Recording status update");
        }
    }

    private void processRecordedVideo(RecordingCallback callback) {
        Log.d(TAG, "[IMMEDIATE] Processing recorded video...");

        recordingStopTime = timeSync.getSynchronizedTime();
        Log.d(TAG, String.format("[IMMEDIATE] Recording stopped at synchronized time: %d", recordingStopTime));

        // Calculate timing
        long totalRecordingDuration = recordingStopTime - actualRecordingStartTime;
        long delayBeforeScheduled = scheduledStartTime - actualRecordingStartTime;

        Log.d(TAG, String.format("[IMMEDIATE] Total recording duration: %d ms", totalRecordingDuration));
        Log.d(TAG, String.format("[IMMEDIATE] Delay before scheduled start: %d ms", delayBeforeScheduled));

        if (delayBeforeScheduled > 50) { // Only trim if delay is significant (>50ms)
            Log.i(TAG, String.format("[IMMEDIATE] Need to trim %d ms from beginning", delayBeforeScheduled));

            // Calculate trim duration
            long trimDuration = totalRecordingDuration - delayBeforeScheduled;

            Log.d(TAG, String.format("[IMMEDIATE] Final video duration after trimming: %d ms", trimDuration));

            // Trim the video (will be implemented in VideoTrimmer class)
            trimVideoAsync(tempRecordingFilePath, finalRecordingFilePath, delayBeforeScheduled, trimDuration, callback);
        } else {
            Log.i(TAG, "[IMMEDIATE] No trimming needed, moving temp file to final location");

            // Simply move the temp file to final location
            moveFile(tempRecordingFilePath, finalRecordingFilePath, callback, totalRecordingDuration);
        }
    }

    private void moveFile(String tempPath, String finalPath, RecordingCallback callback, long durationMs) {
        cameraExecutor.execute(() -> {
            try {
                File tempFile = new File(tempPath);
                File finalFile = new File(finalPath);

                Log.d(TAG, String.format("[IMMEDIATE] Moving file from %s to %s", tempPath, finalPath));

                if (tempFile.renameTo(finalFile)) {
                    Log.i(TAG, "[IMMEDIATE] File moved successfully");
                    recordingState.set(RecordingState.IDLE);
                    callback.onRecordingStopped(finalPath, durationMs);
                } else {
                    Log.e(TAG, "[IMMEDIATE] Failed to move file");
                    recordingState.set(RecordingState.IDLE);
                    callback.onRecordingError("Failed to move recorded file");
                }
            } catch (Exception e) {
                Log.e(TAG, "[IMMEDIATE] Error moving file", e);
                recordingState.set(RecordingState.IDLE);
                callback.onRecordingError("Error moving recorded file: " + e.getMessage());
            }
        });
    }

    private void trimVideoAsync(String inputPath, String outputPath, long trimStartMs, long durationMs, RecordingCallback callback) {
        Log.d(TAG, String.format("[IMMEDIATE] Starting video trimming: input=%s, output=%s, trimStart=%dms, duration=%dms",
            inputPath, outputPath, trimStartMs, durationMs));

        cameraExecutor.execute(() -> {
            // Log video info before trimming
            VideoTrimmer.logVideoInfo(inputPath);

            VideoTrimmer.trimVideo(
                inputPath,
                outputPath,
                trimStartMs * 1000, // Convert to microseconds
                durationMs * 1000,  // Convert to microseconds
                new VideoTrimmer.VideoTrimCallback() {
                    @Override
                    public void onTrimStarted() {
                        Log.d(TAG, "[IMMEDIATE] Video trimming started");
                    }

                    @Override
                    public void onTrimProgress(int progressPercentage) {
                        Log.v(TAG, String.format("[IMMEDIATE] Trimming progress: %d%%", progressPercentage));
                    }

                    @Override
                    public void onTrimCompleted(String outputPath, long actualDurationMs) {
                        Log.i(TAG, String.format("[IMMEDIATE] Video trimming completed: %s, duration: %dms", outputPath, actualDurationMs));

                        // Clean up temp file
                        try {
                            File tempFile = new File(inputPath);
                            if (tempFile.exists() && tempFile.delete()) {
                                Log.d(TAG, "[IMMEDIATE] Temp file deleted successfully");
                            }
                        } catch (Exception e) {
                            Log.w(TAG, "[IMMEDIATE] Failed to delete temp file", e);
                        }

                        // Log final video info
                        VideoTrimmer.logVideoInfo(outputPath);

                        recordingState.set(RecordingState.IDLE);
                        callback.onRecordingStopped(outputPath, actualDurationMs);
                    }

                    @Override
                    public void onTrimError(String error) {
                        Log.e(TAG, String.format("[IMMEDIATE] Video trimming failed: %s", error));
                        recordingState.set(RecordingState.IDLE);
                        callback.onRecordingError("Video trimming failed: " + error);
                    }
                }
            );
        });
    }
}