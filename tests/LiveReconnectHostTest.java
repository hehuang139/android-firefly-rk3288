/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

/** Bounded recovery for streams that end normally instead of reporting a network error. */
public final class LiveReconnectHostTest {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        LiveReconnectPolicy policy = new LiveReconnectPolicy();
        for (int i = 0; i < 3; i++) check(policy.allowCompletion(1000), "Early EOS should reconnect");
        for (int i = 0; i < 100; i++) check(!policy.allowCompletion(59_999), "Rapid EOS loop was not bounded");
        check(policy.allowCompletion(60_000), "A full stable minute must restore recovery");
        check(policy.allowCompletion(0) && policy.allowCompletion(0), "Stable playback did not reset the budget");
        check(!policy.allowCompletion(0), "Stable reset allows more than three reconnects");
        policy.reset();
        check(policy.allowCompletion(0), "A new channel must have its own recovery budget");
        for (int i = 0; i < 100; i++) check(policy.allowCompletion(120_000), "Long live sessions exhausted recovery");
        System.out.println("Live EOS: bounded rapid retries, exact stable-playback boundary, channel reset, and long-session recovery passed");
    }
}
