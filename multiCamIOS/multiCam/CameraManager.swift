//
//  CameraManager.swift
//  multiCam
//
//  Created by Claude Code on 8/24/25.
//

import AVFoundation
import UIKit
import CoreMedia
import MultiCamCommon

@MainActor
class CameraManager: NSObject, ObservableObject {
    @Published var isRecording = false {
        didSet {
            print("isRecording changed to: \(isRecording)")
        }
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @Published var isSetupComplete = false {
        didSet {
            print("isSetupComplete changed to: \(isSetupComplete)")
        }
    }

    @Published var errorMessage: String? {
        didSet {
            print("errorMessage changed to: \(errorMessage ?? "nil")")
        }
    }

    @Published var session: AVCaptureSession? {
        didSet {
            print("session changed to: \(session != nil ? "non-nil" : "nil")")
        }
    }

    // Time synchronization
    let timeSync = TimeSync()

    private var videoOutput: AVCaptureMovieFileOutput?
    private var currentVideoURL: URL?
    private var currentFileId: String?
    private var recordedFiles: [String: URL] = [:]
    private var onRecordingStopped: ((String, Int64) -> Void)?

    // Camera device and resolution for calibration data
    private var currentCameraDevice: AVCaptureDevice?
    private var recordingResolution: CGSize = CGSize(width: 1920, height: 1080) // Default 1080p
    private var cameraCalibration: AVCameraCalibrationData?
    private var photoOutput: AVCapturePhotoOutput?

    // Add device ID property to uniquely identify recordings per device
    private let deviceId: String = {
        if let savedId = UserDefaults.standard.string(forKey: "multiCamDeviceId") {
            return savedId
        }
        let nouns = [
            "Tiger", "Lion", "Eagle", "Shark", "Wolf", "Bear", "Falcon", "Hawk", "Panther", "Leopard",
            "Cobra", "Viper", "Dragon", "Phoenix", "Thunder", "Storm", "Lightning", "Blaze", "Frost", "Shadow",
            "Crystal", "Diamond", "Steel", "Iron", "Silver", "Gold", "Platinum", "Copper", "Bronze", "Titanium",
            "Rocket", "Comet", "Star", "Galaxy", "Nova", "Nebula", "Cosmos", "Orbit", "Meteor", "Asteroid",
            "Ocean", "Mountain", "River", "Forest", "Desert", "Glacier", "Volcano", "Canyon", "Valley", "Peak",
            "Arrow", "Sword", "Shield", "Hammer", "Blade", "Spear", "Bow", "Dart", "Lance", "Mace"
        ]
        let randomNoun = nouns.randomElement() ?? "Device"
        let uuid = UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
        let shortUuid = String(uuid.prefix(8))
        let newId = "\(randomNoun)-\(shortUuid)"
        UserDefaults.standard.set(newId, forKey: "multiCamDeviceId")
        return newId
    }()
    
    // Immediate recording + trimming properties
    private var commandReceivedTime: TimeInterval = 0
    private var targetStartTime: TimeInterval = 0
    private var actualRecordingStartTime: TimeInterval = 0
    private var firstFramePresentationTime: CMTime = CMTime.zero
    private var captureStartTime: CMTime = CMTime.zero

    // Recording state for immediate mode
    private var isImmediateRecording = false
    private var tempRecordingURL: URL?
    private var finalRecordingURL: URL?
    private var scheduledDuration: TimeInterval = 0

    // iOS version detection for startPTS support
    private var supportsStartPTS: Bool {
        if #available(iOS 18.2, *) {
            return true
        }
        return false
    }

    // MARK: - Configuration
    // Skip expensive video re-encoding to make stop responses instant
    private let SHOULD_SKIP_TRIMMING = true

    override init() {
        super.init()
        setupCamera()
        setupInterruptionHandlers()

        // Start NTP synchronization immediately
        Task {
            await timeSync.synchronizeTime()
        }
    }

