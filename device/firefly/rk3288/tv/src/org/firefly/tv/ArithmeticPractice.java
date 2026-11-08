/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.security.SecureRandom;
import java.util.UUID;

/** Untimed, local arithmetic practice; this class never modifies watching time. */
final class ArithmeticPractice {
    private final PuzzleActivity activity;
    private final KidsProgress progress;
    private ArithmeticRound.Session session;
    private TextView feedback;
    private Button next;
    private Button[] choices;
    private long nextReadyAt;
    private boolean active = true;

    ArithmeticPractice(PuzzleActivity activity, Bundle state) {
        this.activity = activity;
        progress = new KidsProgress(activity);
        if (state != null && state.containsKey("math.id")) {
            try {
                session = ArithmeticRound.Session.restore(state.getString("math.id"),
                        state.getString("math.mode"), state.getInt("math.limit"),
                        state.getInt("math.count"), state.getLong("math.seed"),
                        state.getInt("math.index"), state.getInt("math.answered"),
                        state.getInt("math.correct"), state.getBoolean("math.attempted"),
                        state.getBoolean("math.solved"));
            } catch (IllegalArgumentException invalidState) {
                session = null;
            }
        }
        if (session == null) newSession();
    }

    private void newSession() {
        ParentalPrefs settings = new ParentalPrefs(activity);
        session = new ArithmeticRound.Session(UUID.randomUUID().toString(),
                activity.getIntent().getStringExtra("math_mode"), settings.mathLimit(),
                settings.mathQuestions(), new SecureRandom().nextLong());
    }

    void save(Bundle state) {
        state.putString("math.id", session.id);
        state.putString("math.mode", session.mode);
        state.putInt("math.limit", session.limit);
        state.putInt("math.count", session.questionCount);
        state.putLong("math.seed", session.seed);
        state.putInt("math.index", session.index());
        state.putInt("math.answered", session.answered());
        state.putInt("math.correct", session.firstCorrect());
        state.putBoolean("math.attempted", session.attempted());
        state.putBoolean("math.solved", session.solved());
    }

    void show() {
        if (session.completed()) summary();
        else question();
    }

    void close() { active = false; }

    /** Activate only on the first down event; a held confirmation cannot skip a question. */
    boolean handleKeyEvent(KeyEvent event) {
        int key = event.getKeyCode();
        if (key != KeyEvent.KEYCODE_DPAD_CENTER && key != KeyEvent.KEYCODE_ENTER
                && key != KeyEvent.KEYCODE_NUMPAD_ENTER) return false;
        if (event.getAction() == KeyEvent.ACTION_DOWN && event.getRepeatCount() == 0
                && !event.isCanceled()) {
            View focused = activity.getCurrentFocus();
            if (focused != null && focused.isEnabled() && focused.isClickable()) focused.performClick();
        }
        return true;
    }

