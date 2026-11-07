/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;

/** Small remote-accessible settings gateway without requiring a touch interface. */
public final class SettingsActivity extends TvActivity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout page = TvUi.page(this, "设置", "网络、遥控器和播放检查");
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = TvUi.column(this);
        add(content, "网络与互联网", () -> settings(Settings.ACTION_WIRELESS_SETTINGS));
        add(content, "家长模式与儿童内容", () ->
                startActivity(new Intent(this, ParentalActivity.class)));
        add(content, "去广告", () -> new AlertDialog.Builder(this).setTitle("去广告")
                .setMessage("系统已内置广告域名过滤，SmartTube 另有自身的广告处理。\n"
                        + "如使用 CMFA，可导入内置广告规则；详情见项目去广告说明。\n"
                        + "与正片共用域名的贴片广告仍可能播放。")
                .setPositiveButton("知道了", null).show());
        add(content, "国外应用网络", () -> AppLaunch.open(this, AppLaunch.NETWORK));
        add(content, "声音与显示", () -> settings(Settings.ACTION_DISPLAY_SETTINGS));
        add(content, "遥控器适配", () -> startActivity(new Intent(this, RemoteActivity.class)));
        add(content, "硬件解码检查", () -> startActivity(new Intent(this, DecoderActivity.class)));
        add(content, "系统设置", () -> settings(Settings.ACTION_SETTINGS));
        add(content, "重启", () -> confirmRestart(null));
        add(content, "重启到 USB Fastboot", () -> confirmRestart("bootloader"));
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        content.getChildAt(0).requestFocus();
    }

    private void add(LinearLayout parent, String label, Runnable action) {
        Button button = TvUi.button(this, label, view -> action.run());
        TvUi.addButton(parent, button);
    }

    private void settings(String action) {
        AppLaunch.action(this, new Intent(action));
    }

    private void confirmRestart(String reason) {
        String message = reason == null ? "重启 Firefly TV？"
                : "进入 USB Fastboot 后，需要电脑端操作或重新上电才能返回。";
        new AlertDialog.Builder(this).setTitle("重启确认").setMessage(message)
                .setNegativeButton("取消", null)
                .setPositiveButton("重启", (dialog, which) ->
                        getSystemService(PowerManager.class).reboot(reason)).show();
    }
}
