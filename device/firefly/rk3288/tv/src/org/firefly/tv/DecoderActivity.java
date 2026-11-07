/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.content.Intent;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/** Enumerates advertised codecs separately from a real sample playback test. */
public final class DecoderActivity extends TvActivity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private TextView progress;
    private boolean checking;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout page = TvUi.page(this, "硬件解码检查", "先确认解码器，再播放样片检查实际路径");
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = TvUi.column(this);
        MediaCodecInfo[] codecs = new MediaCodecList(MediaCodecList.REGULAR_CODECS)
                .getCodecInfos();
        int hardware = 0;
        for (MediaCodecInfo codec : codecs) {
            if (codec.isEncoder() || !supportsVideo(codec)) {
                continue;
            }
            if (codec.isHardwareAccelerated()) {
                hardware++;
            }
            addCodec(content, codec);
        }
        String summary = hardware == 0 ? "未找到系统声明的硬件视频解码器。"
                : "发现 " + hardware + " 个硬件视频解码器。";
        TextView result = TvUi.text(this, summary, 20, TvUi.ACCENT);
        result.setPadding(0, TvUi.dp(this, 18), 0, TvUi.dp(this, 14));
        content.addView(result);
        content.addView(TvUi.text(this, "硬解测试会指定 Firefly 解码器，完整解码本地样片并统计输出帧数。"
                + "可分别检查 H.264 和 H.265；样片预览用于检查画面与声音。", 16, TvUi.MUTED));
        progress = TvUi.text(this, "请选择一种格式开始检查。", 17, TvUi.ACCENT);
        progress.setTextIsSelectable(true);
        content.addView(progress);
        addCheck(content, "H.264 硬件解码测试", "h264");
        addCheck(content, "H.265 硬件解码测试", "hevc");
        TvUi.addButton(content, TvUi.button(this, "播放 H.264 检查样片",
                view -> startActivity(new Intent(this, LiveActivity.class)
                        .putExtra("decoder_test", true))));
        TvUi.addButton(content, TvUi.button(this, "播放 H.265 检查样片",
                view -> startActivity(new Intent(this, LiveActivity.class)
                        .putExtra("decoder_test", true).putExtra("decoder_codec", "hevc"))));
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    }

    private void addCheck(LinearLayout parent, String label, String kind) {
        Button button = TvUi.button(this, label, view -> check(kind));
        TvUi.addButton(parent, button);
    }

    private void check(String kind) {
        if (checking) {
            return;
        }
        checking = true;
        progress.setText("正在检查 " + ("hevc".equals(kind) ? "H.265" : "H.264") + " 硬解…");
        worker.execute(() -> {
            String message;
            File record = new File(getFilesDir(), "decode-check-" + kind + ".json");
            try {
                Files.deleteIfExists(record.toPath());
                JSONObject result = HardwareDecodeCheck.run(kind);
                result.put("observedEpochMs", System.currentTimeMillis());
                Files.writeString(record.toPath(), result.toString(2), StandardCharsets.UTF_8);
                message = result.getString("component") + "\n已输出 " + result.getInt("frames")
                        + " 帧，耗时 " + result.getLong("elapsedMs") + " 毫秒。";
                Log.i("FireflyDecodeCheck", result.toString());
            } catch (IOException | JSONException | RuntimeException error) {
                Log.e("FireflyDecodeCheck", "Hardware check failed", error);
                recordFailure(record, kind, error.toString());
                message = "硬解检查失败：" + error.getClass().getSimpleName() + " · "
                        + error.getMessage();
            }
            String completed = message;
            handler.post(() -> finishCheck(completed));
        });
    }

    private static void recordFailure(File record, String kind, String error) {
        try {
            JSONObject result = new JSONObject().put("completed", false).put("format", kind)
                    .put("observedEpochMs", System.currentTimeMillis())
                    .put("error", error);
            Files.writeString(record.toPath(), result.toString(2), StandardCharsets.UTF_8);
        } catch (IOException | JSONException failure) {
            Log.e("FireflyDecodeCheck", "Cannot save failed check", failure);
        }
    }

    private void finishCheck(String message) {
        checking = false;
        if (!isDestroyed() && !isFinishing()) {
            progress.setText(message);
        }
    }

    @Override
    protected void onDestroy() {
        worker.shutdownNow();
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private static boolean supportsVideo(MediaCodecInfo codec) {
        for (String type : codec.getSupportedTypes()) {
            if (type.startsWith("video/")) {
                return true;
            }
        }
        return false;
    }

    private void addCodec(LinearLayout parent, MediaCodecInfo codec) {
        String kind = codec.isHardwareAccelerated() ? "硬件" : "软件";
        TextView view = TvUi.text(this, String.format(Locale.ROOT, "%s\n%s · %s",
                codec.getName(), kind, String.join(", ", codec.getSupportedTypes())), 17,
                TvUi.TEXT);
        view.setTextIsSelectable(true);
        view.setPadding(0, TvUi.dp(this, 8), 0, TvUi.dp(this, 8));
        parent.addView(view);
    }
}
