//
//  DeviceListView.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/25/25.
//

import SwiftUI

struct DeviceListView: View {
    @ObservedObject var appState: AppState
    var deviceDiscovery: DeviceDiscovery?
    @State private var showingManualConnection = false
    @State private var manualIP = ""
    @State private var manualPort = "8080"

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "wifi.router")
                    .foregroundColor(.blue)
                Text("Discovered Devices")
                    .font(.headline)

                Spacer()

                if appState.isDiscovering {
                    ProgressView()
                        .scaleEffect(0.8)
                }

                Button("🔍 Discover") {
                    deviceDiscovery?.startDiscovery()
                }
                .font(.caption)
                .buttonStyle(.borderedProminent)
                .disabled(appState.isDiscovering)

                Button("+ Manual") {
                    showingManualConnection = true
                }
                .font(.caption)
                .buttonStyle(.bordered)
            }

            if appState.discoveredDevices.isEmpty && !appState.isDiscovering {
                VStack(alignment: .leading, spacing: 8) {
                    Text("No devices discovered yet.")
                        .foregroundColor(.secondary)

                    Text("Make sure:")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("• iPhone multiCam apps are running")
                        Text("• All devices on same WiFi network")
                        Text("• OAK server is started (if using OAK camera)")
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                }
                .padding()
                .background(Color.gray.opacity(0.1))
                .cornerRadius(8)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(appState.discoveredDevices) { device in
                            DeviceRow(device: device)
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
        }
        .padding()
        .background(Color(.controlBackgroundColor))
        .cornerRadius(10)
        .sheet(isPresented: $showingManualConnection) {
            manualConnectionView
        }
    }

    private var manualConnectionView: some View {
        VStack(spacing: 20) {
            Text("Manual Device Connection")
                .font(.headline)

            VStack(alignment: .leading, spacing: 8) {
                Text("IP Address:")
                    .font(.subheadline)
                TextField("192.168.1.100", text: $manualIP)
                    .textFieldStyle(.roundedBorder)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Port:")
                    .font(.subheadline)
                TextField("8080", text: $manualPort)
                    .textFieldStyle(.roundedBorder)
            }

            HStack(spacing: 10) {
                Button("Cancel") {
                    showingManualConnection = false
                }
                .buttonStyle(.bordered)

                Button("Connect") {
                    addManualDevice()
                }
                .buttonStyle(.borderedProminent)
                .disabled(manualIP.isEmpty)
            }
        }
        .padding()
        .frame(width: 300, height: 250)
    }

    private func addManualDevice() {
        guard !manualIP.isEmpty,
              let port = Int(manualPort),
              port > 0 && port <= 65535 else {
            print("❌ Invalid IP or port: \(manualIP):\(manualPort)")
            return
        }

        let device = MultiCamDevice(
            name: "manual-\(manualIP)",
            ip: manualIP,
            port: port,
            serviceType: "_multicam._tcp."
        )

        appState.addDevice(device)
        showingManualConnection = false

        // Clear the fields
        manualIP = ""
        manualPort = "8080"
    }
}

struct DeviceRow: View {
    let device: MultiCamDevice

    var body: some View {
        HStack {
            Text(device.deviceType.icon)
                .font(.title2)

            VStack(alignment: .leading, spacing: 2) {
                Text(device.displayName)
                    .font(.subheadline)
                    .fontWeight(.medium)

                Text("\(device.ip):\(device.port)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Circle()
                .fill(device.isConnected ? Color.green : Color.gray)
                .frame(width: 8, height: 8)
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(Color(.controlBackgroundColor).opacity(0.5))
        .cornerRadius(6)
    }
}

#Preview {
    DeviceListView(appState: {
        let state = AppState()
        state.discoveredDevices = [
            MultiCamDevice.preview,
            MultiCamDevice(name: "multiCam-OAK", ip: "192.168.1.101", port: 8081, serviceType: "_multicam._tcp.")
        ]
        return state
    }(), deviceDiscovery: DeviceDiscovery())
    .frame(width: 400, height: 300)
}