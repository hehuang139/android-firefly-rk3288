/* SPDX-License-Identifier: Apache-2.0 */
package vendor.firefly.hardware.remote;

/** Privileged board IR/CEC control. JSON protocol version 1, limited to 4096 bytes. */
@VintfStability
interface IRemote {
    /** Returns one JSON result; accepted callers are Android UID 0 and 1000. */
    String request(String json);
}
