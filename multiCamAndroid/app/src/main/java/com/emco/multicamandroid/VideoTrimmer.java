package com.emco.multicamandroid;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMetadataRetriever;
import android.media.MediaMuxer;
import android.util.Log;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.HashMap;

public class VideoTrimmer {

    private static final String TAG = "VideoTrimmer";
    private static final int DEFAULT_BUFFER_SIZE = 1024 * 1024; // 1MB

    public interface VideoTrimCallback {
        void onTrimStarted();
        void onTrimProgress(int progressPercentage);
        void onTrimCompleted(String outputPath, long actualDurationMs);
        void onTrimError(String error);
    }

    public static void trimVideo(String inputPath, String outputPath,
                               long startTimeUs, long durationUs,
                               VideoTrimCallback callback) {

        Log.d(TAG, String.format("[TRIM] Starting video trim: input=%s, output=%s", inputPath, outputPath));
        Log.d(TAG, String.format("[TRIM] Trim parameters: startTime=%dus, duration=%dus", startTimeUs, durationUs));

        callback.onTrimStarted();

        MediaExtractor extractor = new MediaExtractor();
        MediaMuxer muxer = null;

        try {
            // Initialize extractor
            extractor.setDataSource(inputPath);
            int trackCount = extractor.getTrackCount();
            Log.d(TAG, String.format("[TRIM] Input file has %d tracks", trackCount));

            // Get video duration for validation
            long videoDurationUs = getVideoDurationUs(inputPath);
            Log.d(TAG, String.format("[TRIM] Input video duration: %dus (%dms)", videoDurationUs, videoDurationUs / 1000));

            // Validate trim parameters
            if (startTimeUs < 0) {
                startTimeUs = 0;
                Log.w(TAG, "[TRIM] Start time was negative, setting to 0");
            }

            if (startTimeUs + durationUs > videoDurationUs) {
                durationUs = videoDurationUs - startTimeUs;
                Log.w(TAG, String.format("[TRIM] Duration adjusted to fit video length: %dus", durationUs));
            }

            long endTimeUs = startTimeUs + durationUs;
            Log.d(TAG, String.format("[TRIM] Final trim range: %dus to %dus", startTimeUs, endTimeUs));

            // Initialize muxer
            muxer = new MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            HashMap<Integer, Integer> trackIndexMap = new HashMap<>();

            // Add tracks to muxer
            for (int i = 0; i < trackCount; i++) {
                MediaFormat format = extractor.getTrackFormat(i);
                String mimeType = format.getString(MediaFormat.KEY_MIME);
                Log.d(TAG, String.format("[TRIM] Track %d: %s", i, mimeType));

                if (mimeType.startsWith("video/") || mimeType.startsWith("audio/")) {
                    int muxerTrackIndex = muxer.addTrack(format);
                    trackIndexMap.put(i, muxerTrackIndex);
                    Log.d(TAG, String.format("[TRIM] Added track %d to muxer as index %d", i, muxerTrackIndex));
                }
            }

            muxer.start();
            Log.d(TAG, "[TRIM] Muxer started successfully");

            // Process each track
            ByteBuffer buffer = ByteBuffer.allocate(DEFAULT_BUFFER_SIZE);
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();

            for (int trackIndex = 0; trackIndex < trackCount; trackIndex++) {
                if (!trackIndexMap.containsKey(trackIndex)) {
                    Log.d(TAG, String.format("[TRIM] Skipping track %d (not video/audio)", trackIndex));
                    continue;
                }

                MediaFormat format = extractor.getTrackFormat(trackIndex);
                String mimeType = format.getString(MediaFormat.KEY_MIME);
                Log.d(TAG, String.format("[TRIM] Processing track %d (%s)", trackIndex, mimeType));

                extractor.selectTrack(trackIndex);
                extractor.seekTo(startTimeUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC);

                long currentPositionUs = extractor.getSampleTime();
                Log.d(TAG, String.format("[TRIM] Seek result: requested %dus, got %dus", startTimeUs, currentPositionUs));

                int muxerTrackIndex = trackIndexMap.get(trackIndex);
                long samplesProcessed = 0;
                long lastProgressTime = System.currentTimeMillis();

                while (currentPositionUs != -1 && currentPositionUs <= endTimeUs) {
                    buffer.clear();
                    int sampleSize = extractor.readSampleData(buffer, 0);

                    if (sampleSize < 0) {
                        Log.d(TAG, String.format("[TRIM] End of track %d reached", trackIndex));
                        break;
                    }

                    // Skip samples before start time
                    if (currentPositionUs < startTimeUs) {
                        extractor.advance();
                        currentPositionUs = extractor.getSampleTime();
                        continue;
                    }

                    // Adjust timestamp relative to trim start
                    long adjustedTimeUs = currentPositionUs - startTimeUs;

                    // Write sample to muxer
                    bufferInfo.offset = 0;
                    bufferInfo.size = sampleSize;
                    bufferInfo.presentationTimeUs = adjustedTimeUs;

                    // Convert MediaExtractor flags to MediaCodec flags
                    int extractorFlags = extractor.getSampleFlags();
                    int codecFlags = 0;
                    if ((extractorFlags & MediaExtractor.SAMPLE_FLAG_SYNC) != 0) {
                        codecFlags |= MediaCodec.BUFFER_FLAG_KEY_FRAME;
                    }
                    if ((extractorFlags & MediaExtractor.SAMPLE_FLAG_PARTIAL_FRAME) != 0) {
                        codecFlags |= MediaCodec.BUFFER_FLAG_PARTIAL_FRAME;
                    }
                    bufferInfo.flags = codecFlags;

                    muxer.writeSampleData(muxerTrackIndex, buffer, bufferInfo);

                    samplesProcessed++;

                    // Report progress periodically
                    long now = System.currentTimeMillis();
                    if (now - lastProgressTime > 500) { // Every 500ms
                        int progress = (int) ((currentPositionUs - startTimeUs) * 100 / durationUs);
                        progress = Math.min(progress, 100);
                        callback.onTrimProgress(progress);
                        lastProgressTime = now;

                        Log.v(TAG, String.format("[TRIM] Track %d progress: %d%% (%d samples)",
                            trackIndex, progress, samplesProcessed));
                    }

                    extractor.advance();
                    currentPositionUs = extractor.getSampleTime();
                }

                Log.d(TAG, String.format("[TRIM] Track %d completed: %d samples processed", trackIndex, samplesProcessed));
                extractor.unselectTrack(trackIndex);
            }

            Log.i(TAG, "[TRIM] Video trimming completed successfully");
            callback.onTrimCompleted(outputPath, durationUs / 1000);

        } catch (Exception e) {
            Log.e(TAG, "[TRIM] Error during video trimming", e);
            callback.onTrimError("Video trimming failed: " + e.getMessage());
        } finally {
            try {
                if (muxer != null) {
                    muxer.stop();
                    muxer.release();
                }
                extractor.release();
                Log.d(TAG, "[TRIM] Resources released");
            } catch (Exception e) {
                Log.e(TAG, "[TRIM] Error releasing resources", e);
            }
        }
    }