    private void question() {
        ArithmeticRound round = session.question();
        final int index = session.index();
        LinearLayout page = page();
        LinearLayout top = TvUi.row(activity);
        LinearLayout titles = TvUi.column(activity);
        TextView title = text(ArithmeticRound.modeLabel(session.mode), 25, TvUi.TEXT);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        titles.addView(title);
        TextView subtitle = text(session.limit + " 以内 · 不计时，慢慢想", 13, TvUi.MUTED);
        subtitle.setPadding(0, dp(5), 0, 0);
        titles.addView(subtitle);
        top.addView(titles, new LinearLayout.LayoutParams(0, -2, 1));
        TextView counter = text("第 " + (index + 1) + " / " + session.questionCount + " 题", 17, TvUi.TEXT);
        counter.setPadding(0, 0, dp(20), 0);
        top.addView(counter);
        top.addView(exit());
        page.addView(top, new LinearLayout.LayoutParams(-1, dp(60)));
        LinearLayout indicators = TvUi.row(activity);
        for (int i = 0; i < session.questionCount; i++) {
            View line = new View(activity);
            line.setBackground(TvUi.rounded(activity, i <= index ? 0xffbed9ff : 0xff344253, 3));
            LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(0, dp(4), 1);
            if (i + 1 < session.questionCount) position.rightMargin = dp(6);
            indicators.addView(line, position);
        }
        LinearLayout.LayoutParams progressPosition = new LinearLayout.LayoutParams(-1, dp(4));
        progressPosition.topMargin = dp(10);
        progressPosition.bottomMargin = dp(8);
        page.addView(indicators, progressPosition);
        TextView instruction = text(round.instruction, 21, TvUi.TEXT);
        instruction.setGravity(Gravity.CENTER);
        page.addView(instruction, new LinearLayout.LayoutParams(-1, dp(28)));
        TextView equation = text(round.equation, 38, TvUi.TEXT);
        equation.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        equation.setGravity(Gravity.CENTER);
        page.addView(equation, new LinearLayout.LayoutParams(-1, dp(46)));
        QuantityView quantities = new QuantityView(activity, round);
        quantities.setBackground(TvUi.rounded(activity, 0xffedf3ff, 19));
        LinearLayout.LayoutParams quantityPosition = new LinearLayout.LayoutParams(-1, 0, 1);
        quantityPosition.topMargin = dp(4);
        quantityPosition.bottomMargin = dp(10);
        page.addView(quantities, quantityPosition);
        LinearLayout answers = TvUi.row(activity);
        choices = new Button[3];
        for (int i = 0; i < 3; i++) {
            final int choice = i;
            Button button = TvUi.button(activity, round.answers[i], v -> answer(index, choice));
            button.setTextSize("compare".equals(round.kind) ? 23 : 38);
            button.setGravity(Gravity.CENTER);
            button.setContentDescription("选择答案 " + round.answers[i]);
            LinearLayout.LayoutParams position = new LinearLayout.LayoutParams(0, dp(64), 1);
            if (i < 2) position.rightMargin = dp(16);
            answers.addView(button, position);
            choices[i] = button;
        }
        page.addView(answers);
        feedback = text(session.attempted() ? "再数一数圆点，你可以再试一次。" : "用方向键选择，按确定回答。", 16, TvUi.MUTED);
        feedback.setGravity(Gravity.CENTER);
        page.addView(feedback, new LinearLayout.LayoutParams(-1, dp(30)));
        LinearLayout actions = TvUi.row(activity);
        TextView note = text("答错可以重试", 13, TvUi.MUTED);
        actions.addView(note, new LinearLayout.LayoutParams(0, -2, 1));
        next = TvUi.button(activity, index + 1 == session.questionCount ? "完成练习  ›" : "下一题  ›",
                v -> nextQuestion(index));
        next.setGravity(Gravity.CENTER);
        next.setTextSize(16);
        next.setMinHeight(0);
        next.setVisibility(View.INVISIBLE);
        next.setEnabled(false);
        actions.addView(next, new LinearLayout.LayoutParams(dp(160), dp(40)));
        page.addView(actions, new LinearLayout.LayoutParams(-1, dp(40)));
        if (session.solved()) showCorrect();
        else choices[0].requestFocus();
    }

    private void answer(int expectedIndex, int choice) {
        if (!active || session.index() != expectedIndex) return;
        int result = session.answer(choice);
        if (result == ArithmeticRound.Session.IGNORED) return;
        if (result == ArithmeticRound.Session.RETRY) {
            feedback.setText("还差一点，再数一数，然后试一次。");
            feedback.setTextColor(0xffffd1b9);
            feedback.announceForAccessibility("再试一次");
            return;
        }
        showCorrect();
    }

    private void showCorrect() {
        ArithmeticRound round = session.question();
        for (int i = 0; i < choices.length; i++) {
            choices[i].setEnabled(false);
            if (i == round.correctIndex) {
                choices[i].setBackground(TvUi.rounded(activity, 0xffcae9d0, 14));
                choices[i].setTextColor(0xff173521);
            } else choices[i].setAlpha(0.45f);
        }
        feedback.setText("答对了！准备好了，再按下一题。");
        feedback.setTextColor(0xffcae9d0);
        next.setVisibility(View.VISIBLE);
        next.setEnabled(false);
        nextReadyAt = SystemClock.elapsedRealtime() + 650;
        final Button pending = next;
        final int expectedIndex = session.index();
        pending.postDelayed(() -> {
            if (!active || activity.isDestroyed() || next != pending || session.index() != expectedIndex
                    || !session.solved()) return;
            pending.setEnabled(true);
            pending.requestFocus();
        }, 660);
    }

