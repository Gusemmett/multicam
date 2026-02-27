package com.emco.multicamandroid;

import android.content.Context;
import android.util.Log;

/**
 * Example usage of NetworkController and CameraController for synchronized recording.
 *
 * This demonstrates how to:
 * 1. Set up the camera controller
 * 2. Initialize time synchronization
 * 3. Start the network server
 * 4. Handle network commands for synchronized recording
 */
public class NetworkControllerExample {
    private static final String TAG = "NetworkControllerExample";

    private CameraController cameraController;
    private NetworkController networkController;

    public void initialize(Context context) {
        Log.d(TAG, "Initializing NetworkController example...");

        // 1. Initialize camera controller
        cameraController = new CameraController(context, /* lifecycleOwner */ null);

        // 2. Synchronize time with NTP servers for precise timing
        cameraController.synchronizeTime(new TimeSync.SyncCallback() {
            @Override
            public void onSyncComplete(boolean success, long offsetMs) {
                if (success) {
                    Log.i(TAG, String.format("Time synchronized successfully. Offset: %dms", offsetMs));
                    startNetworkServer(context);
                } else {
                    Log.e(TAG, "Time synchronization failed");
                }
            }

            @Override
            public void onSyncError(Exception error) {
                Log.e(TAG, "Time sync error", error);
            }
        });
    }

    private void startNetworkServer(Context context) {
        // 3. Initialize network controller
        networkController = new NetworkController(context, cameraController);

        networkController.setCallback(new NetworkController.NetworkCallback() {
            @Override
            public void onServerStarted() {
                Log.i(TAG, "Network server started successfully");
                Log.i(TAG, "Device is now discoverable as: multiCam-{deviceId}");
                Log.i(TAG, "Listening on port 8080 for commands:");
                Log.i(TAG, "  - START_RECORDING (with timestamp)");
                Log.i(TAG, "  - STOP_RECORDING");
                Log.i(TAG, "  - DEVICE_STATUS");
                Log.i(TAG, "  - GET_VIDEO {fileId}");
                Log.i(TAG, "  - HEARTBEAT");
            }

            @Override
            public void onServerStopped() {
                Log.i(TAG, "Network server stopped");
            }

            @Override
            public void onServerError(String error) {
                Log.e(TAG, "Network server error: " + error);
            }

            @Override
            public void onClientConnected(String clientAddress) {
                Log.i(TAG, "Client connected: " + clientAddress);
            }

            @Override
            public void onClientDisconnected(String clientAddress) {
                Log.i(TAG, "Client disconnected: " + clientAddress);
            }
        });

        // 4. Start the server (listens on port 8080, advertises via mDNS)
        networkController.startServer();
    }

    public void shutdown() {
        Log.d(TAG, "Shutting down...");

        if (networkController != null) {
            networkController.shutdown();
        }

        if (cameraController != null) {
            cameraController.shutdown();
        }
    }
}

/*
USAGE EXAMPLE FROM PYTHON CLIENT:

import socket
import json
import time

# Connect to Android device
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('192.168.1.100', 8080))  # Android device IP

# Start synchronized recording 3 seconds in future
target_time = time.time() + 3.0
cmd = {
    "command": "START_RECORDING",
    "timestamp": target_time,
    "deviceId": "controller"
}

sock.send((json.dumps(cmd) + '\n').encode('utf-8'))
response = json.loads(sock.recv(1024).decode('utf-8'))
print(f"Response: {response}")

# Wait for recording...
time.sleep(10)

# Stop recording
stop_cmd = {
    "command": "STOP_RECORDING",
    "timestamp": time.time(),
    "deviceId": "controller"
}

sock.send((json.dumps(stop_cmd) + '\n').encode('utf-8'))
response = json.loads(sock.recv(1024).decode('utf-8'))
print(f"Stop response: {response}")

sock.close()
*/