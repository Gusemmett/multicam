//
//  UploadManager.swift
//  multiCam
//
//  Created by Claude Code on 10/15/25.
//

import Foundation
import MultiCamCommon
import AWSS3
import AWSClientRuntime
import AWSSDKIdentity
import ClientRuntime

/// Manages upload queue and handles file uploads to cloud storage
@MainActor
class UploadManager: NSObject, ObservableObject {

    // MARK: - Published Properties

    @Published var currentUpload: UploadItem?
    @Published var pendingQueue: [UploadItem] = []
    @Published var failedQueue: [UploadItem] = []

    // MARK: - Private Properties

    private var uploadSession: URLSession?
    private var currentTask: URLSessionUploadTask?
    private var retryAttempts: [String: Int] = [:] // fileName -> retry count
    private let maxRetries = 3

    // IAM credential storage for uploads
    private var iamCredentials: [String: IAMCredentials] = [:] // fileName -> credentials
    private var calibrationData: [String: CalibrationData] = [:] // fileName -> calibration data

    // Progress tracking
    private var uploadStartTime: Date?
    private var lastProgressUpdate: Date?
    private var lastBytesUploaded: Int64 = 0

    // Persistence
    private let queueFileURL: URL = {
        let documentsDirectory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        return documentsDirectory.appendingPathComponent("uploadQueue.json")
    }()

    // MARK: - Initialization

    override init() {
        super.init()
        setupURLSession()
        loadQueue()

        // Start processing queue if there are items
        if !pendingQueue.isEmpty {
            processNextUpload()
        }
    }

    // MARK: - Public Methods

    /// Add a file to the upload queue (presigned URL)
    func queueUpload(fileName: String, fileURL: URL, uploadUrl: String) {
        // Check if already in queue
        if pendingQueue.contains(where: { $0.fileName == fileName }) ||
           currentUpload?.fileName == fileName {
            print("UploadManager: File \(fileName) already in queue")
            return
        }

        // Get file size
        guard let fileSize = try? FileManager.default.attributesOfItem(atPath: fileURL.path)[.size] as? Int64 else {
            print("UploadManager: Could not get file size for \(fileName)")
            return
        }

        let uploadItem = UploadItem(
            fileName: fileName,
            fileSize: fileSize,
            bytesUploaded: 0,
            uploadProgress: 0.0,
            uploadSpeed: 0,
            status: UploadStatus.queued.rawValue,
            uploadUrl: uploadUrl,
            error: nil
        )

        pendingQueue.append(uploadItem)
        saveQueue()

        print("UploadManager: Added \(fileName) to queue (\(pendingQueue.count) items)")

        // Start processing if no current upload
        if currentUpload == nil {
            processNextUpload()
        }
    }

    /// Add a file to the upload queue with IAM credentials
    func queueUploadWithIAM(
        fileName: String,
        fileURL: URL,
        bucket: String,
        key: String,
        accessKeyId: String,
        secretAccessKey: String,
        sessionToken: String,
        region: String,
        deviceId: String,
        calibration: CalibrationData
    ) {
        // Check if already in queue
        if pendingQueue.contains(where: { $0.fileName == fileName }) ||
           currentUpload?.fileName == fileName {
            print("UploadManager: File \(fileName) already in queue")
            return
        }

        // Get file size
        guard let fileSize = try? FileManager.default.attributesOfItem(atPath: fileURL.path)[.size] as? Int64 else {
            print("UploadManager: Could not get file size for \(fileName)")
            return
        }

        // Store IAM credentials and calibration data for this upload
        let credentials = IAMCredentials(
            bucket: bucket,
            key: key,
            accessKeyId: accessKeyId,
            secretAccessKey: secretAccessKey,
            sessionToken: sessionToken,
            region: region,
            deviceId: deviceId
        )
        iamCredentials[fileName] = credentials
        calibrationData[fileName] = calibration

        // Create upload item (use s3:// URL for display)
        let uploadItem = UploadItem(
            fileName: fileName,
            fileSize: fileSize,
            bytesUploaded: 0,
            uploadProgress: 0.0,
            uploadSpeed: 0,
            status: UploadStatus.queued.rawValue,
            uploadUrl: "s3://\(bucket)/\(key)",
            error: nil
        )

        pendingQueue.append(uploadItem)
        saveQueue()

        print("UploadManager: Added \(fileName) to IAM upload queue (\(pendingQueue.count) items)")

        // Start processing if no current upload
        if currentUpload == nil {
            processNextUpload()
        }
    }

