#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Optional userdebug/eng installer. Never change or overwrite an existing app.
SOURCE_DIR='/product/etc/firefly/preinstall'
STATE_DIR='/data/misc/firefly-youtube-preinstall'
LOCK_DIR='/dev/firefly-youtube-preinstall-lock'
PKG_CMD='/system/bin/cmd'
PACKAGE='com.google.android.youtube.tv'
GOOGLE_SIGNER='21199d112cece428c82cb0df221da24ff8674c7a982a83a17a970eec43305b4a'
umask 077
mkdir -p "$STATE_DIR" || exit 1
chmod 700 "$STATE_DIR" || exit 1
# A prior attempt is terminal, including failure or an existing package. This
# respects later user uninstall and prevents an installation loop on each boot.
[ ! -f "$STATE_DIR/attempted" ] || exit 0
# Keep the lock in volatile storage: a power loss before the attempt marker must
# not permanently suppress the PackageManager readiness check on later boots.
mkdir "$LOCK_DIR" 2>/dev/null || exit 0
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT
[ ! -f "$STATE_DIR/attempted" ] || exit 0

status() {
    printf '%s\n' "$1" > "$STATE_DIR/status.tmp" &&
        mv "$STATE_DIR/status.tmp" "$STATE_DIR/status"
    sync
}
fail() { status "$1"; exit 1; }
# Boot-complete normally means PackageManager is ready, but prove the query works
# before consuming the one attempt. A transient service failure can retry next boot.
ready_attempts=0
until "$PKG_CMD" package list packages -u --show-versioncode "$PACKAGE" > "$STATE_DIR/existing.txt" 2> "$STATE_DIR/package-error.txt"; do
    ready_attempts=$((ready_attempts + 1))
    [ "$ready_attempts" -lt 6 ] || fail 'package-manager-not-ready-no-install-attempt'
    sleep 5
done
printf 'one-attempt\n' > "$STATE_DIR/attempted" || exit 1
sync
status 'validating'

EXPECTED_SHA=''
EXPECTED_VERSION=''
EXPECTED_PACKAGE=''
EXPECTED_SIGNER=''
[ -f "$SOURCE_DIR/youtube-tv.conf" ] || fail 'missing-config'
while IFS='=' read -r key value; do
    case "$key" in
        sha256) [ -z "$EXPECTED_SHA" ] || fail 'duplicate-config'; EXPECTED_SHA=$value ;;
        version_code) [ -z "$EXPECTED_VERSION" ] || fail 'duplicate-config'; EXPECTED_VERSION=$value ;;
        package) [ -z "$EXPECTED_PACKAGE" ] || fail 'duplicate-config'; EXPECTED_PACKAGE=$value ;;
        signer_sha256) [ -z "$EXPECTED_SIGNER" ] || fail 'duplicate-config'; EXPECTED_SIGNER=$value ;;
        *) fail 'invalid-config-field' ;;
    esac
done < "$SOURCE_DIR/youtube-tv.conf"
[ "$EXPECTED_PACKAGE" = "$PACKAGE" ] || fail 'wrong-package-config'
[ "$EXPECTED_SIGNER" = "$GOOGLE_SIGNER" ] || fail 'wrong-signer-config'
[ "${#EXPECTED_SHA}" -eq 64 ] || fail 'invalid-hash-config'
case "$EXPECTED_SHA" in *[!0-9a-f]*) fail 'invalid-hash-config' ;; esac
case "$EXPECTED_VERSION" in ''|*[!0-9]*|0) fail 'invalid-version-config' ;; esac
SOURCE_APK="$SOURCE_DIR/YouTubeTV.apk"
[ -f "$SOURCE_APK" ] || fail 'missing-apk'
actual=$(sha256sum "$SOURCE_APK" | cut -d ' ' -f 1)
[ "$actual" = "$EXPECTED_SHA" ] || fail 'source-hash-mismatch'

# Include packages retained after uninstall (-u); do not resurrect one either.
if grep -Eq '^package:com\.google\.android\.youtube\.tv([[:space:]]|$)' "$STATE_DIR/existing.txt"; then
    status 'skipped-existing-package-version-and-signature-left-unchanged'
    exit 0
fi
status 'installing'
# No -r, -d, force or signature override. PackageInstaller handles compressed JNI.
timeout 120 "$PKG_CMD" package install --user 0 "$SOURCE_APK" > "$STATE_DIR/install.txt" 2>&1 || fail 'package-install-failed'
grep -qx 'Success' "$STATE_DIR/install.txt" || fail 'package-install-not-confirmed'
"$PKG_CMD" package list packages --user 0 --show-versioncode "$PACKAGE" > "$STATE_DIR/installed.txt" 2> "$STATE_DIR/package-error.txt" || fail 'installed-query-failed'
grep -qx "package:$PACKAGE versionCode:$EXPECTED_VERSION" "$STATE_DIR/installed.txt" || fail 'installed-package-version-mismatch'
"$PKG_CMD" package path --user 0 "$PACKAGE" > "$STATE_DIR/path.txt" 2> "$STATE_DIR/package-error.txt" || fail 'installed-path-query-failed'
[ "$(grep -c '^package:' "$STATE_DIR/path.txt")" -eq 1 ] || fail 'unexpected-installed-splits'
installed=$(sed -n 's/^package://p' "$STATE_DIR/path.txt")
case "$installed" in /data/app/*/base.apk) ;; *) fail 'unexpected-installed-path' ;; esac
actual=$(sha256sum "$installed" | cut -d ' ' -f 1)
[ "$actual" = "$EXPECTED_SHA" ] || fail 'installed-hash-mismatch'
# Exact original signed bytes + checked package/version retain the Google
# certificate already verified by apksigner against Google's published anchor.
printf '%s\n' "$EXPECTED_SHA" > "$STATE_DIR/success" || fail 'success-marker-failed'
status 'verified-installed-original-google-signed-apk'
exit 0
