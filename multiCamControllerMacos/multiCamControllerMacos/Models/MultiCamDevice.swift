//
//  MultiCamDevice.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation

struct MultiCamDevice: Identifiable, Codable, Hashable {
    let id = UUID()
    let name: String
    let ip: String
    let port: Int
    let serviceType: String
    var isConnected: Bool = false
    var lastSeen: Date = Date()

    var displayName: String {
        // Extract camera ID from device name
        var cleanName = name
        if cleanName.contains("._multicam._tcp.local.") {
            cleanName = cleanName.replacingOccurrences(of: "._multicam._tcp.local.", with: "")
        }

        if cleanName.hasPrefix("multiCam-") {
            cleanName = String(cleanName.dropFirst(9)) // Remove 'multiCam-'
        }

        return cleanName
    }

    var deviceType: DeviceType {
        if name.contains("manual-") {
            return .manual
        } else if displayName.lowercased().contains("oak") {
            return .oak
        } else {
            return .iPhone
        }
    }

    enum DeviceType {
        case iPhone, oak, manual

        var icon: String {
            switch self {
            case .iPhone: return "📱"
            case .oak: return "🎥"
            case .manual: return "📷"
            }
        }
    }
}

extension MultiCamDevice {
    static let preview = MultiCamDevice(
        name: "multiCam-iPhone15Pro",
        ip: "192.168.1.100",
        port: 8080,
        serviceType: "_multicam._tcp."
    )
}