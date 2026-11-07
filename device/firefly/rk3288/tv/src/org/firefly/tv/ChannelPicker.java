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

/** Two-column TV channel browser. Display groups always retain catalog indices. */
final class ChannelPicker extends FrameLayout {
    interface Listener {
        void onChannelSelected(int originalIndex);
        void onFavoriteToggle(int originalIndex);
    }

    private static final int WHITE = 0xfff0f6ff;
    private static final int MUTED = 0xff9eb3cc;
    private static final int BLUE = 0xff7bd4ff;
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

        View outside = new View(context);
        outside.setBackgroundColor(0x16040b16);
        outside.setFocusable(false);
        outside.setOnClickListener(v -> dismiss());
        addView(outside, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout panel = column();
        panel.setPadding(px(34), px(28), px(30), px(18));
        panel.setBackground(new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT,
                new int[] {0xff09192d, 0xff0e223a}));
        int width = Math.round(context.getResources().getDisplayMetrics().widthPixels * 0.65f);
        addView(panel, new FrameLayout.LayoutParams(width, -1, Gravity.START));
        panel.setOnClickListener(v -> { });
        panel.setFocusable(false);

        LinearLayout header = row();
        TextView title = text("电视直播", 34, WHITE);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        clock = text("", 25, WHITE);
        header.addView(clock);
        TextView close = text("关闭 ×", 18, MUTED);
        close.setPadding(px(22), px(12), 0, px(12));
        close.setOnClickListener(v -> dismiss());
        close.setFocusable(false);
        close.setFocusableInTouchMode(false);
        header.addView(close);
        panel.addView(header, new LinearLayout.LayoutParams(-1, px(66)));

        LinearLayout tabBar = row();
        for (int i = 0; i < 2; i++) {
            final int index = i;
            TextView tab = text(i == 0 ? "地区" : "类型", 23, WHITE);
            tab.setGravity(Gravity.CENTER);
            focusable(tab, v -> switchTab(index, true));
            tab.setOnFocusChangeListener((v, focused) -> styleTabs());
            LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(px(126), px(50));
            position.rightMargin = px(12);
            tabBar.addView(tab, position);
            tabs.add(tab);
        }
        TextView count = text(catalog.channels.size() + " 个频道", 18, MUTED);
        count.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        tabBar.addView(count, new LinearLayout.LayoutParams(0, -1, 1));
        panel.addView(tabBar, new LinearLayout.LayoutParams(-1, px(62)));
        View rule = new View(context);
        rule.setBackgroundColor(0xff25415e);
        panel.addView(rule, new LinearLayout.LayoutParams(-1, px(1)));

        LinearLayout columns = row();
        columns.setGravity(Gravity.TOP);
        LinearLayout.LayoutParams contentPosition = new LinearLayout.LayoutParams(-1, 0, 1);
        contentPosition.topMargin = px(18);
        panel.addView(columns, contentPosition);
        groupScroll = scroll();
        groupList = column();
        groupScroll.addView(groupList, new ScrollView.LayoutParams(-1, -2));
        columns.addView(groupScroll, new LinearLayout.LayoutParams(px(224), -1));
        View separator = new View(context);
        separator.setBackgroundColor(0xff213a54);
        LinearLayout.LayoutParams separatorPosition = new LinearLayout.LayoutParams(px(1), -1);
        separatorPosition.leftMargin = px(14);
        separatorPosition.rightMargin = px(22);
        columns.addView(separator, separatorPosition);

        LinearLayout channels = column();
        columns.addView(channels, new LinearLayout.LayoutParams(0, -1, 1));
        listHeading = text("", 20, MUTED);
        listHeading.setGravity(Gravity.CENTER_VERTICAL);
        channels.addView(listHeading, new LinearLayout.LayoutParams(-1, px(36)));
        channelScroll = scroll();
        channelList = column();
        channelScroll.addView(channelList, new ScrollView.LayoutParams(-1, -2));
        channels.addView(channelScroll, new LinearLayout.LayoutParams(-1, 0, 1));

