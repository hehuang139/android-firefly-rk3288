/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.security.SecureRandom;

/** Three untimed picture questions, navigated entirely with the remote. */
public final class PuzzleActivity extends TvActivity {
    private final SecureRandom random = new SecureRandom();
    private ParentalPrefs prefs;
    private int passed;
    private boolean practice;
    private boolean completed;
    private TextView feedback;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new ParentalPrefs(this);
        practice = getIntent().getBooleanExtra("practice", false);
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
        state.putInt("passed", passed);
        state.putBoolean("completed", completed);
        super.onSaveInstanceState(state);
    }

    private void question() {
        if (!practice && prefs.dailyExhausted() && prefs.enabled()) {
            dailyLimit();
            return;
        }
        PuzzleRound round = new PuzzleRound(random, passed % 3, prefs.difficulty());
        LinearLayout page = TvUi.page(this, "动动小脑筋  " + (passed + 1) + " / 3",
                "不计时，慢慢想。方向键选择，确定键回答。");
        TextView instruction = TvUi.text(this, round.instruction, 27, TvUi.TEXT);
        page.addView(instruction);
        TextView target = TvUi.text(this, round.target, 74, round.targetColor);
        target.setGravity(Gravity.CENTER);
        page.addView(target, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout choices = TvUi.row(this);
        for (int index = 0; index < round.answers.length; index++) {
            final boolean correct = index == round.correct;
            Button button = TvUi.button(this, round.answers[index], view -> answer(correct));
            button.setTextSize(64);
            button.setTextColor(round.colors[index]);
            TvUi.addWeighted(choices, button, 116);
        }
        page.addView(choices);
        feedback = TvUi.text(this, "", 21, TvUi.ACCENT);
        page.addView(feedback);
        addExit(page);
        choices.getChildAt(0).requestFocus();
    }

    private void answer(boolean correct) {
        if (!correct) {
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
        TvUi.addButton(page, TvUi.button(this, "返回儿童专区", view -> home()));
        TvUi.addButton(page, TvUi.button(this, "家长解锁", view -> PinDialog.require(this, () -> {
            prefs.setEnabled(false);
            startActivity(new Intent(this, HomeActivity.class));
            finish();
        })));
    }

    private void home() {
        startActivity(new Intent(this, KidsActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP));
        finish();
    }
}
