#!/system/bin/sh
# USB0 is a fixed peripheral. Wait asynchronously for its unique UDC, including
# a delayed controller probe; init and adbd must not wait for this discovery.
set -eu
setprop vendor.firefly.usb.controller.ready 0
while :; do
    selected=''
    ambiguous=0
    for udc in /sys/class/udc/*; do
        [ -e "$udc" ] || continue
        case "$(readlink -f "$udc")" in
            */fe800000.usb/*|*/usb@fe800000/*|*/fe800000.dwc3/*)
                if [ -n "$selected" ]; then
                    ambiguous=1
                    break
                fi
                selected=${udc##*/}
                ;;
        esac
    done
    if [ -n "$selected" ] && [ "$ambiguous" = 0 ]; then
        setprop sys.usb.controller "$selected"
        setprop vendor.firefly.usb.controller.ready 1
        exit 0
    fi
    sleep 1
done