        TextView help = text("↑↓ 选择    ←→ 分类 / 频道    确定 播放    返回 收起", 17, MUTED);
        help.setGravity(Gravity.CENTER_VERTICAL);
        help.setSingleLine(true);
        panel.addView(help, new LinearLayout.LayoutParams(-1, px(54)));
        setContentDescription("电视直播选台，地区和类型分类");
    }

    boolean isShowing() { return getVisibility() == VISIBLE; }

    void show(int originalIndex, ProgramGuide currentGuide) {
        currentIndex = originalIndex;
        focusedIndex = originalIndex;
        guide = currentGuide;
        tabIndex = 0;
        List<ChannelCategories.Group> groups = groups();
        for (int i = 0; i < groups.size(); i++) {
            if (!groups.get(i).key.equals("all") && groups.get(i).indices.contains(originalIndex)) {
                groupSelection[0] = i;
                break;
            }
        }
        setVisibility(VISIBLE);
        updateClock();
        rebuildGroups();
        focusChannel(originalIndex);
        announceForAccessibility("电视直播选台");
    }

    void dismiss() {
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
        if (isShowing()) for (ChannelRow row : channelViews) styleRow(row);
    }

    void refreshFavorites() {
        if (isShowing()) for (ChannelRow row : channelViews) styleRow(row);
    }

    private void updateClock() {
        clock.setText(new SimpleDateFormat("HH:mm", Locale.ROOT).format(new Date()));
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
            tab.setTextColor(focused ? 0xff09213b : i == tabIndex ? BLUE : MUTED);
            tab.setBackground(background(focused ? 0xffd7f0ff : i == tabIndex ? 0xff214766 : 0xff10283f,
                    focused ? BLUE : 0x00000000));
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
            TextView view = text(group.label, 23, WHITE);
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
            });
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, px(59));
            p.bottomMargin = px(7);
            groupList.addView(view, p);
            groupViews.add(view);
        }
        styleTabs();
        styleGroups();
        rebuildChannels();
        groupScroll.post(() -> groupScroll.smoothScrollTo(0,
                groupViews.get(groupSelection[tabIndex]).getTop() - px(12)));
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
            view.setTextColor(focus ? 0xff09213b : selected ? BLUE : WHITE);
            view.setBackground(background(focus ? 0xffd7f0ff : selected ? 0xff173e5b : 0x00000000,
                    focus ? BLUE : 0x00000000));
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
            row.view.setPadding(px(14), px(12), px(10), px(12));
            row.number = text(String.format(Locale.ROOT, "%03d", channel.number), 24, MUTED);
            row.number.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            row.view.addView(row.number, new LinearLayout.LayoutParams(px(65), -2));
            LinearLayout words = column();
            LinearLayout headline = row();
            row.name = text(channel.name, 26, WHITE);
            row.name.setSingleLine(true);
            row.name.setEllipsize(TextUtils.TruncateAt.END);
            headline.addView(row.name, new LinearLayout.LayoutParams(0, -2, 1));
            row.playing = text("当前", 16, BLUE);
            row.playing.setPadding(px(10), 0, 0, 0);
            headline.addView(row.playing);
            words.addView(headline, new LinearLayout.LayoutParams(-1, -2));
            row.programme = text(programme(index), 19, MUTED);
            row.programme.setSingleLine(true);
            row.programme.setEllipsize(TextUtils.TruncateAt.END);
            LinearLayout.LayoutParams epg = new LinearLayout.LayoutParams(-1, -2);
            epg.topMargin = px(9);
            words.addView(row.programme, epg);
            row.view.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
            row.star = text("☆", 28, MUTED);
            row.star.setGravity(Gravity.CENTER);
            row.star.setContentDescription("收藏" + channel.name);
            row.star.setOnClickListener(v -> {
                listener.onFavoriteToggle(index);
                refreshFavorites();
            });
            row.star.setFocusable(false);
            row.star.setFocusableInTouchMode(false);
            row.view.addView(row.star, new LinearLayout.LayoutParams(px(48), px(52)));
            focusable(row.view, v -> {
                dismiss();
                listener.onChannelSelected(index);
            });
            row.view.setOnFocusChangeListener((v, focus) -> {
                if (focus) focusedIndex = index;
                styleRow(row);
            });
            row.view.setContentDescription(channel.number + " " + channel.name + "，" + programme(index));
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, px(91));
            p.bottomMargin = px(8);
            channelList.addView(row.view, p);
            channelViews.add(row);
            styleRow(row);
        }
        channelScroll.scrollTo(0, 0);
    }

    private String programme(int index) {
        return guide == null ? "正在读取节目单…" : guide.current(catalog.channels.get(index).tvgId);
    }

    private void styleRow(ChannelRow row) {
        boolean focus = row.view.hasFocus();
        boolean current = row.index == currentIndex;
        row.view.setBackground(background(focus ? 0xffe0f3ff : current ? 0xff173b58 : 0xff102b44,
                focus ? BLUE : current ? 0xff2e6284 : 0x00000000));
        row.name.setTextColor(focus ? 0xff09213b : WHITE);
        row.number.setTextColor(focus ? 0xff164769 : current ? BLUE : MUTED);
        row.programme.setTextColor(focus ? 0xff36516a : MUTED);
        row.playing.setTextColor(focus ? 0xff15567c : BLUE);
        row.playing.setVisibility(current ? VISIBLE : GONE);
        boolean favorite = favorites.contains(catalog.channels.get(row.index).id);
        row.star.setText(favorite ? "★" : "☆");
        row.star.setTextColor(focus ? 0xff15567c : favorite ? 0xffffd378 : MUTED);
    }

    private void focusChannel(int preferredIndex) {
        if (channelViews.isEmpty()) { tabs.get(tabIndex).requestFocus(); return; }
        ChannelRow selected = channelViews.get(0);
        for (ChannelRow row : channelViews) {
            if (row.index == preferredIndex) { selected = row; break; }
        }
        selected.view.requestFocus();
        final View target = selected.view;
        channelScroll.post(() -> channelScroll.smoothScrollTo(0, target.getTop() - px(100)));
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
                listener.onFavoriteToggle(channel >= 0 ? channelViews.get(channel).index : currentIndex);
                refreshFavorites();
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
        v.setIncludeFontPadding(false);
        return v;
    }
    private LinearLayout column() {
        LinearLayout view = new LinearLayout(getContext());
        view.setOrientation(LinearLayout.VERTICAL);
        return view;
    }
    private LinearLayout row() {
        LinearLayout view = new LinearLayout(getContext());
        view.setOrientation(LinearLayout.HORIZONTAL);
        view.setGravity(Gravity.CENTER_VERTICAL);
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
    private GradientDrawable background(int color, int border) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(px(7));
        if (border != 0) drawable.setStroke(px(2), border);
        return drawable;
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
