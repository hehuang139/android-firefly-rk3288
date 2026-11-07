/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Random;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;

/** Executable regression cases against the actual preferences and puzzle classes. */
public final class ParentalHostTest {
    private static final Logger LOGGER = Logger.getLogger(ParentalHostTest.class.getName());
    private static int checks;

    private ParentalHostTest() { }

    private static void check(boolean condition, String name) {
        checks++;
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        Context context = new Context();
        ParentalPrefs prefs = new ParentalPrefs(context);
        check(!prefs.enabled() && !prefs.hasPin(), "no default PIN and opt-in mode");
        prefs.setEnabled(true);
        check(!prefs.enabled(), "cannot enable mode without a PIN");
        prefs.setPin("482619");
        check(prefs.verifyPin("482619"), "PIN accepted");
        check(!prefs.verifyPin("000000"), "incorrect PIN rejected");
        prefs.setEnabled(true);
        check(prefs.enabled(), "mode enabled after setup");
        check(prefs.remaining() == 15 * 60_000L, "default 15 minute first session");
        check(!prefs.puzzlePassed(), "early quiz cannot replenish a running session");
        prefs.charge(15 * 60_000L);
        check(prefs.remaining() == 0, "session exhaustion");
        ParentalPrefs restarted = new ParentalPrefs(context);
        check(restarted.enabled() && restarted.remaining() == 0, "restart preserves exhaustion");
        check(restarted.puzzlePassed(), "quiz grants a bounded extension");
        check(restarted.remaining() == 5 * 60_000L, "default 5 minute bonus");
        for (int round = 0; round < 9; round++) {
            restarted.charge(5 * 60_000L);
            if (round < 8) {
                check(restarted.puzzlePassed(), "extension within daily allowance");
            }
        }
        check(restarted.dailyExhausted(), "daily cap across many quizzes");
        check(!restarted.puzzlePassed(), "quiz cannot bypass daily cap");
        restarted.setEnabled(false);
        restarted.setEnabled(true);
        check(restarted.dailyExhausted(), "toggle cannot reset daily accounting");
        restarted.allow("org.xbmc.kodi", true);
        Set<String> copy = new HashSet<>(restarted.allowedApps());
        copy.clear();
        check(restarted.allowedApps().contains("org.xbmc.kodi"), "allowlist copied on read");
        restarted.allow("org.xbmc.kodi", false);
        check(restarted.allowedApps().isEmpty(), "provider revocation");
        for (int attempt = 0; attempt < 5; attempt++) {
            check(!restarted.verifyPin("000000"), "PIN attempt rejected");
        }
        check(restarted.lockSeconds() > 0, "five failures cause a persistent cooldown");
        check(!new ParentalPrefs(context).verifyPin("482619"), "restart cannot bypass PIN cooldown");
        long today = WatchBudget.currentDay(Long.MIN_VALUE, System.currentTimeMillis());
        check(WatchBudget.currentDay(today, System.currentTimeMillis() - 172_800_000) == today,
                "clock rollback cannot reset the budget");
        check(WatchBudget.charge(1000, -1000) == 1000, "negative charge cannot refund");
        context.getSharedPreferences("parental", Context.MODE_PRIVATE).edit()
                .putLong("day", today - 1).commit();
        check(restarted.remaining() == 15 * 60_000L && !restarted.dailyExhausted(),
                "new calendar day starts a fresh normal session");
        check(WatchBudget.remaining(1000, 1500, 3000, 0) == 0,
                "lowering a daily limit takes effect immediately");
        check(WatchBudget.remaining(3000, 1000, 1500, 1600) == 0,
                "lowering a session limit takes effect immediately");
        puzzles();
        if (LOGGER.isLoggable(Level.INFO)) {
            LOGGER.info("PASS " + checks + " assertions");
        }
    }

    private static void puzzles() {
        Random random = new Random(1207);
        for (int difficulty = 0; difficulty < 2; difficulty++) {
            for (int kind = 0; kind < 3; kind++) {
                for (int iteration = 0; iteration < 1000; iteration++) {
                    PuzzleRound question = new PuzzleRound(random, kind, difficulty);
                    int correct = question.correct;
                    check(correct >= 0 && correct < 3, "answer slot valid");
                    if (kind == 0) {
                        check(question.colors[correct] == question.targetColor, "color answer");
                    } else if (kind == 1) {
                        check(question.target.equals(question.answers[correct]), "shape answer");
                    } else {
                        int count = (int) question.target.chars().filter(value -> value == '●').count();
                        check(Integer.parseInt(question.answers[correct]) == count, "counting answer");
                        check(new HashSet<>(Arrays.asList(question.answers)).size() == 3,
                                "counting answers are unambiguous");
                    }
                }
            }
        }
    }
}
