# Hardware Controller for Western Digital My Cloud NAS Systems

This repository contains reimplementations of various user space tools for power,
LED, and temperature management of Western Digital My Cloud DL2100, DL4100, PR2100
and PR4100 NAS Systems.


## WARNING

Modifications to the firmware of your device may **render your device unusable**.
Moreover, modifications to the firmware may **void the warranty for your device**.

You are using the programs in this repository at your own risk. *We are not
responsible for any damage caused by these programs, their incorrect usage, or
inaccuracies in this manual.*


## GETTING STARTED


### Prerequisites

The packages *python3*, *python3-serial*, and *python3-smbus* need to be installed
in order to use the tools:

    sudo apt-get install -y python3 python3-serial python3-smbus

Moreover, either *hddtemp* or *smartctl* is necessary in order to monitor the hard
disk temperature:

    sudo apt-get install -y hddtemp


### Setting up the environment

It is highly recommended to run the daemon as a non-priviledged user. Therefore, a
new system user should be created:

    sudo useradd -r -U -M -b /var/run -s /usr/sbin/nologin wdhwd

When the hardware controller daemon was started as root, it automatically drops its
privileges to this user but retains permissions to access necessary peripheral
hardware components. However, the current implementation uses <samp>sudo</samp> to
interact with certain tools, such as the <samp>hddtemp</samp> and
<samp>shutdown</samp> binaries. Therefore sudo-er permissions for those commands
must to be added. An appropriate sudoers configuration file is available as
[tools/wdhwd.sudoers](tools/wdhwd.sudoers):

    sudo chown root.root tools/wdhwd.sudoers
    sudo chmod ug=r,o= tools/wdhwd.sudoers
    sudo mv tools/wdhwd.sudoers /etc/sudoers.d/wdhwd


### Create the daemon configuration

A sample configuration is available in [tools/wdhwd.conf](tools/wdhwd.conf). You can
start by copying this configuration to <samp>/etc/wdhwd/wdhwd.conf</samp>:

    sudo mkdir /etc/wdhwd
    sudo cp tools/wdhwd.conf /etc/wdhwd/wdhwd.conf
    sudo chown root.root /etc/wdhwd/wdhwd.conf
    sudo chmod u=rw,go=r /etc/wdhwd/wdhwd.conf


### Install the application files

The application files should be installed to <samp>/opt/wdhwd</samp> (make
sure to adapt paths in [wdhwd.conf](tools/wdhwd.conf) and
[wdhwd.service](tools/wdhwd.service) when choosing a different location):

    sudo cp -dR . /opt/wdhwd
    sudo chown -R root.root /opt/wdhwd
    sudo chmod -R u=rwX,go=rX /opt/wdhwd
    sudo chmod -R u=rwx,go=rx /opt/wdhwd/scripts/*


### Prepare logging directory

The sample configuration expects a logging directory writable by the user wdhwd at
<samp>/var/log/wdhwd</samp>:

    sudo mkdir /var/log/wdhwd
    sudo chown wdhwd.root /var/log/wdhwd
    sudo chmod -R u=rwX,g=rX,o= /var/log/wdhwd


### Install and start the daemon

In order to use systemd to manage (i.e. start and stop) the hardware controller
daemon, an appropriate service unit file needs to be installed. 

    sudo cp tools/wdhwd.service /etc/systemd/system/
    sudo chown root.root /etc/systemd/system/wdhwd.service
    sudo chmod u=rw,go=r /etc/systemd/system/wdhwd.service
    sudo systemctl daemon-reload
    sudo systemctl enable wdhwd.service
    sudo systemctl start wdhwd.service


## GET LATEST VERSION

Find documentation and grab the latest version on GitHub
<https://github.com/michaelroland/wdnas-hwdaemon>


## COPYRIGHT

- Copyright (c) 2017-2021 Michael Roland <<mi.roland@gmail.com>>
- Copyright (c) 2019 Stefaan Ghysels <<stefaang@gmail.com>>


## DISCLAIMER

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.


## LICENSE

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

**License**: [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.txt)

