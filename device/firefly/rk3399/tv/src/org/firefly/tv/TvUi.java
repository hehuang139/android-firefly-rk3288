/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Shared television spacing, surfaces and focus behaviour. */
final class TvUi {
    static final int BACKGROUND = 0xff090b10;
    static final int PANEL = 0xff191c24;
    static final int TEXT = 0xfff5f5f7;
    static final int MUTED = 0xff9ba3b3;
    static final int ACCENT = 0xffdce7ff;

    private TvUi() { }

    static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    static LinearLayout column(Context context) {
        LinearLayout view = new LinearLayout(context);
        view.setOrientation(LinearLayout.VERTICAL);
        view.setClipChildren(false);
        view.setClipToPadding(false);
        return view;
    }

    static LinearLayout row(Context context) {
        LinearLayout view = column(context);
        view.setOrientation(LinearLayout.HORIZONTAL);
        view.setGravity(Gravity.CENTER_VERTICAL);
        return view;
    }

    static LinearLayout page(Activity activity, String title, String subtitle) {
        LinearLayout page = column(activity);
        page.setBackground(new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[] {0xff151a25, BACKGROUND, BACKGROUND}));
        page.setPadding(dp(activity, 44), dp(activity, 25), dp(activity, 44), dp(activity, 22));
        LinearLayout header = row(activity);
        LinearLayout titles = column(activity);
        TextView eyebrow = text(activity, "FIREFLY TV", 10, MUTED);
        eyebrow.setLetterSpacing(.18f);
        titles.addView(eyebrow);
        TextView heading = text(activity, title, 31, TEXT);
        heading.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        LinearLayout.LayoutParams headingPosition = new LinearLayout.LayoutParams(-1, -2);
        headingPosition.topMargin = dp(activity, 8);
        titles.addView(heading, headingPosition);
        header.addView(titles, new LinearLayout.LayoutParams(0, -2, 1));
        TextView back = text(activity, "‹  返回", 14, TEXT);
        back.setGravity(Gravity.CENTER);
        back.setPadding(dp(activity, 17), dp(activity, 11), dp(activity, 17), dp(activity, 11));
        back.setBackground(focusBackground(activity));
        interactive(back, view -> {
            if (activity instanceof TvActivity) ((TvActivity) activity).handleBackAction();
            else activity.finish();
        });
        header.addView(back);
        page.addView(header, new LinearLayout.LayoutParams(-1, -2));
        TextView detail = text(activity, subtitle, 13, MUTED);
        detail.setPadding(0, dp(activity, 9), 0, dp(activity, 19));
        page.addView(detail);
        activity.setContentView(page);
        return page;
    }

    static TextView text(Context context, String value, int size, int color) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setFontFeatureSettings("kern");
        view.setIncludeFontPadding(false);
        return view;
    }

    static GradientDrawable rounded(Context context, int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(context, radius));
        return shape;
    }

    static StateListDrawable focusBackground(Context context) {
        StateListDrawable states = new StateListDrawable();
        GradientDrawable focused = rounded(context, 0xff343944, 14);
        focused.setStroke(dp(context, 2), TEXT);
        GradientDrawable hovered = rounded(context, 0xff282d38, 14);
        hovered.setStroke(dp(context, 1), 0xff8993a5);
        states.addState(new int[] {android.R.attr.state_pressed}, rounded(context, 0xff474e5b, 14));
        states.addState(new int[] {android.R.attr.state_focused}, focused);
        states.addState(new int[] {android.R.attr.state_hovered}, hovered);
        states.addState(new int[0], rounded(context, PANEL, 14));
        return states;
    }

    static void interactive(View view, View.OnClickListener click) {
        if (view.getId() == View.NO_ID) view.setId(View.generateViewId());
        view.setFocusable(true);
        // A first pointer click activates a tile instead of only granting touch focus.
        view.setFocusableInTouchMode(false);
        view.setClickable(true);
        view.setDefaultFocusHighlightEnabled(false);
        view.setOnClickListener(click);
        view.setOnFocusChangeListener((target, focused) -> {
            boolean fullWidthButton = target instanceof Button;
            target.animate().cancel();
            target.animate().scaleX(focused && !fullWidthButton ? 1.04f : 1f)
                    .scaleY(focused && !fullWidthButton ? 1.04f : 1f)
                    .translationZ(focused ? dp(target.getContext(), 7) : 0)
                    .setDuration(180).setInterpolator(new DecelerateInterpolator()).start();
        });
        view.setOnHoverListener((target, event) -> {
            if (event.getAction() == MotionEvent.ACTION_HOVER_ENTER) target.requestFocus();
            return false;
        });
    }

    static Button button(Context context, String label, View.OnClickListener click) {
        Button button = new Button(context);
        button.setText(label);
        button.setTextSize(17);
        button.setTextColor(TEXT);
        button.setAllCaps(false);
        button.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        button.setMinHeight(dp(context, 54));
        button.setPadding(dp(context, 20), dp(context, 11), dp(context, 20), dp(context, 11));
        button.setBackground(focusBackground(context));
        interactive(button, click);
        return button;
    }

    /** An installed application's actual banner, with an honest icon fallback. */
    static Drawable appBanner(PackageManager manager, String packageName) {
        Intent intent = manager.getLeanbackLaunchIntentForPackage(packageName);
        try {
            if (intent != null && intent.getComponent() != null) {
                Drawable banner = manager.getActivityInfo(intent.getComponent(), 0).loadBanner(manager);
                if (banner != null) return banner;
            }
            return manager.getApplicationBanner(packageName);
        } catch (PackageManager.NameNotFoundException | RuntimeException error) {
            return null;
        }
    }

    static Drawable appIcon(PackageManager manager, String packageName) {
        try {
            return manager.getApplicationIcon(packageName);
        } catch (PackageManager.NameNotFoundException | RuntimeException error) {
            return null;
        }
    }

    static int appTint(String packageName) {
        int[] palette = {0xff324b63, 0xff3d355d, 0xff214c4d, 0xff614248, 0xff3d495f, 0xff4c3f33};
        return palette[Math.floorMod(packageName.hashCode(), palette.length)];
    }

    static LinearLayout appTile(Context context, String label, Drawable banner,
            Drawable icon, int tint, View.OnClickListener click) {
        LinearLayout tile = column(context);
        tile.setGravity(Gravity.TOP);
        tile.setDescendantFocusability(ViewGroup.FOCUS_BLOCK_DESCENDANTS);
        tile.setContentDescription(label);
        RatioFrame art = new RatioFrame(context);
        GradientDrawable backdrop = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[] {tint, 0xff151921});
        backdrop.setCornerRadius(dp(context, 14));
        art.setBackground(backdrop);
        art.setClipToOutline(true);
        art.setDuplicateParentStateEnabled(true);
        StateListDrawable ring = new StateListDrawable();
        GradientDrawable focused = rounded(context, 0x00000000, 14);
        focused.setStroke(dp(context, 3), TEXT);
        GradientDrawable hover = rounded(context, 0x00000000, 14);
        hover.setStroke(dp(context, 2), 0xffa6b2c9);
        ring.addState(new int[] {android.R.attr.state_focused}, focused);
        ring.addState(new int[] {android.R.attr.state_hovered}, hover);
        ring.addState(new int[0], rounded(context, 0x00000000, 14));
        art.setForeground(ring);
        if (banner != null) {
            ImageView image = new ImageView(context);
            image.setImageDrawable(banner);
            image.setScaleType(ImageView.ScaleType.FIT_CENTER);
            art.addView(image, new FrameLayout.LayoutParams(-1, -1));
        } else if (icon != null) {
            ImageView image = new ImageView(context);
            image.setImageDrawable(icon);
            image.setScaleType(ImageView.ScaleType.FIT_CENTER);
            art.addView(image, new FrameLayout.LayoutParams(dp(context, 58), dp(context, 58), Gravity.CENTER));
        } else {
            TextView initial = text(context, label.isEmpty() ? "TV" : label.substring(0, 1), 33, TEXT);
            initial.setGravity(Gravity.CENTER);
            art.addView(initial, new FrameLayout.LayoutParams(-1, -1));
        }
        tile.addView(art, new LinearLayout.LayoutParams(-1, -2));
        TextView title = text(context, label, 14, TEXT);
        title.setSingleLine(true);
        title.setEllipsize(TextUtils.TruncateAt.END);
        title.setGravity(Gravity.CENTER);
        title.setDuplicateParentStateEnabled(true);
        title.setTextColor(new ColorStateList(new int[][] {{android.R.attr.state_focused}, {}},
                new int[] {TEXT, 0xffbfc5d0}));
        LinearLayout.LayoutParams caption = new LinearLayout.LayoutParams(-1, dp(context, 30));
        caption.topMargin = dp(context, 6);
        tile.addView(title, caption);
        interactive(tile, click);
        return tile;
    }

    static LinearLayout appCard(Context context, String label, Drawable icon,
            String fallback, View.OnClickListener click) {
        return appTile(context, label, null, icon, appTint(label), click);
    }

    static void addButton(LinearLayout parent, Button button) {
        LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(-1, -2);
        position.bottomMargin = dp(parent.getContext(), 10);
        parent.addView(button, position);
    }

    static void addWeighted(LinearLayout parent, View child, int height) {
        LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(0, dp(parent.getContext(), height), 1);
        position.rightMargin = dp(parent.getContext(), 12);
        parent.addView(child, position);
    }

    static void emphasize(TextView view) {
        view.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
    }

    private static final class RatioFrame extends FrameLayout {
        RatioFrame(Context context) { super(context); }

        @Override protected void onMeasure(int widthSpec, int heightSpec) {
            int width = View.MeasureSpec.getSize(widthSpec);
            super.onMeasure(widthSpec, View.MeasureSpec.makeMeasureSpec(Math.round(width * 9f / 16f),
                    View.MeasureSpec.EXACTLY));
        }
    }
}
