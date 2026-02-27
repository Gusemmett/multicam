//
//  RecordingSession.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation

class RecordingSession: ObservableObject {
    @Published var isRecording = false
    @Published var recordingStartTime: Date?
    @Published var fileIds: [String: String] = [:] // deviceName: fileId
    @Published var downloadProgress: [String: Double] = [:] // fileName: progress
    @Published var uploadProgress: UploadProgress?

    let sessionId = UUID()

    struct UploadProgress {
        var currentFileIndex: Int = 0
        var totalFiles: Int = 0
        var currentFileProgress: Double = 0
        var currentFileName: String = ""
        var overallProgress: Double = 0

        mutating func update(fileIndex: Int, totalFiles: Int, fileProgress: Double, fileName: String) {
            self.currentFileIndex = fileIndex
            self.totalFiles = totalFiles
            self.currentFileProgress = fileProgress
            self.currentFileName = fileName

            // Calculate overall progress
            let filesCompleted = Double(fileIndex)
            let perFileContribution = 100.0 / Double(totalFiles)
            let currentFileContribution = perFileContribution * (fileProgress / 100.0)
            self.overallProgress = (filesCompleted * perFileContribution) + currentFileContribution
        }
    }

    func startRecording() {
        isRecording = true
        recordingStartTime = Date()
        fileIds.removeAll()
        downloadProgress.removeAll()
        uploadProgress = nil
    }

    func stopRecording(with fileIds: [String: String]) {
        isRecording = false
        self.fileIds = fileIds
    }

    func resetSession() {
        isRecording = false
        recordingStartTime = nil
        fileIds.removeAll()
        downloadProgress.removeAll()
        uploadProgress = nil
    }
}