    private static long getVideoDurationUs(String videoPath) {
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try {
            retriever.setDataSource(videoPath);
            String durationStr = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            if (durationStr != null) {
                long durationMs = Long.parseLong(durationStr);
                return durationMs * 1000; // Convert to microseconds
            }
        } catch (Exception e) {
            Log.e(TAG, "[TRIM] Error getting video duration", e);
        } finally {
            try {
                retriever.release();
            } catch (Exception e) {
                Log.e(TAG, "[TRIM] Error releasing metadata retriever", e);
            }
        }
        return 0;
    }

    // Utility method to get video info for debugging
    public static void logVideoInfo(String videoPath) {
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try {
            retriever.setDataSource(videoPath);

            String duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            String width = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH);
            String height = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT);
            String bitrate = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE);
            String framerate = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_CAPTURE_FRAMERATE);

            Log.d(TAG, String.format("[INFO] Video: %s", videoPath));
            Log.d(TAG, String.format("[INFO] Duration: %s ms", duration));
            Log.d(TAG, String.format("[INFO] Resolution: %sx%s", width, height));
            Log.d(TAG, String.format("[INFO] Bitrate: %s", bitrate));
            Log.d(TAG, String.format("[INFO] Framerate: %s", framerate));

        } catch (Exception e) {
            Log.e(TAG, "[INFO] Error getting video info", e);
        } finally {
            try {
                retriever.release();
            } catch (Exception e) {
                Log.e(TAG, "[INFO] Error releasing metadata retriever", e);
            }
        }
    }
}