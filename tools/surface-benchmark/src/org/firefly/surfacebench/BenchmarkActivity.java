// SPDX-License-Identifier: Apache-2.0
package org.firefly.surfacebench;

import android.app.Activity;
import android.content.res.AssetFileDescriptor;
import android.graphics.Color;
import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.TextView;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;

/** Local AVC -> real SurfaceView; no AudioTrack, network, or software decoder. */
public final class BenchmarkActivity extends Activity implements SurfaceHolder.Callback {
    private static final String TAG = "FireflySurfaceBench";
    private static final String DECODER = "c2.firefly.h264.decoder";
    private HandlerThread thread;
    private Handler handler;
    private MediaCodec codec;
    private MediaExtractor extractor;
    private TextView text;
    private volatile boolean finished;
    private boolean started, inputEos, finishScheduled;
    private boolean paced, dropLate;
    private int fps, inputFrames, decodedFrames, submittedFrames, explicitDrops;
    private int steadyDecoded, steadySubmitted, steadyDropped, renderedFrames, steadyRendered;
    private int decodedLate, renderedLate;
    private long firstPtsUs = Long.MIN_VALUE, epochNs, warmupUs, durationUs, frameNs;
    private long firstSteadyOutputNs, lastSteadyOutputNs, firstSteadyRenderNs, lastSteadyRenderNs;
    private long firstOutputNs, lastOutputNs, startedNs;
    private String sample, error = "", actualDecoder = "", stage = "created";
    private int sourceProfile = -1, sourceLevel = -1;
    private final ArrayList<Long> outputLatenessUs = new ArrayList<>();
    private final ArrayList<Long> renderLatenessUs = new ArrayList<>();

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        fps = getIntent().getIntExtra("fps", 60);
        if (fps != 30 && fps != 60) fps = 60;
        sample = "h264-1080p" + fps + ".mp4";
        paced = getIntent().getBooleanExtra("paced", true);
        dropLate = getIntent().getBooleanExtra("drop_late", false);
        warmupUs = Math.max(0, getIntent().getIntExtra("warmup_ms", 2000)) * 1000L;
        FrameLayout root = new FrameLayout(this);
        SurfaceView video = new SurfaceView(this);
        video.getHolder().addCallback(this);
        video.getHolder().setFixedSize(1920, 1080);
        root.addView(video, new FrameLayout.LayoutParams(-1, -1));
        text = new TextView(this);
        text.setTextColor(Color.WHITE); text.setBackgroundColor(0xB0000000);
        text.setTextSize(18); text.setPadding(18, 10, 18, 10);
        text.setText("H.264 1080p" + fps + " · Surface benchmark\nStarting local sample…");
        root.addView(text, new FrameLayout.LayoutParams(-1, -2));
        setContentView(root);
        thread = new HandlerThread("SurfaceBenchCodec"); thread.start();
        handler = new Handler(thread.getLooper());
    }

    @Override public void surfaceCreated(SurfaceHolder holder) {
        if (started) return;
        started = true;
        final Surface surface = holder.getSurface();
        handler.post(() -> startPlayback(surface));
    }
    @Override public void surfaceChanged(SurfaceHolder h, int f, int w, int ht) {}
    @Override public void surfaceDestroyed(SurfaceHolder h) {
        if (handler != null && !finished) handler.post(() -> finishRun("surface_destroyed"));
    }

    private void startPlayback(Surface surface) {
        try {
            startedNs = System.nanoTime();
            stage = "extract";
            extractor = new MediaExtractor();
            try (AssetFileDescriptor asset = getAssets().openFd(sample)) {
                extractor.setDataSource(asset.getFileDescriptor(), asset.getStartOffset(), asset.getLength());
            }
            MediaFormat format = null;
            for (int i = 0; i < extractor.getTrackCount(); i++) {
                MediaFormat f = extractor.getTrackFormat(i);
                if ("video/avc".equals(f.getString(MediaFormat.KEY_MIME))) {
                    format = f; extractor.selectTrack(i); break;
                }
            }
            if (format == null) throw new IllegalStateException("No AVC track");
            durationUs = format.getLong(MediaFormat.KEY_DURATION);
            frameNs = 1_000_000_000L / fps;
            sourceProfile = format.containsKey(MediaFormat.KEY_PROFILE) ? format.getInteger(MediaFormat.KEY_PROFILE) : -1;
            sourceLevel = format.containsKey(MediaFormat.KEY_LEVEL) ? format.getInteger(MediaFormat.KEY_LEVEL) : -1;
            Log.i(TAG, "SOURCE_FORMAT " + format);
            // Match normal players: let the actual SPS describe profile/level.
            // Explicit level 4.2 config is rejected by this firmware's advertised
            // level 4.1 limit before data is submitted. We do not rewrite the SPS.
            MediaFormat decoderFormat = MediaFormat.createVideoFormat("video/avc",
                format.getInteger(MediaFormat.KEY_WIDTH), format.getInteger(MediaFormat.KEY_HEIGHT));
            decoderFormat.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
            for (int i = 0; format.containsKey("csd-" + i); i++)
                decoderFormat.setByteBuffer("csd-" + i, format.getByteBuffer("csd-" + i).duplicate());
            if (format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE))
                decoderFormat.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE));
            Log.i(TAG, "DECODER_CONFIG " + decoderFormat);
            stage = "create_decoder";
            codec = MediaCodec.createByCodecName(DECODER);
            actualDecoder = codec.getName();
            if (!DECODER.equals(actualDecoder)) throw new IllegalStateException("Decoder substitution");
            codec.setCallback(new MediaCodec.Callback() {
                @Override public void onInputBufferAvailable(MediaCodec c, int index) {
                    if (finished || inputEos) return;
                    try {
                        ByteBuffer b = c.getInputBuffer(index);
                        b.clear();
                        int count = extractor.readSampleData(b, 0);
                        if (count < 0) {
                            inputEos = true;
                            c.queueInputBuffer(index, 0, 0, durationUs, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                        } else {
                            c.queueInputBuffer(index, 0, count, extractor.getSampleTime(), 0);
                            inputFrames++; extractor.advance();
                        }
                    } catch (Throwable ex) { Log.e(TAG, "Failure at " + stage, ex); finishRun(ex.toString()); }
                }
                @Override public void onOutputBufferAvailable(MediaCodec c, int index, MediaCodec.BufferInfo info) {
                    if (finished) return;
                    try {
                        final boolean eos = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                        final boolean image = info.size > 0 && (info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0;
                        if (image) {
                            final long now = System.nanoTime();
                            if (firstPtsUs == Long.MIN_VALUE) {
                                firstPtsUs = info.presentationTimeUs;
                                epochNs = now + (paced ? 250_000_000L : 0);
                                firstOutputNs = now;
                            }
                            lastOutputNs = now;
                            final long relativeUs = info.presentationTimeUs - firstPtsUs;
                            final long targetNs = epochNs + relativeUs * 1000L;
                            final long lateNs = now - targetNs;
                            final boolean steady = relativeUs >= warmupUs;
                            decodedFrames++;
                            if (steady) {
                                steadyDecoded++;
                                if (firstSteadyOutputNs == 0) firstSteadyOutputNs = now;
                                lastSteadyOutputNs = now;
                                outputLatenessUs.add(lateNs / 1000L);
                                if (lateNs > frameNs) decodedLate++;
                            }
                            if (paced && dropLate && lateNs > Math.max(frameNs, 50_000_000L)) {
                                c.releaseOutputBuffer(index, false); explicitDrops++;
                                if (steady) steadyDropped++;
                            } else {
                                if (paced) c.releaseOutputBuffer(index, targetNs);
                                else c.releaseOutputBuffer(index, true);
                                submittedFrames++;
                                if (steady) steadySubmitted++;
                            }
                        } else c.releaseOutputBuffer(index, false);
                        if (eos && !finishScheduled) {
                            finishScheduled = true;
                            long finishNs = paced ? Math.max(System.nanoTime(), epochNs + durationUs * 1000L) : System.nanoTime();
                            handler.postDelayed(() -> finishRun(""), Math.max(1500, (finishNs - System.nanoTime()) / 1_000_000L + 1500));
                        }
                    } catch (Throwable ex) { Log.e(TAG, "Failure at " + stage, ex); finishRun(ex.toString()); }
                }
                @Override public void onError(MediaCodec c, MediaCodec.CodecException e) { finishRun(e.getDiagnosticInfo()); }
                @Override public void onOutputFormatChanged(MediaCodec c, MediaFormat f) { Log.i(TAG, "OUTPUT_FORMAT " + f); }
            }, handler);
            codec.setOnFrameRenderedListener((c, ptsUs, nanoTime) -> {
                if (finished || firstPtsUs == Long.MIN_VALUE || ptsUs == Long.MAX_VALUE) return;
                renderedFrames++;
                long relativeUs = ptsUs - firstPtsUs;
                if (relativeUs >= warmupUs) {
                    steadyRendered++;
                    if (firstSteadyRenderNs == 0) firstSteadyRenderNs = nanoTime;
                    lastSteadyRenderNs = nanoTime;
                    long lateNs = nanoTime - (epochNs + relativeUs * 1000L);
                    renderLatenessUs.add(lateNs / 1000L);
                    if (lateNs > frameNs) renderedLate++;
                }
            }, handler);
            stage = "configure";
            codec.configure(decoderFormat, surface, null, 0);
            stage = "start";
            codec.start();
            stage = "playing";
            Log.i(TAG, "START " + sample + " paced=" + paced + " dropLate=" + dropLate);
            runOnUiThread(() -> text.setVisibility(View.GONE));
            handler.postDelayed(() -> { if (!finished) finishRun("deadline_60_seconds"); }, 60000);
        } catch (Throwable ex) { Log.e(TAG, "Failure at " + stage, ex); finishRun(ex.toString()); }
    }

    private static double rate(int count, long first, long last) {
        return count > 1 && last > first ? (count - 1) * 1_000_000_000.0 / (last - first) : 0;
    }
    private static long percentile(ArrayList<Long> values, double p) {
        if (values.isEmpty()) return 0;
        ArrayList<Long> sorted = new ArrayList<>(values); Collections.sort(sorted);
        return sorted.get(Math.min(sorted.size() - 1, (int)Math.ceil(p * sorted.size()) - 1));
    }

    private void finishRun(String reason) {
        if (finished) return;
        finished = true; error = reason;
        try {
            JSONObject r = new JSONObject()
                .put("sample", sample).put("decoder", actualDecoder).put("paced", paced).put("dropLatePolicy", dropLate)
                .put("sourceFps", fps).put("sourceProfile", sourceProfile).put("sourceLevel", sourceLevel)
                .put("optionalProfileLevelConfigOmitted", true).put("durationUs", durationUs).put("warmupUs", warmupUs)
                .put("inputFrames", inputFrames).put("decodedFrames", decodedFrames).put("submittedFrames", submittedFrames)
                .put("explicitDroppedFrames", explicitDrops).put("renderedCallbackFrames", renderedFrames)
                .put("steadyDecoded", steadyDecoded).put("steadySubmitted", steadySubmitted).put("steadyExplicitDrops", steadyDropped)
                .put("steadyRenderedCallbacks", steadyRendered).put("steadyOutputLateByMoreThanOneFrame", decodedLate)
                .put("steadyRenderLateByMoreThanOneFrame", renderedLate)
                .put("steadyOutputFps", rate(steadyDecoded, firstSteadyOutputNs, lastSteadyOutputNs))
                .put("steadyRenderedCallbackFps", rate(steadyRendered, firstSteadyRenderNs, lastSteadyRenderNs))
                .put("outputLatenessP50Us", percentile(outputLatenessUs, .5)).put("outputLatenessP95Us", percentile(outputLatenessUs, .95))
                .put("renderLatenessP50Us", percentile(renderLatenessUs, .5)).put("renderLatenessP95Us", percentile(renderLatenessUs, .95))
                .put("decoderOutputElapsedMs", (lastOutputNs - firstOutputNs) / 1_000_000L)
                .put("runElapsedMs", (System.nanoTime() - startedNs) / 1_000_000L)
                .put("audioUsed", false).put("networkUsed", false).put("surfaceViewUsed", true)
                .put("error", error).put("stage", stage).put("completedWithoutError", error.isEmpty());
            String json = r.toString(2);
            String name = "surface-" + fps + (paced ? "-paced" : "-throughput") + (dropLate ? "-drop" : "-nodrop") + ".json";
            try (FileOutputStream out = new FileOutputStream(new File(getFilesDir(), name))) { out.write(json.getBytes(StandardCharsets.UTF_8)); }
            Log.i(TAG, "FIREFLY_SURFACE_RESULT " + r.toString());
            runOnUiThread(() -> { text.setText(json); text.setVisibility(View.VISIBLE); });
        } catch (Throwable ex) { Log.e(TAG, "Report failure", ex); }
        if (codec != null) {
            try { codec.stop(); } catch (Exception ignored) {}
            try { codec.release(); } catch (Exception ignored) {}
            codec = null;
        }
        if (extractor != null) { extractor.release(); extractor = null; }
    }

    @Override protected void onDestroy() {
        if (handler != null) handler.post(() -> { finishRun("activity_destroyed"); thread.quitSafely(); });
        super.onDestroy();
    }
}