    private func setupInterruptionHandlers() {
        // Handle session interruptions (e.g., low battery alerts, phone calls)
        NotificationCenter.default.addObserver(
            forName: .AVCaptureSessionWasInterrupted,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }

            if let reason = notification.userInfo?[AVCaptureSessionInterruptionReasonKey] as? AVCaptureSession.InterruptionReason {
                print("⚠️ AVCaptureSession INTERRUPTED")
                print("   Reason: \(self.interruptionReasonString(reason))")
                print("   Recording status: \(self.isRecording ? "RECORDING" : "NOT RECORDING")")

                // Don't stop recording - iOS will handle it gracefully
                // The session will continue recording through most interruptions
            }
        }

        NotificationCenter.default.addObserver(
            forName: .AVCaptureSessionInterruptionEnded,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            print("✅ AVCaptureSession interruption ENDED")
            print("   Recording status: \(self.isRecording ? "RECORDING" : "NOT RECORDING")")
        }

        // Handle when session runtime errors occur
        NotificationCenter.default.addObserver(
            forName: .AVCaptureSessionRuntimeError,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }

            if let error = notification.userInfo?[AVCaptureSessionErrorKey] as? AVError {
                print("❌ AVCaptureSession RUNTIME ERROR")
                print("   Error: \(error.localizedDescription)")
                print("   Recording status: \(self.isRecording ? "RECORDING" : "NOT RECORDING")")
            }
        }
    }

    private func interruptionReasonString(_ reason: AVCaptureSession.InterruptionReason) -> String {
        switch reason {
        case .videoDeviceNotAvailableInBackground:
            return "Video device not available in background"
        case .audioDeviceInUseByAnotherClient:
            return "Audio device in use by another app"
        case .videoDeviceInUseByAnotherClient:
            return "Video device in use by another app"
        case .videoDeviceNotAvailableWithMultipleForegroundApps:
            return "Video device not available with multiple foreground apps"
        case .videoDeviceNotAvailableDueToSystemPressure:
            return "Video device not available due to system pressure"
        @unknown default:
            return "Unknown reason (\(reason.rawValue))"
        }
    }
    
    private func setupCamera() {
        Task { @MainActor in
            do {
                print("Starting camera setup")
                await requestCameraPermission()
                await configureAudioSession()
                await configureSession()
                print("Camera setup completed")
            } catch {
                print("Camera setup error: \(error.localizedDescription)")
                self.errorMessage = error.localizedDescription
            }
        }
    }

    private func configureAudioSession() async {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            // Configure for recording with playback capabilities
            // Allow recording to continue even when system alerts appear
            try audioSession.setCategory(.playAndRecord, mode: .videoRecording, options: [.mixWithOthers, .allowBluetooth])
            try audioSession.setActive(true)
            print("Audio session configured successfully")
        } catch {
            print("Failed to configure audio session: \(error.localizedDescription)")
            // Don't fail the entire setup - camera can still work
        }
    }
    
    private func requestCameraPermission() async {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        print("Camera permission status: \(status.rawValue)")
        
        if status == .notDetermined {
            print("Requesting camera permission...")
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            print("Camera permission granted: \(granted)")
            if !granted {
                self.errorMessage = "Camera permission denied"
                return
            }
        } else if status != .authorized {
            print("Camera permission not authorized")
            self.errorMessage = "Camera permission not granted"
            return
        }
    }
    
    private func configureSession() async {
        print("Configuring capture session...")
        let session = AVCaptureSession()
        session.beginConfiguration()

        // Prevent automatic audio session configuration so we have full control
        session.automaticallyConfiguresApplicationAudioSession = false

        session.sessionPreset = .hd1920x1080
        print("Session preset set to 1080p")
        
        guard let camera = selectBackCameraPreferUltraWide() else {
            print("Could not access camera device")
            self.errorMessage = "Could not access camera"
            return
        }
        print("Camera device found: \(camera.localizedName)")

        // Store camera device for calibration data collection
        self.currentCameraDevice = camera
        
        do {
            let videoInput = try AVCaptureDeviceInput(device: camera)
            if session.canAddInput(videoInput) {
                session.addInput(videoInput)
            } else {
                self.errorMessage = "Could not add video input"
                return
            }
            // Additional configuration: lock device and set frame-rate / zoom preferences
            do {
                try camera.lockForConfiguration()
                // Force 1080p/30 if supported
                let ranges = camera.activeFormat.videoSupportedFrameRateRanges
                if ranges.contains(where: { $0.minFrameRate <= 30 && 30 <= $0.maxFrameRate }) {
                    camera.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 30)
                    camera.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 30)
                }
                // If virtual multi-camera, bias to ultra-wide by zooming to minimum factor
                if camera.deviceType == .builtInDualWideCamera || camera.deviceType == .builtInTripleCamera {
                    let target = camera.minAvailableVideoZoomFactor
                    camera.videoZoomFactor = max(target, 1.0)
                }
                camera.unlockForConfiguration()
            } catch {
                self.errorMessage = "Could not configure camera: \(error.localizedDescription)"
                return
            }
        } catch {
            self.errorMessage = "Could not create video input: \(error.localizedDescription)"
            return
        }
        
        guard let microphone = AVCaptureDevice.default(for: .audio) else {
            self.errorMessage = "Could not access microphone"
            return
        }
        
        do {
            let audioInput = try AVCaptureDeviceInput(device: microphone)
            if session.canAddInput(audioInput) {
                session.addInput(audioInput)
            }
        } catch {
            self.errorMessage = "Could not create audio input: \(error.localizedDescription)"
            return
        }
        
        let movieOutput = AVCaptureMovieFileOutput()
        if session.canAddOutput(movieOutput) {
            session.addOutput(movieOutput)

            if let connection = movieOutput.connection(with: .video) {
                if connection.isVideoStabilizationSupported {
                    connection.preferredVideoStabilizationMode = .auto
                }

                // Set video orientation to landscape
                if connection.isVideoOrientationSupported {
                    connection.videoOrientation = .landscapeRight
                    print("Video orientation set to landscape right")
                }

                // Configure H.265/HEVC codec
                if movieOutput.availableVideoCodecTypes.contains(.hevc) {
                    movieOutput.setOutputSettings([AVVideoCodecKey: AVVideoCodecType.hevc], for: connection)
                    print("Video codec set to H.265/HEVC")
                } else {
                    print("HEVC not available, falling back to default codec")
                }
            }
        } else {
            self.errorMessage = "Could not add movie output"
            return
        }

        // Add photo output for capturing calibration data
        let photoOut = AVCapturePhotoOutput()
        if session.canAddOutput(photoOut) {
            session.addOutput(photoOut)
            self.photoOutput = photoOut
            print("Photo output added for calibration capture")
        } else {
            print("WARNING: Could not add photo output - calibration data will be estimated")
        }

        session.commitConfiguration()
        
        self.session = session
        self.videoOutput = movieOutput
        print("Session configured, setting isSetupComplete = true")
        
        // Explicitly ensure UI update happens on main thread
        await MainActor.run {
            self.isSetupComplete = true
            print("isSetupComplete set to true on main thread")
        }
        
        Task.detached { [weak session] in
            print("Starting session on background thread...")
            session?.startRunning()
            print("Session started!")
        }

        // Capture calibration data asynchronously after session starts
        Task {
            await captureCalibrationData()
        }
    }
    
    private func selectBackCameraPreferUltraWide() -> AVCaptureDevice? {
        // Prefer the 0.5× ultra-wide camera when available, otherwise fall back to other back cameras.
        let types: [AVCaptureDevice.DeviceType] = [
            .builtInUltraWideCamera,     // 0.5× if available
            .builtInDualWideCamera,      // virtual device: ultra-wide + wide
            .builtInTripleCamera,        // virtual device: ultra-wide + wide + tele
            .builtInWideAngleCamera      // fallback (iPhone 8, etc.)
        ]
        let discovery = AVCaptureDevice.DiscoverySession(deviceTypes: types,
                                                         mediaType: .video,
                                                         position: .back)
        let devices = discovery.devices
        if let uw = devices.first(where: { $0.deviceType == .builtInUltraWideCamera }) { return uw }
        if let virt = devices.first(where: { $0.deviceType == .builtInDualWideCamera || $0.deviceType == .builtInTripleCamera }) { return virt }
        return devices.first(where: { $0.deviceType == .builtInWideAngleCamera })
    }

    // MARK: - Calibration Data Capture

    private func captureCalibrationData() async {
        // Wait a bit for session to fully start
        try? await Task.sleep(nanoseconds: 1_000_000_000) // 1 second

        guard let photoOutput = photoOutput else {
            print("CameraManager: No photo output available for calibration capture")
            return
        }

        guard photoOutput.isDepthDataDeliverySupported else {
            print("CameraManager: Depth data not supported - calibration will be estimated")
            return
        }

        print("CameraManager: Capturing depth photo for calibration data...")

        let settings = AVCapturePhotoSettings()
        settings.isDepthDataDeliveryEnabled = true

        let delegate = CalibrationPhotoDelegate { [weak self] calibrationData in
            self?.cameraCalibration = calibrationData
            if calibrationData != nil {
                print("CameraManager: ✅ Camera calibration data captured successfully")
            } else {
                print("CameraManager: ⚠️ Failed to capture calibration data")
            }
        }

        photoOutput.capturePhoto(with: settings, delegate: delegate)

        // Keep delegate alive for the capture
        try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
    }

    func startRecording(at scheduledTime: TimeInterval? = nil) {
        guard let videoOutput = videoOutput,
              !videoOutput.isRecording else {
            print("CameraManager: Cannot start recording - already recording or no video output")
            return
        }

        print("CameraManager: START RECORDING REQUEST")
        print("CameraManager: ==============================================")

        if let scheduledTime = scheduledTime {
            let currentSyncTime = timeSync.getSynchronizedTime()
            let delayUntilTarget = scheduledTime - currentSyncTime

            print("CameraManager: 📅 SCHEDULED RECORDING MODE")
            print("CameraManager:   - Target time: \(scheduledTime)")
            print("CameraManager:   - Current sync time: \(currentSyncTime)")
            print("CameraManager:   - Delay until target: \(Int(delayUntilTarget * 1000))ms")

            // Check if time is synchronized for scheduled recordings
            guard timeSync.isSynchronized else {
                print("CameraManager: Cannot accept scheduled recording: Time not synchronized")
                return
            }

            print("CameraManager: Time synchronized, proceeding with scheduled recording")
            // Use immediate recording with trimming for scheduled recordings
            // Duration will be calculated when STOP command is received
            startImmediateRecording(targetTime: scheduledTime)
        } else {
            print("CameraManager: IMMEDIATE RECORDING MODE")
            // Legacy immediate recording (no trimming)
            let timestamp = timeSync.getSynchronizedTime()
            let timestampMs = Int64(timestamp * 1000)
            let fileId = "\(deviceId)_\(timestampMs).mov"
            let documentsPath = getDocumentsDirectory()
            let videoURL = documentsPath.appendingPathComponent(fileId)

            print("CameraManager:   - File ID: \(fileId)")
            print("CameraManager:   - File path: \(videoURL.lastPathComponent)")

            currentVideoURL = videoURL
            currentFileId = fileId
            executeRecordingStart(to: videoURL)
        }
    }

    func startImmediateRecording(targetTime: TimeInterval) {
        guard let videoOutput = videoOutput,
              !videoOutput.isRecording else {
            print("CameraManager: Cannot start immediate recording - already recording or no video output")
            return
        }

        // Store timing information
        commandReceivedTime = timeSync.getSynchronizedTime()
        targetStartTime = targetTime
        scheduledDuration = 0 // Will be calculated when recording stops
        isImmediateRecording = true

        let timingAccuracy = targetTime - commandReceivedTime

        print("CameraManager: IMMEDIATE RECORDING WITH TRIMMING")
        print("CameraManager:   - Target start time: \(targetTime)")
        print("CameraManager:   - Command received time: \(commandReceivedTime)")
        print("CameraManager:   - Timing accuracy: \(Int(timingAccuracy * 1000))ms \(timingAccuracy > 0 ? "(future)" : "(past)")")

        // Create temporary file URL
        let timestamp = Date().timeIntervalSince1970
        let tempFileName = "temp_recording_\(timestamp).mov"
        tempRecordingURL = getDocumentsDirectory().appendingPathComponent(tempFileName)

        // Create final file URL
        let targetTimestampMs = Int64(targetTime * 1000)
        let finalFileName = "\(deviceId)_\(targetTimestampMs).mov"
        finalRecordingURL = getDocumentsDirectory().appendingPathComponent(finalFileName)
        currentFileId = "\(deviceId)_\(targetTimestampMs).mov"

        print("CameraManager:   - Temp file: \(tempRecordingURL?.lastPathComponent ?? "nil")")
        print("CameraManager:   - Final file: \(finalRecordingURL?.lastPathComponent ?? "nil")")
        print("CameraManager:   - File ID: \(currentFileId ?? "nil")")

        print("CameraManager: Starting camera recording to temp file...")
        // Start recording immediately to temp file
        videoOutput.startRecording(to: tempRecordingURL!, recordingDelegate: self)
        isRecording = true
    }
    
    private func executeRecordingStart(to videoURL: URL) {
        guard let videoOutput = videoOutput else {
            print("CameraManager: Cannot execute recording start - no video output")
            return
        }

        let actualStartTime = Date().timeIntervalSince1970
        print("CameraManager: Executing immediate recording start")
        print("CameraManager:   - Recording start time: \(actualStartTime)")
        print("CameraManager:   - Recording to: \(videoURL.lastPathComponent)")

        videoOutput.startRecording(to: videoURL, recordingDelegate: self)
        isRecording = true
    }
    
    func stopRecording() {
        guard let videoOutput = videoOutput,
              videoOutput.isRecording else {
            print("CameraManager: Cannot stop recording - not currently recording")
            return
        }

        let stopRequestTime = timeSync.getSynchronizedTime()
        print("CameraManager: 🛑 STOP RECORDING REQUEST")
        print("CameraManager: ==============================================")
        print("CameraManager:   - Stop request time: \(stopRequestTime)")

        if isImmediateRecording {
            let recordingDuration = stopRequestTime - commandReceivedTime
            print("CameraManager:   - Recording mode: IMMEDIATE (with trimming)")
            print("CameraManager:   - Command received time: \(commandReceivedTime)")
            print("CameraManager:   - Total recording duration: \(Int(recordingDuration * 1000))ms")
            print("CameraManager:   - Target start time: \(targetStartTime)")
        } else {
            print("CameraManager:   - Recording mode: LEGACY (direct)")
        }

        print("CameraManager: Stopping camera recording...")
        videoOutput.stopRecording()
    }
    
    func getDocumentsDirectory() -> URL {
        return FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }
    
    func listSavedVideos() -> [URL] {
        let documentsPath = getDocumentsDirectory()
        
        do {
            let fileURLs = try FileManager.default.contentsOfDirectory(at: documentsPath, includingPropertiesForKeys: nil)
            return fileURLs.filter { $0.pathExtension.lowercased() == "mov" }
        } catch {
            print("Error listing videos: \(error)")
            return []
        }
    }
    
    func getVideoURL(for fileName: String) -> URL? {
        // First check if it's a file from current session
        if let url = recordedFiles[fileName] {
            return url
        }

        // If not found, check the Documents directory for existing files
        let documentsPath = getDocumentsDirectory()
        let potentialURL = documentsPath.appendingPathComponent(fileName)

        if FileManager.default.fileExists(atPath: potentialURL.path) {
            return potentialURL
        }

        return nil
    }
    
    func getCurrentFileId() -> String? {
        return currentFileId
    }
    
    func setRecordingStoppedHandler(_ handler: @escaping (String, Int64) -> Void) {
        self.onRecordingStopped = handler
    }

    func getCameraInfo() -> (device: AVCaptureDevice, resolution: CGSize, calibration: AVCameraCalibrationData?)? {
        guard let device = currentCameraDevice else {
            return nil
        }
        return (device: device, resolution: recordingResolution, calibration: cameraCalibration)
    }

    func getAllVideoFiles() -> [FileMetadata] {
        let documentsPath = getDocumentsDirectory()
        var files: [FileMetadata] = []

        do {
            let fileURLs = try FileManager.default.contentsOfDirectory(at: documentsPath, includingPropertiesForKeys: [.fileSizeKey, .creationDateKey, .contentModificationDateKey])

            for url in fileURLs {
                guard url.pathExtension.lowercased() == "mov" else { continue }

                let fileName = url.lastPathComponent

                let resourceValues = try url.resourceValues(forKeys: [.fileSizeKey, .creationDateKey, .contentModificationDateKey])

                let fileSize = Int64(resourceValues.fileSize ?? 0)
                let creationDate = resourceValues.creationDate?.timeIntervalSince1970 ?? 0
                let modificationDate = resourceValues.contentModificationDate?.timeIntervalSince1970 ?? 0

                let metadata = FileMetadata(
                    fileName: fileName,
                    fileSize: fileSize,
                    creationDate: creationDate,
                    modificationDate: modificationDate
                )

                files.append(metadata)
            }

            // Sort by creation date, newest first
            files.sort { $0.creationDate > $1.creationDate }

        } catch {
            print("Error getting file metadata: \(error)")
        }

        return files
    }

    // MARK: - Video Trimming Implementation

    private func trimVideoToTarget() {
        guard let tempURL = tempRecordingURL,
              let finalURL = finalRecordingURL else {
            print("Missing URLs for trimming")
            return
        }

        let asset = AVAsset(url: tempURL)

        // Calculate trim offset
        let trimOffsetSeconds = targetStartTime - actualRecordingStartTime
        let trimStartTime = CMTime(seconds: max(0, trimOffsetSeconds), preferredTimescale: 600)

        // Calculate the actual duration to keep (from target start time until recording stop)
        let effectiveRecordingDuration = scheduledDuration - max(0, trimOffsetSeconds)

        // Safety check: if trim offset is larger than total duration, use a minimal duration
        let finalDuration = max(0.1, effectiveRecordingDuration) // Minimum 0.1s
        let recordingDuration = CMTime(seconds: finalDuration, preferredTimescale: 600)

        print("Trimming video:")
        print("   • Trim offset: \(trimOffsetSeconds)s")
        print("   • Start time: \(trimStartTime)")
        print("   • Total recorded duration: \(scheduledDuration)s")
        print("   • Effective duration: \(effectiveRecordingDuration)s")
        print("   • Final duration: \(finalDuration)s")

        // Create export session with HEVC preset
        guard let exportSession = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetHEVCHighestQuality) else {
            print("Failed to create export session")
            fallbackToTempFile()
            return
        }

        // Set trim range
        let trimRange = CMTimeRange(start: trimStartTime, duration: recordingDuration)
        exportSession.timeRange = trimRange
        exportSession.outputURL = finalURL
        exportSession.outputFileType = .mov

        // Export trimmed video
        exportSession.exportAsynchronously { [weak self] in
            DispatchQueue.main.async {
                self?.handleTrimCompletion(exportSession: exportSession)
            }
        }
    }

    private func handleTrimCompletion(exportSession: AVAssetExportSession) {
        switch exportSession.status {
        case .completed:
            print("Video trimming completed successfully")

            // Store final file reference
            if let finalURL = finalRecordingURL,
               let fileId = currentFileId {
                recordedFiles[fileId] = finalURL
                print("Final video stored: \(finalURL.lastPathComponent)")

                // Get file size
                let fileSize = (try? FileManager.default.attributesOfItem(atPath: finalURL.path)[.size] as? Int64) ?? 0

                // Notify completion
                onRecordingStopped?(fileId, fileSize)
            }

            // Cleanup
            cleanupTempFiles()

        case .failed:
            print("Video trimming failed: \(exportSession.error?.localizedDescription ?? "Unknown error")")
            fallbackToTempFile()

        case .cancelled:
            print("Video trimming cancelled")
            fallbackToTempFile()

        default:
            print("Video trimming status: \(exportSession.status.rawValue)")
            fallbackToTempFile()
        }

        // Reset state
        isImmediateRecording = false
    }

    private func handleNormalRecordingCompletion(_ outputFileURL: URL) {
        print("Recording saved to: \(outputFileURL)")
        if let fileId = currentFileId {
            recordedFiles[fileId] = outputFileURL
            print("Stored file mapping: \(fileId) -> \(outputFileURL.lastPathComponent)")

            // Get file size
            let fileSize = (try? FileManager.default.attributesOfItem(atPath: outputFileURL.path)[.size] as? Int64) ?? 0

            // Notify callback of recording completion
            onRecordingStopped?(fileId, fileSize)
        }
    }

    private func handleImmediateRecordingWithoutTrim(_ outputFileURL: URL) {
        print("CameraManager: Using full recording without trimming (instant response mode)")

        guard let tempURL = tempRecordingURL,
              let finalURL = finalRecordingURL else {
            print("CameraManager: ERROR - No temp or final URL available")
            return
        }

        // Move temp file to final destination
        do {
            // Remove final file if it exists
            if FileManager.default.fileExists(atPath: finalURL.path) {
                try FileManager.default.removeItem(at: finalURL)
            }

            // Move temp file to final location
            try FileManager.default.moveItem(at: tempURL, to: finalURL)
            print("CameraManager: Moved recording from temp to final location")
            print("CameraManager:   - Final file: \(finalURL.lastPathComponent)")

            if let fileId = currentFileId {
                recordedFiles[fileId] = finalURL

                // Get file size
                let fileSize = (try? FileManager.default.attributesOfItem(atPath: finalURL.path)[.size] as? Int64) ?? 0
                print("CameraManager:   - File size: \(fileSize) bytes")

                // Notify callback immediately (no trimming delay!)
                onRecordingStopped?(fileId, fileSize)
            }

            // Clean up
            tempRecordingURL = nil
            finalRecordingURL = nil
            isImmediateRecording = false
        } catch {
            print("CameraManager: ERROR moving file: \(error)")
            errorMessage = "Failed to save recording: \(error.localizedDescription)"
        }
    }

    private func fallbackToTempFile() {
        guard let tempURL = tempRecordingURL,
              let finalURL = finalRecordingURL else { return }

        // If trimming fails, use the original temp file
        do {
            if FileManager.default.fileExists(atPath: finalURL.path) {
                try FileManager.default.removeItem(at: finalURL)
            }
            try FileManager.default.moveItem(at: tempURL, to: finalURL)

            if let fileId = currentFileId {
                recordedFiles[fileId] = finalURL

                // Get file size
                let fileSize = (try? FileManager.default.attributesOfItem(atPath: finalURL.path)[.size] as? Int64) ?? 0

                onRecordingStopped?(fileId, fileSize)
            }

            print("Used fallback temp file due to trimming failure")
        } catch {
            print("Fallback failed: \(error)")
        }

        // Don't call cleanupTempFiles here since we moved the temp file
        tempRecordingURL = nil
    }

    private func cleanupTempFiles() {
        if let tempURL = tempRecordingURL,
           FileManager.default.fileExists(atPath: tempURL.path) {
            try? FileManager.default.removeItem(at: tempURL)
        }
        tempRecordingURL = nil
    }

    private func logPerformanceMetrics() {
        let commandToRecordLatency = actualRecordingStartTime - commandReceivedTime
        let targetAccuracy = abs(targetStartTime - actualRecordingStartTime)

        print("Performance Metrics:")
        print("   • Command to record latency: \(Int(commandToRecordLatency * 1000))ms")
        print("   • Target timing accuracy: \(Int(targetAccuracy * 1000))ms")
        print("   • Supports startPTS: \(supportsStartPTS)")
    }
}