    /// Get current upload status
    func getStatus() -> (current: UploadItem?, pending: [UploadItem], failed: [UploadItem]) {
        return (currentUpload, pendingQueue, failedQueue)
    }

    /// Retry a failed upload
    func retryFailedUpload(fileName: String) {
        guard let index = failedQueue.firstIndex(where: { $0.fileName == fileName }) else {
            return
        }

        var item = failedQueue.remove(at: index)
        item = UploadItem(
            fileName: item.fileName,
            fileSize: item.fileSize,
            bytesUploaded: 0,
            uploadProgress: 0.0,
            uploadSpeed: 0,
            status: UploadStatus.queued.rawValue,
            uploadUrl: item.uploadUrl,
            error: nil
        )

        retryAttempts[fileName] = 0
        pendingQueue.append(item)
        saveQueue()

        if currentUpload == nil {
            processNextUpload()
        }
    }

    /// Clear failed queue
    func clearFailedQueue() {
        failedQueue.removeAll()
        saveQueue()
    }

    // MARK: - Private Methods

    /// Read a chunk of data from a file without loading the entire file into memory
    nonisolated private func readFileChunk(at url: URL, offset: Int, length: Int) throws -> Data {
        let fileHandle = try FileHandle(forReadingFrom: url)
        defer {
            try? fileHandle.close()
        }

        // Seek to the offset
        if #available(iOS 13.4, *) {
            try fileHandle.seek(toOffset: UInt64(offset))
        } else {
            fileHandle.seek(toFileOffset: UInt64(offset))
        }

