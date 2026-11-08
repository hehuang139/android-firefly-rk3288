/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

/** Limit rapid, clean stream endings without treating a long live session as a failure loop. */
final class LiveReconnectPolicy {
    private static final int MAX_QUICK_RECONNECTS = 3;
    private static final long STABLE_PLAYBACK_MS = 60_000;
    private int quickReconnects;

    boolean allowCompletion(long playedMs) {
        if (playedMs >= STABLE_PLAYBACK_MS) quickReconnects = 0;
        if (quickReconnects >= MAX_QUICK_RECONNECTS) return false;
        quickReconnects++;
        return true;
    }

    void reset() { quickReconnects = 0; }
}