extension CameraManager: AVCaptureFileOutputRecordingDelegate {
    // iOS 18.2+ with precise startPTS
    @available(iOS 18.2, *)
    nonisolated func fileOutput(_ output: AVCaptureFileOutput,
                               didStartRecordingTo fileURL: URL,
                               startPTS: CMTime,
                               from connections: [AVCaptureConnection]) {
        DispatchQueue.main.async {
            self.actualRecordingStartTime = self.timeSync.getSynchronizedTime()
            self.firstFramePresentationTime = startPTS

            print("CameraManager: RECORDING STARTED (iOS 18.2+ with startPTS)")
            print("CameraManager: ==============================================")
            print("CameraManager:   - File URL: \(fileURL.lastPathComponent)")
            print("CameraManager:   - Start PTS: \(startPTS)")
            print("CameraManager:   - Actual start time: \(self.actualRecordingStartTime)")

            if self.isImmediateRecording {
                let timingOffset = self.targetStartTime - self.actualRecordingStartTime
                print("CameraManager:   - Target start time: \(self.targetStartTime)")
                print("CameraManager:   - Timing offset: \(Int(timingOffset * 1000))ms")
                print("CameraManager:   - Mode: Immediate with trimming")
                self.logPerformanceMetrics()
            } else {
                print("CameraManager:   - Mode: Legacy direct recording")
            }
        }
    }

