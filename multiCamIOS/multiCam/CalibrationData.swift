//
//  CalibrationData.swift
//  multiCam
//
//  Camera calibration data structures for cloud upload
//

import Foundation

// MARK: - Root Calibration Data Structure
struct CalibrationData: Codable {
    let deviceId: String
    let intrinsics: [CameraIntrinsics]
    let extrinsics: [Extrinsics]

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case intrinsics
        case extrinsics
    }
}

// MARK: - Camera Intrinsics
struct CameraIntrinsics: Codable {
    let cameraId: String
    let timestamp: String
    let cameraMetadata: CameraMetadata?
    let lensIntrinsics: LensIntrinsics?
    let distortion: Distortion?
    let sensorInfo: SensorInfo?
    let lensInfo: LensInfo?
    let captureResolution: CaptureResolution?
    let positionalLayout: String?

    enum CodingKeys: String, CodingKey {
        case cameraId = "camera_id"
        case timestamp
        case cameraMetadata = "camera_metadata"
        case lensIntrinsics = "lens_intrinsics"
        case distortion
        case sensorInfo = "sensor_info"
        case lensInfo = "lens_info"
        case captureResolution = "capture_resolution"
        case positionalLayout = "positional_layout"
    }
}

// MARK: - Camera Metadata
struct CameraMetadata: Codable {
    let lensFacing: String?
    let hardwareLevel: Int?

    enum CodingKeys: String, CodingKey {
        case lensFacing = "lens_facing"
        case hardwareLevel = "hardware_level"
    }
}

// MARK: - Lens Intrinsics
struct LensIntrinsics: Codable {
    let focalLengthX: Double?
    let focalLengthY: Double?
    let principalPointX: Double?
    let principalPointY: Double?
    let skew: Double?
    let available: Bool

    enum CodingKeys: String, CodingKey {
        case focalLengthX = "focal_length_x"
        case focalLengthY = "focal_length_y"
        case principalPointX = "principal_point_x"
        case principalPointY = "principal_point_y"
        case skew
        case available
    }
}

// MARK: - Distortion
struct Distortion: Codable {
    let radial: [Double]?
    let tangential: [Double]?
    let available: Bool
}

// MARK: - Sensor Info
struct SensorInfo: Codable {
    let physicalSizeMm: PhysicalSize?
    let activeArraySize: ActiveArraySize?
    let pixelArraySize: PixelArraySize?

    enum CodingKeys: String, CodingKey {
        case physicalSizeMm = "physical_size_mm"
        case activeArraySize = "active_array_size"
        case pixelArraySize = "pixel_array_size"
    }
}

struct PhysicalSize: Codable {
    let width: Double
    let height: Double
}

struct ActiveArraySize: Codable {
    let left: Int
    let top: Int
    let right: Int
    let bottom: Int
    let width: Int
    let height: Int
}

struct PixelArraySize: Codable {
    let width: Int
    let height: Int
}

// MARK: - Lens Info
struct LensInfo: Codable {
    let focalLengthMm: [Double]?

    enum CodingKeys: String, CodingKey {
        case focalLengthMm = "focal_length_mm"
    }
}

// MARK: - Capture Resolution
struct CaptureResolution: Codable {
    let width: Int
    let height: Int
}

// MARK: - Extrinsics (empty for iPhone, but structure defined for future use)
struct Extrinsics: Codable {
    let type: String
    let from: String
    let to: String
    let R: [[Double]]
    let T: [Double]
    let matrix4x4: [[Double]]

    enum CodingKeys: String, CodingKey {
        case type
        case from
        case to
        case R
        case T
        case matrix4x4 = "matrix_4x4"
    }
}
