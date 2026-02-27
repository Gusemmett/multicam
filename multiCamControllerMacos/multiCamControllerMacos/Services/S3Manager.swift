//
//  S3Manager.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation
import AWSS3
import AWSClientRuntime
import ClientRuntime
import SmithyIdentity

// MARK: - AWS Credentials (fill if you prefer static credentials)
// If left empty, the SDK will use the default chain (env vars, ~/.aws/credentials, etc.)
private enum AWSStaticCredentialsConfig {
    static let accessKeyId: String = "***REMOVED***"
    static let secretAccessKey: String = "***REMOVED***"
    static let sessionToken: String? = nil
}

@MainActor
class S3Manager: ObservableObject {
    private let bucketName: String
    private var region: String
    private var s3Client: S3Client?

    @Published var uploadProgress: Double = 0
    @Published var isUploading = false
    @Published var lastUploadResult: UploadResult?

    struct UploadResult {
        let success: Bool
        let sessionFolder: String?
        let uploadedCount: Int
        let error: String?
    }

    struct SingleFileUploadResult {
        let success: Bool
        let s3Key: String?
        let error: String?
    }

    init(bucketName: String, region: String = "us-east-1") {
        self.bucketName = bucketName
        self.region = region
        Task {
            await configureAWSClient()
        }
    }

    func uploadFiles(
        _ filePaths: [String],
        progressCallback: ((Int, Int, Double, String) -> Void)? = nil
    ) async -> UploadResult {
        isUploading = true
        uploadProgress = 0

        print("📤 Starting upload of \(filePaths.count) files to S3...")

        // Generate session folder
        let sessionFolder = generateSessionFolder()

        guard let s3Client = s3Client else {
            isUploading = false
            return UploadResult(success: false, sessionFolder: nil, uploadedCount: 0, error: "S3 client not configured")
        }

        var uploadedCount = 0

        for (index, filePath) in filePaths.enumerated() {
            let fileName = URL(fileURLWithPath: filePath).lastPathComponent
            let s3Key = "\(sessionFolder)\(fileName)"

            print("📤 Uploading \(fileName) to s3://\(bucketName)/\(s3Key)")

            do {
                // Read file data
                let fileData = try Data(contentsOf: URL(fileURLWithPath: filePath))

                // Create S3 upload request
                var putObjectInput = PutObjectInput(
                    body: .data(fileData),
                    bucket: bucketName,
                    key: s3Key
                )
                if let contentType = Self.contentType(for: fileName) {
                    putObjectInput.contentType = contentType
                }

                // Upload to S3
                _ = try await s3Client.putObject(input: putObjectInput)

                uploadedCount += 1
                let progress = Double(uploadedCount) / Double(filePaths.count) * 100.0
                progressCallback?(index, filePaths.count, 100.0, fileName)
                uploadProgress = progress / 100.0

                print("✅ Uploaded \(fileName)")

            } catch {
                // First, try to detect if bucket region differs and retry once
                if let detectedRegion = await detectBucketRegion(), detectedRegion != region {
                    print("🔁 Detected bucket region: \(detectedRegion). Reconfiguring S3 client and retrying upload once...")
                    await configureAWSClient(region: detectedRegion)

                    do {
                        let fileData = try Data(contentsOf: URL(fileURLWithPath: filePath))
                        var retryPut = PutObjectInput(
                            body: .data(fileData),
                            bucket: bucketName,
                            key: s3Key
                        )
                        if let contentType = Self.contentType(for: fileName) {
                            retryPut.contentType = contentType
                        }
                        if let newClient = self.s3Client {
                            _ = try await newClient.putObject(input: retryPut)
                        } else {
                            throw NSError(domain: "S3", code: -1, userInfo: [NSLocalizedDescriptionKey: "S3 client not configured after region change"])
                        }

                        uploadedCount += 1
                        let progress = Double(uploadedCount) / Double(filePaths.count) * 100.0
                        progressCallback?(index, filePaths.count, 100.0, fileName)
                        uploadProgress = progress / 100.0
                        print("✅ Uploaded \(fileName) after region correction")
                        continue
                    } catch {
                        print("❌ Failed to upload \(fileName) after region correction: \(error)")
                    }
                }

                print("❌ Failed to upload \(fileName): \(error)")
                isUploading = false
                return UploadResult(success: false, sessionFolder: sessionFolder, uploadedCount: uploadedCount, error: error.localizedDescription)
            }
        }

        uploadProgress = 1.0
        isUploading = false

        let result = UploadResult(success: true, sessionFolder: sessionFolder, uploadedCount: uploadedCount, error: nil)
        lastUploadResult = result
        print("✅ Upload complete! \(uploadedCount) files uploaded to folder: \(sessionFolder)")
        return result
    }

    func uploadAndCleanup(
        _ filePaths: [String],
        progressCallback: ((Int, Int, Double, String) -> Void)? = nil
    ) async -> UploadResult {
        let uploadResult = await uploadFiles(filePaths, progressCallback: progressCallback)

        if uploadResult.success {
            // Clean up local files after successful upload
            await cleanupLocalFiles(filePaths)
            print("🗑️ Local files cleaned up after successful upload")
        }

        return uploadResult
    }

