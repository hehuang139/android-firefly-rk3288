/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.security.SecureRandom;

/** Arithmetic practice is separate from the original three-question watching gate. */
public final class PuzzleActivity extends TvActivity {
    private final SecureRandom random = new SecureRandom();
    private ParentalPrefs prefs;
    private int passed;
    private boolean practice;
    private boolean completed;
    private TextView feedback;
    private ArithmeticPractice arithmetic;
    private android.window.OnBackInvokedCallback backCallback;
    private final PuzzleInputGate inputGate = new PuzzleInputGate();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new ParentalPrefs(this);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            backCallback = this::home;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, backCallback);
        }
        showPurpose(state);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        PinDialog.cancel(this);
        setIntent(intent);
        if (arithmetic != null) arithmetic.close();
        arithmetic = null;
        inputGate.invalidate();
        passed = 0;
        completed = false;
        showPurpose(null);
    }

    /** The watchdog can reuse this activity with SINGLE_TOP to enter the watching gate. */
    private void showPurpose(Bundle state) {
        practice = getIntent().getBooleanExtra("practice", false);
        if (practice) {
            arithmetic = new ArithmeticPractice(this, state);
            arithmetic.show();
            return;
        }
        passed = state == null ? 0 : state.getInt("passed", 0);
        completed = state != null && state.getBoolean("completed", false);
        if (completed) {
            success();
            return;
        }
        question();
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        if (arithmetic != null) arithmetic.save(state);
        state.putInt("passed", passed);
        state.putBoolean("completed", completed);
        super.onSaveInstanceState(state);
    }

    @Override
    protected void onPause() {
        PinDialog.cancel(this);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (arithmetic != null) arithmetic.close();
        inputGate.invalidate();
        if (android.os.Build.VERSION.SDK_INT >= 33 && backCallback != null) {
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(backCallback);
        }
        super.onDestroy();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (arithmetic != null && arithmetic.handleKeyEvent(event)) return true;
        int key = event.getKeyCode();
        if (arithmetic == null && (key == KeyEvent.KEYCODE_DPAD_CENTER
                || key == KeyEvent.KEYCODE_ENTER || key == KeyEvent.KEYCODE_NUMPAD_ENTER)) {
            if (event.getAction() == KeyEvent.ACTION_DOWN && event.getRepeatCount() == 0
                    && !event.isCanceled()) {
                View focus = getCurrentFocus();
                if (focus != null && focus.isEnabled() && focus.isClickable()) focus.performClick();
            }
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    protected void handleBackAction() { home(); }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            home();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    void returnToKids() { home(); }

    private void question() {
        if (!practice && prefs.dailyExhausted() && prefs.enabled()) {
            dailyLimit();
            return;
        }
        PuzzleRound round = new PuzzleRound(random, passed % 3, prefs.difficulty());
        final int questionId = inputGate.begin(SystemClock.elapsedRealtime());
        LinearLayout page = TvUi.column(this);
        page.setBackgroundColor(TvUi.BACKGROUND);
        page.setPadding(TvUi.dp(this, 42), TvUi.dp(this, 22), TvUi.dp(this, 42), TvUi.dp(this, 22));
        setContentView(page);
        TextView heading = TvUi.text(this, "动动小脑筋  " + (passed + 1) + " / 3", 27, TvUi.TEXT);
        TvUi.emphasize(heading);
        page.addView(heading);
        TextView subtitle = TvUi.text(this, "不计时，慢慢想。完成三题后返回儿童专区。", 14, TvUi.MUTED);
        subtitle.setPadding(0, TvUi.dp(this, 7), 0, TvUi.dp(this, 10));
        page.addView(subtitle);
        TextView instruction = TvUi.text(this, round.instruction, 23, TvUi.TEXT);
        instruction.setGravity(Gravity.CENTER);
        page.addView(instruction, new LinearLayout.LayoutParams(-1, TvUi.dp(this, 36)));
        TextView target = TvUi.text(this, round.target, 62, round.targetColor);
        target.setSingleLine(true);
        target.setGravity(Gravity.CENTER);
        page.addView(target, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout choices = TvUi.row(this);
        for (int index = 0; index < round.answers.length; index++) {
            final boolean correct = index == round.correct;
            Button button = TvUi.button(this, round.answers[index], view -> answer(questionId, correct));
            button.setTextSize(49);
            button.setGravity(Gravity.CENTER);
            button.setTextColor(round.colors[index]);
            LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(0, TvUi.dp(this, 83), 1);
            if (index + 1 < round.answers.length) position.rightMargin = TvUi.dp(this, 16);
            choices.addView(button, position);
        }
        page.addView(choices);
        feedback = TvUi.text(this, "方向键选择，按确定回答。", 16, TvUi.MUTED);
        feedback.setGravity(Gravity.CENTER);
        page.addView(feedback, new LinearLayout.LayoutParams(-1, TvUi.dp(this, 36)));
        addExit(page);
        choices.getChildAt(0).requestFocus();
    }

    private void answer(int questionId, boolean correct) {
        int result = inputGate.submit(questionId, correct, SystemClock.elapsedRealtime());
        if (result == PuzzleInputGate.IGNORED || completed) return;
        if (result == PuzzleInputGate.RETRY) {
            feedback.setText("再看看，你可以再试一次。");
            return;
        }
        passed++;
        if (passed < 3) {
            question();
            return;
        }
        if (!practice && prefs.enabled() && !prefs.puzzlePassed()) {
            dailyLimit();
            return;
        }
        completed = true;
        success();
    }

    private void success() {
        LinearLayout page = TvUi.page(this, "完成啦！", prefs.enabled() && !practice
                ? "可以再看 " + prefs.bonusMinutes() + " 分钟，记得休息眼睛。" : "你完成了三道益智题。");
        TvUi.addButton(page, TvUi.button(this, "返回儿童专区", view -> home()));
        page.getChildAt(page.getChildCount() - 1).requestFocus();
    }

    private void dailyLimit() {
        LinearLayout page = TvUi.page(this, "今天先休息吧", "已达到家长设置的每日观看时间。");
        page.addView(TvUi.text(this, "可以继续玩益智小游戏，或请家长帮忙。", 25, TvUi.ACCENT));
        TvUi.addButton(page, TvUi.button(this, "只玩益智题", view -> {
            passed = 0;
            practice();
        }));
        addExit(page);
    }

    private void practice() {
        startActivity(new Intent(this, PuzzleActivity.class).putExtra("practice", true));
        finish();
    }

    private void addExit(LinearLayout page) {
        LinearLayout exits = TvUi.row(this);
        Button back = TvUi.button(this, "返回儿童专区", view -> home());
        back.setGravity(Gravity.CENTER);
        Button parent = TvUi.button(this, "家长解锁", view -> PinDialog.require(this, () -> {
            prefs.setEnabled(false);
            startActivity(new Intent(this, HomeActivity.class));
            finish();
        }));
        parent.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams left = new LinearLayout.LayoutParams(0, TvUi.dp(this, 54), 1);
        left.rightMargin = TvUi.dp(this, 16);
        exits.addView(back, left);
        exits.addView(parent, new LinearLayout.LayoutParams(0, TvUi.dp(this, 54), 1));
        LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(-1, TvUi.dp(this, 54));
        position.topMargin = TvUi.dp(this, 10);
        page.addView(exits, position);
    }

    private void home() {
        startActivity(new Intent(this, KidsActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP));
        finish();
    }
}
