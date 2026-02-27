//
//  RecordingControlsView.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import SwiftUI

struct RecordingControlsView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var deviceCommunication: DeviceCommunication
    @ObservedObject var s3Manager: S3Manager
    @ObservedObject var fileManager: FileTransferManager

    @State private var countdownTimer: Timer?
    @State private var countdownSeconds = 0

    var body: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                Image(systemName: "video.circle")
                    .foregroundColor(.red)
                    .font(.title2)
                Text("Recording Controls")
                    .font(.headline)
                Spacer()
            }

            // Sync delay info
            Text("Synchronized recording with 3-second delay")
                .font(.caption)
                .foregroundColor(.secondary)

            // Recording buttons
            HStack(spacing: 20) {
                Button(action: startRecording) {
                    HStack {
                        Image(systemName: appState.recordingSession.isRecording ? "record.circle.fill" : "video.fill")
                        Text(appState.recordingSession.isRecording ? "Recording..." : "Start Recording")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(appState.discoveredDevices.isEmpty || appState.recordingSession.isRecording)

                Button(action: stopRecording) {
                    HStack {
                        Image(systemName: "stop.circle")
                        Text("Stop Recording")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(!appState.recordingSession.isRecording)
            }

            // Countdown display
            if countdownSeconds > 0 {
                Text("Recording starts in \(countdownSeconds)...")
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(.red)
                    .transition(.scale.combined(with: .opacity))
            }

            // Status
            VStack(spacing: 8) {
                Text(appState.statusMessage)
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
            }
        }
        .padding()
        .background(Color(.controlBackgroundColor))
        .cornerRadius(10)
        .animation(.easeInOut(duration: 0.3), value: countdownSeconds)
    }

    private func startRecording() {
        guard !appState.discoveredDevices.isEmpty else {
            appState.updateStatus("❌ No devices available. Discover devices first.")
            return
        }

        appState.updateStatus("🔴 Starting recording...")
        appState.recordingSession.startRecording()

        // Send the command immediately with future timestamp
        executeRecordingStart()

        // Start countdown for visual feedback only
        countdownSeconds = 3
        countdownTimer?.invalidate()
        countdownTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { timer in
            countdownSeconds -= 1
            if countdownSeconds <= 0 {
                timer.invalidate()
                countdownTimer = nil
                // Countdown is complete, but command was already sent
            }
        }
    }

    private func executeRecordingStart() {
        Task {
            do {
                print("🎬 Starting recording on \(appState.discoveredDevices.count) devices")

                // Log device details for debugging
                for device in appState.discoveredDevices {
                    print("📱 Device: \(device.displayName) at \(device.ip):\(device.port)")
                }

                let command = MultiCamCommand.startRecording
                let results = await deviceCommunication.sendCommandToAllDevices(
                    devices: appState.discoveredDevices,
                    command: command,
                    syncDelay: 3.0
                )

                // Count successful responses using multiCam device status codes
                let successCount = results.values.compactMap { response -> Int? in
                    return response.isSuccess ? 1 : nil
                }.count

                print("📊 Recording start results: \(successCount)/\(results.count) successful")

                if successCount > 0 {
                    appState.updateStatus("🔴 Recording... Started on \(successCount) device(s)")
                } else {
                    let errorMessages = results.compactMap { (deviceName, response) in
                        response.error != nil ? "\(deviceName): \(response.error!)" : nil
                    }
                    print("❌ Recording start errors: \(errorMessages)")

                    appState.updateStatus("❌ Failed to start recording")
                    appState.recordingSession.resetSession()
                }
            } catch {
                print("❌ Recording start exception: \(error)")
                appState.updateStatus("❌ Recording start failed: \(error.localizedDescription)")
                appState.recordingSession.resetSession()
            }
        }
    }

    private func stopRecording() {
        guard appState.recordingSession.isRecording else { return }

        Task {
            appState.updateStatus("⏹️ Stopping recording...")

            let command = MultiCamCommand.stopRecording
            let results = await deviceCommunication.sendCommandToAllDevices(
                devices: appState.discoveredDevices,
                command: command
            )

            // Extract file IDs from responses
            var fileIds: [String: String] = [:]
            for (deviceName, response) in results {
                if let fileId = response.fileId, !fileId.isEmpty {
                    fileIds[deviceName] = fileId
                }
            }

            appState.recordingSession.stopRecording(with: fileIds)

            if !fileIds.isEmpty {
                appState.updateStatus("✅ Recording stopped. \(fileIds.count) files queued for processing.")

                // Add files to the file manager for async processing
                fileManager.addTransferItems(fileIds: fileIds, sessionId: appState.recordingSession.sessionId)
            } else {
                appState.updateStatus("✅ Recording stopped, but no files returned.")
            }
        }
    }

}

#Preview {
    RecordingControlsView(
        appState: AppState(),
        deviceCommunication: DeviceCommunication(),
        s3Manager: S3Manager(bucketName: "test-bucket"),
        fileManager: FileTransferManager()
    )
    .frame(width: 500, height: 300)
}