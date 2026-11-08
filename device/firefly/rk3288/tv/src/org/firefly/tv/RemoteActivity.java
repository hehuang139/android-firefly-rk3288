/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.os.IBinder;
import android.os.RemoteException;
import android.os.ServiceManager;
import android.util.Log;
import android.view.KeyEvent;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import vendor.firefly.hardware.remote.IRemote;

/** Learns IR scancodes through the board daemon and displays received Android keys. */
public final class RemoteActivity extends TvActivity {
    private static final String TAG = "FireflyRemote";
    private static final String[] LABELS = {"上", "下", "左", "右", "确定", "返回", "主页",
            "菜单", "音量加", "音量减", "电源"};
    private static final int[] LINUX_KEYS = {103, 108, 105, 106, 28, 158, 102, 139,
            115, 114, 116};
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final AtomicInteger generation = new AtomicInteger();
    private TextView status;
    private TextView lastKey;
    private boolean busy;
    private volatile boolean active;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout page = TvUi.page(this, "遥控器", "板载红外 · 电视 CEC · USB 接收器");
        status = TvUi.text(this, "原配红外遥控器可直接使用；其他红外遥控器可以逐键学习。", 17,
                TvUi.MUTED);
        page.addView(status);
        lastKey = TvUi.text(this, "按任意键，查看接收结果", 19, TvUi.ACCENT);
        lastKey.setPadding(0, TvUi.dp(this, 14), 0, TvUi.dp(this, 14));
        page.addView(lastKey);
        ScrollView scroll = new ScrollView(this);
        LinearLayout actions = TvUi.column(this);
        TvUi.addButton(actions, TvUi.button(this, "开始红外学习", view -> selectLearningKey()));
        TvUi.addButton(actions, TvUi.button(this, "恢复原配遥控键位", view -> confirmReset()));
        TvUi.addButton(actions, TvUi.button(this, "查看接收器状态", view -> refreshStatus()));
        TvUi.addButton(actions, TvUi.button(this, "启用电视 CEC 按键", view -> setCec(true)));
        TvUi.addButton(actions, TvUi.button(this, "关闭电视 CEC 按键", view -> setCec(false)));
        actions.addView(TvUi.text(this, "USB 遥控器接普通 USB-A；CEC 需要电视开启对应功能。\n"
                + "电源键用于系统休眠和唤醒；完全断电后需重新供电。", 16, TvUi.MUTED));
        scroll.addView(actions);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        actions.getChildAt(0).requestFocus();
    }

    @Override
    protected void onStart() {
        super.onStart();
        active = true;
        busy = false;
        refreshStatus();
    }

    @Override
    protected void onStop() {
        active = false;
        generation.incrementAndGet();
        busy = false;
        super.onStop();
    }

    private void selectLearningKey() {
        if (busy) {
            return;
        }
        new AlertDialog.Builder(this).setTitle("选择要学习的功能")
                .setItems(LABELS, (dialog, index) -> learn(index)).show();
    }

    private void learn(int index) {
        int operation = beginOperation();
        if (operation < 0) return;
        status.setText("请在 15 秒内对准板载红外接收器，按下“" + LABELS[index] + "”键。");
        executor.execute(() -> {
            try {
                if (!current(operation)) return;
                JSONObject captured = request(new JSONObject().put("command", "capture")
                        .put("timeout", 15));
                requireOk(captured);
                // Binder capture is synchronous and cannot be interrupted by shutdownNow.
                // Never apply a key captured after the user left this page.
                if (!current(operation)) return;
                JSONObject command = new JSONObject().put("command", "set")
                        .put("scancode", captured.getLong("scancode"))
                        .put("keycode", LINUX_KEYS[index]);
                requireOk(request(command));
                show(operation, "已保存“" + LABELS[index] + "”，可以立即试按。");
            } catch (IOException | JSONException error) {
                Log.w(TAG, "IR learning failed", error);
                show(operation, "学习未完成：" + error.getMessage());
            }
        });
    }

    private void confirmReset() {
        if (busy) {
            return;
        }
        new AlertDialog.Builder(this).setTitle("恢复红外键位")
                .setMessage("清除学习结果，恢复 Firefly 原配遥控器键位？")
                .setNegativeButton("取消", null)
                .setPositiveButton("恢复", (dialog, which) -> command("reset")).show();
    }

    private void refreshStatus() {
        if (!busy) {
            command("status");
        }
    }

    private void command(String name) {
        int operation = beginOperation();
        if (operation < 0) return;
        executor.execute(() -> {
            try {
                if (!current(operation)) return;
                JSONObject result = request(new JSONObject().put("command", name));
                requireOk(result);
                String description = "reset".equals(name) ? "已恢复 Firefly 原配红外键位。"
                        : receiverStatus(result);
                show(operation, description);
            } catch (IOException | JSONException error) {
                Log.w(TAG, "Remote service unavailable", error);
                show(operation, "红外接收器暂不可用；USB 遥控器仍可使用。");
            }
        });
    }

    private static String receiverStatus(JSONObject result) {
        String infrared = result.optBoolean("available") ? "红外接收器就绪。"
                : "暂未检测到红外接收器，USB 遥控器可继续使用。";
        String cec = result.optBoolean("cec_enabled") ? "CEC 按键接收已启用。"
                : "CEC 按键接收已关闭。";
        String device = result.optBoolean("cec_available") ? "已发现 CEC 设备。"
                : "暂未发现可用 CEC 设备。";
        return infrared + "\n" + cec + device;
    }

    private void setCec(boolean enabled) {
        int operation = beginOperation();
        if (operation < 0) return;
        executor.execute(() -> {
            try {
                if (!current(operation)) return;
                requireOk(request(new JSONObject().put("command", "cec").put("enabled", enabled)));
                if (!current(operation)) return;
                JSONObject result = request(new JSONObject().put("command", "status"));
                requireOk(result);
                show(operation, receiverStatus(result));
            } catch (IOException | JSONException error) {
                Log.w(TAG, "Cannot change CEC receiver", error);
                show(operation, "CEC 设置失败：" + error.getMessage());
            }
        });
    }

    private static void requireOk(JSONObject result) throws IOException {
        if (!result.optBoolean("ok")) {
            throw new IOException(result.optString("error", "接收器没有返回有效结果"));
        }
    }

    private static JSONObject request(JSONObject request) throws IOException, JSONException {
        IBinder binder = ServiceManager.checkService("vendor.firefly.hardware.remote.IRemote/default");
        if (binder == null) {
            throw new IOException("遥控服务尚未就绪，请稍后重试");
        }
        try {
            String value = IRemote.Stub.asInterface(binder).request(request.toString());
            if (value == null || value.length() > 8192) {
                throw new IOException("无效接收器响应");
            }
            return new JSONObject(value);
        } catch (RemoteException error) {
            throw new IOException("遥控服务连接中断", error);
        }
    }

    private int beginOperation() {
        if (!active || busy || executor.isShutdown()) return -1;
        busy = true;
        return generation.incrementAndGet();
    }

    private boolean current(int operation) {
        return active && generation.get() == operation && !isFinishing() && !isDestroyed()
                && !Thread.currentThread().isInterrupted();
    }

    private void show(int operation, String message) {
        runOnUiThread(() -> {
            if (current(operation) && !isFinishing() && !isDestroyed()) {
                busy = false;
                status.setText(message);
            }
        });
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_DOWN) {
            lastKey.setText("收到：" + KeyEvent.keyCodeToString(event.getKeyCode())
                    + "  ·  扫描码 " + event.getScanCode());
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    protected void onDestroy() {
        active = false;
        generation.incrementAndGet();
        executor.shutdownNow();
        super.onDestroy();
    }
}