        // Read the chunk
        if #available(iOS 13.4, *) {
            guard let data = try fileHandle.read(upToCount: length) else {
                throw NSError(domain: "UploadManager", code: -1,
                            userInfo: [NSLocalizedDescriptionKey: "Failed to read file chunk"])
            }
            return data
        } else {
            return fileHandle.readData(ofLength: length)
        }
    }

    private func setupURLSession() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 300 // 5 minutes
        config.timeoutIntervalForResource = 3600 // 1 hour
        uploadSession = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    private func processNextUpload() {
        guard currentUpload == nil, !pendingQueue.isEmpty else {
            return
        }

        let item = pendingQueue.removeFirst()
        currentUpload = item
        saveQueue()

        print("UploadManager: Starting upload for \(item.fileName)")
        startUpload(item: item)
    }

    private func startUpload(item: UploadItem) {
        // Get file URL from CameraManager (stored in Documents)
        let documentsDirectory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let fileURL = documentsDirectory.appendingPathComponent(item.fileName)

        // Check if file exists
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            handleUploadFailure(item: item, error: "File not found: \(item.fileName)")
            return
        }

        // Check if this upload uses IAM credentials
        if let credentials = iamCredentials[item.fileName] {
            print("UploadManager: Using IAM credentials for \(item.fileName)")
            uploadWithIAMCredentials(item: item, fileURL: fileURL, credentials: credentials)
            return
        }

        // Otherwise, use presigned URL method
        // Create upload request
        guard let uploadUrl = item.uploadUrl, let url = URL(string: uploadUrl) else {
            handleUploadFailure(item: item, error: "Invalid upload URL")
            return
        }

        print("UploadManager: Creating upload request")
        print("UploadManager:   File: \(item.fileName)")
        print("UploadManager:   Size: \(item.fileSize) bytes")
        print("UploadManager:   URL host: \(url.host ?? "unknown")")
        print("UploadManager:   URL path: \(url.path)")

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        // NOTE: Not setting Content-Type - S3 presigned URLs may reject if Content-Type wasn't included in signature

        print("UploadManager:   HTTP Method: \(request.httpMethod ?? "nil")")
        print("UploadManager:   Headers: \(request.allHTTPHeaderFields ?? [:])")

        // Initialize upload tracking
        uploadStartTime = Date()
        lastProgressUpdate = Date()
        lastBytesUploaded = 0

        // For large files (> 50MB), use streaming upload from file to avoid memory issues
        // For smaller files, load into memory for simplicity
        let task: URLSessionUploadTask?
        let fileSizeThreshold = 50 * 1024 * 1024 // 50MB

        if item.fileSize > fileSizeThreshold {
            // Stream from disk (memory efficient for large files)
            print("UploadManager:   Using streaming upload for large file (\(item.fileSize) bytes)")
            task = uploadSession?.uploadTask(with: request, fromFile: fileURL)
        } else {
            // Load into memory (simpler for small files)
            guard let fileData = try? Data(contentsOf: fileURL) else {
                handleUploadFailure(item: item, error: "Could not read file data")
                return
            }
            print("UploadManager:   Data loaded: \(fileData.count) bytes")
            task = uploadSession?.uploadTask(with: request, from: fileData)
        }

        currentTask = task

        // Update status to uploading
        if var current = currentUpload {
            current = UploadItem(
                fileName: current.fileName,
                fileSize: current.fileSize,
                bytesUploaded: current.bytesUploaded,
                uploadProgress: current.uploadProgress,
                uploadSpeed: current.uploadSpeed,
                status: UploadStatus.uploading.rawValue,
                uploadUrl: current.uploadUrl,
                error: nil
            )
            currentUpload = current
        }

        task?.resume()
        print("UploadManager: Upload task started for \(item.fileName)")
    }

    /// Remove file extension from path if present (e.g., "path/file.mov" -> "path")
    private func stripFileExtensionFromPath(_ path: String) -> String {
        let components = path.split(separator: "/")
        guard let lastComponent = components.last else {
            return path
        }

        // Check if last component has a file extension
        let lastComponentStr = String(lastComponent)
        if lastComponentStr.contains(".") && lastComponentStr.split(separator: ".").count > 1 {
            // Has extension, remove the last component
            let pathWithoutFile = components.dropLast().joined(separator: "/")
            print("UploadManager: Stripped filename from path: '\(path)' -> '\(pathWithoutFile)'")
            return pathWithoutFile
        }

        return path
    }

    /// Upload calibration JSON to S3
    private func uploadCalibrationData(
        calibration: CalibrationData,
        credentials: IAMCredentials,
        client: S3Client
    ) async throws {
        // Remove filename from base path if present
        let basePath = stripFileExtensionFromPath(credentials.key)

        // Construct calibration.json path: {basePath}/{deviceId}/calibration.json
        let calibrationKey = "\(basePath)/\(credentials.deviceId)/calibration.json"

        print("UploadManager: Uploading calibration.json to \(calibrationKey)")

        // Encode calibration data to JSON
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let calibrationJson = try encoder.encode(calibration)

        // Upload calibration.json using PutObject (simple upload for small JSON file)
        let putInput = PutObjectInput(
            body: .data(calibrationJson),
            bucket: credentials.bucket,
            contentType: "application/json",
            key: calibrationKey
        )

        _ = try await client.putObject(input: putInput)
        print("UploadManager: Calibration.json uploaded successfully")
    }

    private func uploadWithIAMCredentials(item: UploadItem, fileURL: URL, credentials: IAMCredentials) {
        print("UploadManager: Creating AWS S3 multipart upload with IAM credentials")
        print("UploadManager:   File: \(item.fileName)")
        print("UploadManager:   Bucket: \(credentials.bucket)")
        print("UploadManager:   Key: \(credentials.key)")
        print("UploadManager:   Region: \(credentials.region)")
        print("UploadManager:   Device ID: \(credentials.deviceId)")

        // Update status to uploading
        if var current = currentUpload {
            current = UploadItem(
                fileName: current.fileName,
                fileSize: current.fileSize,
                bytesUploaded: current.bytesUploaded,
                uploadProgress: current.uploadProgress,
                uploadSpeed: current.uploadSpeed,
                status: UploadStatus.uploading.rawValue,
                uploadUrl: current.uploadUrl,
                error: nil
            )
            currentUpload = current
        }

        uploadStartTime = Date()
        lastProgressUpdate = Date()
        lastBytesUploaded = 0

        // Perform multipart upload asynchronously
        Task {
            do {
                // Get file size without loading entire file into memory
                let fileAttributes = try FileManager.default.attributesOfItem(atPath: fileURL.path)
                guard let fileSizeNumber = fileAttributes[.size] as? NSNumber else {
                    throw NSError(domain: "UploadManager", code: -1,
                                userInfo: [NSLocalizedDescriptionKey: "Failed to get file size"])
                }
                let fileSize = fileSizeNumber.intValue
                print("UploadManager: File size: \(fileSize) bytes")

                // Create AWS credential identity with session token
                let credentialIdentity = AWSCredentialIdentity(
                    accessKey: credentials.accessKeyId,
                    secret: credentials.secretAccessKey,
                    sessionToken: credentials.sessionToken
                )

                // Create static credential identity resolver
                let credentialsResolver = try StaticAWSCredentialIdentityResolver(credentialIdentity)

                // Create S3 client configuration
                let config = try await S3Client.S3ClientConfiguration(
                    awsCredentialIdentityResolver: credentialsResolver,
                    region: credentials.region
                )

                let client = S3Client(config: config)

                // STEP 1: Upload calibration.json first
                if let calibration = calibrationData[item.fileName] {
                    try await uploadCalibrationData(
                        calibration: calibration,
                        credentials: credentials,
                        client: client
                    )
                } else {
                    print("UploadManager: WARNING - No calibration data found for \(item.fileName)")
                }

                // STEP 2: Upload video to {basePath}/{deviceId}/{fileName}
                // Remove filename from base path if present
                let basePath = stripFileExtensionFromPath(credentials.key)
                let videoKey = "\(basePath)/\(credentials.deviceId)/\(item.fileName)"
                print("UploadManager: Uploading video to \(videoKey)")

                // Initialize multipart upload
                print("UploadManager: Initializing multipart upload")
                let createInput = CreateMultipartUploadInput(
                    bucket: credentials.bucket,
                    contentType: "video/mp4",
                    key: videoKey
                )
                let createResult = try await client.createMultipartUpload(input: createInput)

                guard let uploadId = createResult.uploadId else {
                    throw NSError(domain: "UploadManager", code: -1,
                                userInfo: [NSLocalizedDescriptionKey: "Failed to get upload ID"])
                }

                print("UploadManager: Multipart upload initialized with ID: \(uploadId)")

                // Calculate parts (5MB chunks, minimum size for multipart except last part)
                let partSize = 5 * 1024 * 1024 // 5MB
                let totalParts = (fileSize + partSize - 1) / partSize
                var completedParts: [S3ClientTypes.CompletedPart] = []

                print("UploadManager: Uploading in \(totalParts) parts of ~\(partSize / 1024 / 1024)MB each (CONCURRENT with max 4 parts at a time)")

                // Upload parts with controlled concurrency (max 4 at a time)
                // This prevents memory issues by limiting concurrent uploads
                var partsCompleted = 0
                let maxConcurrentUploads = 4

                try await withThrowingTaskGroup(of: S3ClientTypes.CompletedPart.self) { group in
                    var nextPartToLaunch = 1

                    // Launch initial batch of uploads
                    for _ in 1...min(maxConcurrentUploads, totalParts) {
                        let partNumber = nextPartToLaunch
                        nextPartToLaunch += 1

                        let start = (partNumber - 1) * partSize
                        let length = min(partSize, fileSize - start)

                        // Add upload task to group (runs concurrently)
                        group.addTask {
                            // Read only this part's data from disk (memory efficient)
                            let partData = try self.readFileChunk(at: fileURL, offset: start, length: length)
                            print("UploadManager: Starting upload of part \(partNumber)/\(totalParts) (\(partData.count) bytes)")

                            let uploadPartInput = UploadPartInput(
                                body: .data(partData),
                                bucket: credentials.bucket,
                                key: videoKey,
                                partNumber: partNumber,
                                uploadId: uploadId
                            )
                            let uploadResult = try await client.uploadPart(input: uploadPartInput)

                            print("UploadManager: Part \(partNumber) upload complete")

                            return S3ClientTypes.CompletedPart(
                                eTag: uploadResult.eTag,
                                partNumber: partNumber
                            )
                        }
                    }

                    // Collect results and launch new tasks as they complete
                    for try await completedPart in group {
                        completedParts.append(completedPart)
                        partsCompleted += 1

                        // Calculate progress based on number of parts completed
                        let bytesUploaded = Int64(partsCompleted * partSize)
                        let actualBytesUploaded = min(bytesUploaded, Int64(fileSize))
                        let progress = Double(actualBytesUploaded) / Double(fileSize) * 100.0
                        let elapsed = Date().timeIntervalSince(uploadStartTime ?? Date())
                        let speed = elapsed > 0 ? Int64(Double(actualBytesUploaded) / elapsed) : 0

                        print("UploadManager: \(partsCompleted)/\(totalParts) parts complete - Progress: \(Int(progress))%")

                        // Update current upload item (thread-safe via MainActor)
                        if var current = currentUpload {
                            current = UploadItem(
                                fileName: current.fileName,
                                fileSize: current.fileSize,
                                bytesUploaded: actualBytesUploaded,
                                uploadProgress: progress,
                                uploadSpeed: speed,
                                status: UploadStatus.uploading.rawValue,
                                uploadUrl: current.uploadUrl,
                                error: nil
                            )
                            currentUpload = current
                        }

                        // Launch next part if any remain
                        if nextPartToLaunch <= totalParts {
                            let partNumber = nextPartToLaunch
                            nextPartToLaunch += 1

                            let start = (partNumber - 1) * partSize
                            let length = min(partSize, fileSize - start)

                            // Add upload task to group (runs concurrently)
                            group.addTask {
                                // Read only this part's data from disk (memory efficient)
                                let partData = try self.readFileChunk(at: fileURL, offset: start, length: length)
                                print("UploadManager: Starting upload of part \(partNumber)/\(totalParts) (\(partData.count) bytes)")

                                let uploadPartInput = UploadPartInput(
                                    body: .data(partData),
                                    bucket: credentials.bucket,
                                    key: videoKey,
                                    partNumber: partNumber,
                                    uploadId: uploadId
                                )
                                let uploadResult = try await client.uploadPart(input: uploadPartInput)

                                print("UploadManager: Part \(partNumber) upload complete")

                                return S3ClientTypes.CompletedPart(
                                    eTag: uploadResult.eTag,
                                    partNumber: partNumber
                                )
                            }
                        }
                    }
                }

                // Sort completed parts by part number (AWS requires this)
                completedParts.sort { $0.partNumber ?? 0 < $1.partNumber ?? 0 }

                // Complete multipart upload
                print("UploadManager: Completing multipart upload with \(completedParts.count) parts")
                let completeInput = CompleteMultipartUploadInput(
                    bucket: credentials.bucket,
                    key: videoKey,
                    multipartUpload: S3ClientTypes.CompletedMultipartUpload(parts: completedParts),
                    uploadId: uploadId
                )
                _ = try await client.completeMultipartUpload(input: completeInput)

                print("UploadManager: Multipart upload succeeded for \(item.fileName)")
                await handleUploadSuccess(item: item)

            } catch {
                print("UploadManager: Multipart upload failed for \(item.fileName): \(error)")
                await handleUploadFailure(item: item, error: error.localizedDescription)
            }
        }
    }

    private func handleUploadSuccess(item: UploadItem) {
        print("UploadManager: Upload succeeded for \(item.fileName)")

        // Delete the file
        let documentsDirectory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let fileURL = documentsDirectory.appendingPathComponent(item.fileName)

        do {
            try FileManager.default.removeItem(at: fileURL)
            print("UploadManager: Deleted file \(item.fileName) after successful upload")
        } catch {
            print("UploadManager: Failed to delete file \(item.fileName): \(error)")
        }

        // Clear retry count, IAM credentials, and calibration data
        retryAttempts.removeValue(forKey: item.fileName)
        iamCredentials.removeValue(forKey: item.fileName)
        calibrationData.removeValue(forKey: item.fileName)

        // Clear current upload
        currentUpload = nil
        currentTask = nil
        saveQueue()

        // Process next
        processNextUpload()
    }

    private func handleUploadFailure(item: UploadItem, error: String) {
        print("UploadManager: Upload failed for \(item.fileName): \(error)")

        let attempts = (retryAttempts[item.fileName] ?? 0) + 1
        retryAttempts[item.fileName] = attempts

        if attempts < maxRetries {
            // Retry with exponential backoff
            let delay = pow(2.0, Double(attempts)) // 2s, 4s, 8s
            print("UploadManager: Retrying \(item.fileName) in \(delay) seconds (attempt \(attempts)/\(maxRetries))")

            // Re-add to front of queue
            pendingQueue.insert(item, at: 0)
            currentUpload = nil
            currentTask = nil
            saveQueue()

            Task {
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                await processNextUpload()
            }
        } else {
            // Move to failed queue
            print("UploadManager: Max retries reached for \(item.fileName), moving to failed queue")

            var failedItem = item
            failedItem = UploadItem(
                fileName: failedItem.fileName,
                fileSize: failedItem.fileSize,
                bytesUploaded: failedItem.bytesUploaded,
                uploadProgress: failedItem.uploadProgress,
                uploadSpeed: failedItem.uploadSpeed,
                status: UploadStatus.failed.rawValue,
                uploadUrl: failedItem.uploadUrl,
                error: error
            )

            failedQueue.append(failedItem)
            retryAttempts.removeValue(forKey: item.fileName)
            currentUpload = nil
            currentTask = nil
            saveQueue()

            // Process next
            processNextUpload()
        }
    }

    // MARK: - Persistence

    private func saveQueue() {
        let queueData = QueueData(
            pending: pendingQueue,
            failed: failedQueue,
            retryAttempts: retryAttempts
        )

        do {
            let encoder = JSONEncoder()
            let data = try encoder.encode(queueData)
            try data.write(to: queueFileURL)
            print("UploadManager: Queue saved (\(pendingQueue.count) pending, \(failedQueue.count) failed)")
        } catch {
            print("UploadManager: Failed to save queue: \(error)")
        }
    }

    private func loadQueue() {
        guard FileManager.default.fileExists(atPath: queueFileURL.path) else {
            print("UploadManager: No saved queue found")
            return
        }

        do {
            let data = try Data(contentsOf: queueFileURL)
            let decoder = JSONDecoder()
            let queueData = try decoder.decode(QueueData.self, from: data)

            pendingQueue = queueData.pending
            failedQueue = queueData.failed
            retryAttempts = queueData.retryAttempts

            print("UploadManager: Queue loaded (\(pendingQueue.count) pending, \(failedQueue.count) failed)")
        } catch {
            print("UploadManager: Failed to load queue: \(error)")
        }
    }
}

