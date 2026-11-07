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
    private final SharedPreferences prefs;

    ParentalPrefs(Context context) {
        prefs = context.createDeviceProtectedStorageContext()
                .getSharedPreferences("parental", Context.MODE_PRIVATE);
    }

    boolean enabled() { return prefs.getBoolean("enabled", false); }
    boolean hasPin() { return prefs.contains("pin_hash"); }
    int sessionMinutes() { return prefs.getInt("session_minutes", 15); }
    int dailyMinutes() { return prefs.getInt("daily_minutes", 60); }
    int bonusMinutes() { return prefs.getInt("bonus_minutes", 5); }
    int difficulty() { return prefs.getInt("difficulty", 0); }
    String resumePackage() { return prefs.getString("resume_package", ""); }
    void setResumePackage(String name) { prefs.edit().putString("resume_package", name).commit(); }

    void setEnabled(boolean value) {
        if (!value || hasPin()) {
            prefs.edit().putBoolean("enabled", value).commit();
        }
    }

    void setLimits(int session, int daily, int bonus, int difficulty) {
        prefs.edit().putInt("session_minutes", session).putInt("daily_minutes", daily)
                .putInt("bonus_minutes", bonus).putInt("difficulty", difficulty).commit();
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
        return WatchBudget.remaining(dailyMinutes() * MINUTE, prefs.getLong("daily_spent", 0),
                minutes * MINUTE, prefs.getLong("session_spent", 0));
    }

    boolean dailyExhausted() {
        rollover();
        return prefs.getLong("daily_spent", 0) >= dailyMinutes() * MINUTE;
    }

    void charge(long milliseconds) {
        rollover();
        prefs.edit().putLong("daily_spent", WatchBudget.charge(
                prefs.getLong("daily_spent", 0), milliseconds))
                .putLong("session_spent", WatchBudget.charge(
                prefs.getLong("session_spent", 0), milliseconds)).commit();
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
        byte[] salt = Base64.decode(prefs.getString("pin_salt", ""), Base64.NO_WRAP);
        byte[] expected = Base64.decode(prefs.getString("pin_hash", ""), Base64.NO_WRAP);
        boolean valid = MessageDigest.isEqual(expected, derive(pin, salt));
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
