#!/usr/bin/env bash

################################################################################
## 
## System up notification
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

mail_sender_name="NAS $(hostname -s)"
mail_sender_addr="$(whoami)"
mail_recipient_addr="root"
sendmail="/usr/sbin/sendmail"

event_timestamp=$(date +'%Y-%m-%d %H:%M:%S %z')

${sendmail} -t -oi -- ${mail_recipient_addr} <<EOM
From: ${mail_sender_name} <${mail_sender_addr}>
To: ${mail_recipient_addr}
Subject: [${mail_sender_name}] System is up and running

Event: System is up and running
Event time: ${event_timestamp}
Hostname: $(hostname -f)


System: $(uname -a)

EOM

