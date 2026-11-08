#!/system/bin/sh
# Controlled initial bring-up. No scans, no connections and no network changes.
set -eu
log_line() { echo "firefly-wifi: $*" > /dev/kmsg; }
fail() { log_line "$*"; exit 1; }
[ "$(uname -r)" = '6.18.60-firefly-tvbox' ] || fail 'kernel release mismatch'
bus=/sys/bus/sdio
[ -w "$bus/drivers_autoprobe" ] || fail 'SDIO bus not ready'
[ ! -d /sys/module/brcmfmac ] || fail 'brcmfmac already loaded; refusing to race'
moddir=/vendor/lib/modules
for module in cfg80211 brcmutil brcmfmac brcmfmac-wcc brcmfmac-cyw brcmfmac-bca; do
    [ -r "$moddir/$module.ko" ] || fail "missing module $module"
done
# USB wifi is outside this controlled bring-up; detect before registering base.
for entry in /sys/bus/usb/devices/*/idVendor; do
    [ -r "$entry" ] || continue
    product=${entry%idVendor}idProduct
    [ -r "$product" ] || continue
    case "$(cat "$entry"):$(cat "$product")" in
        04b4:0bdc|0a5c:0bdc|043e:3101|04b4:bd29|13b1:0039|0a5c:bd27|0a5c:bd1f|0a5c:bd17|0a5c:bd1e|0a5c:bd1d)
            fail 'brcmfmac USB device present; remove it before controlled SDIO bring-up' ;;
    esac
done
# Never disturb storage: recovery is limited to the internal SDIO controller.
find_internal_sdio() {
    devices=''
    have_function2=0
    for device in "$bus"/devices/*; do
        [ -r "$device/vendor" ] && [ -r "$device/device" ] || continue
        case "$(readlink -f "$device")" in */ff0d0000.mmc/*) ;; *) continue;; esac
        case "$device" in *:1|*:2) ;; *) continue;; esac
        case "$(cat "$device/vendor"):$(cat "$device/device")" in
            0x02d0:0x4335|0x02d0:0x4339)
                devices="$devices ${device##*/}"
                case "$device" in *:2) have_function2=1;; esac
                ;;
        esac
    done
}
wait_internal_sdio() {
    for attempt in 0 1 2 3 4 5; do
        find_internal_sdio
        [ "$have_function2" = 0 ] || return 0
        [ "$attempt" = 5 ] || sleep 1
    done
    return 1
}
if ! wait_internal_sdio; then
    # One bounded recovery after the early boot probe failed. This does not
    # claim to fix the underlying power-up timing and never touches eMMC.
    [ -z "$(ls "$bus/devices")" ] || fail 'unmatched/partial SDIO cards present; refusing controller recovery'
    [ "$(readlink -f /dev/block/by-name/boot)" = /dev/block/mmcblk1p1 ] || fail 'unexpected boot storage mapping'
    [ "$(readlink -f /sys/class/mmc_host/mmc0)" = /sys/devices/platform/ff0d0000.mmc/mmc_host/mmc0 ] || fail 'unexpected SDIO host mapping'
    [ ! -d /sys/module/brcmfmac ] || fail 'brcmfmac appeared before recovery'
    driver=/sys/bus/platform/drivers/dwmmc_rockchip
    [ -L "$driver/ff0d0000.mmc" ] || fail 'internal SDIO driver not bound'
    log_line 'early SDIO enumeration absent; one controlled ff0d0000 recovery'
    echo ff0d0000.mmc > "$driver/unbind"
    sleep 1
    echo ff0d0000.mmc > "$driver/bind"
    wait_internal_sdio || fail 'SDIO recovery did not enumerate function2; stopping without further retries'
fi
saved_autoprobe=$(cat "$bus/drivers_autoprobe")
trap 'echo "$saved_autoprobe" > "$bus/drivers_autoprobe"' EXIT
trap 'exit 1' HUP INT TERM
echo 0 > "$bus/drivers_autoprobe"
for module in cfg80211 brcmutil brcmfmac brcmfmac-wcc brcmfmac-cyw brcmfmac-bca; do
    name=$(echo "$module" | tr '-' '_')
    [ -d "/sys/module/$name" ] || /system/bin/insmod "$moddir/$module.ko"
done
for module in cfg80211 brcmutil brcmfmac brcmfmac_wcc brcmfmac_cyw brcmfmac_bca; do
    [ -d "/sys/module/$module" ] || fail "module not registered: $module"
done
echo "$saved_autoprobe" > "$bus/drivers_autoprobe"
for device in $devices; do
    [ -e "$bus/devices/$device/driver" ] || echo "$device" > "$bus/drivers_probe"
done
log_line 'all modules registered; SDIO probe requested; inspect firmware/wlan0 before enabling wifi'
