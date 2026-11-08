/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.net.ConnectivityManager;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.text.format.DateFormat;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** A television-first home with a real resume target and installed app artwork. */
public final class HomeActivity extends TvActivity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private ConnectivityManager connectivity;
    private boolean observing;
    private TextView clock, network, heroTitle, heroDetail, resumeButton;
    private ChannelCatalog catalog;
    private ChannelCatalog.Channel resumeChannel;
    private LinearLayout quickChannels;
    private View firstApp;
    private android.window.OnBackInvokedCallback homeBackCallback;
    private final Runnable tick = new Runnable() {
        @Override public void run() {
            clock.setText(DateFormat.format("HH:mm", new Date()));
            updateNetwork();
            handler.postDelayed(this, 30_000);
        }
    };
    private final ConnectivityManager.NetworkCallback networkCallback =
            new ConnectivityManager.NetworkCallback() {
        @Override public void onAvailable(Network n) { handler.post(() -> updateNetwork()); }
        @Override public void onLost(Network n) { handler.post(() -> updateNetwork()); }
        @Override public void onCapabilitiesChanged(Network n, NetworkCapabilities c) {
            handler.post(() -> updateNetwork());
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        WatchTimeTracker.start(this);
        connectivity = getSystemService(ConnectivityManager.class);
        catalog = ChannelCatalog.load(this);
        buildHome();
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            homeBackCallback = this::handleBackAction;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, homeBackCallback);
        }
    }
    @Override protected void onResume() {
        super.onResume();
        if (new ParentalPrefs(this).enabled()) {
            startActivity(new Intent(this, KidsActivity.class));
            return;
        }
        refreshChannels();
        handler.removeCallbacks(tick);
        handler.post(tick);
        if (connectivity != null && !observing) {
            connectivity.registerNetworkCallback(new android.net.NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(), networkCallback);
            observing = true;
        }
    }
    @Override protected void onPause() {
        handler.removeCallbacksAndMessages(null);
        if (observing) {
            connectivity.unregisterNetworkCallback(networkCallback);
            observing = false;
        }
        super.onPause();
    }
    @Override protected void onDestroy() {
        if (android.os.Build.VERSION.SDK_INT >= 33 && homeBackCallback != null) {
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(homeBackCallback);
        }
        super.onDestroy();
    }
    private int dp(int value) { return TvUi.dp(this, value); }
    private void open(Class<?> activity) { startActivity(new Intent(this, activity)); }
    private void live(boolean picker, String channelId) {
        Intent intent = new Intent(this, LiveActivity.class).putExtra("show_picker", picker);
        if (channelId != null) intent.putExtra("channel_id", channelId);
        startActivity(intent);
    }
    private void buildHome() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(TvUi.BACKGROUND);
        setContentView(root);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setVerticalScrollBarEnabled(false);
        scroll.setClipToPadding(false);
        scroll.setPadding(0, dp(66), 0, dp(24));
        LinearLayout content = TvUi.column(this);
        scroll.addView(content, new ScrollView.LayoutParams(-1, -2));
        root.addView(scroll, new FrameLayout.LayoutParams(-1, -1));
        content.addView(hero(), new LinearLayout.LayoutParams(-1, dp(247)));
        section(content, "我的应用", "全部应用", () -> open(AppsActivity.class));
        HorizontalScrollView appScroll = new HorizontalScrollView(this);
        appScroll.setHorizontalScrollBarEnabled(false);
        appScroll.setClipToPadding(false);
        appScroll.setPadding(dp(43), dp(8), dp(43), dp(14));
        LinearLayout apps = TvUi.row(this);
        appScroll.addView(apps, new HorizontalScrollView.LayoutParams(-2, -2));
        addApp(apps, "哔哩哔哩", AppLaunch.BILIBILI);
        addApp(apps, AppLaunch.youtubeTitle(this), AppLaunch.youtubePackages(this));
        addApp(apps, "酷喵", AppLaunch.YOUKU);
        addApp(apps, "奇异果", AppLaunch.IQIYI);
        addApp(apps, "本地影院", AppLaunch.KODI);
        View kids = TvUi.appTile(this, "儿童专区", null, null, 0xff6652b7,
                v -> open(KidsActivity.class));
        addTile(apps, kids);
        content.addView(appScroll, new LinearLayout.LayoutParams(-1, -2));
        section(content, "频道快捷入口", "浏览全部", () -> live(true, null));
        HorizontalScrollView channelScroll = new HorizontalScrollView(this);
        channelScroll.setHorizontalScrollBarEnabled(false);
        channelScroll.setClipToPadding(false);
        channelScroll.setPadding(dp(43), dp(8), dp(43), dp(22));
        quickChannels = TvUi.row(this);
        channelScroll.addView(quickChannels);
        content.addView(channelScroll, new LinearLayout.LayoutParams(-1, -2));
        TextView foot = TvUi.text(this, "方向键选择     确定打开     返回上一级", 12, TvUi.MUTED);
        foot.setPadding(dp(48), dp(8), dp(48), dp(4));
        content.addView(foot);
        root.addView(navigation(), new FrameLayout.LayoutParams(-1, dp(66), Gravity.TOP));
        resumeButton.post(() -> resumeButton.requestFocus());
    }
    private View navigation() {
        LinearLayout bar = TvUi.row(this);
        bar.setPadding(dp(48), dp(14), dp(40), dp(8));
        bar.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                new int[] {0xff090b10, 0xf2090b10, 0xd9090b10}));
        TextView brand = TvUi.text(this, "firefly  tv", 20, TvUi.TEXT);
        brand.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        brand.setLetterSpacing(.04f);
        bar.addView(brand, new LinearLayout.LayoutParams(dp(148), -2));
        LinearLayout tabs = TvUi.row(this);
        tabs.setPadding(dp(4), dp(4), dp(4), dp(4));
        tabs.setBackground(TvUi.rounded(this, 0xd921242c, 24));
        tabs.addView(nav("首页", true, v -> resumeButton.requestFocus()));
        tabs.addView(nav("直播", false, v -> live(true, null)));
        tabs.addView(nav("应用", false, v -> open(AppsActivity.class)));
        tabs.addView(nav("儿童", false, v -> open(KidsActivity.class)));
        bar.addView(tabs);
        bar.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1));
        network = TvUi.text(this, "", 12, TvUi.MUTED);
        network.setGravity(Gravity.CENTER_VERTICAL);
        network.setPadding(dp(8), 0, dp(14), 0);
        bar.addView(network);
        clock = TvUi.text(this, "", 16, TvUi.TEXT);
        clock.setTypeface(Typeface.create("sans-serif-medium", 0));
        bar.addView(clock);
        TextView settings = nav("设置", false, v -> open(SettingsActivity.class));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(dp(70), dp(38));
        p.leftMargin = dp(16);
        bar.addView(settings, p);
        return bar;
    }
    private TextView nav(String label, boolean selected, View.OnClickListener click) {
        TextView view = TvUi.text(this, label, 15, selected ? 0xff10131a : 0xffd3d6df);
        view.setGravity(Gravity.CENTER);
        view.setPadding(dp(19), dp(9), dp(19), dp(9));
        StateListDrawable states = new StateListDrawable();
        GradientDrawable focus = TvUi.rounded(this, 0xfff5f5f7, 21);
        focus.setStroke(dp(1), 0xffffffff);
        states.addState(new int[]{android.R.attr.state_focused}, focus);
        states.addState(new int[]{android.R.attr.state_pressed}, TvUi.rounded(this, 0xffcfd3df, 21));
        states.addState(new int[0], TvUi.rounded(this, selected ? 0xffe9ebf1 : 0x00000000, 21));
        view.setBackground(states);
        TvUi.interactive(view, click);
        view.setOnFocusChangeListener((v, focused) -> {
            view.setTextColor(focused || selected ? 0xff10131a : 0xffd3d6df);
            view.animate().scaleX(focused ? 1.035f : 1f).scaleY(focused ? 1.035f : 1f)
                    .setDuration(180).start();
        });
        return view;
    }
    private View hero() {
        FrameLayout hero = new FrameLayout(this);
        hero.addView(new EarthBackdrop(this), new FrameLayout.LayoutParams(-1, -1));
        LinearLayout copy = TvUi.column(this);
        copy.setPadding(dp(48), dp(23), dp(32), dp(18));
        TextView tag = TvUi.text(this, "电视直播  /  继续观看", 12, 0xffc7d1d9);
        tag.setLetterSpacing(.10f);
        copy.addView(tag);
        heroTitle = TvUi.text(this, "电视直播", 43, TvUi.TEXT);
        heroTitle.setTypeface(Typeface.create("sans-serif-medium", 0));
        heroTitle.setSingleLine();
        heroTitle.setEllipsize(TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams titlePos = new LinearLayout.LayoutParams(dp(540), dp(66));
        titlePos.topMargin = dp(9);
        copy.addView(heroTitle, titlePos);
        heroDetail = TvUi.text(this, "从你上次停留的频道，继续。", 15, 0xffc0c7d1);
        heroDetail.setSingleLine();
        heroDetail.setEllipsize(TextUtils.TruncateAt.END);
        copy.addView(heroDetail, new LinearLayout.LayoutParams(dp(510), dp(27)));
        LinearLayout actions = TvUi.row(this);
        LinearLayout.LayoutParams actionPos = new LinearLayout.LayoutParams(-2, dp(46));
        actionPos.topMargin = dp(19);
        copy.addView(actions, actionPos);
        resumeButton = action("▶  继续观看", true,
                v -> live(false, resumeChannel == null ? null : resumeChannel.id));
        actions.addView(resumeButton, new LinearLayout.LayoutParams(dp(154), -1));
        TextView browse = action("选择频道", false, v -> live(true, null));
        LinearLayout.LayoutParams browsePos = new LinearLayout.LayoutParams(dp(124), -1);
        browsePos.leftMargin = dp(12);
        actions.addView(browse, browsePos);
        hero.addView(copy, new FrameLayout.LayoutParams(-1, -1));
        TextView credit = TvUi.text(this, "地球之夜  /  NASA", 10, 0xff9eada9);
        FrameLayout.LayoutParams creditPos = new FrameLayout.LayoutParams(-2, -2, Gravity.END | Gravity.BOTTOM);
        creditPos.rightMargin = dp(48); creditPos.bottomMargin = dp(31);
        hero.addView(credit, creditPos);
        return hero;
    }
    private TextView action(String label, boolean primary, View.OnClickListener click) {
        TextView v = TvUi.text(this, label, 16, primary ? 0xff11141b : TvUi.TEXT);
        v.setTypeface(Typeface.create("sans-serif-medium", 0));
        v.setGravity(Gravity.CENTER);
        StateListDrawable states = new StateListDrawable();
        GradientDrawable focus = TvUi.rounded(this, 0xffffffff, 9);
        focus.setStroke(dp(2), 0xffffffff);
        states.addState(new int[]{android.R.attr.state_focused}, focus);
        states.addState(new int[]{android.R.attr.state_pressed}, TvUi.rounded(this, 0xffbec4d1, 9));
        states.addState(new int[0], TvUi.rounded(this, primary ? 0xffeef0f4 : 0xc2333842, 9));
        v.setBackground(states);
        TvUi.interactive(v, click);
        v.setOnFocusChangeListener((view, focused) -> {
            v.setTextColor(primary || focused ? 0xff11141b : TvUi.TEXT);
            v.animate().scaleX(focused ? 1.045f : 1f).scaleY(focused ? 1.045f : 1f)
                    .translationZ(focused ? dp(8) : 0).setDuration(180).start();
        });
        return v;
    }
    private void section(LinearLayout parent, String title, String more, Runnable action) {
        LinearLayout row = TvUi.row(this);
        row.setPadding(dp(48), dp(12), dp(45), dp(3));
        TextView label = TvUi.text(this, title, 21, TvUi.TEXT);
        label.setTypeface(Typeface.create("sans-serif-medium", 0));
        row.addView(label, new LinearLayout.LayoutParams(0, -2, 1));
        TextView link = TvUi.text(this, more + "  ›", 13, TvUi.MUTED);
        link.setPadding(dp(12), dp(9), dp(12), dp(9));
        link.setBackground(TvUi.focusBackground(this));
        TvUi.interactive(link, v -> action.run());
        row.addView(link);
        parent.addView(row);
    }
    private void addApp(LinearLayout row, String label, String[] packages) {
        PackageManager pm = getPackageManager();
        Intent intent = AppLaunch.resolve(pm, packages);
        if (intent == null) return;
        android.content.ComponentName component = intent.resolveActivity(pm);
        if (component == null) return;
        String name = component.getPackageName();
        View tile = TvUi.appTile(this, label, TvUi.appBanner(pm, name), TvUi.appIcon(pm, name),
                TvUi.appTint(name), v -> AppLaunch.open(this, packages));
        if (firstApp == null) firstApp = tile;
        addTile(row, tile);
    }
    private void addTile(LinearLayout row, View tile) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(dp(164), -2);
        p.leftMargin = dp(5); p.rightMargin = dp(10);
        row.addView(tile, p);
    }
    private void refreshChannels() {
        catalog = ChannelCatalog.load(this);
        SharedPreferences prefs = getSharedPreferences("live", MODE_PRIVATE);
        int index = Math.max(0, Math.min(prefs.getInt("last_channel", 0), catalog.channels.size() - 1));
        resumeChannel = catalog.channels.isEmpty() ? null : catalog.channels.get(index);
        heroTitle.setText(resumeChannel == null ? "大屏，随心看。" : resumeChannel.name);
        heroDetail.setText(resumeChannel == null ? "你的应用、直播和私人影院，一个主页。"
                : "上次观看  ·  " + String.format(java.util.Locale.ROOT, "%03d", resumeChannel.number)
                  + " 频道    /    " + (resumeChannel.province.isBlank() ? "电视直播" : resumeChannel.province));
        resumeButton.setText(resumeChannel == null ? "▶  看直播" : "▶  继续观看");
        quickChannels.removeAllViews();
        Set<String> favorites = new HashSet<>(prefs.getStringSet("favorites", new HashSet<>()));
        List<ChannelCatalog.Channel> selected = new ArrayList<>();
        Set<String> added = new HashSet<>();
        if (resumeChannel != null) { selected.add(resumeChannel); added.add(resumeChannel.id); }
        for (ChannelCatalog.Channel c : catalog.channels) {
            if (selected.size() < 8 && favorites.contains(c.id) && added.add(c.id)) selected.add(c);
        }
        for (ChannelCatalog.Channel c : catalog.channels) {
            if (selected.size() < 8 && added.add(c.id)) selected.add(c);
        }
        for (ChannelCatalog.Channel c : selected) {
            LinearLayout card = TvUi.column(this);
            card.setPadding(dp(18), dp(16), dp(18), dp(16));
            card.setBackground(TvUi.focusBackground(this));
            TvUi.interactive(card, v -> live(false, c.id));
            card.setContentDescription("播放频道 " + c.number + " " + c.name);
            TextView number = TvUi.text(this, String.format(java.util.Locale.ROOT, "%03d", c.number), 26, 0xffb5c1d0);
            number.setTypeface(Typeface.create("sans-serif-light", 0));
            card.addView(number);
            TextView name = TvUi.text(this, c.name, 15, TvUi.TEXT);
            name.setSingleLine(); name.setEllipsize(TextUtils.TruncateAt.END);
            LinearLayout.LayoutParams np = new LinearLayout.LayoutParams(-1, -2); np.topMargin = dp(10);
            card.addView(name, np);
            LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(dp(164), dp(101));
            cp.leftMargin = dp(5); cp.rightMargin = dp(10);
            quickChannels.addView(card, cp);
        }
    }
    private void updateNetwork() {
        if (network == null || connectivity == null) return;
        String label = "离线";
        for (Network n : connectivity.getAllNetworks()) {
            NetworkCapabilities c = connectivity.getNetworkCapabilities(n);
            LinkProperties p = connectivity.getLinkProperties(n);
            if (c == null || p == null || p.getLinkAddresses().isEmpty()) continue;
            if (c.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) { label = "有线网络"; break; }
            if (c.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) label = "无线网络";
            else if ("离线".equals(label)) label = "已连接";
        }
        network.setText(label);
    }
    @Override protected void handleBackAction() { }
    @Override public boolean onKeyDown(int keyCode, KeyEvent event) {
        return keyCode == KeyEvent.KEYCODE_BACK || super.onKeyDown(keyCode, event);
    }

    /** NASA ISS photograph with a static scrim; no video wallpaper or blur pass. */
    private static final class EarthBackdrop extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
        private Bitmap image;
        EarthBackdrop(android.content.Context context) {
            super(context);
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
            try (InputStream in = context.getAssets().open("earth-aurora.jpg")) {
                BitmapFactory.Options options = new BitmapFactory.Options();
                options.inPreferredConfig = Bitmap.Config.RGB_565;
                image = BitmapFactory.decodeStream(in, null, options);
            } catch (IOException ignored) { }
        }
        @Override protected void onDraw(Canvas canvas) {
            float w = getWidth(), h = getHeight();
            canvas.drawColor(0xff090b10);
            if (image != null) {
                // Fill the hero with the illuminated limb, retaining stars above it.
                Rect source = new Rect(0, image.getHeight() / 4, image.getWidth(), image.getHeight());
                paint.setShader(null);
                canvas.drawBitmap(image, source, new RectF(w * .21f, -h * .06f, w, h * 1.10f), paint);
            }
            paint.setShader(new LinearGradient(0, 0, w * .82f, 0,
                    new int[]{0xff090b10, 0xf5090b10, 0x68090b10, 0x00090b10},
                    new float[]{0f, .36f, .72f, 1f}, Shader.TileMode.CLAMP));
            canvas.drawRect(0, 0, w, h, paint);
            paint.setShader(new LinearGradient(0, 0, 0, h,
                    new int[]{0xff090b10, 0x00090b10, 0x10090b10, 0xff090b10},
                    new float[]{0f, .16f, .65f, 1f}, Shader.TileMode.CLAMP));
            canvas.drawRect(0, 0, w, h, paint);
            paint.setShader(null);
        }
    }
}
