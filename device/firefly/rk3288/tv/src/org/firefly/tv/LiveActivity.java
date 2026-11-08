/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.SharedPreferences;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.File;
import java.io.IOException;
import java.util.HashSet;
import java.util.Set;

/** Channel playback with bounded preparation, source failover and directional keys. */
public final class LiveActivity extends TvActivity implements SurfaceHolder.Callback {
    private static final String TAG = "FireflyLive";
    private static final int PREPARE_TIMEOUT_MS = 18_000;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable sourceRefresh = this::refreshProgramme;
    private final Runnable hideBanner = () -> this.banner.setVisibility(View.GONE);
    private final Runnable numberSelection = this::selectNumber;
    private final java.util.concurrent.ExecutorService guideWorker =
            java.util.concurrent.Executors.newSingleThreadExecutor();
    private final java.util.concurrent.ExecutorService playbackWorker =
            java.util.concurrent.Executors.newSingleThreadExecutor();
    private java.util.concurrent.Future<?> pendingPlayback;
    private int playbackGeneration;
    private final Runnable guideTick = new Runnable() {
        @Override
        public void run() {
            updateProgramme();
            handler.postDelayed(this, 60_000);
        }
    };
    private ProgramGuide guide;
    private ChannelCatalog catalog;
    private SharedPreferences preferences;
    private Set<String> favorites;
    private SurfaceView surface;
    private LinearLayout banner;
    private TextView channelText;
    private TextView statusText;
    private TextView programmeText;
    private ChannelPicker channelPicker;
    private android.window.OnBackInvokedCallback liveBackCallback;
    private MediaPlayer player;
    private int channelIndex;
    private int sourceIndex;
    private boolean surfaceReady;
    private boolean stopped;
    private boolean decoderTest;
    private String decoderKind;
    private String kidsVideo;
    private long playbackStarted;
    private String digits = "";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        preferences = getSharedPreferences("live", MODE_PRIVATE);
        favorites = new HashSet<>(preferences.getStringSet("favorites", new HashSet<>()));
        catalog = ChannelCatalog.load(this);
        channelIndex = Math.max(0, Math.min(preferences.getInt("last_channel", 0),
                catalog.channels.size() - 1));
        String requestedChannel = getIntent().getStringExtra("channel_id");
        if (requestedChannel != null) {
            for (int index = 0; index < catalog.channels.size(); index++) {
                if (requestedChannel.equals(catalog.channels.get(index).id)) {
                    channelIndex = index;
                    break;
                }
            }
        }
        decoderTest = getIntent().getBooleanExtra("decoder_test", false);
        decoderKind = "hevc".equals(getIntent().getStringExtra("decoder_codec")) ? "hevc" : "h264";
        String requested = getIntent().getStringExtra("kids_video");
        kidsVideo = "colors".equals(requested) || "counting".equals(requested) ? requested : null;
        createPlayerView();
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            liveBackCallback = this::handleBackAction;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, liveBackCallback);
        }
        guideWorker.execute(() -> {
            ProgramGuide loaded = GuideLoader.load(getApplicationContext(), catalog);
            handler.post(() -> {
                if (!isDestroyed()) {
                    guide = loaded;
                    updateProgramme();
                }
            });
        });
    }

    private void createPlayerView() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(android.graphics.Color.BLACK);
        surface = new SurfaceView(this);
        surface.getHolder().addCallback(this);
        root.addView(surface, new FrameLayout.LayoutParams(-1, -1));
        surface.setOnClickListener(v -> chooseChannel());
        banner = TvUi.column(this);
        banner.setBackground(TvUi.rounded(this, 0xef151820, 15));
        banner.setElevation(TvUi.dp(this, 12));
        banner.setPadding(TvUi.dp(this, 24), TvUi.dp(this, 18), TvUi.dp(this, 24),
                TvUi.dp(this, 16));
        LinearLayout headline = TvUi.row(this);
        LinearLayout titles = TvUi.column(this);
        channelText = TvUi.text(this, "电视直播", 25, TvUi.TEXT);
        channelText.setTypeface(android.graphics.Typeface.create("sans-serif-medium", 0));
        channelText.setSingleLine();
        channelText.setEllipsize(android.text.TextUtils.TruncateAt.END);
        titles.addView(channelText);
        programmeText = TvUi.text(this, "", 14, TvUi.MUTED);
        programmeText.setSingleLine();
        programmeText.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams programmePosition = new LinearLayout.LayoutParams(-1, -2);
        programmePosition.topMargin = TvUi.dp(this, 8);
        titles.addView(programmeText, programmePosition);
        headline.addView(titles, new LinearLayout.LayoutParams(0, -2, 1));
        TextView browse = TvUi.text(this, "选台  ›", 14, TvUi.TEXT);
        browse.setGravity(Gravity.CENTER);
        browse.setBackground(TvUi.rounded(this, 0xff30343d, 9));
        browse.setPadding(TvUi.dp(this, 19), TvUi.dp(this, 12), TvUi.dp(this, 19), TvUi.dp(this, 12));
        browse.setClickable(true);
        browse.setFocusable(false);
        browse.setContentDescription("打开频道选择");
        browse.setOnClickListener(v -> chooseChannel());
        browse.setVisibility(decoderTest || kidsVideo != null ? View.GONE : View.VISIBLE);
        headline.addView(browse);
        banner.addView(headline);
        LinearLayout bottom = TvUi.row(this);
        bottom.setPadding(0, TvUi.dp(this, 13), 0, 0);
        statusText = TvUi.text(this, "正在打开…", 13, 0xffb8c9be);
        statusText.setMaxLines(2);
        bottom.addView(statusText, new LinearLayout.LayoutParams(0, -2, 1));
        TextView help = TvUi.text(this, "↑↓ 换台     确定 选台     返回 退出", 12, TvUi.MUTED);
        help.setPadding(TvUi.dp(this, 14), 0, 0, 0);
        help.setVisibility(decoderTest || kidsVideo != null ? View.GONE : View.VISIBLE);
        bottom.addView(help);
        banner.addView(bottom);
        FrameLayout.LayoutParams position = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        position.leftMargin = position.rightMargin = TvUi.dp(this, 34);
        position.bottomMargin = TvUi.dp(this, 24);
        root.addView(banner, position);
        channelPicker = new ChannelPicker(this, catalog, favorites, new ChannelPicker.Listener() {
            @Override public void onChannelSelected(int originalIndex) {
                channelIndex = originalIndex;
                sourceIndex = 0;
                play();
            }
            @Override public void onFavoriteToggle(int originalIndex) {
                toggleFavorite(originalIndex);
            }
        });
        root.addView(channelPicker, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (new ParentalPrefs(this).enabled() && kidsVideo == null) {
            startActivity(new android.content.Intent(this, KidsActivity.class));
            finish();
            return;
        }
        stopped = false;
        handler.post(guideTick);
        if (surfaceReady) {
            play();
        }
        if (getIntent().getBooleanExtra("show_picker", false)) {
            getIntent().removeExtra("show_picker");
            handler.postDelayed(this::chooseChannel, 250);
        }
    }

    @Override
    protected void onStop() {
        stopped = true;
        channelPicker.dismiss();
        handler.removeCallbacksAndMessages(null);
        releasePlayer();
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        if (android.os.Build.VERSION.SDK_INT >= 33 && liveBackCallback != null) {
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(liveBackCallback);
        }
        guideWorker.shutdownNow();
        playbackWorker.shutdownNow();
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private void updateProgramme() {
        if (decoderTest || kidsVideo != null || catalog.channels.isEmpty()) {
            programmeText.setText("");
            return;
        }
        ChannelCatalog.Channel channel = catalog.channels.get(channelIndex);
        programmeText.setText(guide == null ? "正在读取节目单…" : guide.current(channel.tvgId));
        channelPicker.setGuide(guide);
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder) {
        surfaceReady = true;
        if (!stopped) {
            play();
        }
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
        // SurfaceView handles sizing; the current decoder surface remains valid.
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        surfaceReady = false;
        releasePlayer();
    }

    private void play() {
        releasePlayer();
        if (!surfaceReady || stopped) {
            return;
        }
        if (decoderTest) {
            playTest();
            return;
        }
        if (kidsVideo != null) {
            playKidsVideo();
            return;
        }
        if (catalog.channels.isEmpty()) {
            show("当前没有可用频道目录，请检查系统更新。", false);
            return;
        }
        ChannelCatalog.Channel channel = catalog.channels.get(channelIndex);
        channelPicker.setCurrentChannel(channelIndex);
        sourceIndex = Math.floorMod(sourceIndex, channel.sources.size());
        ChannelCatalog.Source source = channel.sources.get(sourceIndex);
        String star = favorites.contains(channel.id) ? " ★" : "";
        channelText.setText(channel.number + "  " + channel.name + star);
        updateProgramme();
        show("正在连接线路 " + (sourceIndex + 1) + "/" + channel.sources.size()
                + (source.requiresProxy ? " · 需要代理网络" : ""), false);
        preferences.edit().putInt("last_channel", channelIndex).apply();
        openSource(source);
    }

    private void openSource(ChannelCatalog.Source source) {
        if (source.resolverProvider.isEmpty()) {
            openResolvedSource(source, source.url);
            return;
        }
        int generation = playbackGeneration;
        pendingPlayback = playbackWorker.submit(() -> {
            try {
                String url = BroadcasterResolver.resolve(source.resolverProvider,
                        source.resolverChannelId);
                handler.post(() -> {
                    if (generation == playbackGeneration && !stopped) {
                        openResolvedSource(source, url);
                    }
                });
            } catch (IOException | RuntimeException error) {
                Log.w(TAG, "Cannot resolve broadcaster channel", error);
                handler.post(() -> {
                    if (generation == playbackGeneration && !stopped) {
                        failover(null, "频道连接失败");
                    }
                });
            }
        });
    }

    private void openResolvedSource(ChannelCatalog.Source source, String url) {
        // Legacy catalogs may request Kodi. Live TV stays in this activity so
        // channel navigation, programme refresh and Back/Escape remain consistent.
        MediaPlayer next = createPlayer();
        try {
            next.setDataSource(this, Uri.parse(url), source.headers);
            prepare(next);
        } catch (IOException | IllegalArgumentException | IllegalStateException error) {
            Log.w(TAG, "Cannot open channel source", error);
            failover(next, "线路连接失败");
        }
    }

    private void refreshProgramme() {
        releasePlayer();
        int generation = playbackGeneration;
        handler.postDelayed(() -> {
            if (generation == playbackGeneration && !stopped) {
                play();
            }
        }, 1000);
    }

    private MediaPlayer createPlayer() {
        MediaPlayer next = new MediaPlayer();
        player = next;
        next.setDisplay(surface.getHolder());
        next.setScreenOnWhilePlaying(true);
        next.setOnPreparedListener(ready -> {
            if (ready == player && !stopped) {
                ready.start();
                playbackStarted = SystemClock.elapsedRealtime();
                handler.removeCallbacksAndMessages(next);
                show(decoderTest ? "正在播放内置检查样片" : "正在播放", true);
            }
        });
        next.setOnErrorListener((failed, what, extra) -> {
            failover(failed, "播放失败（" + what + "/" + extra + "）");
            return true;
        });
        next.setOnInfoListener((active, what, extra) -> {
            if (active == player && what == MediaPlayer.MEDIA_INFO_BUFFERING_START) {
                show("正在缓冲…", false);
            } else if (active == player && what == MediaPlayer.MEDIA_INFO_BUFFERING_END) {
                show("正在播放", true);
            }
            return false;
        });
        next.setOnCompletionListener(completed -> {
            if (completed == player) {
                onPlaybackCompleted();
            }
        });
        return next;
    }

    private void onPlaybackCompleted() {
        if (kidsVideo != null) {
            finish();
        } else if (decoderTest) {
            long seconds = (SystemClock.elapsedRealtime() - playbackStarted) / 1000;
            show("样片播放完成，耗时 " + seconds + " 秒。可返回运行指定解码器的硬解测试。", false);
        }
    }

    private void prepare(MediaPlayer next) {
        next.prepareAsync();
        handler.postAtTime(() -> {
            if (next == player && !stopped) {
                failover(next, "连接超时");
            }
        }, next, SystemClock.uptimeMillis() + PREPARE_TIMEOUT_MS);
    }

    private void playTest() {
        File sample = new File("/product/etc/firefly-tv/" + decoderKind + "-1080p.mp4");
        channelText.setText(("hevc".equals(decoderKind) ? "H.265" : "H.264") + " 1080p 样片预览");
        if (!sample.isFile()) {
            show("未找到内置样片。", false);
            return;
        }
        MediaPlayer next = createPlayer();
        try {
            next.setDataSource(sample.getAbsolutePath());
            prepare(next);
        } catch (IOException | IllegalStateException error) {
            Log.w(TAG, "Cannot open decoder sample", error);
            show("样片打开失败。", false);
            releasePlayer();
        }
    }

    private void playKidsVideo() {
        channelText.setText("colors".equals(kidsVideo) ? "认识颜色" : "数一数：1–5");
        programmeText.setText("原创离线益智短片 · 无广告");
        File sample = new File("/product/etc/firefly-tv/kids/" + kidsVideo + ".mp4");
        MediaPlayer next = createPlayer();
        try {
            next.setDataSource(sample.getAbsolutePath());
            prepare(next);
        } catch (IOException | IllegalStateException error) {
            Log.w(TAG, "Cannot open child video", error);
            show("益智短片打开失败", false);
            releasePlayer();
        }
    }

    private void failover(MediaPlayer failed, String reason) {
        if (failed != player || stopped) {
            return;
        }
        if (refreshExpiringSource()) {
            return;
        }
        releasePlayer();
        if (decoderTest || kidsVideo != null) {
            show(reason + "，请保存系统解码日志。", false);
            return;
        }
        ChannelCatalog.Channel channel = catalog.channels.get(channelIndex);
        if (sourceIndex + 1 < channel.sources.size()) {
            sourceIndex++;
            show(reason + "，正在切换备用线路…", false);
            handler.postDelayed(this::play, 400);
        } else {
            show(reason + "。可按左右切换线路，或按确定键选择其他频道。", false);
        }
    }

    private boolean refreshExpiringSource() {
        if (decoderTest || kidsVideo != null || catalog.channels.isEmpty()) {
            return false;
        }
        ChannelCatalog.Source source = catalog.channels.get(channelIndex).sources.get(sourceIndex);
        if (source.resolverProvider.isEmpty() || playbackStarted == 0
                || SystemClock.elapsedRealtime() - playbackStarted < 60_000) {
            return false;
        }
        playbackStarted = 0;
        releasePlayer();
        show("正在重新连接频道…", false);
        handler.postDelayed(this::play, 400);
        return true;
    }

    private void releasePlayer() {
        handler.removeCallbacks(sourceRefresh);
        playbackGeneration++;
        playbackStarted = 0;
        if (pendingPlayback != null) {
            pendingPlayback.cancel(true);
            pendingPlayback = null;
        }
        MediaPlayer old = player;
        player = null;
        if (old != null) {
            handler.removeCallbacksAndMessages(old);
            old.reset();
            old.release();
        }
    }

    private void show(String value, boolean timed) {
        // Async playback updates must not cover the channel browser.
        banner.setVisibility(channelPicker != null && channelPicker.isShowing()
                ? View.GONE : View.VISIBLE);
        statusText.setText(value);
        handler.removeCallbacks(hideBanner);
        if (timed) {
            handler.postDelayed(hideBanner, 6000);
        }
    }

    private void changeChannel(int delta) {
        if (catalog.channels.isEmpty() || decoderTest || kidsVideo != null) {
            return;
        }
        channelIndex = Math.floorMod(channelIndex + delta, catalog.channels.size());
        sourceIndex = 0;
        play();
    }

    private void changeSource(int delta) {
        if (catalog.channels.isEmpty() || decoderTest || kidsVideo != null) {
            return;
        }
        int count = catalog.channels.get(channelIndex).sources.size();
        sourceIndex = Math.floorMod(sourceIndex + delta, count);
        play();
    }

    private void chooseChannel() {
        if (catalog.channels.isEmpty() || decoderTest || kidsVideo != null) {
            return;
        }
        banner.setVisibility(View.GONE);
        channelPicker.show(channelIndex, guide);
    }

    private void toggleFavorite() {
        if (catalog.channels.isEmpty() || decoderTest || kidsVideo != null) {
            return;
        }
        toggleFavorite(channelIndex);
    }

    private void toggleFavorite(int index) {
        if (index < 0 || index >= catalog.channels.size()) return;
        String id = catalog.channels.get(index).id;
        boolean removed = favorites.remove(id);
        if (!removed) {
            favorites.add(id);
        }
        preferences.edit().putStringSet("favorites", new HashSet<>(favorites)).apply();
        channelPicker.refreshFavorites();
        show(removed ? "已取消收藏" : "已加入收藏", true);
    }

    @Override
    protected void handleBackAction() {
        if (channelPicker != null && channelPicker.isShowing()) channelPicker.dismiss();
        else super.handleBackAction();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (channelPicker != null && channelPicker.isShowing()) {
            int key = event.getKeyCode();
            if (key >= KeyEvent.KEYCODE_0 && key <= KeyEvent.KEYCODE_9) {
                channelPicker.dismiss();
            } else if (channelPicker.handleKeyEvent(event)) {
                return true;
            }
        }
        return super.dispatchKeyEvent(event);
    }

    private boolean digit(int keyCode) {
        if (keyCode < KeyEvent.KEYCODE_0 || keyCode > KeyEvent.KEYCODE_9 || decoderTest
                || kidsVideo != null) {
            return false;
        }
        if (digits.length() >= 3) {
            digits = "";
        }
        digits += keyCode - KeyEvent.KEYCODE_0;
        show("选台：" + digits, false);
        handler.removeCallbacks(numberSelection);
        handler.postDelayed(numberSelection, 1300);
        return true;
    }

    private void selectNumber() {
        if (digits.isEmpty()) {
            return;
        }
        int requested = Integer.parseInt(digits);
        digits = "";
        for (int index = 0; index < catalog.channels.size(); index++) {
            if (catalog.channels.get(index).number == requested) {
                channelIndex = index;
                sourceIndex = 0;
                play();
                return;
            }
        }
        show("没有这个频道编号", true);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (digit(keyCode)) {
            return true;
        }
        switch (keyCode) {
            case KeyEvent.KEYCODE_DPAD_UP:
            case KeyEvent.KEYCODE_CHANNEL_UP:
                changeChannel(1);
                return true;
            case KeyEvent.KEYCODE_DPAD_DOWN:
            case KeyEvent.KEYCODE_CHANNEL_DOWN:
                changeChannel(-1);
                return true;
            case KeyEvent.KEYCODE_DPAD_LEFT:
                changeSource(-1);
                return true;
            case KeyEvent.KEYCODE_DPAD_RIGHT:
                changeSource(1);
                return true;
            case KeyEvent.KEYCODE_DPAD_CENTER:
            case KeyEvent.KEYCODE_ENTER:
                if (event.getRepeatCount() > 0) return true;
                chooseChannel();
                return true;
            case KeyEvent.KEYCODE_MENU:
                toggleFavorite();
                return true;
            default:
                return super.onKeyDown(keyCode, event);
        }
    }
}
