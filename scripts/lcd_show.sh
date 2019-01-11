#!/usr/bin/env bash

################################################################################
## 
## LCD menu action
## Note that it executes both on button press as on release
## 
## Copyright (c) 2018 Stefaan Ghysels <stefaang@gmail.com>
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


function get_ip {
	ip route get 1 | sed 's/^.*src \([^ ]*\).*$/\1/;q'
}

function get_disk_usage {
	df $1 -h --output=avail,pcent | sed 1d | awk '{print $1, "free", $2, "used"}'
}

function get_temperature {
	cd /usr/local/lib/wdhwd
	python3 -m wdhwdaemon.client temperature | sed 's#: #\\n           #'
}

function get_fan_speed {
	cd /usr/local/lib/wdhwd
	python3 -m wdhwdaemon.client fan | sed 's#: #\\n#'
}

function show {
	cd /usr/local/lib/wdhwd
	python3 -m wdhwdaemon.client lcd -t "$1"
}

# button press event triggers both on press as on release
# so we only act on the even numbers
#
# TODO: add long-press example

case "$(( $1 % 10 ))" in 
	0)
		show "   Welcome    "
		;;
	2)
		show "IP address\n$(get_ip)"
		;;
	4)
		root_usage=$(get_disk_usage /)
		show "Root Disk Usage\n${root_usage}"
		;;
	6)
		temperature=$(get_temperature)
		show "$temperature"
		;;
	8)	
		fan_speed=$(get_fan_speed)
		show "$fan_speed"
		;;
	*)
		# do nothing
		;;
esac

