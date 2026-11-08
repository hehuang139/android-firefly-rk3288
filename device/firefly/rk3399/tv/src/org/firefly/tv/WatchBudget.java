/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

/** Pure time-budget arithmetic; a puzzle never replenishes the daily allowance. */
final class WatchBudget {
    private WatchBudget() { }

    static long remaining(long dailyLimit, long dailySpent, long sessionLimit, long sessionSpent) {
        return Math.max(0, Math.min(dailyLimit - dailySpent, sessionLimit - sessionSpent));
    }

    static long charge(long spent, long milliseconds) {
        return Math.min(86_400_000L, spent + Math.max(0, milliseconds));
    }

    static long currentDay(long previousDay, long wallTime) {
        return Math.max(previousDay, java.time.Instant.ofEpochMilli(wallTime)
                .atZone(java.time.ZoneId.systemDefault()).toLocalDate().toEpochDay());
    }
}
