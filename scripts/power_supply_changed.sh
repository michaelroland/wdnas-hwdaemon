#!/usr/bin/env bash

################################################################################
## 
## Power supply changed notification
## 
## Copyright (c) 2017 Michael Roland <mi.roland@gmail.com>
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

power_socket=$1
power_state=$2
event_timestamp=$(date +'%Y-%m-%d %H:%M:%S %z')

if [ "${power_state}" -eq "1" ] ; then
    power_state_human="enabled"
else
    power_state_human="failed"
fi

${sendmail} -t -oi -- ${mail_recipient_addr} <<EOM
From: ${mail_sender_name} <${mail_sender_addr}>
To: ${mail_recipient_addr}
Subject: [${mail_sender_name}] Power supply ${power_socket} ${power_state_human}

Event: Power supply ${power_state_human}
Event time: ${event_timestamp}
Hostname: $(hostname -f)

Power supply on socket ${power_socket} ${power_state_human}.

Socket: ${power_socket}
New state: ${power_state_human} (${power_state})


System: $(uname -a)

EOM

