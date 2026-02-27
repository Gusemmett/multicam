//
//  FileManagementView.swift
//  multiCamControllerMacos
//
//  Created by Claude Code on 9/26/25.
//

import SwiftUI

struct FileManagementView: View {
    @ObservedObject var fileManager: FileTransferManager

    var body: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                Image(systemName: "folder.circle")
                    .foregroundColor(.blue)
                    .font(.title2)
                Text("File Management")
                    .font(.headline)
                Spacer()

                // Summary stats
                HStack(spacing: 12) {
                    if fileManager.activeTransfersCount > 0 {
                        Label("\(fileManager.activeTransfersCount)", systemImage: "arrow.triangle.2.circlepath")
                            .foregroundColor(.blue)
                            .font(.caption)
                    }

                    if fileManager.completedTransfersCount > 0 {
                        Label("\(fileManager.completedTransfersCount)", systemImage: "checkmark.circle.fill")
                            .foregroundColor(.green)
                            .font(.caption)
                    }

                    if fileManager.failedTransfersCount > 0 {
                        Label("\(fileManager.failedTransfersCount)", systemImage: "exclamationmark.triangle")
                            .foregroundColor(.red)
                            .font(.caption)
                    }
                }
            }

            if fileManager.transferItems.isEmpty {
                // Empty state
                VStack(spacing: 8) {
                    Image(systemName: "tray")
                        .font(.title)
                        .foregroundColor(.secondary)
                    Text("No file transfers")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    Text("Files will appear here after recording stops")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(height: 100)
            } else {
                // File transfer list
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(fileManager.transferItems) { item in
                            FileTransferRowView(item: item, fileManager: fileManager)
                        }
                    }
                }
                .frame(maxHeight: 200)

                // Action buttons
                HStack {
                    if fileManager.completedTransfersCount > 0 {
                        Button("Clear Completed") {
                            fileManager.clearCompletedItems()
                        }
                        .buttonStyle(.bordered)
                    }

                    Spacer()
                }
            }
        }
        .padding()
        .background(Color(.controlBackgroundColor))
        .cornerRadius(10)
    }
}

struct FileTransferRowView: View {
    @ObservedObject var item: FileTransferItem
    let fileManager: FileTransferManager

    var body: some View {
        HStack(spacing: 12) {
            // Status icon
            Image(systemName: item.status.icon)
                .foregroundColor(colorForStatus(item.status.color))
                .font(.title3)
                .frame(width: 20)

            // File info
            VStack(alignment: .leading, spacing: 2) {
                Text(item.fileName)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(1)

                Text("\(item.deviceName) • \(item.status.displayText)")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            Spacer()

            // Progress or action
            HStack(spacing: 8) {
                if item.status == .failed {
                    Button(action: {
                        fileManager.retryFailedItem(item)
                    }) {
                        Image(systemName: "arrow.clockwise")
                            .font(.caption)
                    }
                    .buttonStyle(.borderless)
                } else if item.status == .downloading || item.status == .uploading {
                    ProgressView(value: item.overallProgress)
                        .frame(width: 60)

                    Text(String(format: "%.2f%%", item.overallProgress * 100))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .frame(width: 40)
                } else if item.status == .completed {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .font(.caption)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(backgroundColorForStatus(item.status))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(borderColorForStatus(item.status), lineWidth: 1)
        )
    }

    private func colorForStatus(_ colorName: String) -> Color {
        switch colorName {
        case "orange": return .orange
        case "blue": return .blue
        case "green": return .green
        case "red": return .red
        default: return .primary
        }
    }

    private func backgroundColorForStatus(_ status: FileTransferItem.TransferStatus) -> Color {
        switch status {
        case .failed:
            return Color.red.opacity(0.1)
        case .completed:
            return Color.green.opacity(0.1)
        case .downloading, .uploading:
            return Color.blue.opacity(0.1)
        default:
            return Color.clear
        }
    }

    private func borderColorForStatus(_ status: FileTransferItem.TransferStatus) -> Color {
        switch status {
        case .failed:
            return Color.red.opacity(0.3)
        case .completed:
            return Color.green.opacity(0.3)
        case .downloading, .uploading:
            return Color.blue.opacity(0.3)
        default:
            return Color.secondary.opacity(0.2)
        }
    }
}

#Preview {
    FileManagementView(fileManager: {
        let manager = FileTransferManager()

        // Add some sample items for preview
        let item1 = FileTransferItem(deviceName: "iPhone-1", fileId: "video123", sessionId: UUID())
        item1.status = .downloading
        item1.downloadProgress = 0.7

        let item2 = FileTransferItem(deviceName: "iPhone-2", fileId: "video456", sessionId: UUID())
        item2.status = .uploading
        item2.uploadProgress = 0.3

        let item3 = FileTransferItem(deviceName: "iPhone-3", fileId: "video789", sessionId: UUID())
        item3.status = .completed

        manager.transferItems = [item1, item2, item3]
        return manager
    }())
    .frame(width: 400, height: 300)
}