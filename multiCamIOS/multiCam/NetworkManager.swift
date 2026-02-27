import Foundation
import Network
import Combine
import UIKit
import AVFoundation
import MultiCamCommon

@MainActor
class NetworkManager: NSObject, ObservableObject {
    @Published var isConnected = false
    @Published var connectionStatus = "Disconnected"
    @Published var connectedDevices: [String] = []

    private var listener: NWListener?
    private var connection: NWConnection?
    private var netService: NetService?
    private var healthCheckTimer: Timer?
    private var pathMonitor: NWPathMonitor?
    private var retryCount = 0
    private let maxRetries = 5
    private var isServiceRunning = false

    private let deviceId: String = {
        // Check if device ID is already stored
        if let savedDeviceId = UserDefaults.standard.string(forKey: "multiCamDeviceId") {
            return savedDeviceId
        }

        // Generate new device ID
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
        let newDeviceId = "\(randomNoun)-\(shortUuid)"

        // Save to UserDefaults
        UserDefaults.standard.set(newDeviceId, forKey: "multiCamDeviceId")

        return newDeviceId
    }()
    private let port: NWEndpoint.Port = 8080
    
    private var onCommandType: ((CommandType, TimeInterval?) -> Void)?
    private var onScheduledStartCommand: ((TimeInterval) -> Void)?
    private var onGetVideoCommand: ((String) -> URL?)?
    private var onStopCommandType: ((NWConnection) -> Void)?
    private var onListFilesCommand: (() -> [FileMetadata])?
    private var onSyncStatusCheck: (() -> Bool)?
    private var onRecordingStatusCheck: (() -> Bool)?
    private var onGetCameraInfo: (() -> (device: AVCaptureDevice, resolution: CGSize, calibration: AVCameraCalibrationData?)?)?
    private var lastRecordedFileName: String?

    // Upload manager
    private var uploadManager: UploadManager?

    override init() {
        super.init()
        setupAppLifecycleObservers()
        startServices()
        setupNetworkMonitoring()
    }
    
    deinit {
        Task { @MainActor in
            cleanup()
        }
    }
    
    func setCommandTypeHandler(_ handler: @escaping (CommandType, TimeInterval?) -> Void) {
        self.onCommandType = handler
    }
    
    func setGetVideoHandler(_ handler: @escaping (String) -> URL?) {
        self.onGetVideoCommand = handler
    }
    
    func setStopRecordingHandler(_ handler: @escaping (NWConnection) -> Void) {
        self.onStopCommandType = handler
    }
    
    func setScheduledStartHandler(_ handler: @escaping (TimeInterval) -> Void) {
        self.onScheduledStartCommand = handler
    }
    
    func setListFilesHandler(_ handler: @escaping () -> [FileMetadata]) {
        self.onListFilesCommand = handler
    }

    func setSyncStatusHandler(_ handler: @escaping () -> Bool) {
        self.onSyncStatusCheck = handler
    }

    func setRecordingStatusHandler(_ handler: @escaping () -> Bool) {
        self.onRecordingStatusCheck = handler
    }

    func setCameraInfoHandler(_ handler: @escaping () -> (device: AVCaptureDevice, resolution: CGSize, calibration: AVCameraCalibrationData?)?) {
        self.onGetCameraInfo = handler
    }

    func setUploadManager(_ manager: UploadManager) {
        self.uploadManager = manager
    }

    func getDeviceId() -> String {
        return deviceId
    }
    
    func setLastRecordedFileName(_ fileName: String) {
        self.lastRecordedFileName = fileName
    }
    
    func sendStopRecordingResponse(to connection: NWConnection, fileName: String, fileSize: Int64) {
        let response = StopRecordingResponse(
            deviceId: deviceId,
            status: DeviceStatus.recordingStopped.rawValue,
            timestamp: Date().timeIntervalSince1970,
            fileName: fileName,
            fileSize: fileSize
        )

        do {
            let data = try JSONEncoder().encode(response)
            connection.send(content: data, completion: .contentProcessed { error in
                if let error = error {
                    print("NetworkManager: Failed to send stop recording response: \(error)")
                } else {
                    print("NetworkManager: Stop recording response sent successfully")
                }
            })
        } catch {
            print("NetworkManager: Failed to encode stop recording response: \(error)")
        }
    }
    
