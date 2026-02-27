//
//  DeviceCommunication.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation
import Network

@MainActor
class DeviceCommunication: ObservableObject {
    private let timeoutInterval: TimeInterval = 60.0 // Timeout for non-download commands

    // Helper class to manage continuation state safely
    private class ContinuationState: @unchecked Sendable {
        private var _isResumed = false
        private let lock = NSLock()

        var isResumed: Bool {
            lock.withLock { _isResumed }
        }

        func markResumed() -> Bool {
            lock.withLock {
                if _isResumed {
                    return false // Already resumed
                }
                _isResumed = true
                return true // Successfully marked as resumed
            }
        }
    }

    enum CommunicationError: Error, LocalizedError {
        case connectionFailed(String)
        case encodingFailed
        case decodingFailed
        case timeout
        case invalidResponse
        case fileDownloadFailed(String)

        var errorDescription: String? {
            switch self {
            case .connectionFailed(let message):
                return "Connection failed: \(message)"
            case .encodingFailed:
                return "Failed to encode command"
            case .decodingFailed:
                return "Failed to decode response"
            case .timeout:
                return "Request timed out - device may be offline"
            case .invalidResponse:
                return "Invalid response from device"
            case .fileDownloadFailed(let message):
                return "File download failed: \(message)"
            }
        }
    }

    func sendCommand(
        to device: MultiCamDevice,
        command: MultiCamCommand,
        progressCallback: (@Sendable (Double) -> Void)? = nil
    ) async throws -> MultiCamResponse {
        // Validate port range
        guard device.port > 0 && device.port <= 65535 else {
            throw CommunicationError.connectionFailed("Invalid port number: \(device.port)")
        }

        let connection = NWConnection(
            host: NWEndpoint.Host(device.ip),
            port: NWEndpoint.Port(integerLiteral: UInt16(device.port)),
            using: .tcp
        )

        return try await withCheckedThrowingContinuation { continuation in
            let state = ContinuationState()

            connection.stateUpdateHandler = { connectionState in
                switch connectionState {
                case .ready:
                    Task {
                        do {
                            let response = try await self.sendCommandData(
                                connection: connection,
                                command: command,
                                progressCallback: progressCallback
                            )
                            if state.markResumed() {
                                continuation.resume(returning: response)
                            }
                        } catch {
                            if state.markResumed() {
                                continuation.resume(throwing: error)
                            }
                        }
                    }
                case .failed(let error):
                    if state.markResumed() {
                        continuation.resume(throwing: CommunicationError.connectionFailed(error.localizedDescription))
                    }
                case .cancelled:
                    if state.markResumed() {
                        continuation.resume(throwing: CommunicationError.connectionFailed("Connection cancelled"))
                    }
                default:
                    break
                }
            }

            connection.start(queue: .main)

            // Set timeout only for non-file-download commands
            // File downloads have their own stall-based timeout
            if command.command != "GET_VIDEO" {
                DispatchQueue.main.asyncAfter(deadline: .now() + timeoutInterval) {
                    if state.markResumed() {
                        connection.cancel()
                        continuation.resume(throwing: CommunicationError.timeout)
                    }
                }
            }
        }
    }

