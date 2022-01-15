#!/usr/bin/env bash

################################################################################
## 
## LCD menu action
## 
## Copyright (c) 2018-2019 Stefaan Ghysels <stefaang@gmail.com>
## Copyright (c) 2021 Michael Roland <mi.roland@gmail.com>
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

function get_ip {
	ip route get 1 | sed -n -E 's/^.*src\s+(\S+).*$/\1/p'
}

function get_disk_usage {
	df "$1" -h --output=avail,pcent | awk 'NR==2{print $1" / "$2" used"}'
}

function get_temperature {
	wdhwc temperature | sed -n -E 's/^PMC temperature:\s+(.*)$/\1/p'
}

function get_fan_speed {
	wdhwc fan | sed -n -E 's/^Fan speed:\s+(.*)\s+%$/\1%/p'
}


menu_position_file="${PWD}/${menu_position_db}"
if [ -d "${RUNTIME_DIRECTORY}" ] ; then
    menu_position_file="${RUNTIME_DIRECTORY}/${menu_position_db}"
fi
menu_position=$(cat "${menu_position_file}" 2>/dev/null || echo 0)

menu_items=5

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
        show "IP address:" "$(get_ip)"
        ;;
    2)
        show "Temperature:" "$(get_temperature)"
        ;;
    3)
        show "Fan speed:" "$(get_fan_speed)"
        ;;
    4)
        show "Root disk usage:" "$(get_disk_usage /)"
        ;;
    *)
        ;;
esac

