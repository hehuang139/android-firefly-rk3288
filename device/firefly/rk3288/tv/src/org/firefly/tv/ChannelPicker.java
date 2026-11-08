/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Floating channel browser. Every displayed row retains its catalog identity. */
final class ChannelPicker extends FrameLayout {
    interface Listener {
        void onChannelSelected(int originalIndex);
        void onFavoriteToggle(int originalIndex);
    }

    private static final int WHITE = 0xfff5f5f7;
    private static final int MUTED = 0xffa0a5b2;
    private static final int INK = 0xff17191f;
    private static final int GREEN = 0xffb9dfc1;
    private final ChannelCatalog catalog;
    private final Set<String> favorites;
    private final Listener listener;
    private final float unit;
    private final List<ChannelCategories.Group> regions;
    private final List<ChannelCategories.Group> types;
    private final List<TextView> tabs = new ArrayList<>();
    private final List<TextView> groupViews = new ArrayList<>();
    private final List<ChannelRow> channelViews = new ArrayList<>();
    private final int[] groupSelection = new int[] {0, 0};
    private final ScrollView groupScroll;
    private final ScrollView channelScroll;
    private final LinearLayout groupList;
    private final LinearLayout channelList;
    private final TextView listHeading;
    private final TextView clock;
    private final TextView nowPlaying;
    private final LinearLayout panel;
    private final View outside;
    private ProgramGuide guide;
    private int tabIndex;
    private int currentIndex;
    private int focusedIndex;

    ChannelPicker(Context context, ChannelCatalog catalog, Set<String> favorites,
            Listener listener) {
        super(context);
        this.catalog = catalog;
        this.favorites = favorites;
        this.listener = listener;
        unit = context.getResources().getDisplayMetrics().heightPixels / 900f;
        regions = ChannelCategories.regions(catalog.channels);
        types = ChannelCategories.types(catalog.channels);
        setVisibility(GONE);
        setFocusable(false);

        setClipChildren(false);
        setClipToPadding(false);
        outside = new View(context);
        outside.setBackground(new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT,
                new int[] {0x70000000, 0x08000000}));
        outside.setFocusable(false);
        outside.setOnClickListener(v -> dismiss());
        addView(outside, new FrameLayout.LayoutParams(-1, -1));

