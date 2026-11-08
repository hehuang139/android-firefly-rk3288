#!/system/bin/sh
# Original Firefly-RK3399 / AP6356S only. No controller reset or storage writes.
set -eu
fail() { echo "firefly-rk3399-wifi: $*" > /dev/kmsg; exit 1; }
[ "$(uname -r)" = '6.18.60-firefly-rk3399-android17' ] || fail 'kernel release mismatch'
bus=/sys/bus/sdio
[ -w "$bus/drivers_autoprobe" ] || fail 'SDIO bus unavailable'
[ ! -d /sys/module/brcmfmac ] || exit 0
devices=''
for attempt in 0 1 2 3 4 5 6 7 8 9 10; do
    devices=''
    have_function2=0
    for device in "$bus"/devices/*; do
        [ -r "$device/vendor" ] && [ -r "$device/device" ] || continue
        case "$(readlink -f "$device")" in */fe310000.mmc/*) ;; *) continue;; esac
        [ "$(cat "$device/vendor"):$(cat "$device/device")" = '0x02d0:0x4356' ] || continue
        case "$device" in *:1) devices="$devices ${device##*/}";; *:2) devices="$devices ${device##*/}"; have_function2=1;; esac
    done
    [ "$have_function2" = 0 ] || break
    [ "$attempt" = 10 ] || sleep 1
done
[ "$have_function2" = 1 ] || fail 'AP6356S SDIO function2 absent; no reset attempted'
moddir=/vendor/lib/modules
for module in cfg80211 brcmutil brcmfmac brcmfmac-wcc brcmfmac-cyw brcmfmac-bca; do
    [ -r "$moddir/$module.ko" ] || fail "missing module $module"
done
saved_autoprobe=$(cat "$bus/drivers_autoprobe")
trap 'echo "$saved_autoprobe" > "$bus/drivers_autoprobe"' EXIT
trap 'exit 1' HUP INT TERM
echo 0 > "$bus/drivers_autoprobe"
for module in cfg80211 brcmutil brcmfmac brcmfmac-wcc brcmfmac-cyw brcmfmac-bca; do
    name=$(echo "$module" | tr '-' '_')
    [ -d "/sys/module/$name" ] || /system/bin/insmod "$moddir/$module.ko"
done
echo "$saved_autoprobe" > "$bus/drivers_autoprobe"
for device in $devices; do
    [ -e "$bus/devices/$device/driver" ] || echo "$device" > "$bus/drivers_probe"
done
echo 'firefly-rk3399-wifi: modules loaded; verify firmware and wlan0 before association' > /dev/kmsg
