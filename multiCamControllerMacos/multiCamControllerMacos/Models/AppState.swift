//
//  AppState.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation
import SwiftUI

@MainActor
class AppState: ObservableObject {
    @Published var discoveredDevices: [MultiCamDevice] = []
    @Published var statusMessage = "🔴 Ready"
    @Published var isDiscovering = false
    @Published var recordingSession = RecordingSession()

    // OAK Server state
    @Published var isOAKServerRunning = false
    @Published var oakServerPort = 8081

    // S3 Configuration
    let s3BucketName = "87c3e07f-3661-4489-829a-ddfa26943cb3"
    let s3Region = "us-east-1"

    func updateStatus(_ message: String) {
        statusMessage = message
    }

    func addDevice(_ device: MultiCamDevice) {
        // Update existing device or add new one
        if let index = discoveredDevices.firstIndex(where: { $0.name == device.name }) {
            discoveredDevices[index] = device
        } else {
            discoveredDevices.append(device)
        }
    }

    func removeDevice(named deviceName: String) {
        discoveredDevices.removeAll { $0.name == deviceName }
    }

    func clearDevices() {
        discoveredDevices.removeAll()
    }

    func removeOAKDevices() {
        discoveredDevices.removeAll { device in
            device.deviceType == .oak || device.name.contains("oak-")
        }
    }

    var deviceStatusText: String {
        if discoveredDevices.isEmpty {
            return """
            No devices discovered yet.

            Make sure:
            • iPhone multiCam apps are running
            • All devices on same WiFi network
            • OAK server is started (if using OAK camera)
            """
        }

        let deviceList = discoveredDevices.map { device in
            "\(device.deviceType.icon) \(device.displayName): \(device.ip):\(device.port)"
        }.joined(separator: "\n")

        return deviceList
    }
}