    // iOS < 18.2 fallback
    nonisolated func fileOutput(_ output: AVCaptureFileOutput, didStartRecordingTo fileURL: URL, from connections: [AVCaptureConnection]) {
        DispatchQueue.main.async {
            self.actualRecordingStartTime = self.timeSync.getSynchronizedTime()

            // Capture session synchronization clock time as fallback
            if let session = self.session, let syncClock = session.synchronizationClock {
                self.captureStartTime = syncClock.time
            }

            print("CameraManager: RECORDING STARTED (iOS < 18.2 fallback)")
            print("CameraManager: ==============================================")
            print("CameraManager:   - File URL: \(fileURL.lastPathComponent)")
            print("CameraManager:   - Actual start time: \(self.actualRecordingStartTime)")
            print("CameraManager:   - Sync clock time: \(self.captureStartTime)")

            if self.isImmediateRecording {
                let timingOffset = self.targetStartTime - self.actualRecordingStartTime
                print("CameraManager:   - Target start time: \(self.targetStartTime)")
                print("CameraManager:   - Timing offset: \(Int(timingOffset * 1000))ms")
                print("CameraManager:   - Mode: Immediate with trimming")
                self.logPerformanceMetrics()
            } else {
                print("CameraManager:   - Mode: Legacy direct recording")
            }
        }
    }

