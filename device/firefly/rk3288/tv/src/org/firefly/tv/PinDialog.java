/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.InputType;
import android.view.KeyEvent;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Toast;

/** All destructive or parent-only actions require a fresh PIN challenge. */
final class PinDialog {
    private PinDialog() { }

    static void require(Activity activity, Runnable action) {
        if (!new ParentalPrefs(activity).hasPin()) {
            create(activity, action);
            return;
        }
        EditText input = field(activity, "输入家长 PIN");
        AlertDialog dialog = new AlertDialog.Builder(activity).setTitle("家长验证")
                .setView(input).setNegativeButton("取消", null)
                .setPositiveButton("确定", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(view -> verify(activity, dialog, input, action)));
        cancelWithEscape(dialog);
        dialog.show();
    }

    private static void verify(Activity activity, AlertDialog dialog, EditText input, Runnable action) {
        ParentalPrefs prefs = new ParentalPrefs(activity);
        if (prefs.verifyPin(input.getText().toString())) {
            dialog.dismiss();
            action.run();
        } else {
            input.setText("");
            String text = prefs.lockSeconds() > 0 ? "请等待 " + prefs.lockSeconds() + " 秒后再试"
                    : "PIN 不正确";
            Toast.makeText(activity, text, Toast.LENGTH_SHORT).show();
        }
    }

    static void create(Activity activity, Runnable action) {
        LinearLayout form = TvUi.column(activity);
        EditText first = field(activity, "设置 4–8 位数字 PIN");
        EditText second = field(activity, "再次输入 PIN");
        form.addView(first);
        form.addView(second);
        AlertDialog dialog = new AlertDialog.Builder(activity).setTitle("建立家长 PIN")
                .setMessage("请保存好 PIN，孩子不能通过益智题修改家长设置。")
                .setView(form).setNegativeButton("取消", null)
                .setPositiveButton("保存", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(view -> save(activity, dialog, first, second, action)));
        cancelWithEscape(dialog);
        dialog.show();
    }

    private static void cancelWithEscape(AlertDialog dialog) {
        dialog.setOnKeyListener((ignored, code, event) -> {
            if (code != KeyEvent.KEYCODE_ESCAPE || !event.hasNoModifiers()) {
                return false;
            }
            if (event.getAction() == KeyEvent.ACTION_UP && !event.isCanceled()) {
                dialog.cancel();
            }
            return true;
        });
    }

    private static void save(Activity activity, AlertDialog dialog, EditText first,
            EditText second, Runnable action) {
        String pin = first.getText().toString();
        if (!pin.matches("[0-9]{4,8}") || !pin.equals(second.getText().toString())) {
            Toast.makeText(activity, "请输入相同的 4–8 位数字 PIN", Toast.LENGTH_SHORT).show();
            return;
        }
        new ParentalPrefs(activity).setPin(pin);
        dialog.dismiss();
        action.run();
    }

    private static EditText field(Activity activity, String hint) {
        EditText result = new EditText(activity);
        result.setHint(hint);
        result.setSingleLine(true);
        result.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        return result;
    }
}
