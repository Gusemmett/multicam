//
//  CameraIntrinsicsCollector.swift
//  multiCam
//
//  Collects camera intrinsic calibration data from AVCameraCalibrationData
//

import AVFoundation
import CoreMedia
import UIKit

class CameraIntrinsicsCollector {

    /// Collects camera calibration data from AVCameraCalibrationData (exact) or estimates from device
    /// - Parameters:
    ///   - device: The AVCaptureDevice to collect intrinsics from
    ///   - deviceId: The multiCam device ID
    ///   - recordingResolution: The actual resolution used for recording
    ///   - calibrationData: Optional AVCameraCalibrationData from depth capture
    /// - Returns: CalibrationData containing device intrinsics
    static func collectCalibrationData(
        from device: AVCaptureDevice,
        deviceId: String,
        recordingResolution: CGSize?,
        calibrationData: AVCameraCalibrationData?
    ) -> CalibrationData {

        let timestamp = ISO8601DateFormatter().string(from: Date())
        let cameraId = device.uniqueID

        if let calibrationData = calibrationData {
            // Use exact calibration data from depth photo
            print("CameraIntrinsicsCollector: Using exact calibration data from depth capture")
            return collectFromCalibrationData(
                calibrationData: calibrationData,
                deviceId: deviceId,
                cameraId: cameraId,
                timestamp: timestamp,
                device: device,
                recordingResolution: recordingResolution
            )
        } else {
            // Fall back to estimation
            print("CameraIntrinsicsCollector: WARNING - Using estimated calibration data")
            return collectEstimated(
                device: device,
                deviceId: deviceId,
                cameraId: cameraId,
                timestamp: timestamp,
                recordingResolution: recordingResolution
            )
        }
    }

    // MARK: - Exact Calibration from AVCameraCalibrationData

    private static func collectFromCalibrationData(
        calibrationData: AVCameraCalibrationData,
        deviceId: String,
        cameraId: String,
        timestamp: String,
        device: AVCaptureDevice,
        recordingResolution: CGSize?
    ) -> CalibrationData {

        // Extract intrinsic matrix
        let intrinsicMatrix = calibrationData.intrinsicMatrix
        let fx = Double(intrinsicMatrix.columns.0.x)
        let fy = Double(intrinsicMatrix.columns.1.y)
        let cx = Double(intrinsicMatrix.columns.2.x)
        let cy = Double(intrinsicMatrix.columns.2.y)

        let lensIntrinsics = LensIntrinsics(
            focalLengthX: fx,
            focalLengthY: fy,
            principalPointX: cx,
            principalPointY: cy,
            skew: 0.0,
            available: true
        )

        // Extract distortion parameters
        let distortion = extractDistortion(from: calibrationData)

        // Camera metadata
        let cameraMetadata = CameraMetadata(
            lensFacing: device.position == .back ? "BACK" : "FRONT",
            hardwareLevel: 3  // iOS cameras are generally "full" capability
        )

        // Sensor info from calibrationData
        let pixelSize = calibrationData.pixelSize
        let imageSize = calibrationData.intrinsicMatrixReferenceDimensions

        let sensorInfo = SensorInfo(
            physicalSizeMm: PhysicalSize(
                width: Double(pixelSize) * Double(imageSize.width),
                height: Double(pixelSize) * Double(imageSize.height)
            ),
            activeArraySize: ActiveArraySize(
                left: 0,
                top: 0,
                right: Int(imageSize.width),
                bottom: Int(imageSize.height),
                width: Int(imageSize.width),
                height: Int(imageSize.height)
            ),
            pixelArraySize: PixelArraySize(
                width: Int(imageSize.width),
                height: Int(imageSize.height)
            )
        )

        // Lens info (estimated based on device type)
        let focalLengthMm = estimateFocalLengthMm(for: device)
        let lensInfo = LensInfo(focalLengthMm: focalLengthMm != nil ? [focalLengthMm!] : nil)

        // Capture resolution
        let captureResolution: CaptureResolution?
        if let resolution = recordingResolution {
            captureResolution = CaptureResolution(
                width: Int(resolution.width),
                height: Int(resolution.height)
            )
        } else {
            captureResolution = CaptureResolution(
                width: Int(imageSize.width),
                height: Int(imageSize.height)
            )
        }

        let intrinsics = CameraIntrinsics(
            cameraId: cameraId,
            timestamp: timestamp,
            cameraMetadata: cameraMetadata,
            lensIntrinsics: lensIntrinsics,
            distortion: distortion,
            sensorInfo: sensorInfo,
            lensInfo: lensInfo,
            captureResolution: captureResolution,
            positionalLayout: "center"
        )

        return CalibrationData(
            deviceId: deviceId,
            intrinsics: [intrinsics],
            extrinsics: []
        )
    }

