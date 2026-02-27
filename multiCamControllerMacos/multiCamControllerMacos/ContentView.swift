//
//  ContentView.swift
//  multiCamControllerMacos
//
//  Created by Angus Emmett on 9/25/25.
//

import SwiftUI

struct ContentView: View {
    @StateObject private var appState = AppState()
    @StateObject private var deviceDiscovery = DeviceDiscovery()
    @StateObject private var deviceCommunication = DeviceCommunication()
    @StateObject private var oakServerManager = OAKServerManager()
    @StateObject private var s3Manager = S3Manager(bucketName: "87c3e07f-3661-4489-829a-ddfa26943cb3")
    @StateObject private var fileManager = FileTransferManager()

    var body: some View {
        VStack(spacing: 20) {
            // Header
            headerView

            // Main content
            HStack(alignment: .top, spacing: 20) {
                // Left column
                VStack(spacing: 16) {
                    // Device discovery section
                    deviceDiscoverySection
                }
                .frame(minWidth: 350)

                // Right column
                VStack(spacing: 16) {
                    // Recording controls
                    RecordingControlsView(
                        appState: appState,
                        deviceCommunication: deviceCommunication,
                        s3Manager: s3Manager,
                        fileManager: fileManager
                    )

                    // File management
                    FileManagementView(fileManager: fileManager)

                    Spacer()
                }
                .frame(minWidth: 350)
            }

            Spacer()
        }
        .padding()
        .frame(minWidth: 750, minHeight: 600)
        .onAppear {
            setupConnections()
            startOAKServerAutomatically()
        }
    }

    private var headerView: some View {
        HStack {
            VStack(alignment: .leading) {
                Text("🎥 MultiCam Controller")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                Text("Control multiple iPhone and OAK cameras for synchronized recording")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
    }

    private var deviceDiscoverySection: some View {
        DeviceListView(appState: appState, deviceDiscovery: deviceDiscovery)
    }


    private func setupConnections() {
        deviceDiscovery.appState = appState
        fileManager.configure(
            deviceCommunication: deviceCommunication,
            s3Manager: s3Manager,
            appState: appState
        )
    }

    private func startOAKServerAutomatically() {
        // Skip automatic OAK server startup for now
        print("ℹ️ Skipping OAK server auto-start - start manually if needed")

        // Start device discovery immediately
        deviceDiscovery.startDiscovery()
    }
}

#Preview {
    ContentView()
}