    private func sendCommandData(
        connection: NWConnection,
        command: MultiCamCommand,
        progressCallback: (@Sendable (Double) -> Void)? = nil
    ) async throws -> MultiCamResponse {
        // Encode command to JSON
        let encoder = JSONEncoder()
        guard let commandData = try? encoder.encode(command) else {
            throw CommunicationError.encodingFailed
        }

        print("📤 Sending command: \(command.command) to device")

        // Send command
        return try await withCheckedThrowingContinuation { continuation in
            let state = ContinuationState()

            connection.send(content: commandData, completion: .contentProcessed { error in
                if let error = error {
                    if state.markResumed() {
                        continuation.resume(throwing: CommunicationError.connectionFailed(error.localizedDescription))
                    }
                    return
                }

                // Handle different response types
                if command.command == "GET_VIDEO" {
                    // Handle file download
                    Task {
                        do {
                            let filePath = try await self.handleFileDownload(
                                connection: connection,
                                fileId: command.fileId ?? "",
                                progressCallback: progressCallback ?? { _ in }
                            )
                            let response = MultiCamResponse(status: "success", message: filePath, fileId: command.fileId, files: nil, error: nil)
                            if state.markResumed() {
                                continuation.resume(returning: response)
                            }
                        } catch {
                            if state.markResumed() {
                                continuation.resume(throwing: error)
                            }
                        }
                    }
                } else {
                    // Handle JSON response
                    connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { data, _, isComplete, error in
                        if let error = error {
                            if state.markResumed() {
                                continuation.resume(throwing: CommunicationError.connectionFailed(error.localizedDescription))
                            }
                            return
                        }

                        guard let data = data else {
                            if state.markResumed() {
                                continuation.resume(throwing: CommunicationError.invalidResponse)
                            }
                            return
                        }

                        do {
                            let decoder = JSONDecoder()
                            let response = try decoder.decode(MultiCamResponse.self, from: data)
                            print("📦 Parsed JSON response for \(command.command): \(response)")
                            if state.markResumed() {
                                continuation.resume(returning: response)
                            }
                        } catch {
                            // Log raw response for debugging
                            if let responseString = String(data: data, encoding: .utf8) {
                                print("📦 Raw response for \(command.command): '\(responseString)'")

                                // Handle various response formats for different commands
                                let trimmed = responseString.trimmingCharacters(in: .whitespacesAndNewlines)

                                // For START_RECORDING, check for known status responses
                                if command.command == "START_RECORDING" {
                                    // Check if it's a known multiCam status
                                    let knownStatuses = ["ready", "recording", "scheduled_recording_accepted", "command_received", "ok", "200"]
                                    if trimmed.isEmpty || knownStatuses.contains(trimmed.lowercased()) {
                                        let status = trimmed.isEmpty ? "command_received" : trimmed
                                        let response = MultiCamResponse(status: status, message: trimmed, fileId: nil, files: nil, error: nil)
                                        if state.markResumed() {
                                            continuation.resume(returning: response)
                                        }
                                        return
                                    }
                                }

                                // Try to handle raw string response for STOP_RECORDING
                                if command.command == "STOP_RECORDING" && !responseString.isEmpty {
                                    let response = MultiCamResponse(status: "success", message: nil, fileId: responseString.trimmingCharacters(in: .whitespacesAndNewlines), files: nil, error: nil)
                                    if state.markResumed() {
                                        continuation.resume(returning: response)
                                    }
                                    return
                                }
                            } else {
                                print("📦 Binary response for \(command.command), length: \(data.count)")
                            }

                            print("❌ JSON decode failed for \(command.command): \(error)")
                            if state.markResumed() {
                                continuation.resume(throwing: CommunicationError.decodingFailed)
                            }
                        }
                    }
                }
            })
        }
    }

    private func handleFileDownload(
        connection: NWConnection,
        fileId: String,
        progressCallback: @escaping @Sendable (Double) -> Void
    ) async throws -> String {
        print("📥 Starting file download for fileId: \(fileId)")

        return try await withCheckedThrowingContinuation { continuation in
            // First, read header size (4 bytes)
            connection.receive(minimumIncompleteLength: 4, maximumLength: 4) { headerSizeData, _, _, error in
                if let error = error {
                    continuation.resume(throwing: CommunicationError.fileDownloadFailed("Header size read failed: \(error.localizedDescription)"))
                    return
                }

                guard let headerSizeData = headerSizeData, headerSizeData.count == 4 else {
                    continuation.resume(throwing: CommunicationError.fileDownloadFailed("Invalid header size data"))
                    return
                }

                // Parse header size (big-endian uint32)
                let headerSize = headerSizeData.withUnsafeBytes { $0.load(as: UInt32.self).bigEndian }
                print("📄 Header size: \(headerSize) bytes")

                // Read header data
                connection.receive(minimumIncompleteLength: Int(headerSize), maximumLength: Int(headerSize)) { headerData, _, _, error in
                    if let error = error {
                        continuation.resume(throwing: CommunicationError.fileDownloadFailed("Header read failed: \(error.localizedDescription)"))
                        return
                    }

                    guard let headerData = headerData else {
                        continuation.resume(throwing: CommunicationError.fileDownloadFailed("No header data received"))
                        return
                    }

                    do {
                        // Parse header JSON
                        let headerInfo = try JSONSerialization.jsonObject(with: headerData) as! [String: Any]
                        let fileName = headerInfo["fileName"] as! String
                        let fileSize = headerInfo["fileSize"] as! Int64

                        print("📁 File: \(fileName), Size: \(fileSize) bytes (\(Double(fileSize) / 1024 / 1024) MB)")

                        // Create downloads directory
                        let downloadsDir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
                        let multiCamDir = downloadsDir.appendingPathComponent("multiCam")
                        try FileManager.default.createDirectory(at: multiCamDir, withIntermediateDirectories: true)

                        // Use original filename (already contains device ID)
                        let localPath = multiCamDir.appendingPathComponent(fileName)

                        // Download file data
                        Task {
                            do {
                                try await self.downloadFileData(
                                    connection: connection,
                                    fileSize: fileSize,
                                    localPath: localPath,
                                    progressCallback: progressCallback
                                )
                                continuation.resume(returning: localPath.path)
                            } catch {
                                continuation.resume(throwing: error)
                            }
                        }

                    } catch {
                        continuation.resume(throwing: CommunicationError.fileDownloadFailed("Header parsing failed: \(error.localizedDescription)"))
                    }
                }
            }
        }
    }