    func uploadSingleFile(
        filePath: String,
        sessionFolder: String,
        progressCallback: ((Double) -> Void)? = nil
    ) async -> SingleFileUploadResult {
        guard let s3Client = s3Client else {
            return SingleFileUploadResult(success: false, s3Key: nil, error: "S3 client not configured")
        }

        let fileName = URL(fileURLWithPath: filePath).lastPathComponent
        let s3Key = "\(sessionFolder)\(fileName)"

        print("📤 Uploading \(fileName) to s3://\(bucketName)/\(s3Key)")

        do {
            let fileData = try Data(contentsOf: URL(fileURLWithPath: filePath))

            var putObjectInput = PutObjectInput(
                body: .data(fileData),
                bucket: bucketName,
                key: s3Key
            )
            if let contentType = Self.contentType(for: fileName) {
                putObjectInput.contentType = contentType
            }

            _ = try await s3Client.putObject(input: putObjectInput)

            progressCallback?(100.0)
            print("✅ Uploaded \(fileName)")

            return SingleFileUploadResult(success: true, s3Key: s3Key, error: nil)

        } catch {
            if let detectedRegion = await detectBucketRegion(), detectedRegion != region {
                print("🔁 Detected bucket region: \(detectedRegion). Reconfiguring S3 client and retrying upload once...")
                await configureAWSClient(region: detectedRegion)

                do {
                    let fileData = try Data(contentsOf: URL(fileURLWithPath: filePath))
                    var retryPut = PutObjectInput(
                        body: .data(fileData),
                        bucket: bucketName,
                        key: s3Key
                    )
                    if let contentType = Self.contentType(for: fileName) {
                        retryPut.contentType = contentType
                    }
                    if let newClient = self.s3Client {
                        _ = try await newClient.putObject(input: retryPut)
                    } else {
                        throw NSError(domain: "S3", code: -1, userInfo: [NSLocalizedDescriptionKey: "S3 client not configured after region change"])
                    }

                    progressCallback?(100.0)
                    print("✅ Uploaded \(fileName) after region correction")
                    return SingleFileUploadResult(success: true, s3Key: s3Key, error: nil)
                } catch {
                    print("❌ Failed to upload \(fileName) after region correction: \(error)")
                }
            }

            print("❌ Failed to upload \(fileName): \(error)")
            return SingleFileUploadResult(success: false, s3Key: nil, error: error.localizedDescription)
        }
    }

    private func cleanupLocalFiles(_ filePaths: [String]) async {
        for filePath in filePaths {
            do {
                try FileManager.default.removeItem(atPath: filePath)
                print("🗑️ Deleted local file: \(URL(fileURLWithPath: filePath).lastPathComponent)")
            } catch {
                print("⚠️ Failed to delete \(filePath): \(error.localizedDescription)")
            }
        }
    }

    private func generateSessionFolder() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd/HH-mm-ss"
        return formatter.string(from: Date()) + "/"
    }

    // MARK: - AWS SDK Integration

    private func configureAWSClient(region: String? = nil) async {
        do {
            // Prefer static credentials if provided; otherwise fall back to default chain
            let hasStaticCredentials = !AWSStaticCredentialsConfig.accessKeyId.isEmpty && !AWSStaticCredentialsConfig.secretAccessKey.isEmpty

            let effectiveRegion = region ?? self.region
            let config: S3Client.S3ClientConfiguration
            if hasStaticCredentials {
                let identity = AWSCredentialIdentity(
                    accessKey: AWSStaticCredentialsConfig.accessKeyId,
                    secret: AWSStaticCredentialsConfig.secretAccessKey
                )
                let resolver = StaticAWSCredentialIdentityResolver(identity)
                config = try await S3Client.S3ClientConfiguration(
                    awsCredentialIdentityResolver: resolver,
                    region: effectiveRegion
                )
            } else {
                config = try await S3Client.S3ClientConfiguration(region: effectiveRegion)
            }

            s3Client = S3Client(config: config)
            if let newRegion = region {
                self.region = newRegion
            }
            print("✅ AWS S3 client configured for region: \(self.region)")
        } catch {
            print("❌ Failed to configure AWS S3 client: \(error)")
        }
    }

    func testConnection() async -> Bool {
        guard let s3Client = s3Client else {
            print("❌ S3 client not configured")
            return false
        }

        do {
            let headBucketInput = HeadBucketInput(bucket: bucketName)
            _ = try await s3Client.headBucket(input: headBucketInput)
            print("✅ S3 connection test successful for bucket: \(bucketName)")
            return true
        } catch {
            print("❌ S3 connection test failed: \(error)")
            return false
        }
    }

    // MARK: - Helpers
    private func detectBucketRegion() async -> String? {
        do {
            guard let s3Client = s3Client else { return nil }
            let headBucketInput = HeadBucketInput(bucket: bucketName)
            _ = try await s3Client.headBucket(input: headBucketInput)
            // If headBucket succeeds, the region is correct; return current
            return region
        } catch {
            // In AWS SDK Swift v2, we handle errors differently
            // Most region-related errors will be service errors that we can't easily extract from
            // For now, return nil and let the calling code handle the error
            print("⚠️ Region detection failed: \(error)")
            return nil
        }
    }
    private static func contentType(for fileName: String) -> String? {
        let ext = URL(fileURLWithPath: fileName).pathExtension.lowercased()
        switch ext {
        case "mp4": return "video/mp4"
        case "mov": return "video/quicktime"
        case "jpg", "jpeg": return "image/jpeg"
        case "png": return "image/png"
        case "wav": return "audio/wav"
        case "mp3": return "audio/mpeg"
        case "json": return "application/json"
        case "txt": return "text/plain"
        default: return nil
        }
    }
}
