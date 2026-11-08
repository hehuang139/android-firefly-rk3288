/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Every parent panel is authorized only for its current foreground visit. */
public final class ParentalActivity extends TvActivity {
    private ParentalPrefs prefs;
    private boolean authorized;
    private boolean resumed;
    private boolean initialChallenge = true;
    private AlertDialog options;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new ParentalPrefs(this);
        buildGate();
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        if (initialChallenge) {
            initialChallenge = false;
            authenticate();
        }
    }

    @Override
    protected void onPause() {
        resumed = false;
        authorized = false;
        if (options != null) options.dismiss();
        PinDialog.cancel(this);
        if (!isFinishing()) buildGate();
        super.onPause();
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (!isChangingConfigurations()) finish();
    }

    private void authenticate() {
        PinDialog.require(this, () -> {
            if (!resumed || isFinishing() || isDestroyed()) return;
            authorized = true;
            build();
        });
    }

    private boolean mayChange() {
        return authorized && resumed && !isFinishing() && !isDestroyed();
    }

    private void buildGate() {
        LinearLayout page = TvUi.page(this, "家长设置", "验证后管理孩子的观看与学习安排");
        View verify = TvUi.button(this, prefs.hasPin() ? "验证家长 PIN" : "建立家长 PIN",
                view -> authenticate());
        page.addView(verify);
        TextView note = TvUi.text(this, "设置与用时仅在验证后显示。离开此页后需要重新验证。", 14, TvUi.MUTED);
        note.setPadding(0, dp(18), 0, 0);
        page.addView(note);
        verify.requestFocus();
    }

    private void build() {
        if (!mayChange()) {
            buildGate();
            return;
        }
        LinearLayout page = TvUi.page(this, "家长设置", "3–6 岁 · 观看有安排，学习慢慢来");
        ScrollView scroll = new ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        LinearLayout content = TvUi.column(this);
        content.setPadding(dp(12), dp(7), dp(12), dp(14));
        section(content, "当前状态");
        LinearLayout status = TvUi.column(this);
        status.setPadding(dp(18), dp(15), dp(18), dp(15));
        status.setBackground(TvUi.rounded(this, TvUi.PANEL, 14));
        TextView mode = TvUi.text(this, prefs.enabled() ? "家长模式已开启" : "家长模式已关闭", 20, TvUi.TEXT);
        TvUi.emphasize(mode);
        status.addView(mode);
        TextView used = TvUi.text(this, "今日视频已用 " + duration(prefs.dailyUsed())
                + "    剩余 " + duration(prefs.dailyRemaining())
                + "    本段剩余 " + duration(prefs.remaining()), 13, TvUi.MUTED);
        used.setPadding(0, dp(9), 0, 0);
        status.addView(used);
        content.addView(status);
        View toggle = add(content, prefs.enabled() ? "关闭家长模式" : "开启家长模式", () -> {
            prefs.setEnabled(!prefs.enabled());
            WatchTimeTracker.start(this);
            build();
        });

        section(content, "视频观看");
        add(content, "每段观看   " + prefs.sessionMinutes() + " 分钟", () -> chooseMinutes(
                "每段观看时长", new int[] {5, 10, 15, 20, 30}, 0));
        add(content, "每日上限   " + prefs.dailyMinutes() + " 分钟", () -> chooseMinutes(
                "每日累计上限 · 答题不能增加", new int[] {15, 30, 45, 60, 90}, 1));
        add(content, "完成续看挑战后   " + prefs.bonusMinutes() + " 分钟", () -> chooseMinutes(
                "每次完成三题后的续看时长", new int[] {3, 5, 10, 15}, 2));
        add(content, "续看小挑战   " + (prefs.difficulty() == 0 ? "颜色、形状和 1–5 数数" : "简单版 · 1–3 数数"),
                this::difficulty);
        note(content, "只计算允许的视频应用和内置短片的前台时间，包括选片时间。游戏和算术练习不计入。"
                + "到时先停止视频；每日上限不会因答题、重启或开关模式而清零。用时最多预记 5 秒。");

        section(content, "算术练习");
        add(content, "加减法范围   " + prefs.mathLimit() + " 以内", () -> chooseMath(true));
        add(content, "每轮题数   " + prefs.mathQuestions() + " 题", () -> chooseMath(false));
        note(content, "默认 10 以内、每轮 5 题，适合家长陪伴的 3–6 岁启蒙。算术练习与视频续看额度独立，答错可以重试。");

        section(content, "应用许可与家长操作");
        add(content, "选择允许的视频应用", this::providers);
        add(content, "修改家长 PIN", () -> PinDialog.require(this, () -> {
            if (mayChange()) PinDialog.create(this, () -> { if (mayChange()) build(); });
        }));
        add(content, "进入儿童乐园", () -> startActivity(new Intent(this, KidsActivity.class)));
        note(content, "应用许可只控制入口和观看时间，不替代视频平台自己的儿童模式。请先在应用内选好内容与分龄。");
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        toggle.requestFocus();
    }

    private void chooseMinutes(String title, int[] values, int field) {
        String[] labels = new String[values.length];
        int selected = -1;
        int current = field == 0 ? prefs.sessionMinutes() : field == 1 ? prefs.dailyMinutes() : prefs.bonusMinutes();
        for (int index = 0; index < values.length; index++) {
            labels[index] = values[index] + " 分钟";
            if (values[index] == current) selected = index;
        }
        options = new AlertDialog.Builder(this).setTitle(title).setSingleChoiceItems(labels, selected, (dialog, which) -> {
            if (!mayChange()) return;
            prefs.setLimits(field == 0 ? values[which] : prefs.sessionMinutes(),
                    field == 1 ? values[which] : prefs.dailyMinutes(),
                    field == 2 ? values[which] : prefs.bonusMinutes(), prefs.difficulty());
            dialog.dismiss();
            build();
        }).setNegativeButton("取消", null).create();
        showOptions();
    }

    private void chooseMath(boolean range) {
        int[] values = range ? new int[] {5, 10, 20} : new int[] {5, 10};
        String[] labels = new String[values.length];
        int selected = -1;
        int current = range ? prefs.mathLimit() : prefs.mathQuestions();
        for (int index = 0; index < values.length; index++) {
            labels[index] = values[index] + (range ? " 以内加减法" : " 题");
            if (values[index] == current) selected = index;
        }
        options = new AlertDialog.Builder(this).setTitle(range ? "算术范围" : "每轮题数")
                .setSingleChoiceItems(labels, selected, (dialog, which) -> {
                    if (!mayChange()) return;
                    prefs.setMathOptions(range ? values[which] : prefs.mathLimit(),
                            range ? prefs.mathQuestions() : values[which]);
                    dialog.dismiss();
                    build();
                }).setNegativeButton("取消", null).create();
        showOptions();
    }

    private void difficulty() {
        options = new AlertDialog.Builder(this).setTitle("视频续看小挑战")
                .setSingleChoiceItems(new String[] {"颜色、形状、1–5 数数", "简单版 · 颜色、形状、1–3 数数"},
                prefs.difficulty(), (dialog, which) -> {
                    if (!mayChange()) return;
                    prefs.setLimits(prefs.sessionMinutes(), prefs.dailyMinutes(), prefs.bonusMinutes(), which);
                    dialog.dismiss();
                    build();
                }).setNegativeButton("取消", null).create();
        showOptions();
    }

    private void providers() {
        boolean[] checked = new boolean[KidsContent.LABELS.length];
        String[] labels = KidsContent.LABELS.clone();
        for (int index = 0; index < labels.length; index++) {
            String name = KidsContent.installed(this, index);
            checked[index] = !name.isEmpty() && prefs.allowedApps().contains(name);
            if (name.isEmpty()) labels[index] += "（未安装）";
        }
        options = new AlertDialog.Builder(this).setTitle("允许的儿童视频应用")
                .setMultiChoiceItems(labels, checked, (dialog, which, selected) -> {
                    if (!mayChange()) return;
                    String name = KidsContent.installed(this, which);
                    if (name.isEmpty()) {
                        ((AlertDialog) dialog).getListView().setItemChecked(which, false);
                    } else {
                        prefs.allow(name, selected);
                    }
                }).setPositiveButton("完成", null).create();
        showOptions();
    }

    private void showOptions() {
        PinDialog.cancelWithEscape(options);
        options.show();
    }

    private View add(LinearLayout content, String title, Runnable action) {
        View button = TvUi.button(this, title, view -> { if (mayChange()) action.run(); });
        LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(-1, -2);
        position.topMargin = dp(9);
        content.addView(button, position);
        return button;
    }

    private void section(LinearLayout content, String title) {
        TextView heading = TvUi.text(this, title, 16, TvUi.TEXT);
        TvUi.emphasize(heading);
        heading.setPadding(dp(2), dp(23), 0, dp(12));
        content.addView(heading);
    }

    private void note(LinearLayout content, String value) {
        TextView label = TvUi.text(this, value, 12, TvUi.MUTED);
        label.setPadding(dp(3), dp(11), dp(3), 0);
        label.setLineSpacing(dp(3), 1f);
        content.addView(label);
    }

    private int dp(int value) { return TvUi.dp(this, value); }

    private static String duration(long milliseconds) {
        long seconds = Math.max(0, milliseconds / 1000);
        return seconds / 60 + " 分 " + seconds % 60 + " 秒";
    }
}