    private void nextQuestion(int expectedIndex) {
        if (!active || session.index() != expectedIndex || SystemClock.elapsedRealtime() < nextReadyAt) return;
        if (session.next()) show();
    }

    private void summary() {
        progress.recordRound(session.id, session.mode, session.limit,
                session.answered(), session.firstCorrect());
        LinearLayout page = page();
        LinearLayout top = TvUi.row(activity);
        top.addView(text("练习完成", 25, TvUi.TEXT), new LinearLayout.LayoutParams(0, -2, 1));
        top.addView(exit());
        page.addView(top, new LinearLayout.LayoutParams(-1, dp(48)));
        LinearLayout center = TvUi.column(activity);
        center.setGravity(Gravity.CENTER);
        TextView title = text("你完成了 " + session.questionCount + " 道题！", 36, TvUi.TEXT);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        center.addView(title);
        TextView encouragement = text("每一次认真思考，都是小小的进步。", 18, TvUi.MUTED);
        encouragement.setPadding(0, dp(14), 0, dp(25));
        center.addView(encouragement);
        LinearLayout results = TvUi.row(activity);
        results.setGravity(Gravity.CENTER);
        results.addView(stat("完成题目", Integer.toString(session.questionCount)));
        results.addView(stat("首答正确", session.firstCorrect() + " / " + session.questionCount));
        results.addView(stat("本次范围", session.limit + " 以内"));
        center.addView(results);
        TextView note = text("答错后再答对，同样完成了这道题。", 14, TvUi.MUTED);
        note.setPadding(0, dp(20), 0, 0);
        center.addView(note);
        page.addView(center, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout actions = TvUi.row(activity);
        Button again = TvUi.button(activity, "再练一轮", v -> { newSession(); show(); });
        again.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams againPosition = new LinearLayout.LayoutParams(0, dp(57), 1);
        againPosition.rightMargin = dp(18);
        actions.addView(again, againPosition);
        Button back = TvUi.button(activity, "返回儿童专区", v -> activity.returnToKids());
        back.setGravity(Gravity.CENTER);
        actions.addView(back, new LinearLayout.LayoutParams(0, dp(57), 1));
        page.addView(actions);
        again.requestFocus();
    }

    private LinearLayout stat(String label, String value) {
        LinearLayout card = TvUi.column(activity);
        card.setGravity(Gravity.CENTER);
        card.setPadding(dp(23), dp(22), dp(23), dp(22));
        card.setBackground(TvUi.rounded(activity, 0xff233247, 18));
        TextView figure = text(value, 29, TvUi.TEXT);
        figure.setGravity(Gravity.CENTER);
        card.addView(figure);
        TextView caption = text(label, 14, TvUi.MUTED);
        caption.setPadding(0, dp(8), 0, 0);
        card.addView(caption);
        LinearLayout.LayoutParams size = new LinearLayout.LayoutParams(dp(203), -2);
        size.leftMargin = dp(6);
        size.rightMargin = dp(6);
        card.setLayoutParams(size);
        return card;
    }

    private LinearLayout page() {
        LinearLayout page = TvUi.column(activity);
        page.setBackground(new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[] {0xff1b2b43, 0xff111c2b, 0xff0d1624}));
        page.setPadding(dp(36), dp(16), dp(36), dp(18));
        activity.setContentView(page);
        return page;
    }

    private TextView exit() {
        TextView exit = text("‹  儿童专区", 14, TvUi.TEXT);
        exit.setGravity(Gravity.CENTER);
        exit.setPadding(dp(17), dp(11), dp(17), dp(11));
        exit.setBackground(TvUi.focusBackground(activity));
        TvUi.interactive(exit, v -> activity.returnToKids());
        return exit;
    }

