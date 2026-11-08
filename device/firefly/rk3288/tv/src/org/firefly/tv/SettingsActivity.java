/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Everyday television settings, with maintenance actions kept in a separate menu. */
public final class SettingsActivity extends TvActivity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout page = TvUi.page(this, "设置", "让电视更适合你");
        ScrollView scroll = new ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        LinearLayout content = TvUi.column(this);
        content.setPadding(dp(12), dp(7), dp(12), dp(10));
        View network = tile("网络连接", "有线网络与无线网络", 0, 0xff829fc8,
                () -> settings(Settings.ACTION_WIRELESS_SETTINGS));
        addPair(content, network, tile("声音", "音量与音频设置", 1, 0xffaf9bd9,
                () -> settings(Settings.ACTION_SOUND_SETTINGS)));
        addPair(content, tile("显示", "画面与屏幕设置", 2, 0xff92bcb1,
                () -> settings(Settings.ACTION_DISPLAY_SETTINGS)),
                tile("儿童与家长", "观看时间、应用与 PIN", 3, 0xffd0b38d,
                () -> startActivity(new Intent(this, ParentalActivity.class))));
        addPair(content, tile("遥控器", "按键设置与红外学习", 4, 0xffb1a7d2,
                () -> startActivity(new Intent(this, RemoteActivity.class))),
                tile("应用管理", "查看已安装的应用", 5, 0xff98adc9,
                () -> settings(Settings.ACTION_MANAGE_APPLICATIONS_SETTINGS)));

        TextView section = TvUi.text(this, "设备", 13, TvUi.MUTED);
        section.setPadding(dp(3), dp(9), 0, dp(12));
        content.addView(section);
        addPair(content, tile("更多设置", "系统、网络工具与播放检查", 6, 0xff9ca8ba,
                this::showMore), tile("重新启动", "关闭应用并重启设备", 7, 0xffaaadb5,
                () -> confirmRestart(null)));
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        network.requestFocus();
    }

    private int dp(int value) { return TvUi.dp(this, value); }

    private void addPair(LinearLayout parent, View left, View right) {
        LinearLayout row = TvUi.row(this);
        LinearLayout.LayoutParams first = new LinearLayout.LayoutParams(0, dp(82), 1);
        first.rightMargin = dp(16);
        row.addView(left, first);
        row.addView(right, new LinearLayout.LayoutParams(0, dp(82), 1));
        LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(-1, -2);
        position.bottomMargin = dp(14);
        parent.addView(row, position);
    }

    private View tile(String title, String detail, int icon, int tint, Runnable action) {
        LinearLayout tile = TvUi.row(this);
        tile.setPadding(dp(19), dp(13), dp(18), dp(13));
        tile.setBackground(TvUi.focusBackground(this));
        tile.setContentDescription(title + "，" + detail);
        tile.setDescendantFocusability(android.view.ViewGroup.FOCUS_BLOCK_DESCENDANTS);
        tile.addView(new SettingIcon(this, icon, tint), new LinearLayout.LayoutParams(dp(38), dp(38)));
        LinearLayout labels = TvUi.column(this);
        TextView name = TvUi.text(this, title, 18, TvUi.TEXT);
        TvUi.emphasize(name);
        labels.addView(name);
        TextView summary = TvUi.text(this, detail, 12, TvUi.MUTED);
        summary.setSingleLine(true);
        summary.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams caption = new LinearLayout.LayoutParams(-1, -2);
        caption.topMargin = dp(7);
        labels.addView(summary, caption);
        LinearLayout.LayoutParams textPosition = new LinearLayout.LayoutParams(0, -2, 1);
        textPosition.leftMargin = dp(15);
        tile.addView(labels, textPosition);
        TextView arrow = TvUi.text(this, "›", 25, 0xff697383);
        arrow.setPadding(dp(8), 0, 0, 0);
        arrow.setGravity(Gravity.CENTER);
        tile.addView(arrow);
        TvUi.interactive(tile, view -> action.run());
        return tile;
    }

    private void settings(String action) {
        Intent target = new Intent(action);
        if (target.resolveActivity(getPackageManager()) == null) {
            // AOSP TV exposes combined display/sound and a TV network entry.
            if (Settings.ACTION_DISPLAY_SETTINGS.equals(action)) {
                target = new Intent(Settings.ACTION_SOUND_SETTINGS);
            } else if (Settings.ACTION_WIRELESS_SETTINGS.equals(action)) {
                target = new Intent("android.settings.NETWORK_SETTINGS_TV_OEM_LINK");
            }
        }
        if (target.resolveActivity(getPackageManager()) == null) {
            target = new Intent(Settings.ACTION_SETTINGS);
        }
        AppLaunch.action(this, target);
    }

    private void showMore() {
        String[] labels = {"系统设置", "广告过滤说明", "网络工具", "硬件解码检查", "进入 USB 维护模式"};
        new AlertDialog.Builder(this).setTitle("更多设置").setItems(labels, (dialog, which) -> {
            switch (which) {
                case 0: settings(Settings.ACTION_SETTINGS); break;
                case 1: showAdFiltering(); break;
                case 2: AppLaunch.open(this, AppLaunch.NETWORK); break;
                case 3: startActivity(new Intent(this, DecoderActivity.class)); break;
                case 4: confirmRestart("bootloader"); break;
                default: break;
            }
        }).setNegativeButton("返回", null).show();
    }

    private void showAdFiltering() {
        new AlertDialog.Builder(this).setTitle("广告过滤")
                .setMessage("系统已内置广告域名过滤，SmartTube 另有自身的广告处理。\n"
                        + "如使用 CMFA，可导入内置广告规则；详情见项目去广告说明。\n"
                        + "与正片共用域名的贴片广告仍可能播放。")
                .setPositiveButton("知道了", null).show();
    }

    private void confirmRestart(String reason) {
        String message = reason == null ? "重启 Firefly TV？正在使用的应用会关闭。"
                : "进入 USB Fastboot 后，需要电脑端操作或重新上电才能返回。";
        new AlertDialog.Builder(this).setTitle(reason == null ? "重新启动" : "USB 维护模式")
                .setMessage(message).setNegativeButton("取消", null)
                .setPositiveButton("重启", (dialog, which) ->
                        getSystemService(PowerManager.class).reboot(reason)).show();
    }

    /** Small original line icons; no runtime bitmap decoding or animation. */
    private static final class SettingIcon extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final int kind;
        private final int color;

        SettingIcon(Context context, int kind, int color) {
            super(context);
            this.kind = kind;
            this.color = color;
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        }

        @Override protected void onDraw(Canvas canvas) {
            canvas.save();
            canvas.scale(getWidth() / 40f, getHeight() / 40f);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(2.1f);
            paint.setStrokeCap(Paint.Cap.ROUND);
            paint.setStrokeJoin(Paint.Join.ROUND);
            paint.setColor(color);
            switch (kind) {
                case 0:
                    canvas.drawArc(new RectF(4, 10, 36, 42), 220, 100, false, paint);
                    canvas.drawArc(new RectF(10, 16, 30, 36), 220, 100, false, paint);
                    canvas.drawArc(new RectF(16, 22, 24, 30), 220, 100, false, paint);
                    paint.setStyle(Paint.Style.FILL); canvas.drawCircle(20, 29, 1.6f, paint);
                    break;
                case 1:
                    Path speaker = new Path();
                    speaker.moveTo(7, 16); speaker.lineTo(13, 16); speaker.lineTo(21, 10);
                    speaker.lineTo(21, 30); speaker.lineTo(13, 24); speaker.lineTo(7, 24); speaker.close();
                    canvas.drawPath(speaker, paint);
                    canvas.drawArc(new RectF(19, 14, 31, 26), -65, 130, false, paint);
                    canvas.drawArc(new RectF(17, 8, 37, 32), -58, 116, false, paint);
                    break;
                case 2:
                    canvas.drawRoundRect(new RectF(5, 8, 35, 29), 3, 3, paint);
                    canvas.drawLine(20, 29, 20, 34, paint); canvas.drawLine(13, 34, 27, 34, paint);
                    break;
                case 3:
                    canvas.drawCircle(16, 13, 5, paint); canvas.drawCircle(29, 17, 3.5f, paint);
                    canvas.drawArc(new RectF(7, 22, 25, 41), 180, 180, false, paint);
                    canvas.drawArc(new RectF(24, 25, 36, 37), 200, 160, false, paint);
                    break;
                case 4:
                    canvas.drawRoundRect(new RectF(12, 3, 28, 37), 5, 5, paint);
                    canvas.drawCircle(20, 14, 4.5f, paint);
                    canvas.drawLine(17, 25, 23, 25, paint); canvas.drawLine(17, 30, 23, 30, paint);
                    break;
                case 5:
                    for (int y = 0; y < 2; y++) for (int x = 0; x < 2; x++)
                        canvas.drawRoundRect(new RectF(6 + x * 16, 6 + y * 16, 17 + x * 16, 17 + y * 16), 2, 2, paint);
                    break;
                case 6:
                    canvas.drawLine(7, 11, 33, 11, paint); canvas.drawLine(7, 20, 33, 20, paint);
                    canvas.drawLine(7, 29, 33, 29, paint);
                    canvas.drawCircle(15, 11, 3, paint); canvas.drawCircle(26, 20, 3, paint);
                    canvas.drawCircle(13, 29, 3, paint);
                    break;
                default:
                    canvas.drawArc(new RectF(7, 7, 33, 33), -50, 300, false, paint);
                    canvas.drawLine(28, 5, 29, 13, paint); canvas.drawLine(22, 13, 29, 13, paint);
                    break;
            }
            canvas.restore();
        }
    }
}