    private func setupNetworkListener() {
        do {
            listener = try NWListener(using: .tcp, on: port)
            
            listener?.newConnectionHandler = { [weak self] connection in
                Task { @MainActor in
                    self?.handleNewConnection(connection)
                }
            }
            
            listener?.stateUpdateHandler = { [weak self] state in
                Task { @MainActor in
                    switch state {
                    case .ready:
                        self?.connectionStatus = "Listening for connections"
                        self?.retryCount = 0
                        print("NetworkManager: Listener ready on port \(self?.port.rawValue ?? 0)")
                    case .failed(let error):
                        self?.connectionStatus = "Failed: \(error.localizedDescription)"
                        print("NetworkManager: Listener failed with error: \(error)")
                        if let strongSelf = self, strongSelf.isServiceRunning && strongSelf.retryCount < strongSelf.maxRetries {
                            strongSelf.retryCount += 1
                            let backoffTime = min(pow(2.0, Double(strongSelf.retryCount)), 30.0)
                            print("NetworkManager: Retrying listener in \(backoffTime) seconds (attempt \(strongSelf.retryCount))")
                            try? await Task.sleep(nanoseconds: UInt64(backoffTime * 1_000_000_000))
                            strongSelf.setupNetworkListener()
                        }
                    case .cancelled:
                        self?.connectionStatus = "Cancelled"
                        print("NetworkManager: Listener cancelled")
                    default:
                        break
                    }
                }
            }
            
            listener?.start(queue: .global(qos: .userInitiated))
        } catch {
            connectionStatus = "Failed to create listener: \(error.localizedDescription)"
            print("NetworkManager: Failed to create listener: \(error)")
        }
    }
    
