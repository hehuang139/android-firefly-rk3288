/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import java.text.Collator;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** A gallery of real installed application banners, navigable with a remote. */
public final class AppsActivity extends TvActivity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        PackageManager manager = getPackageManager();
        Map<String, String> installed = new LinkedHashMap<>();
        collect(manager, Intent.CATEGORY_LEANBACK_LAUNCHER, installed);
        collect(manager, Intent.CATEGORY_LAUNCHER, installed);
        List<String> packages = new ArrayList<>(installed.keySet());
        Collator collator = Collator.getInstance(Locale.getDefault());
        packages.sort((left, right) -> collator.compare(installed.get(left), installed.get(right)));

        LinearLayout page = TvUi.page(this, "你的应用", installed.size() + " 个已安装应用 · 按确定键打开");
        ScrollView scroll = new ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        // Keep the viewport clipping: focused tiles have their own safe padding.
        scroll.setClipToPadding(true);
        LinearLayout grid = TvUi.column(this);
        grid.setPadding(dp(7), dp(7), dp(7), dp(10));
        LinearLayout row = null;
        View first = null;
        int index = 0;
        for (String name : packages) {
            if (index % 4 == 0) {
                row = TvUi.row(this);
                row.setGravity(android.view.Gravity.TOP);
                LinearLayout.LayoutParams rowPosition = new LinearLayout.LayoutParams(-1, -2);
                rowPosition.bottomMargin = dp(20);
                grid.addView(row, rowPosition);
            }
            View tile = TvUi.appTile(this, installed.get(name), TvUi.appBanner(manager, name),
                    TvUi.appIcon(manager, name), TvUi.appTint(name), view -> AppLaunch.open(this, name));
            LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(0, -2, 1);
            if (index % 4 != 3) position.rightMargin = dp(18);
            row.addView(tile, position);
            if (first == null) first = tile;
            index++;
        }
        if (row != null) while (index % 4 != 0) {
            LinearLayout.LayoutParams empty = new LinearLayout.LayoutParams(0, 1, 1);
            if (index % 4 != 3) empty.rightMargin = dp(18);
            row.addView(new View(this), empty);
            index++;
        }
        if (packages.isEmpty()) grid.addView(TvUi.text(this, "安装应用后，它们会出现在这里。", 18, TvUi.MUTED));
        scroll.addView(grid);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        if (first != null) first.requestFocus();
    }

    private int dp(int value) { return TvUi.dp(this, value); }

    private void collect(PackageManager manager, String category, Map<String, String> result) {
        for (ResolveInfo info : manager.queryIntentActivities(
                new Intent(Intent.ACTION_MAIN).addCategory(category), 0)) {
            String name = info.activityInfo.packageName;
            if (!getPackageName().equals(name)) result.putIfAbsent(name, info.loadLabel(manager).toString());
        }
    }
}
