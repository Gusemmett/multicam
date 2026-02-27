//
//  OAKServerManager.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation

@MainActor
class OAKServerManager: ObservableObject {
    @Published var isRunning = false
    @Published var serverPort = 8081
    @Published var serverStatus = "Stopped"

    private var oakProcess: Process?
    private let videosDirectory: URL

    init() {
        // Create videos directory in user's Documents
        let documentsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        videosDirectory = documentsDir.appendingPathComponent("MultiCam Controller").appendingPathComponent("oak_videos")

        // Ensure directory exists
        try? FileManager.default.createDirectory(at: videosDirectory, withIntermediateDirectories: true)
    }

    func startOAKServer() async throws {
        guard !isRunning else {
            print("⚠️ OAK server is already running")
            return
        }

        print("🎥 Starting OAK server...")
        serverStatus = "Starting..."

        // Get bundle path for OAK controller
        guard let oakServerPath = getOAKServerPath() else {
            throw OAKServerError.oakControllerNotFound
        }

        // Create Python process
        oakProcess = Process()
        guard let process = oakProcess else {
            throw OAKServerError.processCreationFailed
        }

        // Configure process
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [
            oakServerPath.path,
            "--port", String(serverPort),
            "--videos-dir", videosDirectory.path
        ]

        // Set up environment
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = oakServerPath.deletingLastPathComponent().path
        process.environment = environment

        // Set up output handling
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = errorPipe

        // Monitor output
        outputPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let output = String(data: data, encoding: .utf8) {
                print("OAK Server Output: \(output.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }

        errorPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let error = String(data: data, encoding: .utf8) {
                print("OAK Server Error: \(error.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }

        // Set termination handler
        process.terminationHandler = { [weak self] process in
            Task { @MainActor in
                self?.isRunning = false
                self?.serverStatus = "Stopped"
                self?.oakProcess = nil
                print("🛑 OAK server process terminated with status: \(process.terminationStatus)")
            }
        }

        do {
            try process.run()
            isRunning = true
            serverStatus = "Running on port \(serverPort)"
            print("✅ OAK server started successfully on port \(serverPort)")
            print("📁 Videos directory: \(videosDirectory.path)")
        } catch {
            serverStatus = "Failed to start"
            throw OAKServerError.launchFailed(error.localizedDescription)
        }
    }

    func stopOAKServer() {
        guard let process = oakProcess, isRunning else {
            print("⚠️ OAK server is not running")
            return
        }

        print("🛑 Stopping OAK server...")
        serverStatus = "Stopping..."

        // Terminate the process
        process.terminate()

        // Wait for termination with timeout
        DispatchQueue.global().async {
            let semaphore = DispatchSemaphore(value: 0)
            DispatchQueue.global().asyncAfter(deadline: .now() + 5.0) {
                semaphore.signal()
            }

            process.waitUntilExit()
            semaphore.signal()

            // If process didn't terminate gracefully, force kill
            if process.isRunning {
                process.interrupt()
                if process.isRunning {
                    // Last resort - force kill
                    kill(process.processIdentifier, SIGKILL)
                }
            }
        }

        isRunning = false
        serverStatus = "Stopped"
        oakProcess = nil
        print("✅ OAK server stopped")
    }

    private func getOAKServerPath() -> URL? {
        // First, try to find the OAK server in the app bundle
        if let bundlePath = Bundle.main.url(forResource: "OAK-Controller-Rpi", withExtension: nil),
           let serverPath = findOAKServerScript(in: bundlePath) {
            return serverPath
        }

        // For development, try relative path from the main Python project
        let currentDir = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let developmentOAKPath = currentDir.appendingPathComponent("../multiCamController/OAK-Controller-Rpi")
        if let serverPath = findOAKServerScript(in: developmentOAKPath) {
            return serverPath
        }

        print("❌ Could not find OAK server script")
        return nil
    }

    private func findOAKServerScript(in directory: URL) -> URL? {
        let fileManager = FileManager.default
        let possiblePaths = [
            directory.appendingPathComponent("src/run_multicam_server.py"),
            directory.appendingPathComponent("run_multicam_server.py"),
            directory.appendingPathComponent("server.py")
        ]

        for path in possiblePaths {
            if fileManager.fileExists(atPath: path.path) {
                print("📍 Found OAK server at: \(path.path)")
                return path
            }
        }

        return nil
    }

    enum OAKServerError: Error, LocalizedError {
        case oakControllerNotFound
        case processCreationFailed
        case launchFailed(String)

        var errorDescription: String? {
            switch self {
            case .oakControllerNotFound:
                return "OAK Controller not found in app bundle"
            case .processCreationFailed:
                return "Failed to create Python process"
            case .launchFailed(let reason):
                return "Failed to launch OAK server: \(reason)"
            }
        }
    }

    deinit {
        Task { @MainActor in
            stopOAKServer()
        }
    }
}