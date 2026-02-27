//
//  FileManager.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/26/25.
//

import Foundation
import SwiftUI

@MainActor
class FileTransferManager: ObservableObject {
    @Published var transferItems: [FileTransferItem] = []
    @Published var isProcessing = false

    private var deviceCommunication: DeviceCommunication?
    private var s3Manager: S3Manager?
    private var appState: AppState?

    private let maxConcurrentUploads = 2
    private var activeUploadTasks: Set<UUID> = []

    func configure(deviceCommunication: DeviceCommunication, s3Manager: S3Manager, appState: AppState) {
        self.deviceCommunication = deviceCommunication
        self.s3Manager = s3Manager
        self.appState = appState
    }

    func addTransferItems(fileIds: [String: String], sessionId: UUID) {
        for (deviceName, fileId) in fileIds {
            let transferItem = FileTransferItem(
                deviceName: deviceName,
                fileId: fileId,
                sessionId: sessionId
            )
            transferItems.append(transferItem)
        }

        startProcessingQueue()
    }

    private func startProcessingQueue() {
        guard !isProcessing else { return }
        isProcessing = true

        Task {
            await processTransferQueue()
        }
    }

    private func processTransferQueue() async {
        guard let deviceCommunication = deviceCommunication,
              let s3Manager = s3Manager,
              let appState = appState else {
            print("❌ FileTransferManager not properly configured")
            return
        }

        let queuedItems = transferItems.filter { $0.status == .queued }

        for item in queuedItems {
            await downloadFile(item: item, deviceCommunication: deviceCommunication, appState: appState)
        }

        await processUploadQueue(s3Manager: s3Manager)

        isProcessing = false

        if hasQueuedItems() {
            startProcessingQueue()
        }
    }

    private func downloadFile(
        item: FileTransferItem,
        deviceCommunication: DeviceCommunication,
        appState: AppState
    ) async {
        guard let device = appState.discoveredDevices.first(where: { $0.name == item.deviceName }) else {
            item.markFailed(error: "Device not found: \(item.deviceName)")
            return
        }

        item.status = .downloading

        do {
            let command = MultiCamCommand.getVideo(fileId: item.fileId)
            let response = try await deviceCommunication.sendCommand(
                to: device,
                command: command,
                progressCallback: { progress in
                    Task { @MainActor in
                        item.updateDownloadProgress(progress)
                    }
                }
            )

            if let filePath = response.message, !filePath.isEmpty {
                item.markDownloadCompleted(localPath: filePath)
                item.markUploadQueued()
                print("✅ Downloaded file from \(item.deviceName): \(filePath)")
            } else {
                item.markFailed(error: "No file path returned from device")
            }
        } catch {
            item.markFailed(error: "Download failed: \(error.localizedDescription)")
            print("❌ Failed to download from \(item.deviceName): \(error)")
        }
    }

    private func processUploadQueue(s3Manager: S3Manager) async {
        let uploadQueuedItems = transferItems.filter {
            $0.status == .uploadQueued && !activeUploadTasks.contains($0.id)
        }

        let availableSlots = maxConcurrentUploads - activeUploadTasks.count
        let itemsToProcess = Array(uploadQueuedItems.prefix(availableSlots))

        await withTaskGroup(of: Void.self) { group in
            for item in itemsToProcess {
                activeUploadTasks.insert(item.id)
                group.addTask {
                    await self.uploadFile(item: item, s3Manager: s3Manager)
                }
            }
        }
    }

    private func uploadFile(item: FileTransferItem, s3Manager: S3Manager) async {
        guard let localFilePath = item.localFilePath else {
            item.markFailed(error: "No local file path available")
            activeUploadTasks.remove(item.id)
            return
        }

        item.markUploading()

        let result = await s3Manager.uploadSingleFile(
            filePath: localFilePath,
            sessionFolder: generateSessionFolder(for: item.sessionId)
        ) { progress in
            Task { @MainActor in
                item.updateUploadProgress(progress)
            }
        }

        await MainActor.run {
            activeUploadTasks.remove(item.id)

            if result.success, let s3Key = result.s3Key {
                item.markCompleted(s3Key: s3Key)
                cleanupLocalFile(at: localFilePath)
            } else {
                item.markFailed(error: result.error ?? "Upload failed")
            }
        }

        if hasQueuedUploadItems() {
            Task {
                await processUploadQueue(s3Manager: s3Manager)
            }
        }
    }

    private func cleanupLocalFile(at path: String) {
        do {
            //try Foundation.FileManager.default.removeItem(atPath: path)
            print("🗑️ Deleted local file: \(URL(fileURLWithPath: path).lastPathComponent)")
        } catch {
            print("⚠️ Failed to delete \(path): \(error.localizedDescription)")
        }
    }

    private func generateSessionFolder(for sessionId: UUID) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd/HH-mm-ss"

        // Try to get the recording start time from AppState's current session
        var folderTimestamp: String
        if let appState = appState,
           appState.recordingSession.sessionId == sessionId,
           let startTime = appState.recordingSession.recordingStartTime {
            folderTimestamp = formatter.string(from: startTime)
        } else {
            // Fallback to current time if session not found
            folderTimestamp = formatter.string(from: Date())
        }

        return "\(folderTimestamp)_\(sessionId.uuidString.prefix(8))/"
    }

    private func hasQueuedItems() -> Bool {
        return transferItems.contains { $0.status == .queued }
    }

    private func hasQueuedUploadItems() -> Bool {
        return transferItems.contains { $0.status == .uploadQueued }
    }

    func clearCompletedItems() {
        transferItems.removeAll { $0.status == .completed }
    }

    func retryFailedItem(_ item: FileTransferItem) {
        guard item.status == .failed else { return }

        item.status = .queued
        item.downloadProgress = 0.0
        item.uploadProgress = 0.0
        item.errorMessage = nil

        startProcessingQueue()
    }

    var activeTransfersCount: Int {
        transferItems.filter {
            $0.status == .downloading || $0.status == .uploading
        }.count
    }

    var completedTransfersCount: Int {
        transferItems.filter { $0.status == .completed }.count
    }

    var failedTransfersCount: Int {
        transferItems.filter { $0.status == .failed }.count
    }
}
