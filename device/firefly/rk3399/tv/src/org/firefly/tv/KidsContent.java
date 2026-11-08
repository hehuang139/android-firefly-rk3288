/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

/** Curated provider entries; approval is separate from the provider's own child mode. */
final class KidsContent {
    static final String[] LABELS = {"银河奇异果 · 少儿内容", "酷喵 · 少儿内容", "Kodi · 本地益智视频"};
    static final String[][] PACKAGES = {AppLaunch.IQIYI, AppLaunch.YOUKU, AppLaunch.KODI};
    static final String[] NOTES = {
        "适合寻找颜色、数字、自然启蒙节目；先在奇异果内启用儿童模式及内容分龄。",
        "可选择芝麻街等学龄前启蒙内容；先在酷喵内启用儿童模式及内容分龄。",
        "由家长准备自有或获授权的启蒙视频；建议只添加儿童视频文件夹。"
    };

    private KidsContent() { }

    static String installed(android.app.Activity activity, int index) {
        android.content.Intent intent = AppLaunch.resolve(activity.getPackageManager(), PACKAGES[index]);
        return intent == null ? "" : intent.getComponent().getPackageName();
    }
}
