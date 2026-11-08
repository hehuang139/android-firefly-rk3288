/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

/** Prevent stale picture-question callbacks and rapid repeated confirmations. */
final class PuzzleInputGate {
    static final int IGNORED = 0;
    static final int RETRY = -1;
    static final int CORRECT = 1;
    private int generation;
    private boolean consumed;
    private long readyAt;

    int begin(long now) {
        generation++;
        consumed = false;
        readyAt = now + 500;
        return generation;
    }

    int submit(int question, boolean correct, long now) {
        if (question != generation || consumed || now < readyAt) return IGNORED;
        if (!correct) return RETRY;
        consumed = true;
        return CORRECT;
    }

    void invalidate() {
        generation++;
        consumed = true;
    }
}
