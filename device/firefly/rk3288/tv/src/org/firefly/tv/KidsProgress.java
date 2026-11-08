/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.HashSet;
import java.util.Set;

/** Local completed-practice totals, isolated from all parental viewing budgets. */
final class KidsProgress {
    private static final Object LOCK = new Object();
    private final SharedPreferences prefs;

    KidsProgress(Context context) {
        prefs = context.createDeviceProtectedStorageContext()
                .getSharedPreferences("kids_progress", Context.MODE_PRIVATE);
    }

    int completedRounds() { return prefs.getInt("completed_rounds", 0); }
    int answeredQuestions() { return prefs.getInt("answered_questions", 0); }
    int firstTryCorrect() { return prefs.getInt("first_try_correct", 0); }
    String lastMode() { return ArithmeticRound.normalizeMode(prefs.getString("last_mode", "mixed")); }
    int lastLimit() { return ArithmeticRound.normalizeLimit(prefs.getInt("last_limit", 10)); }

    /** A restored completion screen may call this again; one identity counts only once. */
    boolean recordRound(String roundId, String mode, int limit, int answered, int firstCorrect) {
        if (roundId == null || roundId.isEmpty() || roundId.length() > 128
                || !ArithmeticRound.normalizeMode(mode).equals(mode)
                || ArithmeticRound.normalizeLimit(limit) != limit
                || (answered != 5 && answered != 10) || firstCorrect < 0 || firstCorrect > answered) {
            throw new IllegalArgumentException("Invalid completed practice result");
        }
        synchronized (LOCK) {
            Set<String> recorded = new HashSet<>(prefs.getStringSet("recorded_rounds", new HashSet<>()));
            if (recorded.contains(roundId)) return false;
            recorded.add(roundId);
            return prefs.edit().putStringSet("recorded_rounds", recorded)
                    .putInt("completed_rounds", sum(completedRounds(), 1))
                    .putInt("answered_questions", sum(answeredQuestions(), answered))
                    .putInt("first_try_correct", sum(firstTryCorrect(), firstCorrect))
                    .putString("last_mode", mode).putInt("last_limit", limit).commit();
        }
    }

    private static int sum(int value, int increment) {
        return (int) Math.min(Integer.MAX_VALUE, Math.max(0L, value) + increment);
    }
}
