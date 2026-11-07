/* SPDX-License-Identifier: MIT */
/* Compile for ARM32 to check the AOSP ARM32 GSI's binder64 wire ABI. */
#include <linux/android/binder.h>
_Static_assert(sizeof(void *) == 4, "Must compile this check for ARM32");
_Static_assert(sizeof(binder_size_t) == 8, "AOSP ARM32 requires binder64 size");
_Static_assert(sizeof(binder_uintptr_t) == 8, "AOSP ARM32 requires binder64 ptr");
_Static_assert(BINDER_CURRENT_PROTOCOL_VERSION == 8, "Binder64 protocol");
int firefly_android_binder64_abi_check(void) { return 0; }
