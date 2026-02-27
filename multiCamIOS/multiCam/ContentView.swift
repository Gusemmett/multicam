//
//  ContentView.swift
//  multiCam
//
//  Created by Angus Emmett on 8/23/25.
//

import SwiftUI
import Network
import UIKit

struct ContentView: View {
    @StateObject private var cameraManager = CameraManager()
    @StateObject private var networkManager = NetworkManager()
    @StateObject private var uploadManager = UploadManager()
    @State private var batteryLevel: Float = UIDevice.current.batteryLevel

    var body: some View {
        ZStack {
            // Black background to hide white bars around camera preview
            Color.black
                .ignoresSafeArea(.all)

            Group {
                if let session = cameraManager.session, cameraManager.isSetupComplete {
                    CameraPreviewView(session: session, deviceId: networkManager.getDeviceId())
                        .ignoresSafeArea(.all)
                        .clipped()
                        .onAppear {
                            print("Camera preview appeared")
                        }
                } else {
                    Color.black
                        .ignoresSafeArea(.all)
                        .onAppear {
                            print("Showing black screen - setupComplete: \(cameraManager.isSetupComplete), session: \(cameraManager.session != nil)")
                            if let error = cameraManager.errorMessage {
                                print("Error: \(error)")
                            }
                        }
                }
            }
            .onChange(of: cameraManager.isSetupComplete) { setupComplete in
                print("UI detected isSetupComplete change: \(setupComplete)")
            }
            .onChange(of: cameraManager.session) { session in
                print("UI detected session change: \(session != nil)")
            }

            // Recording status indicator and battery indicator
            VStack {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(cameraManager.isRecording ? "RECORDING" : "NOT RECORDING")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundColor(cameraManager.isRecording ? .red : .white)

                        Text("Device ID: \(networkManager.getDeviceId())")
                            .font(.caption)
                            .fontWeight(.bold)
                            .foregroundColor(.white)
                    }
                    .padding(.leading, 20)
                    .padding(.top, 20)

                    Spacer()

                    // Battery indicator
                    Text(batteryLevel >= 0 ? "\(Int(batteryLevel * 100))%" : "--")
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(batteryLevel < 0.25 ? .red : .white)
                        .padding(.trailing, 20)
                        .padding(.top, 20)
                }
                Spacer()
            }
        }
        .onAppear {
            // Enable battery monitoring
            UIDevice.current.isBatteryMonitoringEnabled = true
            batteryLevel = UIDevice.current.batteryLevel

            // Observe battery level changes
            NotificationCenter.default.addObserver(
                forName: UIDevice.batteryLevelDidChangeNotification,
                object: nil,
                queue: .main
            ) { _ in
                batteryLevel = UIDevice.current.batteryLevel
            }

            // Force landscape orientation aggressively
            DispatchQueue.main.async {
                UIDevice.current.setValue(UIInterfaceOrientation.landscapeRight.rawValue, forKey: "orientation")
                UINavigationController.attemptRotationToDeviceOrientation()
            }

            // Also force it again after a short delay to ensure it takes effect
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                UIDevice.current.setValue(UIInterfaceOrientation.landscapeRight.rawValue, forKey: "orientation")
                UINavigationController.attemptRotationToDeviceOrientation()
            }

            // Store network connections that are waiting for stop recording response
            var pendingStopConnections: [NWConnection] = []
            
            networkManager.setCommandTypeHandler { command, timestamp in
                switch command {
                case .startRecording:
                    cameraManager.startRecording()
                case .stopRecording:
                    cameraManager.stopRecording()
                case .deviceStatus, .heartbeat, .getVideo, .listFiles, .uploadToCloud:
                    break
                }
            }
            
            networkManager.setScheduledStartHandler { scheduledTime in
                cameraManager.startRecording(at: scheduledTime)
            }
            
            networkManager.setStopRecordingHandler { connection in
                pendingStopConnections.append(connection)
            }
            
            cameraManager.setRecordingStoppedHandler { fileName, fileSize in
                networkManager.setLastRecordedFileName(fileName)

                // Send responses to all pending connections
                for connection in pendingStopConnections {
                    networkManager.sendStopRecordingResponse(to: connection, fileName: fileName, fileSize: fileSize)
                }
                pendingStopConnections.removeAll()
            }

            networkManager.setGetVideoHandler { fileName in
                return cameraManager.getVideoURL(for: fileName)
            }
            
            networkManager.setListFilesHandler {
                return cameraManager.getAllVideoFiles()
            }

            networkManager.setSyncStatusHandler {
                return cameraManager.timeSync.isSynchronized
            }

            networkManager.setRecordingStatusHandler {
                return cameraManager.isRecording
            }

            networkManager.setCameraInfoHandler {
                return cameraManager.getCameraInfo()
            }

            // Connect upload manager to network manager
            networkManager.setUploadManager(uploadManager)
        }
    }
}

#Preview {
    ContentView()
}