    private TextView text(String value, int size, int color) { return TvUi.text(activity, value, size, color); }
    private int dp(int value) { return TvUi.dp(activity, value); }

    /** Shapes are drawn directly so counting never depends on an emoji or coloured text font. */
    private static final class QuantityView extends View {
        private final ArithmeticRound round;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        QuantityView(Context context, ArithmeticRound round) {
            super(context);
            this.round = round;
            String description;
            if ("count".equals(round.kind)) description = round.left + " 个圆点";
            else if ("sub".equals(round.kind)) description = "原有 " + round.left + " 个圆点，划掉 " + round.right + " 个";
            else description = "左边 " + round.left + " 个圆点，右边 " + round.right + " 个圆点";
            setContentDescription(description);
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        }

        @Override protected void onDraw(Canvas canvas) {
            float width = getWidth(), height = getHeight();
            if (width <= 0 || height <= 0) return;
            boolean pair = "add".equals(round.kind) || "compare".equals(round.kind);
            float inset = Math.min(width, height) * 0.08f;
            if (pair) {
                float middle = width / 2f;
                dots(canvas, new RectF(inset, inset, middle - inset * 1.3f, height - inset),
                        round.left, 0, "左边");
                dots(canvas, new RectF(middle + inset * 1.3f, inset, width - inset, height - inset),
                        round.right, 0, "右边");
                paint.setColor(0xff48617c);
                paint.setTextSize(Math.min(height * .2f, width * .035f));
                paint.setTextAlign(Paint.Align.CENTER);
                paint.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
                canvas.drawText("add".equals(round.kind) ? "+" : "?", middle, height * .56f, paint);
            } else {
                float bodyWidth = Math.min(width * .7f, height * 3.3f);
                dots(canvas, new RectF((width - bodyWidth) / 2f, inset,
                                (width + bodyWidth) / 2f, height - inset), round.left,
                        "sub".equals(round.kind) ? round.right : 0,
                        "sub".equals(round.kind) ? "划掉的圆点表示拿走" : "数一数这些圆点");
            }
        }

        private void dots(Canvas canvas, RectF bounds, int count, int removed, String label) {
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(0xff4c627a);
            paint.setTextAlign(Paint.Align.CENTER);
            paint.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            float labelSize = Math.min(bounds.height() * .14f, 23f * getResources().getDisplayMetrics().density);
            paint.setTextSize(labelSize);
            canvas.drawText(label, bounds.centerX(), bounds.top + labelSize, paint);
            float top = bounds.top + labelSize * 1.7f;
            if (count == 0) {
                paint.setTextSize(labelSize * 1.45f);
                canvas.drawText("没有圆点", bounds.centerX(), (top + bounds.bottom) * .5f + labelSize * .45f, paint);
                return;
            }
            int columns = Math.min(5, count);
            int rows = (count + columns - 1) / columns;
            float cell = Math.min(bounds.width() / (columns + .8f), (bounds.bottom - top) / (rows + .2f));
            float startX = bounds.centerX() - columns * cell / 2f;
            float startY = top + ((bounds.bottom - top) - rows * cell) / 2f;
            for (int i = 0; i < count; i++) {
                float x = startX + (i % columns + .5f) * cell;
                float y = startY + (i / columns + .5f) * cell;
                float radius = cell * .34f;
                boolean crossed = i >= count - removed;
                paint.setStyle(crossed ? Paint.Style.STROKE : Paint.Style.FILL);
                paint.setStrokeWidth(Math.max(1.5f, cell * .04f));
                paint.setColor(crossed ? 0xff7a8798 : 0xff274766);
                canvas.drawCircle(x, y, radius, paint);
                if (crossed) {
                    canvas.drawLine(x - radius, y - radius, x + radius, y + radius, paint);
                    canvas.drawLine(x - radius, y + radius, x + radius, y - radius, paint);
                }
            }
            paint.setStyle(Paint.Style.FILL);
        }
    }
}
