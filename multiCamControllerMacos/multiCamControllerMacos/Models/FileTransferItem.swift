//
//  FileTransferItem.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/26/25.
//

import Foundation

class FileTransferItem: ObservableObject, Identifiable {
    let id = UUID()

    @Published var deviceName: String
    @Published var fileId: String
    @Published var fileName: String
    @Published var status: TransferStatus
    @Published var downloadProgress: Double = 0.0
    @Published var uploadProgress: Double = 0.0
    @Published var errorMessage: String?
    @Published var localFilePath: String?
    @Published var s3Key: String?

    let sessionId: UUID
    let createdAt: Date

    enum TransferStatus {
        case queued
        case downloading
        case downloadCompleted
        case uploadQueued
        case uploading
        case completed
        case failed

        var displayText: String {
            switch self {
            case .queued: return "Queued"
            case .downloading: return "Downloading"
            case .downloadCompleted: return "Download Complete"
            case .uploadQueued: return "Upload Queued"
            case .uploading: return "Uploading"
            case .completed: return "Completed"
            case .failed: return "Failed"
            }
        }

        var icon: String {
            switch self {
            case .queued: return "clock"
            case .downloading: return "arrow.down.circle"
            case .downloadCompleted: return "checkmark.circle"
            case .uploadQueued: return "clock"
            case .uploading: return "arrow.up.circle"
            case .completed: return "checkmark.circle.fill"
            case .failed: return "exclamationmark.triangle"
            }
        }

        var color: String {
            switch self {
            case .queued, .uploadQueued: return "orange"
            case .downloading, .uploading: return "blue"
            case .downloadCompleted: return "green"
            case .completed: return "green"
            case .failed: return "red"
            }
        }
    }

    init(deviceName: String, fileId: String, sessionId: UUID) {
        self.deviceName = deviceName
        self.fileId = fileId
        self.fileName = "\(deviceName)_\(fileId).mp4"
        self.status = .queued
        self.sessionId = sessionId
        self.createdAt = Date()
    }

    var overallProgress: Double {
        switch status {
        case .queued:
            return 0.0
        case .downloading:
            return downloadProgress * 0.3
        case .downloadCompleted, .uploadQueued:
            return 0.3
        case .uploading:
            return 0.3 + (uploadProgress * 0.7)
        case .completed:
            return 1.0
        case .failed:
            return 0.0
        }
    }

    func updateDownloadProgress(_ progress: Double) {
        downloadProgress = progress
    }

    func updateUploadProgress(_ progress: Double) {
        uploadProgress = progress
    }

    func markDownloadCompleted(localPath: String) {
        localFilePath = localPath
        downloadProgress = 1.0
        status = .downloadCompleted
    }

    func markUploadQueued() {
        status = .uploadQueued
    }

    func markUploading() {
        status = .uploading
    }

    func markCompleted(s3Key: String) {
        self.s3Key = s3Key
        uploadProgress = 1.0
        status = .completed
    }

    func markFailed(error: String) {
        errorMessage = error
        status = .failed
    }
}