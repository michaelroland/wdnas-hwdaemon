# User Space Tools for Western Digital My Cloud DL2100 NAS Systems

This repository contains reimplementations of various user space tools for power,
LED, and temperature management of Western Digital My Cloud DL2100 NAS Systems.


## WARNING

Modifications to the firmware of your device may **render your device unusable**.
Moreover, modifications to the firmware may **void the warranty for your device**.

You are using the programs in this repository at your own risk. *We are not
responsible for any damage caused by these programs, their incorrect usage, or
inaccuracies in this manual.*


## GETTING STARTED


### Prerequisites

The packages *python*, *python-serial*, and *python-smbus* need to be installed
in order to use the tools:

    sudo apt install python python-serial python-smbus

Moreover, *hddtemp* is necessary in order to monitor the hard disk temperature:

    sudo apt install hddtemp


### Setting up the environment

While the hardware controller daemon could be run as root, it is highly recommended
to run the daemon as a non-priviledged user. This non-priviledged user needs
permissions to access various hardware such as serial ports and harddisk SMART
information. Therefore, a new system user needs to be created:

    sudo useradd -r -U -M -b /var/run -s /usr/sbin/nologin wdhwd

The user needs permissions to access the serial port (group "dialout") and the
I2C/SMBUS (group "i2c"):

    sudo usermod -a -G dialout,i2c wdhwd

Moreover, the user needs sudo-er permissions to execute the <samp>hddtemp</samp>
and <samp>shutdown</samp> binaries:

    echo '# sudoers file for Western Digital Hardware Controller Daemon
    wdhwd ALL=(ALL) NOPASSWD: NOEXEC: NOMAIL: NOSETENV: /usr/sbin/hddtemp /dev/sd?, \
            /sbin/shutdown -P now, /sbin/shutdown -P +60, /sbin/shutdown -c
    ' >wdhwd.sudoers
    sudo chown root.root wdhwd.sudoers
    sudo chmod 0440 wdhwd.sudoers
    sudo mv wdhwd.sudoers /etc/sudoers.d/wdhwd


## GET LATEST VERSION

Find documentation and grab the latest version on GitHub
<https://github.com/michaelroland/wdnas-dl2100-hwtools>


## COPYRIGHT

- Copyright (c) 2017 Michael Roland <<mi.roland@gmail.com>>


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