    nonisolated func fileOutput(_ output: AVCaptureFileOutput, didFinishRecordingTo outputFileURL: URL, from connections: [AVCaptureConnection], error: Error?) {
        DispatchQueue.main.async {
            self.isRecording = false

            let recordingStopTime = self.timeSync.getSynchronizedTime()
            print("CameraManager: 🛑 RECORDING FINISHED")
            print("CameraManager: ==============================================")
            print("CameraManager:   - Stop time: \(recordingStopTime)")
            print("CameraManager:   - Output file: \(outputFileURL.lastPathComponent)")

            if let error = error {
                print("CameraManager: Recording error: \(error)")
                self.errorMessage = "Recording failed: \(error.localizedDescription)"
                self.cleanupTempFiles()
                return
            }

            if self.isImmediateRecording {
                // Calculate actual recording duration
                let actualRecordingDuration = recordingStopTime - self.actualRecordingStartTime
                self.scheduledDuration = actualRecordingDuration

                print("CameraManager: Immediate recording completed")
                print("CameraManager:   - Recording start time: \(self.actualRecordingStartTime)")
                print("CameraManager:   - Recording stop time: \(recordingStopTime)")
                print("CameraManager:   - Actual recording duration: \(Int(actualRecordingDuration * 1000))ms")
                print("CameraManager:   - Target start time: \(self.targetStartTime)")

                // Check if we should skip trimming (for instant stop response)
                if self.SHOULD_SKIP_TRIMMING {
                    print("CameraManager: SKIPPING TRIM - Using full recording for instant response")
                    self.handleImmediateRecordingWithoutTrim(outputFileURL)
                } else {
                    print("CameraManager: Starting trim process...")
                    self.trimVideoToTarget()
                }
            } else {
                print("CameraManager: Legacy recording completed")
                let recordingDuration = recordingStopTime - self.actualRecordingStartTime
                print("CameraManager:   - Recording duration: \(Int(recordingDuration * 1000))ms")
                // Handle normal recording completion
                self.handleNormalRecordingCompletion(outputFileURL)
            }
        }
    }
}

// MARK: - Calibration Photo Delegate

private class CalibrationPhotoDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    private let completion: (AVCameraCalibrationData?) -> Void

    init(completion: @escaping (AVCameraCalibrationData?) -> Void) {
        self.completion = completion
        super.init()
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        if let error = error {
            print("CalibrationPhotoDelegate: Photo capture error: \(error)")
            completion(nil)
            return
        }

        guard let depthData = photo.depthData else {
            print("CalibrationPhotoDelegate: No depth data in photo")
            completion(nil)
            return
        }

        let calibrationData = depthData.cameraCalibrationData
        print("CalibrationPhotoDelegate: Extracted calibration data from depth photo")
        completion(calibrationData)
    }
}
