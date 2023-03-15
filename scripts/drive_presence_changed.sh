#!/usr/bin/env bash

################################################################################
## 
## Drive presence changed notification
## 
## Copyright (c) 2017-2023 Michael Roland <mi.roland@gmail.com>
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

retry_count="90"
while [[ $retry_count -gt 0 && -z $(hostname --all-fqdns) ]]; do
    sleep 1
    retry_count=$((retry_count - 1))
done

mail_sender_name="NAS $(hostname -s)"
mail_sender_addr="$(whoami)"
mail_recipient_addr="root"
sendmail="/usr/sbin/sendmail"

drive_bay=$1
drive_state=$2
drive_name=$3
event_timestamp=$(date +'%Y-%m-%d %H:%M:%S %z')

if [ "${drive_state}" -eq "1" ] ; then
    drive_state_human="present"
else
    drive_state_human="absent"
fi

${sendmail} -t -oi -- ${mail_recipient_addr} <<EOM
From: ${mail_sender_name} <${mail_sender_addr}>
To: ${mail_recipient_addr}
Subject: [${mail_sender_name}] Drive presence changed

Event: Drive presence changed
Event time: ${event_timestamp}
Hostname: $(hostname -f)

Disk ${drive_name} in drive bay ${drive_bay} changed its presence state.
The drive is ${drive_state_human} now.

Drive bay: ${drive_bay}
Device: ${drive_name}
New state: ${drive_state_human} (${drive_state})


System: $(uname -a)

EOM