    /// Extract distortion coefficients from lens distortion lookup table
    private static func extractDistortion(from calibrationData: AVCameraCalibrationData) -> Distortion {
        let lookupTable = calibrationData.lensDistortionLookupTable
        let distortionCenter = calibrationData.lensDistortionCenter

        guard lookupTable != nil else {
            return Distortion(radial: nil, tangential: nil, available: false)
        }

        // Convert lookup table to approximate radial distortion coefficients
        // The lookup table describes radial distortion from center to corner
        // We'll approximate with a simple polynomial fit for k1, k2

        // For now, we'll extract the lookup table as raw data and let the consumer handle it
        // Or convert to OpenCV-style coefficients via polynomial approximation

        // Simple approximation: use early values in lookup table to estimate k1, k2
        let data = lookupTable!
        let floatCount = data.count / MemoryLayout<Float>.size
        let floats = data.withUnsafeBytes { buffer in
            Array(buffer.bindMemory(to: Float.self))
        }

        // Simple polynomial approximation
        // This is a rough conversion - ideally would fit a polynomial to the lookup table
        let k1: Double
        let k2: Double

        if floatCount >= 2 {
            // Use first few values to approximate distortion
            k1 = Double(floats[min(floatCount / 4, floatCount - 1)])
            k2 = floatCount > floatCount / 2 ? Double(floats[floatCount / 2]) : 0.0
        } else {
            k1 = 0.0
            k2 = 0.0
        }

        return Distortion(
            radial: [k1, k2],
            tangential: nil,  // iPhone cameras have negligible tangential distortion
            available: true
        )
    }

    // MARK: - Fallback Estimation (if no depth data)

    private static func collectEstimated(
        device: AVCaptureDevice,
        deviceId: String,
        cameraId: String,
        timestamp: String,
        recordingResolution: CGSize?
    ) -> CalibrationData {

        let formatDescription = device.activeFormat.formatDescription
        let dimensions = CMVideoFormatDescriptionGetDimensions(formatDescription)
        let width = Double(dimensions.width)
        let height = Double(dimensions.height)

        // Estimate focal length from field of view
        let fovRadians = Double(device.activeFormat.videoFieldOfView) * .pi / 180.0
        let focalLengthPixels = width / (2.0 * tan(fovRadians / 2.0))

        let lensIntrinsics = LensIntrinsics(
            focalLengthX: focalLengthPixels,
            focalLengthY: focalLengthPixels,
            principalPointX: width / 2.0,
            principalPointY: height / 2.0,
            skew: 0.0,
            available: false  // Estimated, not exact
        )

        let distortion = Distortion(
            radial: nil,
            tangential: nil,
            available: false
        )

        let cameraMetadata = CameraMetadata(
            lensFacing: device.position == .back ? "BACK" : "FRONT",
            hardwareLevel: 3
        )

        let sensorInfo = SensorInfo(
            physicalSizeMm: PhysicalSize(width: 4.8, height: 3.6),  // Typical estimate
            activeArraySize: ActiveArraySize(
                left: 0,
                top: 0,
                right: Int(dimensions.width),
                bottom: Int(dimensions.height),
                width: Int(dimensions.width),
                height: Int(dimensions.height)
            ),
            pixelArraySize: PixelArraySize(
                width: Int(dimensions.width),
                height: Int(dimensions.height)
            )
        )

        let focalLengthMm = estimateFocalLengthMm(for: device)
        let lensInfo = LensInfo(focalLengthMm: focalLengthMm != nil ? [focalLengthMm!] : nil)

        let captureResolution: CaptureResolution?
        if let resolution = recordingResolution {
            captureResolution = CaptureResolution(
                width: Int(resolution.width),
                height: Int(resolution.height)
            )
        } else {
            captureResolution = CaptureResolution(
                width: Int(dimensions.width),
                height: Int(dimensions.height)
            )
        }

        let intrinsics = CameraIntrinsics(
            cameraId: cameraId,
            timestamp: timestamp,
            cameraMetadata: cameraMetadata,
            lensIntrinsics: lensIntrinsics,
            distortion: distortion,
            sensorInfo: sensorInfo,
            lensInfo: lensInfo,
            captureResolution: captureResolution,
            positionalLayout: "center"
        )

        return CalibrationData(
            deviceId: deviceId,
            intrinsics: [intrinsics],
            extrinsics: []
        )
    }

    // MARK: - Helpers

    private static func estimateFocalLengthMm(for device: AVCaptureDevice) -> Double? {
        let deviceType = device.deviceType

        // Approximate focal lengths for iPhone lenses
        if deviceType == .builtInUltraWideCamera {
            return 2.0  // ~13mm equivalent (0.5x)
        } else if deviceType == .builtInWideAngleCamera {
            return 4.2  // ~26mm equivalent (1x)
        } else if deviceType == .builtInTelephotoCamera {
            return 6.0  // ~52mm equivalent (2x) or higher
        } else {
            return 4.2  // Default to wide angle
        }
    }
}