// MARK: - URLSessionDelegate

extension UploadManager: URLSessionTaskDelegate, URLSessionDataDelegate {

    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64, totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        Task { @MainActor in
            guard var current = currentUpload else { return }

            let now = Date()
            let progress = Double(totalBytesSent) / Double(totalBytesExpectedToSend) * 100.0

            // Calculate upload speed
            var speed: Int64 = 0
            if let lastUpdate = lastProgressUpdate {
                let timeInterval = now.timeIntervalSince(lastUpdate)
                if timeInterval > 0 {
                    let bytesDelta = totalBytesSent - lastBytesUploaded
                    speed = Int64(Double(bytesDelta) / timeInterval)
                }
            }

            // Update tracking variables
            lastProgressUpdate = now
            lastBytesUploaded = totalBytesSent

            // Update current upload
            current = UploadItem(
                fileName: current.fileName,
                fileSize: current.fileSize,
                bytesUploaded: totalBytesSent,
                uploadProgress: progress,
                uploadSpeed: speed,
                status: UploadStatus.uploading.rawValue,
                uploadUrl: current.uploadUrl,
                error: nil
            )
            currentUpload = current

            if Int(progress) % 10 == 0 && Int(progress) > 0 {
                print("UploadManager: Upload progress for \(current.fileName): \(Int(progress))% (\(speed / 1024) KB/s)")
            }
        }
    }

    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        Task { @MainActor in
            guard let item = currentUpload else { return }

            if let error = error {
                print("UploadManager: Upload error for \(item.fileName): \(error)")
                print("UploadManager:   Error details: \(error.localizedDescription)")
                handleUploadFailure(item: item, error: error.localizedDescription)
            } else if let httpResponse = task.response as? HTTPURLResponse {
                print("UploadManager: Upload completed for \(item.fileName)")
                print("UploadManager:   HTTP Status: \(httpResponse.statusCode)")
                print("UploadManager:   Response Headers: \(httpResponse.allHeaderFields)")

                if httpResponse.statusCode >= 200 && httpResponse.statusCode < 300 {
                    handleUploadSuccess(item: item)
                } else {
                    var errorMessage = "HTTP \(httpResponse.statusCode)"

                    // Try to get response body for more details
                    if let data = objc_getAssociatedObject(task, "responseData") as? Data,
                       let responseBody = String(data: data, encoding: .utf8) {
                        print("UploadManager:   Response Body: \(responseBody)")
                        errorMessage += " - \(responseBody)"
                    }

                    handleUploadFailure(item: item, error: errorMessage)
                }
            } else {
                print("UploadManager: Unknown response type for \(item.fileName)")
                handleUploadFailure(item: item, error: "Unknown response type")
            }
        }
    }

    // Capture response data for error details
    nonisolated func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        Task { @MainActor in
            // Store data on task for later retrieval
            objc_setAssociatedObject(dataTask, "responseData", data, .OBJC_ASSOCIATION_RETAIN)
        }
    }
}

// MARK: - Supporting Types

private struct QueueData: Codable {
    let pending: [UploadItem]
    let failed: [UploadItem]
    let retryAttempts: [String: Int]
}

private struct IAMCredentials {
    let bucket: String
    let key: String
    let accessKeyId: String
    let secretAccessKey: String
    let sessionToken: String
    let region: String
    let deviceId: String
}
