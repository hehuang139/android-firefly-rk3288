/* SPDX-License-Identifier: GPL-2.0 */
/* Temporary Firefly boot diagnosis. No device state changes. */
#ifndef _LINUX_FIREFLY_HANTRO_DIAG_H
#define _LINUX_FIREFLY_HANTRO_DIAG_H
struct device;
void firefly_hantro_diag(struct device *dev, const char *mark);
#endif
