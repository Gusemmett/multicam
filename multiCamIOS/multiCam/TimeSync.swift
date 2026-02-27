//
//  TimeSync.swift
//  multiCam
//
//  Time synchronization manager using NTP for precise multi-device sync
//

import Foundation

@MainActor
class TimeSync: ObservableObject {
    @Published var isSynchronized = false
    @Published var timeOffset: TimeInterval = 0
    @Published var syncStatus: String = "Not synchronized"
    @Published var lastSyncTime: Date?

    private let ntpClient: NTPClient
    private let syncAttempts = 4  // Send 4 requests, select best 3
    private let maxAcceptableRTT: TimeInterval = 0.5 // 500ms max RTT
    private let resyncInterval: TimeInterval = 300 // 5 minutes

    init(ntpServer: String = "pool.ntp.org") {
        self.ntpClient = NTPClient(server: ntpServer)
    }

    func synchronizeTime() async {
        let syncStartTime = Date().timeIntervalSince1970
        print("TimeSync: ===============================================")
        print("TimeSync: Starting NTP time synchronization at \(syncStartTime)")
        print("TimeSync: Attempts: \(syncAttempts), Max RTT: \(Int(maxAcceptableRTT * 1000))ms")

        // Update status on main actor
        await MainActor.run {
            syncStatus = "Synchronizing..."
        }

        var successfulSyncs: [(offset: TimeInterval, rtt: TimeInterval)] = []

        // Perform multiple sync attempts
        for attempt in 1...syncAttempts {
            let attemptStartTime = Date().timeIntervalSince1970
            print("TimeSync: -----------------------------------------------")
            print("TimeSync: Sync attempt \(attempt)/\(syncAttempts) starting at \(attemptStartTime)")

            do {
                let (ntpTime, receiveTime, roundTripTime) = try await ntpClient.getNTPTime()

                // Calculate time offset using proper NTP logic
                // ntpTime = T3 (server transmit timestamp)
                // receiveTime = T4 (client receive timestamp) - captured at exact moment
                // For proper NTP: offset = T3 - T4 + (roundTripTime / 2)
                // This accounts for network delay assuming symmetric paths
                let networkDelay = roundTripTime / 2
                let offset = ntpTime - receiveTime + networkDelay

                print("TimeSync: Attempt \(attempt) Results:")
                print("TimeSync:   - NTP Time (T3): \(ntpTime)")
                print("TimeSync:   - Receive Time (T4): \(receiveTime)")
                print("TimeSync:   - Network Delay: \(Int(networkDelay * 1000))ms")
                print("TimeSync:   - Calculated Offset: \(Int(offset * 1000))ms")
                print("TimeSync:   - RTT: \(Int(roundTripTime * 1000))ms")

                // Only use results with reasonable RTT
                if roundTripTime <= maxAcceptableRTT {
                    successfulSyncs.append((offset: offset, rtt: roundTripTime))
                    print("TimeSync: Attempt \(attempt) ACCEPTED (RTT \(Int(roundTripTime * 1000))ms <= \(Int(maxAcceptableRTT * 1000))ms)")
                } else {
                    print("TimeSync: Attempt \(attempt) REJECTED (RTT \(Int(roundTripTime * 1000))ms > \(Int(maxAcceptableRTT * 1000))ms)")
                }

            } catch {
                print("TimeSync: Attempt \(attempt) failed: \(error.localizedDescription)")
            }

            // Small delay between attempts to avoid overwhelming the server
            if attempt < syncAttempts {
                do {
                    try await Task.sleep(nanoseconds: 500_000_000) // 500ms delay
                } catch {
                    print("TimeSync: Sleep interrupted")
                    break
                }
            }
        }

        // Calculate final offset from successful attempts and update UI on main actor
        if !successfulSyncs.isEmpty {
            // Select the best 3 offsets from all successful attempts (discarding outliers)
            let selectedSyncs = selectBestOffsets(from: successfulSyncs)

            let averageOffset = selectedSyncs.reduce(0) { $0 + $1.offset } / Double(selectedSyncs.count)
            let averageRTT = selectedSyncs.reduce(0) { $0 + $1.rtt } / Double(selectedSyncs.count)
            let minOffset = selectedSyncs.min(by: { $0.offset < $1.offset })?.offset ?? 0
            let maxOffset = selectedSyncs.max(by: { $0.offset < $1.offset })?.offset ?? 0
            let offsetRange = abs(maxOffset - minOffset)

            print("TimeSync: ===============================================")
            print("TimeSync: SYNCHRONIZATION SUMMARY:")
            print("TimeSync:   - Total successful attempts: \(successfulSyncs.count)/\(syncAttempts)")
            print("TimeSync:   - Selected for averaging: \(selectedSyncs.count)")
            if successfulSyncs.count > selectedSyncs.count {
                let discarded = successfulSyncs.count - selectedSyncs.count
                print("TimeSync:   - Discarded outliers: \(discarded)")
            }
            print("TimeSync:   - Average offset: \(Int(averageOffset * 1000))ms")
            print("TimeSync:   - Average RTT: \(Int(averageRTT * 1000))ms")
            print("TimeSync:   - Offset range: \(Int(offsetRange * 1000))ms (min: \(Int(minOffset * 1000))ms, max: \(Int(maxOffset * 1000))ms)")
            print("TimeSync:   - Quality: \(offsetRange < 0.05 ? "EXCELLENT" : offsetRange < 0.1 ? "GOOD" : offsetRange < 0.2 ? "FAIR" : "POOR")")

            // Update UI properties on main actor
            await MainActor.run {
                self.timeOffset = averageOffset
                self.isSynchronized = true
                self.lastSyncTime = Date()
                self.syncStatus = "Synchronized (offset: \(Int(averageOffset * 1000))ms)"
                print("TimeSync: UI properties updated - isSynchronized: \(self.isSynchronized), status: \(self.syncStatus)")
            }

            print("TimeSync: SYNCHRONIZATION COMPLETE - Final offset: \(Int(averageOffset * 1000))ms")
        } else {
            print("TimeSync: ===============================================")
            print("TimeSync: SYNCHRONIZATION FAILED - All attempts failed or rejected")
            print("TimeSync: Check network connectivity and NTP server accessibility")

            // Update UI properties on main actor
            await MainActor.run {
                self.isSynchronized = false
                self.syncStatus = "Synchronization failed"
            }
            print("TimeSync: UI updated with failure status")
        }

        let syncEndTime = Date().timeIntervalSince1970
        print("TimeSync: Total sync duration: \(Int((syncEndTime - syncStartTime) * 1000))ms")
        print("TimeSync: ===============================================")
    }

