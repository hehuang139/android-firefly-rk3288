/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.HashSet;
import java.util.Set;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.spec.InvalidKeySpecException;

/** Device-protected, synchronous budget checkpoints and salted parent credentials. */
final class ParentalPrefs {
    private static final long MINUTE = 60_000L;
    private static final long DAY = 86_400_000L;
    private final SharedPreferences prefs;

    ParentalPrefs(Context context) {
        prefs = context.createDeviceProtectedStorageContext()
                .getSharedPreferences("parental", Context.MODE_PRIVATE);
    }

    boolean enabled() { return prefs.getBoolean("enabled", false); }
    boolean hasPin() { return prefs.contains("pin_hash"); }
    int sessionMinutes() { return validOrDefault(prefs.getInt("session_minutes", 15), 15, 5, 10, 15, 20, 30); }
    int dailyMinutes() { return validOrDefault(prefs.getInt("daily_minutes", 60), 60, 15, 30, 45, 60, 90); }
    int bonusMinutes() { return validOrDefault(prefs.getInt("bonus_minutes", 5), 5, 3, 5, 10, 15); }
    int difficulty() { return validOrDefault(prefs.getInt("difficulty", 0), 0, 0, 1); }
    int mathLimit() { return validOrDefault(prefs.getInt("math_limit", 10), 10, 5, 10, 20); }
    int mathQuestions() { return validOrDefault(prefs.getInt("math_questions", 5), 5, 5, 10); }
    String resumePackage() { return prefs.getString("resume_package", ""); }
    void setResumePackage(String name) { prefs.edit().putString("resume_package", name).commit(); }

    void setEnabled(boolean value) {
        if (!value || hasPin()) {
            prefs.edit().putBoolean("enabled", value).commit();
        }
    }

    void setLimits(int session, int daily, int bonus, int difficulty) {
        requireChoice(session, 5, 10, 15, 20, 30);
        requireChoice(daily, 15, 30, 45, 60, 90);
        requireChoice(bonus, 3, 5, 10, 15);
        requireChoice(difficulty, 0, 1);
        prefs.edit().putInt("session_minutes", session).putInt("daily_minutes", daily)
                .putInt("bonus_minutes", bonus).putInt("difficulty", difficulty).commit();
    }

    void setMathOptions(int limit, int questions) {
        requireChoice(limit, 5, 10, 20);
        requireChoice(questions, 5, 10);
        prefs.edit().putInt("math_limit", limit).putInt("math_questions", questions).commit();
    }

    private static int validOrDefault(int value, int fallback, int... choices) {
        for (int choice : choices) if (value == choice) return value;
        return fallback;
    }

    private static void requireChoice(int value, int... choices) {
        for (int choice : choices) if (value == choice) return;
        throw new IllegalArgumentException("Unsupported parental setting");
    }

    private void rollover() {
        long oldDay = prefs.getLong("day", Long.MIN_VALUE);
        long day = WatchBudget.currentDay(oldDay, System.currentTimeMillis());
        if (day > oldDay) {
            prefs.edit().putLong("day", day).putLong("daily_spent", 0)
                    .putLong("session_spent", 0).putBoolean("bonus_session", false).commit();
        }
    }

    long remaining() {
        rollover();
        int minutes = prefs.getBoolean("bonus_session", false) ? bonusMinutes() : sessionMinutes();
        return WatchBudget.remaining(dailyMinutes() * MINUTE, dailyUsed(),
                minutes * MINUTE, Math.max(0, Math.min(DAY, prefs.getLong("session_spent", 0))));
    }

    boolean dailyExhausted() {
        return dailyRemaining() == 0;
    }

    long dailyUsed() {
        rollover();
        return Math.max(0, Math.min(DAY, prefs.getLong("daily_spent", 0)));
    }

    long dailyRemaining() {
        return Math.max(0, dailyMinutes() * MINUTE - dailyUsed());
    }

    void charge(long milliseconds) {
        rollover();
        long charge = Math.max(0, Math.min(DAY, milliseconds));
        prefs.edit().putLong("daily_spent", WatchBudget.charge(
                dailyUsed(), charge))
                .putLong("session_spent", WatchBudget.charge(
                Math.max(0, Math.min(DAY, prefs.getLong("session_spent", 0))), charge)).commit();
    }

    boolean puzzlePassed() {
        if (dailyExhausted() || remaining() > 0) {
            return false;
        }
        prefs.edit().putLong("session_spent", 0).putBoolean("bonus_session", true).commit();
        return true;
    }

    Set<String> allowedApps() {
        return new HashSet<>(prefs.getStringSet("allowed_apps", new HashSet<>()));
    }

    void allow(String name, boolean allowed) {
        Set<String> names = allowedApps();
        if (allowed) {
            names.add(name);
        } else {
            names.remove(name);
        }
        prefs.edit().putStringSet("allowed_apps", names).commit();
    }

    void setPin(String pin) {
        if (pin == null || !pin.matches("[0-9]{4,8}")) {
            throw new IllegalArgumentException("PIN must contain 4 to 8 digits");
        }
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        prefs.edit().putString("pin_salt", Base64.encodeToString(salt, Base64.NO_WRAP))
                .putString("pin_hash", Base64.encodeToString(derive(pin, salt), Base64.NO_WRAP))
                .putLong("pin_lock_until", 0).putInt("pin_failures", 0).commit();
    }

    boolean verifyPin(String pin) {
        if (lockSeconds() > 0 || !hasPin()) {
            return false;
        }
        boolean valid = false;
        try {
            byte[] salt = Base64.decode(prefs.getString("pin_salt", ""), Base64.NO_WRAP);
            byte[] expected = Base64.decode(prefs.getString("pin_hash", ""), Base64.NO_WRAP);
            valid = pin != null && pin.matches("[0-9]{4,8}") && salt.length == 16
                    && expected.length == 32 && MessageDigest.isEqual(expected, derive(pin, salt));
        } catch (IllegalArgumentException error) {
            // Corrupt credentials must reject access, not crash or allow PIN replacement.
        }
        int failures = valid ? 0 : prefs.getInt("pin_failures", 0) + 1;
        prefs.edit().putInt("pin_failures", failures % 5).putLong("pin_lock_until",
                failures >= 5 ? System.currentTimeMillis() + 30_000 : 0).commit();
        return valid;
    }

    long lockSeconds() {
        return Math.max(0, (prefs.getLong("pin_lock_until", 0) - System.currentTimeMillis()
                + 999) / 1000);
    }

    private static byte[] derive(String pin, byte[] salt) {
        PBEKeySpec spec = new PBEKeySpec(pin.toCharArray(), salt, 60_000, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } catch (NoSuchAlgorithmException | InvalidKeySpecException error) {
            throw new IllegalStateException("PIN derivation unavailable", error);
        } finally {
            spec.clearPassword();
        }
    }
}
