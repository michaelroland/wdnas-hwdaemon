#!/usr/bin/env bash

################################################################################
## 
## Button pressed notification
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

# set a message on LCD
function show {
	cd /usr/local/lib/wdhwd
	python3 -m wdhwdaemon.client lcd -t "$1"
}

USB_PRESSED=/tmp/usb_button_pressed
if [ ! -e ${USB_PRESSED} ]; then
	touch ${USB_PRESSED}
	show "USB button pressed"
else
	lastModified=$(date +%s -r ${USB_PRESSED})
	now=$(date +%s)
	show "USB button released\nafter $(( $now - $lastModified )) seconds"
	rm ${USB_PRESSED}
fi


# e.g. backup data from USB
# rsync -a /mnt/usb/data /mnt/volume/data

# or upload to the cloud
# cadaver cp /mnt/usb/data somecloud.com