    func getSynchronizedTime() -> TimeInterval {
        let localTime = Date().timeIntervalSince1970
        let syncTime = localTime + timeOffset

        if !isSynchronized {
            print("TimeSync: WARNING - returning unsynchronized time: \(localTime)")
            return localTime
        }

        print("TimeSync: Synchronized time: \(syncTime) (local: \(localTime) + offset: \(Int(timeOffset * 1000))ms)")
        return syncTime
    }

    func shouldResync() -> Bool {
        guard let lastSync = lastSyncTime else {
            return true
        }

        let timeSinceSync = Date().timeIntervalSince(lastSync)
        return timeSinceSync > resyncInterval
    }

    func getTimeSinceLastSync() -> TimeInterval? {
        guard let lastSync = lastSyncTime else {
            return nil
        }
        return Date().timeIntervalSince(lastSync)
    }

    func calculateDelayUntil(targetTime: TimeInterval) -> TimeInterval {
        let currentSyncTime = getSynchronizedTime()
        let delay = targetTime - currentSyncTime

        print("TimeSync: Target time: \(targetTime), Current sync time: \(currentSyncTime), Delay: \(Int(delay * 1000))ms")

        return delay
    }

    // Select the 3 most consistent offsets from all successful attempts
    private func selectBestOffsets(from syncs: [(offset: TimeInterval, rtt: TimeInterval)]) -> [(offset: TimeInterval, rtt: TimeInterval)] {
        guard syncs.count > 3 else {
            print("TimeSync: Using all \(syncs.count) offsets (not enough to discard outliers)")
            return syncs
        }

        print("TimeSync: Selecting best 3 from \(syncs.count) offsets...")

        // Try all combinations of 3 offsets and find the set with minimum range
        var bestCombination: [(offset: TimeInterval, rtt: TimeInterval)] = []
        var minimumRange = Double.infinity

        for i in 0..<syncs.count {
            for j in (i+1)..<syncs.count {
                for k in (j+1)..<syncs.count {
                    let combination = [syncs[i], syncs[j], syncs[k]]
                    let offsets = combination.map { $0.offset }
                    let range = offsets.max()! - offsets.min()!

                    if range < minimumRange {
                        minimumRange = range
                        bestCombination = combination
                        print("TimeSync: Found better combination with range \(Int(range * 1000))ms: offsets [\(Int(syncs[i].offset * 1000)), \(Int(syncs[j].offset * 1000)), \(Int(syncs[k].offset * 1000))]ms")
                    }
                }
            }
        }

        // Log which offsets were discarded
        let selectedOffsets = Set(bestCombination.map { Int($0.offset * 1000) })
        let allOffsets = syncs.map { Int($0.offset * 1000) }
        let discardedOffsets = allOffsets.filter { !selectedOffsets.contains($0) }

        if !discardedOffsets.isEmpty {
            print("TimeSync: Discarded outlier offsets: \(discardedOffsets)ms")
        }

        print("TimeSync: Selected best 3 offsets with range \(Int(minimumRange * 1000))ms")
        return bestCombination
    }

    // Debug information
    func getDebugInfo() -> String {
        let syncTime = getSynchronizedTime()
        let systemTime = Date().timeIntervalSince1970
        let offsetMs = Int(timeOffset * 1000)
        let timeSinceSync = getTimeSinceLastSync().map { Int($0) } ?? 0

        return """
        Synchronized: \(isSynchronized)
        Offset: \(offsetMs)ms
        System time: \(systemTime)
        Sync time: \(syncTime)
        Time since last sync: \(timeSinceSync)s
        """
    }
}