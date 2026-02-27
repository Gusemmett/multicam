//
//  MultiCamCommand.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation

struct MultiCamCommand: Codable {
    let command: String
    let timestamp: TimeInterval
    let deviceId: String
    let fileId: String?

    init(command: String, timestamp: TimeInterval? = nil, deviceId: String = "controller", fileId: String? = nil) {
        self.command = command
        self.timestamp = timestamp ?? Date().timeIntervalSince1970
        self.deviceId = deviceId
        self.fileId = fileId
    }

    static let startRecording = MultiCamCommand(command: "START_RECORDING")
    static let stopRecording = MultiCamCommand(command: "STOP_RECORDING")
    static let deviceStatus = MultiCamCommand(command: "DEVICE_STATUS")
    static let listFiles = MultiCamCommand(command: "LIST_FILES")

    static func getVideo(fileId: String) -> MultiCamCommand {
        MultiCamCommand(command: "GET_VIDEO", fileId: fileId)
    }
}

struct MultiCamResponse: Codable {
    let status: String?
    let message: String?
    let fileId: String?
    let files: [FileInfo]?
    let error: String?

    struct FileInfo: Codable {
        let fileName: String
        let fileId: String
        let fileSize: Int64
        let creationDate: TimeInterval
    }

    // Helper to check if response indicates success based on multiCam device status codes
    var isSuccess: Bool {
        guard let status = status else {
            // No status field - consider success if no error
            return error == nil
        }

        // Check against known multiCam device status codes
        switch status.lowercased() {
        case "ready", "recording", "scheduled_recording_accepted", "command_received", "recording_stopped":
            return true
        case "error", "time_not_synchronized", "file_not_found":
            return false
        case "stopping":
            return true // Stopping is still a valid state, not an error
        default:
            // Unknown status - consider success if no error field
            return error == nil
        }
    }
}