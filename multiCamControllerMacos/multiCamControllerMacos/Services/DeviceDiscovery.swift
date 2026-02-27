//
//  DeviceDiscovery.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import Foundation
import Network

@MainActor
class DeviceDiscovery: NSObject, ObservableObject {
    private let serviceBrowser = NetServiceBrowser()
    private let serviceType = "_multicam._tcp."
    private let serviceDomain = ""

    @Published var discoveredServices: [NetService] = []

    weak var appState: AppState?

    override init() {
        super.init()
        serviceBrowser.delegate = self
    }

    func startDiscovery() {
        appState?.isDiscovering = true
        appState?.updateStatus("🔍 Discovering devices...")
        appState?.clearDevices()

        print("🔍 Starting mDNS discovery for \(serviceType)")
        serviceBrowser.searchForServices(ofType: serviceType, inDomain: serviceDomain)

        // Set a timeout to automatically retry or show alternative options
        DispatchQueue.main.asyncAfter(deadline: .now() + 10.0) {
            if let appState = self.appState, appState.isDiscovering && appState.discoveredDevices.isEmpty {
                print("⚠️ mDNS discovery timeout - suggesting manual device entry")
                appState.updateStatus("⚠️ Auto-discovery timed out. Try manual device connection.")
                appState.isDiscovering = false
                self.stopDiscovery()
            }
        }
    }

    func stopDiscovery() {
        appState?.isDiscovering = false
        serviceBrowser.stop()
        print("🛑 Stopped mDNS discovery")
    }

    private func createDevice(from service: NetService) -> MultiCamDevice? {
        // For immediate device creation, we can use the hostname if available
        // The service might not be fully resolved yet, but we can still create the device

        var deviceIP = service.hostName ?? "unknown"

        // Try to extract IP from addresses if available
        if let addresses = service.addresses, !addresses.isEmpty {
            let address = addresses[0]
            var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))

            let result = getnameinfo(
                address.withUnsafeBytes { $0.bindMemory(to: sockaddr.self).baseAddress! },
                socklen_t(address.count),
                &hostname, socklen_t(hostname.count),
                nil, 0,
                NI_NUMERICHOST
            )

            if result == 0, let ip = String(cString: hostname, encoding: .utf8) {
                deviceIP = ip
            }
        } else if let hostName = service.hostName {
            // Use hostname if addresses not available yet
            deviceIP = hostName.replacingOccurrences(of: ".local.", with: "")
        }

        // Validate service port (NetService.port can return -1 if unresolved)
        let validPort = service.port > 0 ? service.port : 8080

        let device = MultiCamDevice(
            name: service.name,
            ip: deviceIP,
            port: validPort,
            serviceType: service.type
        )

        print("📱 Found device: \(device.displayName) at \(deviceIP):\(validPort)")
        return device
    }
}

// MARK: - NetServiceBrowserDelegate
extension DeviceDiscovery: NetServiceBrowserDelegate {
    nonisolated func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        Task { @MainActor in
            print("🔍 Found service: \(service.name)")
            discoveredServices.append(service)

            // Start resolving the service to get proper IP address
            service.delegate = self
            service.resolve(withTimeout: 5.0)

            if !moreComing {
                let deviceCount = appState?.discoveredDevices.count ?? 0
                if deviceCount > 0 {
                    appState?.updateStatus("✅ Found \(deviceCount) device(s)")
                } else {
                    appState?.updateStatus("Waiting")
                }
                appState?.isDiscovering = false
                stopDiscovery()
            }
        }
    }

    nonisolated func netServiceBrowser(_ browser: NetServiceBrowser, didRemove service: NetService, moreComing: Bool) {
        Task { @MainActor in
            print("❌ Service removed: \(service.name)")
            discoveredServices.removeAll { $0.name == service.name }
            appState?.removeDevice(named: service.name)
        }
    }

    nonisolated func netServiceBrowser(_ browser: NetServiceBrowser, didNotSearch errorDict: [String: NSNumber]) {
        Task { @MainActor in
            let errorCode = errorDict["NSNetServicesErrorCode"]?.intValue ?? 0
            let errorDomain = errorDict["NSNetServicesErrorDomain"]?.description ?? "Unknown"

            print("❌ Service browser did not search - Domain: \(errorDomain), Code: \(errorCode)")
            print("❌ Full error dict: \(errorDict)")

            var errorMessage = "Discovery failed"
            if errorCode == -72000 {
                errorMessage = "Network permission denied. Please check app entitlements and network settings."
            } else if errorCode == -72004 {
                errorMessage = "Network service not found or unavailable."
            }

            appState?.updateStatus("❌ \(errorMessage)")
            appState?.isDiscovering = false
        }
    }

    nonisolated func netServiceBrowserWillSearch(_ browser: NetServiceBrowser) {
        print("🔍 Service browser will search")
    }

    nonisolated func netServiceBrowserDidStopSearch(_ browser: NetServiceBrowser) {
        Task { @MainActor in
            print("🛑 Service browser stopped search")
            appState?.isDiscovering = false
        }
    }
}

// MARK: - NetServiceDelegate
extension DeviceDiscovery: NetServiceDelegate {
    nonisolated func netServiceDidResolveAddress(_ sender: NetService) {
        Task { @MainActor in
            print("✅ Service resolved: \(sender.name)")
            if let device = createDevice(from: sender) {
                appState?.addDevice(device)
                print("📱 Added resolved device: \(device.displayName) at \(device.ip):\(device.port)")
            }
        }
    }

    nonisolated func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        Task { @MainActor in
            print("❌ Service resolution failed for \(sender.name): \(errorDict)")
            // Still try to create device with default port as fallback
            if let device = createDevice(from: sender) {
                appState?.addDevice(device)
                print("📱 Added unresolved device: \(device.displayName) at \(device.ip):\(device.port)")
            }
        }
    }
}