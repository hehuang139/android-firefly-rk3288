/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/** Arithmetic, approved video and local learning progress for young children. */
public final class KidsActivity extends TvActivity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView remaining;
    private LinearLayout content;
    private ScrollView scroll;
    private final List<TextView> tabs = new ArrayList<>();
    private int selectedTab;
    private android.window.OnBackInvokedCallback backCallback;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            ParentalPrefs prefs = new ParentalPrefs(KidsActivity.this);
            String text = prefs.enabled() ? "视频还可看约 " + ((prefs.remaining() + 59_999) / 60_000)
                    + " 分钟  ·  算术练习不占观看额度" : "3–6 岁  ·  离线算术随时学  ·  视频管理未开启";
            if (remaining != null && !text.contentEquals(remaining.getText())) remaining.setText(text);
            handler.postDelayed(this, 1000);
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        selectedTab = state == null ? 0 : Math.max(0, Math.min(2, state.getInt("kids_tab", 0)));
        WatchTimeTracker.start(this);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            backCallback = this::leave;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, backCallback);
        }
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        state.putInt("kids_tab", selectedTab);
        super.onSaveInstanceState(state);
    }
    @Override protected void onResume() {
        super.onResume();
        build();
        handler.removeCallbacks(refresh);
        handler.post(refresh);
    }
    @Override protected void onPause() {
        handler.removeCallbacks(refresh);
        PinDialog.cancel(this);
        super.onPause();
    }
    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if (android.os.Build.VERSION.SDK_INT >= 33 && backCallback != null)
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(backCallback);
        super.onDestroy();
    }
    private int dp(int value) { return TvUi.dp(this, value); }

    private void build() {
        LinearLayout page = TvUi.page(this, "儿童乐园", "数一数，算一算。每天发现一点新本领。");
        LinearLayout status = TvUi.row(this);
        remaining = TvUi.text(this, "", 12, 0xffc4cce0);
        remaining.setMaxLines(2);
        status.addView(remaining, new LinearLayout.LayoutParams(0, -2, 1));
        TextView parent = chip("家长设置  ›", () -> startActivity(new Intent(this, ParentalActivity.class)));
        status.addView(parent);
        page.addView(status, new LinearLayout.LayoutParams(-1, dp(38)));
        LinearLayout navigation = TvUi.row(this);
        String[] labels = {"算术练习", "启蒙视频", "学习记录"};
        tabs.clear();
        for (int index = 0; index < labels.length; index++) {
            final int choice = index;
            TextView tab = chip(labels[index], () -> showTab(choice));
            LinearLayout.LayoutParams pos = new LinearLayout.LayoutParams(dp(130), dp(37));
            pos.rightMargin = dp(12);
            navigation.addView(tab, pos);
            tabs.add(tab);
        }
        LinearLayout.LayoutParams navPos = new LinearLayout.LayoutParams(-1, dp(49));
        navPos.topMargin = dp(9);
        page.addView(navigation, navPos);
        scroll = new ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        content = TvUi.column(this);
        content.setPadding(dp(10), dp(10), dp(10), dp(18));
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        showTab(selectedTab);
        tabs.get(selectedTab).requestFocus();
    }
    private TextView chip(String label, Runnable action) {
        TextView view = TvUi.text(this, label, 14, TvUi.TEXT);
        view.setGravity(Gravity.CENTER);
        view.setPadding(dp(15), dp(9), dp(15), dp(9));
        view.setBackground(TvUi.focusBackground(this));
        TvUi.interactive(view, v -> action.run());
        return view;
    }
    private void showTab(int index) {
        selectedTab = index;
        for (int i = 0; i < tabs.size(); i++) {
            TextView tab = tabs.get(i);
            boolean selected = i == index;
            tab.setSelected(selected);
            tab.setTextColor(selected ? 0xffe8d8ac : TvUi.TEXT);
            tab.setContentDescription(tab.getText() + (selected ? "，当前分类" : ""));
            StateListDrawable state = TvUi.focusBackground(this);
            if (selected) {
                GradientDrawable resting = TvUi.rounded(this, 0xff34313b, 14);
                resting.setStroke(dp(1), 0xff80745a);
                state = new StateListDrawable();
                GradientDrawable focused = TvUi.rounded(this, 0xff45424c, 14);
                focused.setStroke(dp(2), TvUi.TEXT);
                state.addState(new int[]{android.R.attr.state_focused}, focused);
                state.addState(new int[]{}, resting);
            }
            tab.setBackground(state);
        }
        content.removeAllViews();
        if (index == 0) arithmetic();
        else if (index == 1) videos();
        else progress();
        scroll.scrollTo(0, 0);
        tabs.get(index).requestFocus();
    }
    private void arithmetic() {
        ParentalPrefs prefs = new ParentalPrefs(this);
        TextView hint = TvUi.text(this, prefs.mathLimit() + " 以内  ·  每组 " + prefs.mathQuestions()
                + " 题  ·  不计时，答错可以再试", 13, TvUi.MUTED);
        hint.setPadding(dp(3), 0, 0, dp(14));
        content.addView(hint);
        String[] modes = {"count", "add", "sub", "compare", "mixed"};
        String[] titles = {"数一数", "加法启蒙", "减法启蒙", "比大小", "混合练习"};
        String[] details = {"看图认识数量", "合在一起有多少", "拿走以后剩多少", "认识大于、小于和等于", "把学会的本领一起用"};
        int[] colors = {0xff315b61, 0xff4e486f, 0xff695049, 0xff3e5b48, 0xff5d4760};
        LinearLayout row = null;
        for (int i = 0; i < modes.length; i++) {
            if (i % 3 == 0) { row = TvUi.row(this); addRow(row); }
            final String mode = modes[i];
            addCard(row, card(titles[i], details[i], mode, colors[i], () -> practice(mode)), i % 3);
        }
        KidsProgress stats = new KidsProgress(this);
        String recent = ArithmeticRound.normalizeMode(stats.lastMode());
        addCard(row, card(stats.completedRounds() == 0 ? "我的小进步" : "再练一组",
                stats.completedRounds() == 0 ? "完成后看看自己的收获" : "上次：" + ArithmeticRound.modeLabel(recent),
                "progress", 0xff4f5468,
                () -> { if (stats.completedRounds() == 0) showTab(2); else practice(recent); }), 2);
    }
    private void practice(String mode) {
        startActivity(new Intent(this, PuzzleActivity.class).putExtra("practice", true)
                .putExtra("math_mode", ArithmeticRound.normalizeMode(mode)));
    }
    private void addRow(LinearLayout row) {
        LinearLayout.LayoutParams pos = new LinearLayout.LayoutParams(-1, -2);
        pos.bottomMargin = dp(17);
        content.addView(row, pos);
    }
    private void addCard(LinearLayout row, View card, int column) {
        LinearLayout.LayoutParams pos = new LinearLayout.LayoutParams(0, dp(129), 1);
        if (column != 2) pos.rightMargin = dp(17);
        row.addView(card, pos);
    }
    private View card(String title, String detail, String art, int color, Runnable action) {
        FrameLayout tile = new FrameLayout(this);
        tile.setBackground(new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{color, 0xff202633}));
        ((GradientDrawable)tile.getBackground()).setCornerRadius(dp(16));
        tile.setClipToOutline(true);
        tile.setContentDescription(title + "，" + detail);
        tile.setDescendantFocusability(android.view.ViewGroup.FOCUS_BLOCK_DESCENDANTS);
        tile.addView(new MathArt(this, art), new FrameLayout.LayoutParams(-1, dp(67)));
        LinearLayout labels = TvUi.column(this);
        labels.setPadding(dp(17), 0, dp(17), dp(14));
        TextView name = TvUi.text(this, title, 20, TvUi.TEXT); TvUi.emphasize(name);
        labels.addView(name);
        TextView desc = TvUi.text(this, detail, 12, 0xffd0d4df);
        desc.setSingleLine(); desc.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams caption = new LinearLayout.LayoutParams(-1, -2); caption.topMargin = dp(7);
        labels.addView(desc, caption);
        tile.addView(labels, new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM));
        StateListDrawable ring = new StateListDrawable();
        GradientDrawable focus = TvUi.rounded(this, 0x00000000, 16); focus.setStroke(dp(3), TvUi.TEXT);
        ring.addState(new int[]{android.R.attr.state_focused}, focus);
        ring.addState(new int[]{}, TvUi.rounded(this, 0x00000000, 16));
        tile.setForeground(ring);
        TvUi.interactive(tile, v -> action.run());
        return tile;
    }
    private void videos() {
        TextView title = TvUi.text(this, "离线启蒙短片", 18, TvUi.TEXT);
        title.setPadding(dp(3), 0, 0, dp(14)); content.addView(title);
        LinearLayout local = TvUi.row(this); addRow(local);
        int count = 0;
        if (new File("/product/etc/firefly-tv/kids/colors.mp4").isFile()) {
            addCard(local, card("认识颜色", "原有离线短片", "color", 0xff315b61, () -> video("colors")), count++);
        }
        if (new File("/product/etc/firefly-tv/kids/counting.mp4").isFile()) {
            addCard(local, card("数一数", "认识 1–5", "count", 0xff695049, () -> video("counting")), count++);
        }
        if (count == 0) { content.removeView(local); note("尚未安装离线短片，算术练习不需要下载内容。"); }
        else while (count < 3) { LinearLayout.LayoutParams pos = new LinearLayout.LayoutParams(0, 1, 1); if (count++ != 2) pos.rightMargin=dp(17); local.addView(new View(this), pos); }
        TextView heading = TvUi.text(this, "家长选好的视频应用", 18, TvUi.TEXT);
        heading.setPadding(dp(3), dp(12), 0, dp(15)); content.addView(heading);
        Set<String> allowed = new ParentalPrefs(this).allowedApps();
        LinearLayout row = TvUi.row(this); int providers = 0;
        for (int i = 0; i < KidsContent.LABELS.length; i++) {
            String name = KidsContent.installed(this, i);
            if (!name.isEmpty() && allowed.contains(name)) {
                View tile = TvUi.appTile(this, KidsContent.LABELS[i], TvUi.appBanner(getPackageManager(), name),
                        TvUi.appIcon(getPackageManager(), name), TvUi.appTint(name), v -> open(name));
                LinearLayout.LayoutParams pos = new LinearLayout.LayoutParams(0, -2, 1);pos.rightMargin=dp(17);
                row.addView(tile,pos);providers++;
            }
        }
        if (providers == 0) note("请家长在“家长设置”中选择允许使用的视频应用，并检查应用内的儿童内容。");
        else {
            while (providers++ < 3) row.addView(new View(this),new LinearLayout.LayoutParams(0,1,1));
            content.addView(row);
        }
    }
    private void progress() {
        KidsProgress stats = new KidsProgress(this);
        TextView title = TvUi.text(this, stats.completedRounds() == 0 ? "从第一组小练习开始" : "每一次尝试，都在进步", 24, TvUi.TEXT);
        title.setPadding(dp(3), dp(5), 0, dp(20));content.addView(title);
        LinearLayout row = TvUi.row(this); addRow(row);
        metric(row, Integer.toString(stats.completedRounds()), "已完成练习组");
        metric(row, Integer.toString(stats.answeredQuestions()), "已完成题目");
        metric(row, stats.answeredQuestions()==0 ? "—" : Math.round(100f*stats.firstTryCorrect()/stats.answeredQuestions())+"%", "第一次就答对");
        note("记录只保存在这台设备。答错后可以再试；练习不会增加视频观看额度。");
        if (stats.completedRounds() > 0) {
            TextView last = TvUi.text(this, "最近练习：" + ArithmeticRound.modeLabel(stats.lastMode())
                    + " · " + stats.lastLimit() + " 以内", 16, TvUi.MUTED);
            last.setPadding(dp(3), dp(18), 0, dp(18));content.addView(last);
        }
        TextView again = chip("开始一组混合练习  ›", () -> practice("mixed"));
        LinearLayout.LayoutParams pos=new LinearLayout.LayoutParams(-2,-2);pos.topMargin=dp(18);content.addView(again,pos);
    }
    private void metric(LinearLayout row, String value, String label) {
        LinearLayout box = TvUi.column(this);box.setPadding(dp(20),dp(18),dp(20),dp(18));
        box.setBackground(TvUi.rounded(this,TvUi.PANEL,14));
        box.addView(TvUi.text(this,value,35,0xffe7d5a6));
        TextView caption=TvUi.text(this,label,13,TvUi.MUTED);caption.setPadding(0,dp(10),0,0);box.addView(caption);
        LinearLayout.LayoutParams pos=new LinearLayout.LayoutParams(0,-2,1);pos.rightMargin=dp(12);row.addView(box,pos);
    }
    private void note(String text) {
        TextView note=TvUi.text(this,text,14,TvUi.MUTED);note.setPadding(dp(18),dp(17),dp(18),dp(17));
        note.setBackground(TvUi.rounded(this,TvUi.PANEL,13));content.addView(note);
    }
    private void open(String name) {
        ParentalPrefs prefs=new ParentalPrefs(this);
        if (!prefs.allowedApps().contains(name) || !AppLaunch.available(this, name)) {
            showTab(1);
            android.widget.Toast.makeText(this, "请家长重新确认应用许可", android.widget.Toast.LENGTH_SHORT).show();
            return;
        }
        if (prefs.enabled() && prefs.remaining()==0) { prefs.setResumePackage(name);startActivity(new Intent(this,PuzzleActivity.class)); }
        else AppLaunch.open(this,name);
    }
    private void video(String name) {
        ParentalPrefs prefs=new ParentalPrefs(this);
        if (prefs.enabled() && prefs.remaining()==0) {startActivity(new Intent(this,PuzzleActivity.class));return;}
        startActivity(new Intent(this,LiveActivity.class).putExtra("kids_video",name));
    }
    private void leave() {
        if (new ParentalPrefs(this).enabled()) PinDialog.require(this,this::parentExit);
        else parentExit();
    }
    private void parentExit() {new ParentalPrefs(this).setEnabled(false);startActivity(new Intent(this,HomeActivity.class));finish();}
    @Override protected void handleBackAction() {leave();}
    @Override public boolean onKeyDown(int keyCode,KeyEvent event) {
        if(keyCode==KeyEvent.KEYCODE_BACK){if(event.getRepeatCount()==0)leave();return true;}
        return super.onKeyDown(keyCode,event);
    }

    private static final class MathArt extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        private final String kind;
        MathArt(Context context,String kind){super(context);this.kind=kind;setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        @Override protected void onDraw(Canvas canvas) {
            canvas.save();canvas.translate(getWidth()/2f,getHeight()/2f);float scale=Math.min(getWidth()/240f,getHeight()/67f);canvas.scale(scale,scale);
            int[] colors={0xffe6c982,0xff93c8c9,0xffc6b0df,0xffe5a8a5,0xffaacb9c};
            if("count".equals(kind)||"color".equals(kind)) {
                for(int i=0;i<5;i++){paint.setColor(colors[i]);canvas.drawCircle((i-2)*29,0,10,paint);}
            } else {
                String value="add".equals(kind)?"2 + 3":"sub".equals(kind)?"5 − 2":"compare".equals(kind)?"2 < 5":"mixed".equals(kind)?"+  −  =":"1  2  3";
                paint.setTypeface(Typeface.create("sans-serif-medium",0));paint.setTextSize(34);paint.setTextAlign(Paint.Align.CENTER);paint.setColor(0xffeaddb8);
                canvas.drawText(value,0,12,paint);
            }
            canvas.restore();
        }
    }
}