    private func downloadFileData(
        connection: NWConnection,
        fileSize: Int64,
        localPath: URL,
        progressCallback: @escaping @Sendable (Double) -> Void
    ) async throws {
        let outputStream = OutputStream(url: localPath, append: false)!
        outputStream.open()
        defer { outputStream.close() }

        var bytesReceived: Int64 = 0
        let chunkSize = 8192
        let stallTimeout: TimeInterval = 600.0 // Timeout if no progress for 10 minutes
        var lastProgressTime = Date()

        while bytesReceived < fileSize {
            let remainingBytes = fileSize - bytesReceived

            // Ensure remainingBytes is positive
            guard remainingBytes > 0 else {
                print("⚠️ Invalid remaining bytes: \(remainingBytes), stopping download")
                break
            }

            let requestSize = min(chunkSize, Int(remainingBytes))

            // Check for stall timeout
            let timeSinceLastProgress = Date().timeIntervalSince(lastProgressTime)
            if timeSinceLastProgress > stallTimeout {
                throw CommunicationError.fileDownloadFailed("Download stalled - no progress for \(Int(stallTimeout)) seconds")
            }

            let chunkData: Data = try await withCheckedThrowingContinuation { continuation in
                connection.receive(minimumIncompleteLength: 1, maximumLength: requestSize) { data, _, _, error in
                    if let error = error {
                        continuation.resume(throwing: CommunicationError.fileDownloadFailed("Chunk read failed: \(error.localizedDescription)"))
                        return
                    }

                    guard let data = data else {
                        continuation.resume(throwing: CommunicationError.fileDownloadFailed("No chunk data received"))
                        return
                    }

                    continuation.resume(returning: data)
                }
            }

            // Write chunk to file
            let bytesWritten = chunkData.withUnsafeBytes { bytes in
                outputStream.write(bytes.bindMemory(to: UInt8.self).baseAddress!, maxLength: chunkData.count)
            }

            if bytesWritten < 0 {
                throw CommunicationError.fileDownloadFailed("File write failed")
            }

            bytesReceived += Int64(chunkData.count)
            lastProgressTime = Date() // Reset stall timeout on progress

            // Progress update
            let progress = Double(bytesReceived) / Double(fileSize)

            // Call progress callback
            Task { @MainActor in
                progressCallback(progress)
            }
        }

        print("✅ File downloaded successfully: \(localPath.path)")
    }

    func sendCommandToAllDevices(
        devices: [MultiCamDevice],
        command: MultiCamCommand,
        syncDelay: TimeInterval = 0
    ) async -> [String: MultiCamResponse] {
        var results: [String: MultiCamResponse] = [:]

        // For START_RECORDING, calculate future timestamp
        let syncTimestamp = Date().timeIntervalSince1970 + syncDelay
        let syncCommand = MultiCamCommand(
            command: command.command,
            timestamp: command.command == "START_RECORDING" ? syncTimestamp : command.timestamp,
            deviceId: command.deviceId,
            fileId: command.fileId
        )

        if command.command == "START_RECORDING" && syncDelay > 0 {
            print("🎬 Broadcasting synchronized \(command.command) to \(devices.count) device(s)")
            print("⏰ Scheduled start time: \(syncTimestamp) (in \(syncDelay) seconds)")
        }

        // Send commands concurrently
        await withTaskGroup(of: (String, Result<MultiCamResponse, Error>).self) { group in
            for device in devices {
                group.addTask {
                    do {
                        let response = try await self.sendCommand(to: device, command: syncCommand)
                        return (device.name, .success(response))
                    } catch {
                        print("❌ Failed to send command to \(device.name): \(error)")
                        return (device.name, .failure(error))
                    }
                }
            }

            for await (deviceName, result) in group {
                switch result {
                case .success(let response):
                    // Debug log the actual response
                    print("✅ Response from \(deviceName):")
                    print("   Status: \(response.status ?? "nil")")
                    print("   Message: \(response.message ?? "nil")")
                    print("   FileId: \(response.fileId ?? "nil")")
                    print("   Error: \(response.error ?? "nil")")
                    print("   IsSuccess: \(response.isSuccess)")
                    results[deviceName] = response
                case .failure(let error):
                    print("❌ Error from \(deviceName): \(error)")
                    // Create error response
                    results[deviceName] = MultiCamResponse(
                        status: "error",
                        message: error.localizedDescription,
                        fileId: nil,
                        files: nil,
                        error: error.localizedDescription
                    )
                }
            }
        }

        return results
    }
}