        panel = column();
        panel.setPadding(px(30), px(24), px(30), px(16));
        GradientDrawable glass = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[] {0xfa20232a, 0xfc0c0e13});
        glass.setCornerRadius(px(28));
        glass.setStroke(px(1), 0x20ffffff);
        panel.setBackground(glass);
        panel.setElevation(px(24));
        int width = Math.min(px(1000), Math.round(context.getResources().getDisplayMetrics().widthPixels * 0.65f));
        FrameLayout.LayoutParams panelPosition = new FrameLayout.LayoutParams(width, -1, Gravity.START);
        panelPosition.setMargins(px(28), px(28), px(28), px(28));
        addView(panel, panelPosition);
        panel.setOnClickListener(v -> { });
        panel.setFocusable(false);

        LinearLayout header = row();
        TextView title = text("电视直播", 34, WHITE);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        clock = text("", 21, MUTED);
        clock.setFontFeatureSettings("tnum");
        header.addView(clock);
        TextView close = text("×", 30, MUTED);
        close.setContentDescription("关闭选台");
        close.setGravity(Gravity.CENTER);
        close.setBackground(background(0x12ffffff, 0, 20));
        close.setOnClickListener(v -> dismiss());
        close.setFocusable(false);
        close.setFocusableInTouchMode(false);
        LinearLayout.LayoutParams closePosition = new LinearLayout.LayoutParams(px(40), px(40));
        closePosition.leftMargin = px(22);
        header.addView(close, closePosition);
        panel.addView(header, new LinearLayout.LayoutParams(-1, px(52)));

        LinearLayout tabBar = row();
        LinearLayout segment = row();
        segment.setPadding(px(4), px(4), px(4), px(4));
        segment.setBackground(background(0x66000000, 0x10ffffff, 16));
        for (int i = 0; i < 2; i++) {
            final int index = i;
            TextView tab = text(i == 0 ? "地区" : "类型", 21, WHITE);
            tab.setGravity(Gravity.CENTER);
            focusable(tab, v -> switchTab(index, true));
            tab.setOnFocusChangeListener((v, focused) -> {
                styleTabs();
                animateFocus(v, focused, 1.025f);
            });
            LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(px(114), px(42));
            if (i == 0) position.rightMargin = px(4);
            segment.addView(tab, position);
            tabs.add(tab);
        }
        tabBar.addView(segment);
        TextView count = text(catalog.channels.size() + " 个频道", 17, MUTED);
        count.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        tabBar.addView(count, new LinearLayout.LayoutParams(0, -1, 1));
        LinearLayout.LayoutParams tabPosition = new LinearLayout.LayoutParams(-1, px(68));
        tabPosition.topMargin = px(10);
        panel.addView(tabBar, tabPosition);
        View rule = new View(context);
        rule.setBackgroundColor(0x18ffffff);
        panel.addView(rule, new LinearLayout.LayoutParams(-1, px(1)));

        LinearLayout columns = row();
        columns.setGravity(Gravity.TOP);
        LinearLayout.LayoutParams contentPosition = new LinearLayout.LayoutParams(-1, 0, 1);
        contentPosition.topMargin = px(15);
        panel.addView(columns, contentPosition);
        groupScroll = scroll();
        groupList = column();
        groupScroll.addView(groupList, new ScrollView.LayoutParams(-1, -2));
        groupScroll.setPadding(px(3), px(35), px(3), px(4));
        columns.addView(groupScroll, new LinearLayout.LayoutParams(px(174), -1));
        View separator = new View(context);
        separator.setBackgroundColor(0x10ffffff);
        LinearLayout.LayoutParams separatorPosition = new LinearLayout.LayoutParams(px(1), -1);
        separatorPosition.leftMargin = px(18);
        separatorPosition.rightMargin = px(18);
        columns.addView(separator, separatorPosition);

        LinearLayout channels = column();
        columns.addView(channels, new LinearLayout.LayoutParams(0, -1, 1));
        listHeading = text("", 18, MUTED);
        listHeading.setGravity(Gravity.CENTER_VERTICAL);
        channels.addView(listHeading, new LinearLayout.LayoutParams(-1, px(36)));
        channelScroll = scroll();
        channelScroll.setPadding(px(6), px(5), px(6), px(5));
        channelList = column();
        channelScroll.addView(channelList, new ScrollView.LayoutParams(-1, -2));
        channels.addView(channelScroll, new LinearLayout.LayoutParams(-1, 0, 1));

        View footerRule = new View(context);
        footerRule.setBackgroundColor(0x18ffffff);
        LinearLayout.LayoutParams footerRulePosition = new LinearLayout.LayoutParams(-1, px(1));
        footerRulePosition.topMargin = px(8);
        panel.addView(footerRule, footerRulePosition);
        nowPlaying = text("", 17, GREEN);
        nowPlaying.setSingleLine(true);
        nowPlaying.setEllipsize(TextUtils.TruncateAt.END);
        nowPlaying.setGravity(Gravity.CENTER_VERTICAL);
        panel.addView(nowPlaying, new LinearLayout.LayoutParams(-1, px(35)));
        TextView help = text("↑↓ 选择    ←→ 切换区域    确定播放    菜单收藏    返回收起", 15, MUTED);
        help.setGravity(Gravity.CENTER_VERTICAL);
        help.setSingleLine(true);
        panel.addView(help, new LinearLayout.LayoutParams(-1, px(28)));
        setContentDescription("电视直播选台，地区和类型分类");
    }

    boolean isShowing() { return getVisibility() == VISIBLE; }

    void show(int originalIndex, ProgramGuide currentGuide) {
        currentIndex = originalIndex;
        focusedIndex = originalIndex;
        guide = currentGuide;
        tabIndex = 0;
        groupSelection[0] = 0;
        List<ChannelCategories.Group> groups = groups();
        for (int i = 0; i < groups.size(); i++) {
            if (!groups.get(i).key.equals("all") && groups.get(i).indices.contains(originalIndex)) {
                groupSelection[0] = i;
                break;
            }
        }
        setVisibility(VISIBLE);
        panel.animate().cancel();
        outside.animate().cancel();
        panel.setAlpha(0f);
        panel.setTranslationX(-px(22));
        outside.setAlpha(0f);
        panel.animate().alpha(1f).translationX(0f).setDuration(180)
                .setInterpolator(new DecelerateInterpolator()).start();
        outside.animate().alpha(1f).setDuration(180).start();
        updateClock();
        updateNowPlaying();
        rebuildGroups();
        focusChannel(originalIndex);
        announceForAccessibility("电视直播选台");
    }

    void dismiss() {
        panel.animate().cancel();
        outside.animate().cancel();
        setVisibility(GONE);
        clearFocus();
    }

    void setGuide(ProgramGuide value) {
        guide = value;
        if (isShowing()) {
            updateClock();
            for (ChannelRow row : channelViews) {
                row.programme.setText(programme(row.index));
                ChannelCatalog.Channel channel = catalog.channels.get(row.index);
                row.view.setContentDescription(channel.number + " " + channel.name + "，" + programme(row.index));
            }
        }
    }

    void setCurrentChannel(int index) {
        currentIndex = index;
        if (isShowing()) {
            updateNowPlaying();
            for (ChannelRow row : channelViews) styleRow(row);
        }
    }

    void refreshFavorites() {
        if (isShowing()) for (ChannelRow row : channelViews) styleRow(row);
    }

    private void updateClock() {
        clock.setText(new SimpleDateFormat("HH:mm", Locale.ROOT).format(new Date()));
    }

    private void updateNowPlaying() {
        if (currentIndex >= 0 && currentIndex < catalog.channels.size()) {
            ChannelCatalog.Channel channel = catalog.channels.get(currentIndex);
            nowPlaying.setText("●  当前频道    " + channel.number + "  " + channel.name);
        } else nowPlaying.setText("选择一个频道开始观看");
    }

    private List<ChannelCategories.Group> groups() { return tabIndex == 0 ? regions : types; }

    private void switchTab(int index, boolean focusTab) {
        tabIndex = index;
        rebuildGroups();
        if (focusTab) tabs.get(index).requestFocus();
    }

    private void styleTabs() {
        for (int i = 0; i < tabs.size(); i++) {
            TextView tab = tabs.get(i);
            boolean focused = tab.hasFocus();
            boolean selected = i == tabIndex;
            tab.setTextColor(focused || selected ? INK : MUTED);
            tab.setTypeface(Typeface.create(selected ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
            tab.setBackground(background(focused ? 0xffffffff : selected ? 0xffdfe1e7 : 0x00000000,
                    focused ? WHITE : 0, 12));
        }
    }

    private void rebuildGroups() {
        groupList.removeAllViews();
        groupViews.clear();
        List<ChannelCategories.Group> groups = groups();
        if (groups.isEmpty()) {
            channelList.removeAllViews();
            channelViews.clear();
            listHeading.setText("当前没有频道");
            styleTabs();
            return;
        }
        groupSelection[tabIndex] = Math.min(groupSelection[tabIndex], groups.size() - 1);
        for (int i = 0; i < groups.size(); i++) {
            final int groupIndex = i;
            ChannelCategories.Group group = groups.get(i);
            TextView view = text(group.label, 22, WHITE);
            view.setGravity(Gravity.CENTER_VERTICAL);
            view.setPadding(px(16), 0, px(12), 0);
            view.setSingleLine(true);
            view.setEllipsize(TextUtils.TruncateAt.END);
            view.setContentDescription(group.label + "，" + group.indices.size() + "个频道");
            focusable(view, v -> {
                selectGroup(groupIndex);
                focusChannel(focusedIndex);
            });
            view.setOnFocusChangeListener((v, focus) -> {
                if (focus && groupSelection[tabIndex] != groupIndex) selectGroup(groupIndex);
                styleGroups();
                animateFocus(v, focus, 1.025f);
            });
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, px(51));
            p.bottomMargin = px(6);
            groupList.addView(view, p);
            groupViews.add(view);
        }
        styleTabs();
        styleGroups();
        rebuildChannels();
        final TextView selectedGroup = groupViews.get(groupSelection[tabIndex]);
        groupScroll.post(() -> {
            if (selectedGroup.getParent() == groupList) {
                groupScroll.smoothScrollTo(0, selectedGroup.getTop());
            }
        });
    }

    private void selectGroup(int index) {
        groupSelection[tabIndex] = index;
        styleGroups();
        rebuildChannels();
    }

    private void styleGroups() {
        for (int i = 0; i < groupViews.size(); i++) {
            TextView view = groupViews.get(i);
            boolean focus = view.hasFocus();
            boolean selected = i == groupSelection[tabIndex];
            view.setTextColor(focus ? INK : selected ? WHITE : MUTED);
            view.setTypeface(Typeface.create(focus || selected ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
            view.setBackground(background(focus ? WHITE : selected ? 0x18ffffff : 0x00000000,
                    focus ? WHITE : 0, 13));
        }
    }

    private void rebuildChannels() {
        channelList.removeAllViews();
        channelViews.clear();
        ChannelCategories.Group group = groups().get(groupSelection[tabIndex]);
        listHeading.setText(group.label + "  ·  " + group.indices.size() + " 个频道");
        for (int index : group.indices) {
            ChannelCatalog.Channel channel = catalog.channels.get(index);
            ChannelRow row = new ChannelRow(index);
            row.view = row();
            row.view.setGravity(Gravity.CENTER_VERTICAL);
            row.view.setPadding(px(14), px(10), px(10), px(10));
            row.number = text(String.format(Locale.ROOT, "%03d", channel.number), 20, MUTED);
            row.number.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            row.number.setFontFeatureSettings("tnum");
            row.number.setGravity(Gravity.CENTER);
            LinearLayout.LayoutParams numberPosition = new LinearLayout.LayoutParams(px(53), px(53));
            numberPosition.rightMargin = px(16);
            row.view.addView(row.number, numberPosition);
            LinearLayout words = column();
            LinearLayout headline = row();
            row.name = text(channel.name, 25, WHITE);
            row.name.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            row.name.setSingleLine(true);
            row.name.setEllipsize(TextUtils.TruncateAt.END);
            headline.addView(row.name, new LinearLayout.LayoutParams(0, -2, 1));
            row.playing = text("●", 12, GREEN);
            row.playing.setContentDescription("当前频道");
            row.playing.setPadding(px(12), 0, px(4), 0);
            headline.addView(row.playing);
            words.addView(headline, new LinearLayout.LayoutParams(-1, -2));
            row.programme = text(programme(index), 17, MUTED);
            row.programme.setSingleLine(true);
            row.programme.setEllipsize(TextUtils.TruncateAt.END);
            LinearLayout.LayoutParams epg = new LinearLayout.LayoutParams(-1, -2);
            epg.topMargin = px(7);
            words.addView(row.programme, epg);
            row.view.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
            row.star = text("☆", 25, MUTED);
            row.star.setGravity(Gravity.CENTER);
            row.star.setContentDescription("收藏" + channel.name);
            row.star.setOnClickListener(v -> {
                listener.onFavoriteToggle(index);
                refreshFavorites();
            });
            row.star.setFocusable(false);
            row.star.setFocusableInTouchMode(false);
            row.view.addView(row.star, new LinearLayout.LayoutParams(px(42), px(50)));
            focusable(row.view, v -> {
                dismiss();
                listener.onChannelSelected(index);
            });
            row.view.setOnFocusChangeListener((v, focus) -> {
                if (focus) focusedIndex = index;
                styleRow(row);
                animateFocus(v, focus, 1.012f);
            });
            row.view.setContentDescription(channel.number + " " + channel.name + "，" + programme(index));
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, px(84));
            p.bottomMargin = px(7);
            channelList.addView(row.view, p);
            channelViews.add(row);
            styleRow(row);
        }
        channelScroll.scrollTo(0, 0);
    }

    private String programme(int index) {
        String value = guide == null ? "正在读取节目单…" : guide.current(catalog.channels.get(index).tvgId);
        return "当前暂无节目单".equals(value) ? "暂无节目单" : value;
    }

    private void styleRow(ChannelRow row) {
        boolean focus = row.view.hasFocus();
        boolean current = row.index == currentIndex;
        row.view.setBackground(background(focus ? WHITE : current ? 0xff2b3039 : 0x06ffffff,
                focus ? WHITE : current ? 0x22ffffff : 0, 17));
        row.name.setTextColor(focus ? INK : WHITE);
        row.number.setTextColor(focus ? INK : current ? WHITE : 0xffc4c7d1);
        row.number.setBackground(background(focus ? 0xffe0e2e8 : 0xff343943, 0, 12));
        row.programme.setTextColor(focus ? 0xff656a76 : MUTED);
        row.playing.setTextColor(focus ? 0xff377949 : GREEN);
        row.playing.setVisibility(current ? VISIBLE : GONE);
        boolean favorite = favorites.contains(catalog.channels.get(row.index).id);
        row.star.setText(favorite ? "★" : "☆");
        row.star.setTextColor(focus ? 0xff636975 : favorite ? 0xffe2c58b : 0xff747986);
        row.star.setAlpha(focus || favorite ? 1f : 0.7f);
    }

    private void focusChannel(int preferredIndex) {
        if (channelViews.isEmpty()) { tabs.get(tabIndex).requestFocus(); return; }
        ChannelRow selected = channelViews.get(0);
        for (ChannelRow row : channelViews) {
            if (row.index == preferredIndex) { selected = row; break; }
        }
        selected.view.requestFocus();
        final View target = selected.view;
        channelScroll.post(() -> {
            if (target.getParent() == channelList) {
                channelScroll.smoothScrollTo(0, Math.max(0, target.getTop() - px(91)));
            }
        });
    }

    /** Consume panel navigation before LiveActivity can change channel/source. */
    boolean handleKeyEvent(KeyEvent event) {
        if (!isShowing()) return false;
        int key = event.getKeyCode();
        if (key == KeyEvent.KEYCODE_BACK || key == KeyEvent.KEYCODE_ESCAPE) {
            if (event.getAction() == KeyEvent.ACTION_UP && !event.isCanceled()) dismiss();
            return true;
        }
        boolean navigation = key == KeyEvent.KEYCODE_DPAD_UP || key == KeyEvent.KEYCODE_DPAD_DOWN
                || key == KeyEvent.KEYCODE_DPAD_LEFT || key == KeyEvent.KEYCODE_DPAD_RIGHT
                || key == KeyEvent.KEYCODE_DPAD_CENTER || key == KeyEvent.KEYCODE_ENTER
                || key == KeyEvent.KEYCODE_NUMPAD_ENTER || key == KeyEvent.KEYCODE_MENU;
        if (!navigation) return false;
        if (event.getAction() != KeyEvent.ACTION_DOWN) return true;
        View focus = findFocus();
        int tab = tabs.indexOf(focus);
        int category = groupViews.indexOf(focus);
        int channel = -1;
        for (int i = 0; i < channelViews.size(); i++) if (channelViews.get(i).view == focus) channel = i;
        if (key == KeyEvent.KEYCODE_MENU) {
            if (event.getRepeatCount() == 0) {
                int target = channel >= 0 ? channelViews.get(channel).index : currentIndex;
                if (target >= 0 && target < catalog.channels.size()) {
                    listener.onFavoriteToggle(target);
                    refreshFavorites();
                }
            }
        } else if (key == KeyEvent.KEYCODE_ENTER || key == KeyEvent.KEYCODE_DPAD_CENTER
                || key == KeyEvent.KEYCODE_NUMPAD_ENTER) {
            if (event.getRepeatCount() == 0 && focus != null) focus.performClick();
        } else if (tab >= 0) {
            if (key == KeyEvent.KEYCODE_DPAD_LEFT || key == KeyEvent.KEYCODE_DPAD_RIGHT) {
                switchTab(key == KeyEvent.KEYCODE_DPAD_LEFT ? 0 : 1, true);
            } else if (key == KeyEvent.KEYCODE_DPAD_DOWN && !groupViews.isEmpty()) {
                groupViews.get(groupSelection[tabIndex]).requestFocus();
            }
        } else if (category >= 0) {
            if (key == KeyEvent.KEYCODE_DPAD_RIGHT) focusChannel(focusedIndex);
            else if (key == KeyEvent.KEYCODE_DPAD_UP && category == 0) tabs.get(tabIndex).requestFocus();
            else if (key == KeyEvent.KEYCODE_DPAD_UP || key == KeyEvent.KEYCODE_DPAD_DOWN) {
                int next = Math.max(0, Math.min(groupViews.size() - 1,
                        category + (key == KeyEvent.KEYCODE_DPAD_UP ? -1 : 1)));
                groupViews.get(next).requestFocus();
            }
        } else if (channel >= 0) {
            if (key == KeyEvent.KEYCODE_DPAD_LEFT) groupViews.get(groupSelection[tabIndex]).requestFocus();
            else if (key == KeyEvent.KEYCODE_DPAD_UP && channel == 0) tabs.get(tabIndex).requestFocus();
            else if (key == KeyEvent.KEYCODE_DPAD_UP || key == KeyEvent.KEYCODE_DPAD_DOWN) {
                int next = Math.max(0, Math.min(channelViews.size() - 1,
                        channel + (key == KeyEvent.KEYCODE_DPAD_UP ? -1 : 1)));
                channelViews.get(next).view.requestFocus();
            }
        } else focusChannel(currentIndex);
        return true;
    }

    private int px(int value) { return Math.max(1, Math.round(value * unit)); }
    private TextView text(String value, int size, int color) {
        TextView v = new TextView(getContext());
        v.setText(value);
        v.setTextSize(TypedValue.COMPLEX_UNIT_PX, size * unit);
        v.setTextColor(color);
        v.setFontFeatureSettings("kern");
        v.setIncludeFontPadding(false);
        return v;
    }
    private LinearLayout column() {
        LinearLayout view = new LinearLayout(getContext());
        view.setOrientation(LinearLayout.VERTICAL);
        view.setClipChildren(false);
        view.setClipToPadding(false);
        return view;
    }
    private LinearLayout row() {
        LinearLayout view = new LinearLayout(getContext());
        view.setOrientation(LinearLayout.HORIZONTAL);
        view.setGravity(Gravity.CENTER_VERTICAL);
        view.setClipChildren(false);
        view.setClipToPadding(false);
        return view;
    }
    private ScrollView scroll() {
        ScrollView view = new ScrollView(getContext());
        view.setFillViewport(false);
        view.setFocusable(false);
        view.setVerticalScrollBarEnabled(false);
        view.setOverScrollMode(OVER_SCROLL_NEVER);
        view.setClipToPadding(true);
        return view;
    }
    private GradientDrawable background(int color, int border, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(px(radius));
        if (border != 0) drawable.setStroke(px(1), border);
        return drawable;
    }
    private void animateFocus(View view, boolean focused, float scale) {
        view.animate().cancel();
        view.animate().scaleX(focused ? scale : 1f).scaleY(focused ? scale : 1f)
                .translationZ(focused ? px(4) : 0f).setDuration(160)
                .setInterpolator(new DecelerateInterpolator()).start();
    }
    private void focusable(View view, View.OnClickListener click) {
        view.setFocusable(true);
        view.setFocusableInTouchMode(false);
        view.setClickable(true);
        view.setOnClickListener(click);
        view.setOnHoverListener((v, event) -> {
            if (event.getAction() == MotionEvent.ACTION_HOVER_ENTER) v.requestFocus();
            return false;
        });
    }
    private static final class ChannelRow {
        final int index;
        LinearLayout view;
        TextView number, name, programme, playing, star;
        ChannelRow(int index) { this.index = index; }
    }
}
