/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.widget.LinearLayout;
import android.widget.ScrollView;

/** PIN-gated controls. There is deliberately no factory PIN or unlimited quiz refill. */
public final class ParentalActivity extends TvActivity {
    private ParentalPrefs prefs;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new ParentalPrefs(this);
        buildGate();
        PinDialog.require(this, this::build);
    }

    @Override
    protected void onStop() {
        super.onStop();
        // Returning from recents must not resurrect an already-authorized parent panel.
        if (!isChangingConfigurations()) {
            finish();
        }
    }

    private void buildGate() {
        LinearLayout page = TvUi.page(this, "家长设置", "验证后管理观看时长与儿童内容");
        TvUi.addButton(page, TvUi.button(this, prefs.hasPin() ? "验证家长 PIN" : "设置家长 PIN",
                view -> PinDialog.require(this, this::build)));
        TvUi.addButton(page, TvUi.button(this, "返回", view -> finish()));
        page.getChildAt(2).requestFocus();
    }

    private void build() {
        LinearLayout page = TvUi.page(this, "家长设置", "默认适合 3–5 岁；方向键和确定键即可操作。");
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = TvUi.column(this);
        add(content, prefs.enabled() ? "关闭家长模式" : "开启家长模式", () -> {
            prefs.setEnabled(!prefs.enabled());
            WatchTimeTracker.start(this);
            build();
        });
        add(content, "每段观看：" + prefs.sessionMinutes() + " 分钟", () -> choose(
                "每段观看时长", new int[] {5, 10, 15, 20, 30}, 0));
        add(content, "每日上限：" + prefs.dailyMinutes() + " 分钟", () -> choose(
                "每日累计上限（答题不能增加）", new int[] {15, 30, 45, 60, 90}, 1));
        add(content, "答题后续看：" + prefs.bonusMinutes() + " 分钟", () -> choose(
                "每次完成三题后续看", new int[] {3, 5, 10, 15}, 2));
        add(content, "题目难度：" + (prefs.difficulty() == 0 ? "3–5 岁" : "更简单（1–3 数数）"),
                this::difficulty);
        add(content, "选择儿童视频应用", this::providers);
        add(content, "修改家长 PIN", () -> PinDialog.create(this, this::build));
        add(content, "进入儿童专区", () -> startActivity(new Intent(this, KidsActivity.class)));
        content.addView(TvUi.text(this,
                "按儿童视频应用的前台使用时间计时；退出应用会停止其后台播放。\n"
                + "到时停止视频，完成三道益智题后可续看。每日上限仍然有效。\n"
                + "重启保留用时，时间预记到 5 秒；请先为应用启用儿童模式并检查内容。",
                17, TvUi.MUTED));
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        content.getChildAt(0).requestFocus();
    }

    private void choose(String title, int[] values, int field) {
        String[] labels = new String[values.length];
        for (int index = 0; index < values.length; index++) {
            labels[index] = values[index] + " 分钟";
        }
        new AlertDialog.Builder(this).setTitle(title).setItems(labels, (dialog, which) -> {
            int session = field == 0 ? values[which] : prefs.sessionMinutes();
            int daily = field == 1 ? values[which] : prefs.dailyMinutes();
            int bonus = field == 2 ? values[which] : prefs.bonusMinutes();
            prefs.setLimits(session, daily, bonus, prefs.difficulty());
            build();
        }).setNegativeButton("取消", null).show();
    }

    private void difficulty() {
        new AlertDialog.Builder(this).setTitle("益智题难度")
                .setItems(new String[] {"3–5 岁：颜色、形状、1–5 数数", "更简单：颜色、形状、1–3 数数"},
                (dialog, which) -> {
                    prefs.setLimits(prefs.sessionMinutes(), prefs.dailyMinutes(),
                            prefs.bonusMinutes(), which);
                    build();
                }).show();
    }

    private void providers() {
        boolean[] checked = new boolean[KidsContent.LABELS.length];
        String[] labels = KidsContent.LABELS.clone();
        for (int index = 0; index < labels.length; index++) {
            String name = KidsContent.installed(this, index);
            checked[index] = prefs.allowedApps().contains(name);
            if (name.isEmpty()) {
                labels[index] += "（未安装）";
            }
        }
        new AlertDialog.Builder(this).setTitle("只允许已检查且已开启儿童模式的应用")
                .setMultiChoiceItems(labels, checked, (dialog, which, selected) -> {
                    String name = KidsContent.installed(this, which);
                    if (!name.isEmpty()) {
                        prefs.allow(name, selected);
                    }
                }).setPositiveButton("完成", null).setNeutralButton("准备说明", (dialog, which) ->
                        new AlertDialog.Builder(this).setTitle("儿童节目与应用")
                                .setMessage(String.join("\n\n", KidsContent.NOTES)
                                + "\n\n在线视频的会员、地区和内容分级由提供方管理。")
                                .setPositiveButton("知道了", null).show()).show();
    }

    private void add(LinearLayout content, String title, Runnable action) {
        TvUi.addButton(content, TvUi.button(this, title, view -> action.run()));
    }
}
