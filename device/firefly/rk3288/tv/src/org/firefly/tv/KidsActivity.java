/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
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
                    + ((prefs.remaining() + 59_999) / 60_000) + " 分钟" : "自由探索 · 家长模式尚未开启");
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
        handler.removeCallbacks(refresh);
        handler.post(refresh);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(refresh);
        super.onPause();
    }

    private void build() {
        LinearLayout page = TvUi.page(this, "儿童乐园", "3–5 岁 · 认颜色、找形状、数一数");
        ScrollView scroll = new ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        LinearLayout content = TvUi.column(this);
        content.setPadding(dp(7), dp(7), dp(7), dp(10));
        LinearLayout status = TvUi.row(this);
        remaining = TvUi.text(this, "", 13, 0xffbdc4dc);
        status.addView(remaining, new LinearLayout.LayoutParams(0, -2, 1));
        TextView parent = TvUi.text(this, "家长设置  ›", 13, TvUi.TEXT);
        parent.setPadding(dp(15), dp(9), dp(15), dp(9));
        parent.setBackground(TvUi.focusBackground(this));
        TvUi.interactive(parent, view -> startActivity(new Intent(this, ParentalActivity.class)));
        status.addView(parent);
        content.addView(status);

        LinearLayout lessons = TvUi.row(this);
        View game = lesson("动动小脑筋", "颜色 · 形状 · 数字", 0, 0xff343b64, () ->
                startActivity(new Intent(this, PuzzleActivity.class).putExtra("practice", true)));
        addLesson(lessons, game);
        if (new java.io.File("/product/etc/firefly-tv/kids/colors.mp4").isFile()) {
            addLesson(lessons, lesson("认识颜色", "离线启蒙短片", 1, 0xff28524d, () -> video("colors")));
        }
        if (new java.io.File("/product/etc/firefly-tv/kids/counting.mp4").isFile()) {
            addLesson(lessons, lesson("数一数", "一起认识 1–5", 2, 0xff634438, () -> video("counting")));
        }
        LinearLayout.LayoutParams last = (LinearLayout.LayoutParams)
                lessons.getChildAt(lessons.getChildCount() - 1).getLayoutParams();
        last.rightMargin = 0;
        LinearLayout.LayoutParams lessonPosition = new LinearLayout.LayoutParams(-1, -2);
        lessonPosition.topMargin = dp(19);
        content.addView(lessons, lessonPosition);
        addProviders(content);

        TextView leave = TvUi.text(this, "返回电视主页  ›", 13, TvUi.MUTED);
        leave.setGravity(Gravity.CENTER);
        leave.setPadding(dp(18), dp(13), dp(18), dp(13));
        leave.setBackground(TvUi.focusBackground(this));
        TvUi.interactive(leave, view -> leave());
        LinearLayout.LayoutParams leavePosition = new LinearLayout.LayoutParams(-2, -2);
        leavePosition.topMargin = dp(22);
        content.addView(leave, leavePosition);
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        game.requestFocus();
    }

    private int dp(int value) { return TvUi.dp(this, value); }

    private void addLesson(LinearLayout row, View tile) {
        LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(0, dp(184), 1);
        position.rightMargin = dp(17);
        row.addView(tile, position);
    }

    private View lesson(String title, String detail, int style, int color, Runnable action) {
        FrameLayout tile = new FrameLayout(this);
        GradientDrawable background = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[] {color, 0xff1c202d});
        background.setCornerRadius(dp(17));
        tile.setBackground(background);
        tile.setClipToOutline(true);
        tile.setContentDescription(title + "，" + detail);
        tile.addView(new LessonArt(this, style), new FrameLayout.LayoutParams(-1, dp(116)));
        LinearLayout labels = TvUi.column(this);
        labels.setPadding(dp(20), 0, dp(20), dp(18));
        TextView name = TvUi.text(this, title, 21, TvUi.TEXT);
        TvUi.emphasize(name);
        labels.addView(name);
        TextView summary = TvUi.text(this, detail, 12, 0xffc0c4d3);
        LinearLayout.LayoutParams caption = new LinearLayout.LayoutParams(-1, -2);
        caption.topMargin = dp(7);
        labels.addView(summary, caption);
        tile.addView(labels, new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM));
        android.graphics.drawable.StateListDrawable ring = new android.graphics.drawable.StateListDrawable();
        GradientDrawable focused = TvUi.rounded(this, 0x00000000, 17);
        focused.setStroke(dp(3), TvUi.TEXT);
        ring.addState(new int[] {android.R.attr.state_focused}, focused);
        ring.addState(new int[0], TvUi.rounded(this, 0x00000000, 17));
        tile.setForeground(ring);
        tile.setDescendantFocusability(android.view.ViewGroup.FOCUS_BLOCK_DESCENDANTS);
        TvUi.interactive(tile, view -> action.run());
        return tile;
    }

    private void addProviders(LinearLayout content) {
        ParentalPrefs prefs = new ParentalPrefs(this);
        Set<String> allowed = prefs.allowedApps();
        TextView heading = TvUi.text(this, "家长选好的应用", 17, TvUi.TEXT);
        TvUi.emphasize(heading);
        heading.setPadding(dp(2), dp(25), 0, dp(13));
        content.addView(heading);
        LinearLayout providers = TvUi.row(this);
        providers.setGravity(Gravity.TOP);
        int count = 0;
        for (int index = 0; index < KidsContent.LABELS.length; index++) {
            String name = KidsContent.installed(this, index);
            if (!name.isEmpty() && allowed.contains(name)) {
                count++;
                View tile = TvUi.appTile(this, KidsContent.LABELS[index],
                        TvUi.appBanner(getPackageManager(), name), TvUi.appIcon(getPackageManager(), name),
                        TvUi.appTint(name), view -> open(name));
                LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(0, -2, 1);
                position.rightMargin = dp(18);
                providers.addView(tile, position);
            }
        }
        if (count == 0) {
            TextView empty = TvUi.text(this, "请家长先选择允许打开的应用，并在应用内开启儿童模式。", 14, TvUi.MUTED);
            empty.setPadding(dp(18), dp(20), dp(18), dp(20));
            empty.setBackground(TvUi.rounded(this, TvUi.PANEL, 13));
            content.addView(empty);
        } else {
            // Preserve consistent gallery widths when only one provider is approved.
            for (int i = count; i < 3; i++) {
                LinearLayout.LayoutParams empty = new LinearLayout.LayoutParams(0, 1, 1);
                empty.rightMargin = dp(18);
                providers.addView(new View(this), empty);
            }
            LinearLayout.LayoutParams last = (LinearLayout.LayoutParams) providers.getChildAt(2).getLayoutParams();
            last.rightMargin = 0;
            content.addView(providers);
        }
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

    /** Original illustrations for the actual included learning activities. */
    private static final class LessonArt extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final int style;

        LessonArt(Context context, int style) {
            super(context);
            this.style = style;
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        }

        @Override protected void onDraw(Canvas canvas) {
            float scale = Math.min(getWidth() / 260f, getHeight() / 116f);
            canvas.save();
            canvas.translate(getWidth() / 2f, getHeight() / 2f);
            canvas.scale(scale, scale);
            if (style == 0) {
                paint.setColor(0xffb2a1e9);
                canvas.save(); canvas.rotate(-14); canvas.drawRoundRect(new RectF(-68, -27, -15, 26), 11, 11, paint); canvas.restore();
                paint.setColor(0xffe9c988); canvas.drawCircle(15, 4, 24, paint);
                paint.setColor(0xff96c7d3);
                Path triangle = new Path(); triangle.moveTo(58, -28); triangle.lineTo(87, 26); triangle.lineTo(29, 26); triangle.close();
                canvas.drawPath(triangle, paint);
            } else if (style == 1) {
                paint.setColor(0xffe7a5a5); canvas.drawCircle(-46, 0, 29, paint);
                paint.setColor(0xffe6d18b); canvas.drawCircle(0, -10, 29, paint);
                paint.setColor(0xff8fbfc8); canvas.drawCircle(44, 5, 29, paint);
                paint.setColor(0x55ffffff); canvas.drawCircle(-53, -10, 7, paint);
                canvas.drawCircle(-7, -20, 7, paint); canvas.drawCircle(37, -5, 7, paint);
            } else {
                int[] colors = {0xffd3b6ee, 0xffe6cf94, 0xff9dcab9};
                for (int i = 0; i < 3; i++) {
                    float left = -78 + i * 55;
                    canvas.save(); canvas.rotate(i == 0 ? -8 : i == 2 ? 8 : 0, left + 23, 0);
                    paint.setColor(colors[i]); canvas.drawRoundRect(new RectF(left, -28, left + 47, 29), 10, 10, paint);
                    paint.setColor(0xff3a3342); paint.setTypeface(android.graphics.Typeface.create("sans-serif-medium", 0));
                    paint.setTextSize(35); paint.setTextAlign(Paint.Align.CENTER);
                    canvas.drawText(Integer.toString(i + 1), left + 23, 13, paint); canvas.restore();
                }
            }
            canvas.restore();
        }
    }
}
