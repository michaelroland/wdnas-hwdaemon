#!/usr/bin/env bash

################################################################################
## 
## LCD menu action
## 
## Copyright (c) 2018-2019 Stefaan Ghysels <stefaang@gmail.com>
## Copyright (c) 2021-2022 Michael Roland <mi.roland@gmail.com>
## 
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
## 
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
## 
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.
## 
################################################################################


SCRIPT_NAME=$(basename $0)
SCRIPT_PATH=$(readlink -f "$(dirname $0)")

PATH="${PATH}:${SCRIPT_PATH}/../bin:/opt/wdhwd/bin"
export PATH

menu_position_db="lcd_menu.idx"
action="$1"


function show {
    wdhwc lcd -t "$1" "$2"
}

function show_r {
    show "$1" "$(printf "%16s" "$2")"
}

function get_ip {
	ip route get 1 | sed -n -E 's/^.*src\s+(\S+).*$/\1/p'
}

function get_temperature {
	wdhwc temperature | sed -n -E 's/^PMC temperature:\s+(.*)\s+°(C|F)\s*$/\1 \2/p'
}

function get_fan_speed {
	wdhwc fan | sed -n -E 's/^Fan speed:\s+(.*)\s+%\s*$/\1%/p'
}

function get_all_disk_usage {
	df -h -l -x tmpfs -x devtmpfs --output=target,size,avail,pcent \
        | tail -n+2 \
        | grep -v -E '^/(boot|dev|proc|sys|tmp)(\/|\s)' \
        | sort -b -k1
}

function get_disk_name {
	echo "$1" | sed -n -E 's/^(\S+).*$/\1/p'
}

function get_disk_free {
	echo "$1" | sed -n -E 's/^\S+\s+(\S+)\s+(\S+)\s+(\S+)\s*$/\2\/\1 free/p'
}

function get_disk_usage {
	echo "$1" | sed -n -E 's/^\S+\s+(\S+)\s+(\S+)\s+(\S+)\s*$/\3 used/p'
}


menu_position_file="${PWD}/${menu_position_db}"
if [ -d "${RUNTIME_DIRECTORY}" ] ; then
    menu_position_file="${RUNTIME_DIRECTORY}/${menu_position_db}"
fi
menu_position=$(cat "${menu_position_file}" 2>/dev/null || echo 0)

base_menu_items=4

disk_usage=$(get_all_disk_usage)
num_disks=$(echo "$disk_usage" | wc -l)

menu_items=$(( base_menu_items + 2 * num_disks))

case "${action}" in
    "lcd_up_long")
        menu_position=$(( (menu_items + menu_position - 1) % menu_items ))
        ;;
    "lcd_up")
        menu_position=$(( (menu_items + menu_position - 1) % menu_items ))
        ;;
    "lcd_down_long")
        menu_position=$(( (menu_position + 1) % menu_items ))
        ;;
    "lcd_down")
        menu_position=$(( (menu_position + 1) % menu_items ))
        ;;
    "usb_copy_long")
        exit 0
        ;;
    "usb_copy")
        exit 0
        ;;
esac

echo "${menu_position}" >"${menu_position_file}"

case "${menu_position}" in
    0)
        show "" ""
        ;;
    1)
        show_r "IP address:" "$(get_ip)"
        ;;
    2)
        show_r "Temperature:" "$(get_temperature)"
        ;;
    3)
        show_r "Fan speed:" "$(get_fan_speed)"
        ;;
    *)
        menu_offset=$(( menu_position - base_menu_items ))
        disk_index=$(( menu_offset / 2 + 1 ))
        line_index=$(( menu_offset % 2 ))
        disk_usage_line=$(echo "${disk_usage}" | tail -n+${disk_index} | head -n1)
        disk_name=$(get_disk_name "${disk_usage_line}")
        disk_usage=""
        case "${line_index}" in
            0)
                disk_usage=$(get_disk_free "${disk_usage_line}")
                ;;
            *)
                disk_usage=$(get_disk_usage "${disk_usage_line}")
                ;;
        esac
        show_r "Disk: ${disk_name}" "$disk_usage"
        ;;
esac

