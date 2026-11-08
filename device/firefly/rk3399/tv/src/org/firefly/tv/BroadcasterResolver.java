/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;
import java.io.IOException;
/** Optional provider protocol hook. Public builds accept direct authorized URLs. */
final class BroadcasterResolver {
    private BroadcasterResolver() { }
    static String resolve(String provider, String channelId) throws IOException {
        throw new IOException("This build supports direct authorized stream URLs only");
    }
}
