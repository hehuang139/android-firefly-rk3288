/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.Set;

/** Child home only lists explicitly parent-approved video providers. */
public final class KidsActivity extends TvActivity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView remaining;
    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            ParentalPrefs prefs = new ParentalPrefs(KidsActivity.this);
            remaining.setText(prefs.enabled() ? "本段还可观看约 "
                    + ((prefs.remaining() + 59_999) / 60_000) + " 分钟" : "家长模式尚未启用");
            handler.postDelayed(this, 1000);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        WatchTimeTracker.start(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        build();
        handler.post(refresh);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(refresh);
        super.onPause();
    }

    private void build() {
        LinearLayout page = TvUi.page(this, "儿童益智", "3–5 岁 · 认颜色 · 认形状 · 数一数");
        remaining = TvUi.text(this, "", 24, TvUi.ACCENT);
        page.addView(remaining);
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = TvUi.column(this);
        TvUi.addButton(content, TvUi.button(this, "玩一会儿益智小游戏", view ->
                startActivity(new Intent(this, PuzzleActivity.class).putExtra("practice", true))));
        if (new java.io.File("/product/etc/firefly-tv/kids/colors.mp4").isFile())
            TvUi.addButton(content, TvUi.button(this, "认识颜色 · 离线益智短片", view -> video("colors")));
        if (new java.io.File("/product/etc/firefly-tv/kids/counting.mp4").isFile())
            TvUi.addButton(content, TvUi.button(this, "数一数 1–5 · 离线益智短片", view -> video("counting")));
        addProviders(content);
        TvUi.addButton(content, TvUi.button(this, "家长设置", view ->
                startActivity(new Intent(this, ParentalActivity.class))));
        TvUi.addButton(content, TvUi.button(this, "返回电视主页", view -> leave()));
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        content.getChildAt(0).requestFocus();
    }

    private void addProviders(LinearLayout content) {
        ParentalPrefs prefs = new ParentalPrefs(this);
        Set<String> allowed = prefs.allowedApps();
        int count = 0;
        for (int index = 0; index < KidsContent.LABELS.length; index++) {
            String name = KidsContent.installed(this, index);
            if (allowed.contains(name)) {
                count++;
                TvUi.addButton(content, TvUi.button(this, KidsContent.LABELS[index], view -> open(name)));
            }
        }
        if (count == 0) {
            content.addView(TvUi.text(this, "请家长先选择儿童视频应用，并启用应用内的儿童模式。",
                    20, TvUi.MUTED));
        }
        content.addView(TvUi.text(this, "推荐内容：颜色与形状、1–5 数数、动物与自然、童谣。",
                18, TvUi.MUTED));
    }

    private void open(String name) {
        ParentalPrefs prefs = new ParentalPrefs(this);
        if (prefs.enabled() && prefs.remaining() == 0) {
            prefs.setResumePackage(name);
            startActivity(new Intent(this, PuzzleActivity.class));
        } else {
            AppLaunch.open(this, name);
        }
    }

    private void video(String name) {
        ParentalPrefs prefs = new ParentalPrefs(this);
        if (prefs.enabled() && prefs.remaining() == 0) {
            startActivity(new Intent(this, PuzzleActivity.class));
            return;
        }
        startActivity(new Intent(this, LiveActivity.class).putExtra("kids_video", name));
    }

    private void leave() {
        if (new ParentalPrefs(this).enabled()) {
            PinDialog.require(this, this::parentExit);
        } else {
            parentExit();
        }
    }

    private void parentExit() {
        new ParentalPrefs(this).setEnabled(false);
        startActivity(new Intent(this, HomeActivity.class));
        finish();
    }

    @Override
    protected void handleBackAction() {
        leave();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            leave();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }
}