    private func handleNewConnection(_ connection: NWConnection) {
        self.connection = connection
        self.isConnected = true
        self.connectionStatus = "Connected to controller"
        
        connection.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                switch state {
                case .ready:
                    print("NetworkManager: Connection ready")
                    self?.receiveMessage(connection: connection)
                case .failed(let error):
                    print("NetworkManager: Connection failed: \(error)")
                    self?.isConnected = false
                    self?.connectionStatus = "Connection failed"
                case .cancelled:
                    print("NetworkManager: Connection cancelled")
                    self?.isConnected = false
                    self?.connectionStatus = "Connection cancelled"
                default:
                    break
                }
            }
        }
        
        connection.start(queue: .global(qos: .userInitiated))
    }
    
    private func receiveMessage(connection: NWConnection) {
        // Increased buffer to 8KB to handle large IAM credentials (session tokens can be long)
        connection.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, isComplete, error in
            if let error = error {
                print("NetworkManager: Receive error: \(error)")
                return
            }
            
            if let data = data, !data.isEmpty {
                self?.processReceivedData(data, connection: connection)
            }
            
            if !isComplete {
                self?.receiveMessage(connection: connection)
            }
        }
    }
    
    private func processReceivedData(_ data: Data, connection: NWConnection) {
        do {
            let message = try JSONDecoder().decode(CommandMessage.self, from: data)
            print("NetworkManager: Received command: \(message.command.rawValue)")
            
            Task { @MainActor in
                if message.command == .getVideo {
                    self.handleGetVideoRequest(message, connection: connection)
                } else if message.command == .listFiles {
                    self.handleListFilesRequest(connection: connection)
                } else if message.command == .uploadToCloud {
                    self.handleUploadToCloudRequest(message, connection: connection)
                } else if message.command == .stopRecording {
                    // Handle stop recording specially - don't send response immediately
                    self.onCommandType?(message.command, message.timestamp)
                    self.onStopCommandType?(connection)
                } else if message.command == .startRecording && message.timestamp != nil {
                    // Handle scheduled start recording - check sync status first
                    print("NetworkManager: Received scheduled start recording for timestamp \(message.timestamp)")

                    // Get sync status from camera manager (via callback)
                    // For now, we'll add a sync check callback
                    if let syncCheck = self.onSyncStatusCheck?(), !syncCheck {
                        self.sendErrorResponse("Device clock not synchronized with network", to: connection)
                        return
                    }

                    self.onScheduledStartCommand?(message.timestamp)

                    let batteryLevel = self.getBatteryLevel()
                    let (uploadQueue, failedUploadQueue) = self.getUploadQueues()

                    let response = StatusResponse(
                        deviceId: self.deviceId,
                        status: DeviceStatus.scheduledRecordingAccepted.rawValue,
                        timestamp: Date().timeIntervalSince1970,
                        batteryLevel: batteryLevel,
                        deviceType: "iOS:iPhone",
                        uploadQueue: uploadQueue,
                        failedUploadQueue: failedUploadQueue
                    )

                    self.sendResponse(response, to: connection)
                } else if message.command == .startRecording {
                    // Handle immediate start recording (no timestamp)
                    self.onCommandType?(message.command, message.timestamp)

                    let batteryLevel = self.getBatteryLevel()
                    let (uploadQueue, failedUploadQueue) = self.getUploadQueues()

                    let response = StatusResponse(
                        deviceId: self.deviceId,
                        status: DeviceStatus.recording.rawValue,
                        timestamp: Date().timeIntervalSince1970,
                        batteryLevel: batteryLevel,
                        deviceType: "iOS:iPhone",
                        uploadQueue: uploadQueue,
                        failedUploadQueue: failedUploadQueue
                    )

                    self.sendResponse(response, to: connection)
                } else {
                    print("NetworkManager: Processing command in else block: \(message.command.rawValue)")
                    self.onCommandType?(message.command, message.timestamp)

                    let batteryLevel = self.getBatteryLevel()
                    let (uploadQueue, failedUploadQueue) = self.getUploadQueues()

                    // Check actual recording status
                    let hasRecordingHandler = self.onRecordingStatusCheck != nil
                    let isRecording = self.onRecordingStatusCheck?() ?? false
                    let currentStatus = isRecording ? DeviceStatus.recording.rawValue : DeviceStatus.ready.rawValue
                    print("NetworkManager: DEVICE_STATUS - hasRecordingHandler: \(hasRecordingHandler), isRecording: \(isRecording), returning status: \(currentStatus)")

                    let response = StatusResponse(
                        deviceId: self.deviceId,
                        status: currentStatus,
                        timestamp: Date().timeIntervalSince1970,
                        batteryLevel: batteryLevel,
                        deviceType: "iOS:iPhone",
                        uploadQueue: uploadQueue,
                        failedUploadQueue: failedUploadQueue
                    )

                    self.sendResponse(response, to: connection)
                }
            }
        } catch {
            print("NetworkManager: Failed to decode message: \(error)")
        }
    }
    
    private func sendResponse(_ response: StatusResponse, to connection: NWConnection) {
        do {
            let data = try JSONEncoder().encode(response)
            connection.send(content: data, completion: .contentProcessed { error in
                if let error = error {
                    print("NetworkManager: Failed to send response: \(error)")
                } else {
                    print("NetworkManager: Response sent successfully")
                }
            })
        } catch {
            print("NetworkManager: Failed to encode response: \(error)")
        }
    }
    
    private func startBonjourService() {
        guard netService == nil else {
            print("NetworkManager: Bonjour service already running")
            return
        }

        netService = NetService(domain: "", type: "_multicam._tcp.", name: "multiCam-\(deviceId)", port: Int32(port.rawValue))
        netService?.delegate = self
        netService?.publish()
        print("NetworkManager: Started Bonjour service: multiCam-\(deviceId)")
    }
    
    private func stopBonjourService() {
        if netService != nil {
            print("NetworkManager: Stopping Bonjour service")
            netService?.stop()
            netService = nil
        }
    }
    
    private func stopListener() {
        if listener != nil || connection != nil {
            print("NetworkManager: Stopping network listener and connections")
            listener?.cancel()
            connection?.cancel()
            listener = nil
            connection = nil
            isConnected = false
            connectionStatus = "Disconnected"
        }
    }
    
    func sendHeartbeat() {
        guard let connection = connection, isConnected else { return }

        let heartbeat = CommandMessage(command: .heartbeat, timestamp: Date().timeIntervalSince1970, deviceId: deviceId)
        do {
            let data = try JSONEncoder().encode(heartbeat)
            connection.send(content: data, completion: .contentProcessed { error in
                if let error = error {
                    print("NetworkManager: Failed to send heartbeat: \(error)")
                }
            })
        } catch {
            print("NetworkManager: Failed to encode heartbeat: \(error)")
        }
    }
    
    private func handleGetVideoRequest(_ message: CommandMessage, connection: NWConnection) {
        guard let fileName = message.fileName,
              let fileURL = onGetVideoCommand?(fileName) else {
            sendErrorResponse("Requested file not found: \(message.fileName ?? "nil")", to: connection)
            return
        }

        // Get file size WITHOUT loading entire file into memory
        guard let fileAttributes = try? FileManager.default.attributesOfItem(atPath: fileURL.path),
              let fileSizeNumber = fileAttributes[.size] as? NSNumber else {
            sendErrorResponse("Could not determine file size for \(fileName)", to: connection)
            return
        }

        let fileSize = fileSizeNumber.int64Value
        print("NetworkManager: Preparing to send file \(fileName) (\(fileSize) bytes, \(Double(fileSize) / 1024 / 1024) MB)")

        do {
            // Create and encode file response header
            let fileResponse = FileResponse(
                deviceId: deviceId,
                fileName: fileName,
                fileSize: fileSize,
                status: DeviceStatus.ready.rawValue
            )

            let headerData = try JSONEncoder().encode(fileResponse)
            var headerSize = UInt32(headerData.count).bigEndian

            // Build header packet (size + JSON header)
            var headerPacket = Data()
            headerPacket.append(withUnsafeBytes(of: &headerSize) { Data($0) })
            headerPacket.append(headerData)

            print("NetworkManager: Sending header (\(headerPacket.count) bytes)...")

            // Send header immediately (fast response!)
            connection.send(content: headerPacket, completion: .contentProcessed { [weak self] error in
                if let error = error {
                    print("NetworkManager: Failed to send header: \(error)")
                    return
                }

                print("NetworkManager: Header sent successfully, starting file stream...")

                // Stream file data in chunks after header is sent
                Task {
                    await self?.streamFileData(fileURL: fileURL, fileName: fileName, connection: connection)
                }
            })

        } catch {
            print("NetworkManager: Error encoding header: \(error)")
            sendErrorResponse("Error encoding header: \(error.localizedDescription)", to: connection)
        }
    }
    
    /// Stream file data in chunks to avoid loading entire file into memory
    nonisolated private func streamFileData(fileURL: URL, fileName: String, connection: NWConnection) async {
        let chunkSize = 1024 * 1024  // 1MB chunks for efficient streaming

        guard let fileHandle = try? FileHandle(forReadingFrom: fileURL) else {
            print("NetworkManager: ERROR - Could not open file for streaming: \(fileName)")
            return
        }

        defer {
            try? fileHandle.close()
        }

        var totalSent: Int64 = 0
        var chunkCount = 0

        print("NetworkManager: Starting chunked file transfer...")

        // Stream file in chunks
        while true {
            autoreleasepool {
                let chunk: Data?
                if #available(iOS 13.4, *) {
                    chunk = try? fileHandle.read(upToCount: chunkSize)
                } else {
                    chunk = fileHandle.readData(ofLength: chunkSize)
                }

                guard let chunkData = chunk, !chunkData.isEmpty else {
                    return  // EOF reached
                }

                // Send chunk synchronously within the semaphore
                let semaphore = DispatchSemaphore(value: 0)
                var sendError: Error?

                connection.send(content: chunkData, completion: .contentProcessed { error in
                    sendError = error
                    semaphore.signal()
                })

                semaphore.wait()

                if let error = sendError {
                    print("NetworkManager: ERROR sending chunk \(chunkCount): \(error)")
                    return  // Stop on error
                }

                totalSent += Int64(chunkData.count)
                chunkCount += 1

                // Log progress every 10 chunks (10MB)
                if chunkCount % 10 == 0 {
                    let mbSent = Double(totalSent) / 1024 / 1024
                    print("NetworkManager: Sent \(chunkCount) chunks (\(String(format: "%.1f", mbSent)) MB)...")
                }

                // Check if this was the last chunk
                if chunkData.count < chunkSize {
                    return  // Partial chunk means EOF
                }
            }
        }

        print("NetworkManager: File stream complete - \(fileName)")
        print("NetworkManager:   Total sent: \(totalSent) bytes (\(Double(totalSent) / 1024 / 1024) MB)")
        print("NetworkManager:   Chunks sent: \(chunkCount)")
    }

    private func handleListFilesRequest(connection: NWConnection) {
        let files = onListFilesCommand?() ?? []

        let response = ListFilesResponse(
            deviceId: deviceId,
            status: DeviceStatus.ready.rawValue,
            timestamp: Date().timeIntervalSince1970,
            files: files
        )

        do {
            let data = try JSONEncoder().encode(response)
            connection.send(content: data, completion: .contentProcessed { error in
                if let error = error {
                    print("NetworkManager: Failed to send list files response: \(error)")
                } else {
                    print("NetworkManager: List files response sent successfully (\(files.count) files)")
                }
            })
        } catch {
            print("NetworkManager: Failed to encode list files response: \(error)")
            sendErrorResponse("Error listing files: \(error.localizedDescription)", to: connection)
        }
    }

    private func handleUploadToCloudRequest(_ message: CommandMessage, connection: NWConnection) {
        guard let fileName = message.fileName else {
            sendErrorResponse("Missing fileName in UPLOAD_TO_CLOUD command", to: connection)
            return
        }

        guard let uploadManager = uploadManager else {
            sendErrorResponse("Upload manager not initialized", to: connection)
            return
        }

        // Get file URL from handler
        guard let fileURL = onGetVideoCommand?(fileName) else {
            sendErrorResponse("File not found: \(fileName)", to: connection)
            return
        }

        // Collect camera calibration data
        let calibrationData: CalibrationData
        if let cameraInfo = onGetCameraInfo?() {
            print("NetworkManager: Collecting camera calibration data")
            calibrationData = CameraIntrinsicsCollector.collectCalibrationData(
                from: cameraInfo.device,
                deviceId: deviceId,
                recordingResolution: cameraInfo.resolution,
                calibrationData: cameraInfo.calibration
            )
        } else {
            print("NetworkManager: WARNING - Camera info not available, using minimal calibration data")
            // Fallback: create minimal calibration data with just device ID
            calibrationData = CalibrationData(
                deviceId: deviceId,
                intrinsics: [],
                extrinsics: []
            )
        }

        // Check if using IAM credentials or presigned URL
        if let bucket = message.s3Bucket,
           let key = message.s3Key,
           let accessKeyId = message.awsAccessKeyId,
           let secretAccessKey = message.awsSecretAccessKey,
           let sessionToken = message.awsSessionToken,
           let region = message.awsRegion {
            // Use IAM credentials authentication
            print("NetworkManager: Queuing IAM credential upload for \(fileName)")
            uploadManager.queueUploadWithIAM(
                fileName: fileName,
                fileURL: fileURL,
                bucket: bucket,
                key: key,
                accessKeyId: accessKeyId,
                secretAccessKey: secretAccessKey,
                sessionToken: sessionToken,
                region: region,
                deviceId: deviceId,
                calibration: calibrationData
            )
        } else if let uploadUrl = message.uploadUrl {
            // Use presigned URL authentication
            print("NetworkManager: Queuing presigned URL upload for \(fileName)")
            uploadManager.queueUpload(fileName: fileName, fileURL: fileURL, uploadUrl: uploadUrl)
        } else {
            sendErrorResponse("Missing authentication credentials (uploadUrl or IAM credentials) in UPLOAD_TO_CLOUD command", to: connection)
            return
        }

        // Send success response using StatusResponse
        let batteryLevel = getBatteryLevel()
        let (uploadQueue, failedUploadQueue) = getUploadQueues()

        let response = StatusResponse(
            deviceId: deviceId,
            status: DeviceStatus.uploadQueued.rawValue,
            timestamp: Date().timeIntervalSince1970,
            batteryLevel: batteryLevel,
            deviceType: "iOS:iPhone",
            uploadQueue: uploadQueue,
            failedUploadQueue: failedUploadQueue
        )

        sendResponse(response, to: connection)
        print("NetworkManager: Upload queued for file \(fileName)")
    }

    private func sendErrorResponse(_ errorMessage: String, to connection: NWConnection) {
        let response = ErrorResponse(
            deviceId: deviceId,
            status: DeviceStatus.error.rawValue,
            timestamp: Date().timeIntervalSince1970,
            message: errorMessage
        )

        do {
            let data = try JSONEncoder().encode(response)
            connection.send(content: data, completion: .contentProcessed { _ in })
        } catch {
            print("NetworkManager: Failed to send error response: \(error)")
        }
    }

    // MARK: - Robustness Improvements

    private func setupAppLifecycleObservers() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appDidBecomeActive),
            name: UIApplication.didBecomeActiveNotification,
            object: nil
        )

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appWillResignActive),
            name: UIApplication.willResignActiveNotification,
            object: nil
        )
    }

    @objc private func appDidBecomeActive() {
        print("NetworkManager: App became active - checking services")
        Task { @MainActor in
            await restartServicesIfNeeded()
        }
    }

    @objc private func appWillResignActive() {
        print("NetworkManager: App will resign active")
    }

    private func startServices() {
        setupNetworkListener()
        startBonjourService()
        startHealthMonitoring()
        isServiceRunning = true
        retryCount = 0
    }

    private func restartServicesIfNeeded() async {
        guard !isServiceRunning || netService == nil || listener == nil else { return }

        print("NetworkManager: Restarting services...")
        stopListener()
        stopBonjourService()

        try? await Task.sleep(nanoseconds: 500_000_000)
        startServices()
    }

    private func startHealthMonitoring() {
        healthCheckTimer?.invalidate()
        healthCheckTimer = Timer.scheduledTimer(withTimeInterval: 30.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.performHealthCheck()
            }
        }
    }

    private func performHealthCheck() async {
        guard isServiceRunning else { return }

        let listenerHealthy = listener?.state == .ready
        let serviceHealthy = netService != nil

        if !listenerHealthy || !serviceHealthy {
            print("NetworkManager: Health check failed - listener: \(listenerHealthy), service: \(serviceHealthy)")
            if retryCount < maxRetries {
                retryCount += 1
                await restartServicesWithBackoff()
            } else {
                print("NetworkManager: Max retries reached, stopping health monitoring")
                connectionStatus = "Service failed after \(maxRetries) retries"
            }
        } else {
            retryCount = 0
        }
    }

    private func restartServicesWithBackoff() async {
        let backoffTime = min(pow(2.0, Double(retryCount)), 60.0)
        print("NetworkManager: Restarting services in \(backoffTime) seconds (attempt \(retryCount))")

        try? await Task.sleep(nanoseconds: UInt64(backoffTime * 1_000_000_000))
        await restartServicesIfNeeded()
    }

    private func setupNetworkMonitoring() {
        pathMonitor = NWPathMonitor()
        pathMonitor?.pathUpdateHandler = { [weak self] path in
            Task { @MainActor in
                if path.status == .satisfied {
                    print("NetworkManager: Network path satisfied")
                    await self?.restartServicesIfNeeded()
                } else {
                    print("NetworkManager: Network path not satisfied")
                    self?.connectionStatus = "Network unavailable"
                }
            }
        }
        pathMonitor?.start(queue: .global(qos: .background))
    }

    private func getBatteryLevel() -> Double? {
        UIDevice.current.isBatteryMonitoringEnabled = true
        let level = UIDevice.current.batteryLevel
        return level >= 0 ? Double(level * 100) : nil
    }

    private func getUploadQueues() -> ([UploadItem], [UploadItem]) {
        guard let uploadManager = uploadManager else {
            return ([], [])
        }

        let status = uploadManager.getStatus()
        var uploadQueue: [UploadItem] = []
        var failedUploadQueue: [UploadItem] = []

        // Add current upload if exists
        if let current = status.current {
            uploadQueue.append(current)
        }

        // Add pending uploads
        uploadQueue.append(contentsOf: status.pending)

        // Get failed uploads (if uploadManager supports it)
        // For now, return empty array - this would need to be implemented in UploadManager
        failedUploadQueue = []

        return (uploadQueue, failedUploadQueue)
    }

    private func cleanup() {
        print("NetworkManager: Cleaning up resources")
        isServiceRunning = false
        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        pathMonitor?.cancel()
        pathMonitor = nil

        stopListener()
        stopBonjourService()

        NotificationCenter.default.removeObserver(self)
    }
}

extension NetworkManager: NetServiceDelegate {
    func netServiceDidPublish(_ sender: NetService) {
        print("NetworkManager: Bonjour service published successfully")
        connectionStatus = "Advertising on network"
        retryCount = 0
    }

    func netService(_ sender: NetService, didNotPublish errorDict: [String : NSNumber]) {
        print("NetworkManager: Failed to publish Bonjour service: \(errorDict)")
        connectionStatus = "Failed to advertise on network"

        if retryCount < maxRetries {
            retryCount += 1
            let backoffTime = min(pow(2.0, Double(retryCount)), 30.0)
            print("NetworkManager: Retrying Bonjour service in \(backoffTime) seconds (attempt \(retryCount))")

            DispatchQueue.main.asyncAfter(deadline: .now() + backoffTime) { [weak self] in
                Task { @MainActor in
                    self?.stopBonjourService()
                    try? await Task.sleep(nanoseconds: 100_000_000)
                    self?.startBonjourService()
                }
            }
        }
    }

    func netServiceDidStop(_ sender: NetService) {
        print("NetworkManager: Bonjour service stopped")
        if isServiceRunning {
            print("NetworkManager: Unexpected service stop - attempting restart")
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                startBonjourService()
            }
        }
    }
}
