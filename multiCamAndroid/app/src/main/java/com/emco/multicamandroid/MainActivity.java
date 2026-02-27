package com.emco.multicamandroid;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.PowerManager;
import android.view.View;
import android.view.WindowManager;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.view.PreviewView;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

public class MainActivity extends AppCompatActivity implements CameraController.CameraCallback {

    private static final String TAG = "MultiCamAndroid";
    private static final int REQUEST_CODE_PERMISSIONS = 10;
    private static final String[] REQUIRED_PERMISSIONS = {
        Manifest.permission.CAMERA,
        Manifest.permission.RECORD_AUDIO,
        Manifest.permission.INTERNET,
        Manifest.permission.ACCESS_NETWORK_STATE
    };

    private PreviewView previewView;
    private CameraController cameraController;
    private NetworkController networkController;
    private PowerManager.WakeLock wakeLock;

    private TextView recordingStatusText;
    private TextView deviceIdText;
    private Handler statusUpdateHandler;
    private Runnable statusUpdateRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Enable immersive fullscreen mode
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN,
                WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);

        // Keep app open and prevent phone from sleeping
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // Acquire wake lock to keep the device awake
        PowerManager powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MultiCamAndroid:WakeLock");
        wakeLock.acquire();

        setContentView(R.layout.activity_main);

        previewView = findViewById(R.id.previewView);
        recordingStatusText = findViewById(R.id.recordingStatusText);
        deviceIdText = findViewById(R.id.deviceIdText);

        cameraController = new CameraController(this, this);

        // Initialize status display
        updateRecordingStatus(false);
        updateDeviceIdDisplay();

        // Start periodic status updates
        startStatusUpdates();

        if (allPermissionsGranted()) {
            startCamera();
        } else {
            ActivityCompat.requestPermissions(this, REQUIRED_PERMISSIONS, REQUEST_CODE_PERMISSIONS);
        }
    }

    private void startCamera() {
        cameraController.startCamera(previewView, this);
    }

    @Override
    public void onCameraReady() {
        // Camera is ready, now start the network controller
        startNetworkController();
    }

    private void startNetworkController() {
        // First synchronize time for precise recording
        cameraController.synchronizeTime(new TimeSync.SyncCallback() {
            @Override
            public void onSyncComplete(boolean success, long offsetMs) {
                if (success) {
                    runOnUiThread(() -> {
                        Toast.makeText(MainActivity.this, "Time synchronized (offset: " + offsetMs + "ms)", Toast.LENGTH_SHORT).show();
                    });
                } else {
                    runOnUiThread(() -> {
                        Toast.makeText(MainActivity.this, "Time sync failed - recording may be inaccurate", Toast.LENGTH_LONG).show();
                    });
                }
            }

            @Override
            public void onSyncError(Exception error) {
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Time sync error: " + error.getMessage(), Toast.LENGTH_LONG).show();
                });
            }
        });

        networkController = new NetworkController(this, cameraController);

        // Update device ID display now that we have NetworkController
        updateDeviceIdDisplay();

        networkController.setCallback(new NetworkController.NetworkCallback() {
            @Override
            public void onServerStarted() {
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Network server started - device discoverable", Toast.LENGTH_SHORT).show();
                });
            }

            @Override
            public void onServerStopped() {
                // Server stopped
            }

            @Override
            public void onServerError(String error) {
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Network error: " + error, Toast.LENGTH_LONG).show();
                });
            }

            @Override
            public void onClientConnected(String clientAddress) {
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Client connected: " + clientAddress, Toast.LENGTH_SHORT).show();
                });
            }

            @Override
            public void onClientDisconnected(String clientAddress) {
                // Client disconnected
            }
        });

        // Start the server
        networkController.startServer();
    }

    @Override
    public void onCameraError(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private boolean allPermissionsGranted() {
        for (String permission : REQUIRED_PERMISSIONS) {
            if (ContextCompat.checkSelfPermission(this, permission) != PackageManager.PERMISSION_GRANTED) {
                return false;
            }
        }
        return true;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_CODE_PERMISSIONS) {
            if (allPermissionsGranted()) {
                startCamera();
            } else {
                Toast.makeText(this, "Camera permission is required to use this app",
                    Toast.LENGTH_LONG).show();
                finish();
            }
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();

        if (networkController != null) {
            networkController.shutdown();
        }

        if (cameraController != null) {
            cameraController.shutdown();
        }

        // Stop status updates
        stopStatusUpdates();

        // Release wake lock
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
    }

    private void updateRecordingStatus(boolean isRecording) {
        runOnUiThread(() -> {
            if (recordingStatusText != null) {
                if (isRecording) {
                    recordingStatusText.setText("RECORDING");
                    recordingStatusText.setTextColor(getResources().getColor(android.R.color.holo_red_light, null));
                } else {
                    recordingStatusText.setText("NOT RECORDING");
                    recordingStatusText.setTextColor(getResources().getColor(android.R.color.white, null));
                }
            }
        });
    }

    private void updateDeviceIdDisplay() {
        // Get device ID from NetworkController when it's initialized
        if (networkController != null) {
            String deviceId = DeviceIdGenerator.getDeviceId(this);
            runOnUiThread(() -> {
                if (deviceIdText != null) {
                    deviceIdText.setText("Device ID: " + deviceId);
                }
            });
        } else {
            // Show loading text until NetworkController is ready
            runOnUiThread(() -> {
                if (deviceIdText != null) {
                    deviceIdText.setText("Device ID: Loading...");
                }
            });
        }
    }

    private void startStatusUpdates() {
        statusUpdateHandler = new Handler();
        statusUpdateRunnable = new Runnable() {
            @Override
            public void run() {
                // Update recording status based on actual camera controller state
                if (cameraController != null) {
                    boolean isRecording = cameraController.isRecording();
                    updateRecordingStatus(isRecording);
                }

                // Schedule next update
                if (statusUpdateHandler != null) {
                    statusUpdateHandler.postDelayed(this, 250); // Update every 250ms for smooth UI
                }
            }
        };

        // Start the updates
        statusUpdateHandler.post(statusUpdateRunnable);
    }

    private void stopStatusUpdates() {
        if (statusUpdateHandler != null && statusUpdateRunnable != null) {
            statusUpdateHandler.removeCallbacks(statusUpdateRunnable);
            statusUpdateHandler = null;
            statusUpdateRunnable = null;
        }
    }

    // Method to be called when recording status changes (for immediate updates)
    public void onRecordingStatusChanged(boolean isRecording) {
        updateRecordingStatus(isRecording);
    }
}