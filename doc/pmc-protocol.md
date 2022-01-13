# PMC/BBC Protocol Documentation

The PMC chip (on DL2100/DL4100) or BBC chip (on PR2100/PR4100) is a separate microcontroller that
controls the fan, LEDs, LCD and drive bay power, and that monitors the board temperature, drive
bay status, front buttons and power supply state. It is connected to the main processor (host)
over a serial UART interface. This serial interface is accessible as <samp>/dev/ttyS0</samp>
(on DL2100/DL4100) or <samp>/dev/ttyS2</samp> (on PR2100/PR4100)[^WD-Community-PR-Firmware].


> #### Speculations on the Acronyms "PMC" and "BBC"
> 
> - PMC might be an acronym for peripheral management controller or power management controller.
> - BBC might be an acronym for baseboard controller.


## Serial Interface Parameters

- Baud rate: 9600
- Data bits: 8
- Parity: none
- Stop bits: 1


## Transmission Protocol

Communication on the serial line is encoded as US-ASCII text. Messages are terminated with a
carriage return character (<tt>CR</tt>, ASCII code <samp>0x0D</samp>, `"\r"`).

There are three types of protocol messages exchanged over the serial line:

- Commands are sent from the host to the PMC. A command starts a command-response sequence.
- Responses are sent from the PMC to the host. Response messages may only be sent as part of
  a command-response sequence (i.e. in direct response to a preceding command).
- Interrupts are sent from the PMC to the host. Interrupts may be sent by the PMC at any time.

> **TODO:** It would be interesting to analyze how the update command (<samp>UPD</samp>) works.
> A post[^WD-Community-PR-Command-Bruteforce] on WD Community suggests that the update command
> may switch into an interactive menu. Moreover, submitting the firmware binary would probably
> require different message structures. Consequently, this command might use additional message
> types.

Command-response sequences can be split into two types: getter sequences and setter sequences.


### Getter Sequences

Getter sequences are used to obtain data (e.g. current board temperature, current fan speed,
current LED state, etc.) from the PMC. A command consists of a command code
(<samp><i>CMD</i></samp>) only:

<pre>
<i>CMD</i>\r
</pre>

In a successful response, the PMC echos the command code, followed by the character "=",
followed by the data value (<samp><i>DATA</i></samp>):

<pre>
<i>CMD</i>=<i>DATA</i>\r
</pre>

If the command fails (e.g. due to an invalid command code), the PMC returns the failure
indicator ("<samp>ERR</samp>"):

<pre>
ERR\r
</pre>


### Setter Sequences

Setter sequences are used to update data (e.g. new fan speed, new LED state, etc.) on the PMC.
A command consists of a command code (<samp><i>CMD</i></samp>), followed by the character "=",
followed by the new data value (<samp><i>DATA</i></samp>):

<pre>
<i>CMD</i>=<i>DATA</i>\r
</pre>

If the command succeeds, the PMC returns the acknowledgment indicator ("<samp>ACK</samp>"):

<pre>
ACK\r
</pre>

If the command fails (e.g. due to an invalid command code, or an invalid data value), the PMC
returns the failure indicator ("<samp>ERR</samp>"):

<pre>
ERR\r
</pre>


### Interrupts

Interrupt messages are used to notify the host about pending events on the PMC. An interrupt
message consists of the interrupt indicator ("<samp>ALERT</samp>"):

<pre>
ALERT\r
</pre>

The host may then read the interrupt status register to determine the event that triggered
the interrupt.

The host can enable/disable specific interrupt sources through the interrupt mask register.


## Commands

Command codes are typically encoded as three upper-case characters.


### VER: Get Version

This command reads the PMC version information. The version information is encoded as a
US-ASCII string of the form "<samp>WD (PMC|BBC) v\d+</samp>".

- Command: "<samp>VER</samp>"
- Response: "<samp>VER=<i>VERSION-STRING</i></samp>"

#### Observations

The following values were observed for the version information:

- On DL2100: "<samp>WD PMC v17</samp>"
- On PR4100: "<samp>WD BBC v02</samp>"


### CFG: Get/Set Configuration Register

This command reads and writes the PMC configuration register. The register value (1 byte)
is encoded as a hexadecimal number. Leading zeros may be omitted.

Getter sequence:

- Command: "<samp>CFG</samp>"
- Response: "<samp>CFG=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>CFG=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### Observations

The following values were observed for the configuration register:

- On DL2100: "<samp>03</samp>"
- On PR4100: "<samp>03</samp>"

#### Configuration Register Value

- Bit 0: automatic drive bay power enable based on presence detection
- Bit 1: *unknown* (set upon power-up)
- Bit 2: *unknown* (cleared upon power-up)
- Bit 3: *unknown* (cleared upon power-up)
- Bit 4: *unknown* (cleared upon power-up)
- Bit 5: *unknown* (cleared upon power-up)
- Bit 6: *unknown* (cleared upon power-up)
- Bit 7: *unknown* (cleared upon power-up)

> **TODO:** The function of some of the bits in the configuration register is unknown. Further
> analysis of the remaining bits would be interesting.


### STA: Get Status Register

This command reads the PMC (power-up?) status register. The register value (1 byte) is
encoded as a hexadecimal number.

- Command: "<samp>STA</samp>"
- Response: "<samp>STA=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

#### Observations

The following values were observed for the status register:

- On DL2100 and PR4100, when powered up with power adapter at socket 1 plugged in: "<samp>6c</samp>"
- On DL2100 and PR4100, when powered up with power adapter at socket 2 plugged in: "<samp>6a</samp>"
- On DL2100 and PR4100, when powered up with power adapter at sockets 1 and 2 plugged in: "<samp>6e</samp>"

#### Status Register Value

- Bit 0: *unknown* (cleared upon power-up)
- Bit 1: Power adapter at socket 2 plugged in (and supplying power) during start-up
- Bit 2: Power adapter at socket 1 plugged in (and supplying power) during start-up
- Bit 3: *unknown* (set upon power-up), might indicate that USB copy button was not pressed during start-up (unverified!)
- Bit 4: *unknown* (cleared upon power-up)
- Bit 5: *unknown* (set upon power-up), might indicate that LCD up button was not pressed during start-up (unverified!)
- Bit 6: *unknown* (set upon power-up), might indicate that LCD down button was not pressed during start-up (unverified!)
- Bit 7: *unknown* (cleared upon power-up)

> **TODO:** The function of some of the bits in the status register is unknown or unverified.
> Further analysis of the remaining bits would be interesting.


### ISR: Get Interrupt Status Register

This command reads the interrupt status register. The register value (1 byte) is
encoded as a hexadecimal number.

- Command: "<samp>ISR</samp>"
- Response: "<samp>ISR=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

#### Observations

The following values were observed for the interrupt status register:

- On DL2100 and PR4100: "<samp>00</samp>"
- On DL2100 and PR4100 with IMR set to <samp>0xFF</samp> and after receiving an interrupt (<samp>ALERT</samp>):
    - After boot-up when the power adapter at socket 1 was unplugged and re-plugged while powered off: "<samp>6c</samp>" (same value as STA)
    - After boot-up when the power adapter at socket 2 was unplugged and re-plugged while powered off: "<samp>6a</samp>" (same value as STA)
    - After boot-up when the power adapters at both sockets were unplugged and re-plugged while powered off: "<samp>6e</samp>" (same value as STA)
    - After boot-up when the power adapters at both sockets were unplugged and re-plugged while powered off: "<samp>6e</samp>" (same value as STA)
    - When the power adapter at socket 1 is unplugged or re-plugged while powered on: "<samp>04</samp>"
    - When the power adapter at socket 2 is unplugged or re-plugged while powered on: "<samp>02</samp>"
    - When a drive is inserted into or removed from any drive bay: "<samp>10</samp>"
    - When the USB copy button is pressed or released: "<samp>08</samp>"
- On PR4100 with IMR set to <samp>0xFF</samp> and after receiving an interrupt (<samp>ALERT</samp>):
    - When the LCD up button is pressed or released: "<samp>20</samp>"
    - When the LCD down button is pressed or released: "<samp>40</samp>"

#### Interrupt Status Register Value

The interrupt status register represents a bitmask of the current pending interrupts when the
PMC signaled an interrupt. The flags are automatically cleared after the register was read.

- Bit 0: *unknown* (always observed as cleared)
- Bit 1: Power adapter state at socket 2 changed
- Bit 2: Power adapter state at socket 1 changed
- Bit 3: USB copy button pressed or released
- Bit 4: Drive presence changed
- Bit 5: LCD up button pressed or released
- Bit 6: LCD down button pressed or released
- Bit 7: Echo setter command (<samp>ECH=XX</samp>) received

> **TODO:** The function of some of the bits in the interrupt status register is unknown.
> Further analysis of the remaining bits would be interesting.


### IMR: Get/Set Interrupt Mask Register

This command reads and writes the interrupt mask register. The register value (1 byte) is
encoded as a hexadecimal number.

Getter sequence:

- Command: "<samp>IMR</samp>"
- Response: "<samp>IMR=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>IMR=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### Observations

The original firmware on the DL2100 and PR4100 set the interrupt mask register to
"<samp>ff</samp>" (<samp>0xFF</samp>) upon startup.

#### Interrupt Mask Register Value

The interrupt mask register represents a bitmask of the enabled interrupts. The bitmask
matches the corresponding flags in the interrupt status register. The value <samp>0xFF</samp>
enables all interrupts.

- Bit 0: *unknown*
- Bit 1: Enable power adapter state at socket 2 changed interrupt
- Bit 2: Enable power adapter state at socket 1 changed interrupt
- Bit 3: Enable USB copy button pressed or released interrupt
- Bit 4: Enable Drive presence changed interrupt
- Bit 5: Enable LCD up button pressed or released interrupt
- Bit 6: Enable LCD down button pressed or released interrupt
- Bit 7: Enable echo setter command (<samp>ECH=XX</samp>) received interrupt

> **TODO:** The function of some of the bits in the interrupt mask register is unknown.
> Further analysis of the remaining bits would be interesting.


### ECH: Get/Set Echo Register

This command reads and writes the echo(?) register. The register value (1 byte) is encoded
as a hexadecimal number. Writing the echo register causes an immediate interrupt with the
echo interrupt flag (bit 7) set.

> **TODO:** The interpretation of this command is pure speculation based on observations.
> It's unclear if this command is actually intended as an echo mechanism or if it has other
> side-effects that were not observed yet.

Getter sequence:

- Command: "<samp>ECH</samp>"
- Response: "<samp>ECH=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>ECH=<i>VALUE</i></samp>"
- Response: "<samp>ALERT</samp>"

> Note: This setter sequence deviates from typical setter sequences as there is no direct
> response (acknowledgment). Instead, the PMC immediately sends an interrupt message.

#### Observations

The following values were observed for the interrupt status register:

- On DL2100 and PR4100 upon power-up: "<samp>00</samp>"
- On DL2100 and PR4100, this read value always matches the previously set value.
- On DL2100 and PR4100, setting any value immediately triggers an interrupt request with
  ISR set to <samp>0x80</samp>. No other side-effects were observed yet.


### UPD: Update Mode

This command brings the PMC into update mode.

> **TODO:** It is unclear how this command works exactly. However,
> observations[^WD-Community-PR-Command-Examination] suggest that this command might allow
> dumping the current PMC firmware which would allow more detailed analysis of the PMC
> functionality.

#### Observations

The getter sequence variant of this command causes a "WDPMC Update Menu" to be output on the
serial line:

<pre>
========= WDPMC Update Menu v1.0 =============
Reset PMC -------------------------------- 0
Write Image To PMC Internal Flash -------- 1
Read Image From PMC Internal Flash ------- 2
Execute The New Program ------------------ 3
==============================================
</pre>
Subsequent communication causes the following error message[^WD-Community-PR-Command-Bruteforce]:
<pre>
Invalid Number ! ==> The number should be either 1, 2 or 3
</pre>
Hence, it seems that this is an interactive menu that does not follow the usual PMC serial
transmission protocol. The update menu uses the term "PMC" even on the PR4100 (despite the
different terminology in the version string).


### BKL: Get/Set LCD Background Light Intensity

This command reads and writes the LCD background light intensity register. The register value
(1 byte) is encoded as a hexadecimal value.

Getter sequence:

- Command: "<samp>BKL</samp>"
- Response: "<samp>BKL=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>BKL=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### Observations

The default value on PR4100 is "<samp>64</samp>" (<samp>0x64</samp>, potentially indicating 100%)
upon startup.

#### LCD Background Light Intensity Register Value

The LCD background light intensity register contains an unsigned integer that represents the
current LCD background light intensity in percent.


### LNx: Set LCD Text Lines

These commands write the LCD text lines (LN1 for the first line, LN2 for the second line).
The text value is US-ASCII encoded.

Line 1:

- Command: "<samp>LN1=<i>TEXT</i></samp>"
- Response: "<samp>ACK</samp>"

Line 2:

- Command: "<samp>LN2=<i>TEXT</i></samp>"
- Response: "<samp>ACK</samp>"

#### Observations

The default values on PR4100 are "<samp>Welcome to WD</samp>" (line 1) and "<samp>My Cloud PR4100</samp>"
(line 2) upon startup. The values are write-only. If more than 16 characters (display width) are provided,
the additional characters seem to be ignored.


### TMP: Get Temperature

This command reads the board temperature register. The register value (1 byte) is encoded
as a hexadecimal value.

- Command: "<samp>TMP</samp>"
- Response: "<samp>TMP=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

#### Observations

Various observed values on the DL2100 and PR4100 at room temperature during normal operation:
"<samp>1f</samp>", "<samp>28</samp>", "<samp>2e</samp>", "<samp>2f</samp>", "<samp>33</samp>".

#### Board Temperature Register Value

The board temperature register contains an unsigned integer that represents the current
temperature in degrees Celsius.


### FAN: Get/Set Fan Intensity

This command reads and writes the fan intensity register. The register value (1 byte) is encoded
as a hexadecimal value.

Getter sequence:

- Command: "<samp>FAN</samp>"
- Response: "<samp>FAN=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>FAN=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### Observations

- The default value on DL2100 and PR4100 is "<samp>50</samp>" (<samp>0x50</samp>, indicating 80%)
  upon startup.
- WD's wdhws seems to enforce the value to remain between 0 and 99.

#### Fan Intensity Register Value

The fan intensity register contains an unsigned integer that represents the current fan speed
in percent.


### RPM: Get Fan Speed RPM

This command reads the fan speed (RPM) register. The register value (2 bytes) is encoded
as a hexadecimal value.

- Command: "<samp>RPM</samp>"
- Response: "<samp>RPM=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a four-digit
  hexadecimal value)

#### Observations

The following values were observed for the fan speed (RPM) register:

- On DL2100:
  - "<samp>10E0</samp>" at <samp>FAN=50</samp> indicating 4320 RPM with fan at 80%.
  - "<samp>0726</samp>" at <samp>FAN=1f</samp> indicating 1830 RPM with fan at 31%.
- On PR4100:
  - "<samp>079e</samp>" at <samp>FAN=50</samp> indicating 1950 RPM with fan at 80%.
  - "<samp>04ec</samp>" at <samp>FAN=30</samp> indicating 1260 RPM with fan at 48%.
  - "<samp>0366</samp>" at <samp>FAN=1f</samp> indicating 870 RPM with fan at 31%.

#### Fan Speed RPM Register Value

The fan speed (RPM) register contains an unsigned integer that represents the current
fan speed in RPM.


### TAC: Get Fan Tacho Count

This command reads the fan tacho count register (fan speed in tacho pulses per second).
The register value (2 bytes) is encoded as a hexadecimal value.

- Command: "<samp>TAC</samp>"
- Response: "<samp>TAC=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a four-digit
  hexadecimal value)

#### Observations

The following values were observed for the fan speed (tacho pulses per second) register:

- On DL2100:
  - "<samp>003e</samp>" at <samp>RPM=0744</samp> and <samp>FAN=1e</samp> indicating 62 pulses at 1860 RPM and fan at 30%.
  - "<samp>008f</samp>" at <samp>RPM=10a4</samp> and <samp>FAN=50</samp> indicating 143 pulses at 4260 RPM and fan at 80%.
- On PR4100:
  - "<samp>0041</samp>" at <samp>RPM=079e</samp> and <samp>FAN=50</samp> indicating 65 pulses at 1950 RPM and fan at 80%.
  - "<samp>002c</samp>" at <samp>RPM=04ec</samp> and <samp>FAN=30</samp> indicating 44 pulses at 1260 RPM and fan at 48%.
  - "<samp>001c</samp>" at <samp>RPM=0366</samp> and <samp>FAN=1f</samp> indicating 28 pulses at 870 RPM and fan at 31%.

#### Fan Tacho Count Register Value

The fan tacho count register contains an unsigned integer that represents the current
fan speed in tacho pulses per second.


### LED: Get/Set LED Steady Status

This command reads and writes the LED steady status register. The register value (1 byte) is
encoded as a hexadecimal value.

Getter sequence:

- Command: "<samp>LED</samp>"
- Response: "<samp>LED=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>LED=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### LED Steady Status Register Value

The LED steady status register represents a bitmask of the enabled color LEDs.

- Bit 0: Power button LED blue
- Bit 1: Power button LED red
- Bit 2: Power button LED green
- Bit 3: USB button LED blue
- Bit 4: USB button LED red
- Bit 5: *not used*
- Bit 6: *not used*
- Bit 7: *not used*

The power button LED supports combinations of RGB by turning multiple color components on
simulateneously. Similarly the USB button supports the combination of red and blue to purple.


### BLK: Get/Set LED Blink Status

This command reads and writes the LED blink status register. The register value (1 byte) is
encoded as a hexadecimal value.

Getter sequence:

- Command: "<samp>BLK</samp>"
- Response: "<samp>BLK=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>BLK=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### LED Blink Status Register Value

The LED blink status register represents a bitmask of color LEDs that should blink. The bitmask
matches the corresponding flags in the LED steady state register. Blink cycles (50% on, 50% off)
start at the configured LED steady state (e.g. if blue power button LED is on and blink is set
for blue and read power button LEDs, the power button LED will toggle between blue and red).


### PLS: Get/Set LED Pulse Status

This command reads and writes the LED pulse status register. The register value (1 byte) is
encoded as a hexadecimal value.

Getter sequence:

- Command: "<samp>PLS</samp>"
- Response: "<samp>PLS=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>PLS=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### LED Pulse Status Register Value

The LED pulse status register turns pulsing blue light for the power button on or off.

- Bit 0: Pulse power button LED blue
- Bit 1: *not used*
- Bit 2: *not used*
- Bit 3: *not used*
- Bit 4: *not used*
- Bit 5: *not used*
- Bit 6: *not used*
- Bit 7: *not used*


### DP0: Get Drive Presence Mask

This command reads the drive presence mask register. The register value (1 byte) is encoded
as a hexadecimal value.

- Command: "<samp>DP0</samp>"
- Response: "<samp>DP0=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

#### Observations

The following values were observed for the drive presence mask register:

- On DL2100:
  - "<samp>8c</samp>" when drives inserted in both bays.
  - "<samp>8d</samp>" when no drive is inserted in bay 1 (left).
  - "<samp>8e</samp>" when no drive is inserted in bay 0 (right).
- On PR4100:
  - "<samp>90</samp>" when drives inserted in all 4 bays.
  - "<samp>91</samp>" when no drive is inserted in bay 0 (left).
  - "<samp>92</samp>" when no drive is inserted in bay 1 (second from left).
  - "<samp>94</samp>" when no drive is inserted in bay 2 (third from left).
  - "<samp>98</samp>" when no drive is inserted in bay 3 (right).

#### Drive Presence Mask Register Value

The drive presence mask register contains a bitmask indicating the size of the drivebay array
and the inserted drives.

- Bit 0: Cleared when drive in bay 0 (right on DL2100, left on PR4100) is present, set when drive is absent
- Bit 1: Cleared when drive in bay 1 (left on DL2100) is present, set when drive is absent
- Bit 2: Cleared when drive in bay 2 is present, set when drive is absent (always set on DL2100)
- Bit 3: Cleared when drive in bay 3 (right on PR4100) is present, set when drive is absent (always set on DL2100)
- Bit 4: 4-bay indicator (set if 4 bays exist, cleared if only 2 bays exist)
- Bit 5: *unknown* (always cleared)
- Bit 6: *unknown* (always cleared)
- Bit 7: *unknown* (always set)


### DE0: Get/Set Drive Enable Mask

This command reads and writes the drive enable mask register. The register value (1 byte) is
encoded as a hexadecimal value.

Getter sequence:

- Command: "<samp>DE0</samp>"
- Response: "<samp>DE0=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>DE0=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### Observations

The following values were observed for the drive enable mask register:

- On DL2100:
  - "<samp>f3</samp>" when drives in both bays are powered up.
  - "<samp>f2</samp>" when drive in bay 1 (left) is powered up.
  - "<samp>f1</samp>" when drive in bay 0 (right) is powered up.
- On PR4100:
  - "<samp>ff</samp>" when drives in all 4 bays are powered up.

#### Drive Enable Mask Register Value

The drive enable mask register contains a bitmask indicating the enabled drive bays and
drive bay alert (red) LED status.

- Bit 0: Set when drive in bay 0 (right on DL2100, left on PR4100) is powered up, cleared when drive is absent or powered down (also indicated by blue drive bay power LED).
- Bit 1: Set when drive in bay 1 (left on DL2100) is powered up, cleared when drive is absent or powered down (also indicated by blue drive bay power LED).
- Bit 2: Set when drive in bay 2 is powered up, cleared when drive is absent or powered down (also indicated by blue drive bay power LED).
- Bit 3: Set when drive in bay 3 (right on PR4100) is powered up, cleared when drive is absent or powered down (also indicated by blue drive bay power LED).
- Bit 4: Set when drive alert LED (red) for bay 0 (right on DL2100, left on PR4100) is off, cleared when alert LED is on.
- Bit 5: Set when drive alert LED (red) for bay 1 (left on DL2100) is off, cleared when alert LED is on.
- Bit 6: Set when drive alert LED (red) for bay 2 is off, cleared when alert LED is on.
- Bit 7: Set when drive alert LED (red) for bay 3 (right on PR4100) is off, cleared when alert LED is on.

Instead of setting the drive enable mask register directly, the DLS/DLC setter commands
can be used to make (atomic?) bitwise modifications.


### DLS: Set Bits in Drive Enable Mask

This command sets bits in the drive enable mask register. The bitmask to be set in the
register value (1 bytes) is encoded as a hexadecimal value.

- Command: "<samp>DLS=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"


### DLC: Clear Bits in Drive Enable Mask

This command clears bits in the drive enable mask register. The bitmask to be cleared in the
register value (1 bytes) is encoded as a hexadecimal value.

- Command: "<samp>DLS=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"


### DLB: Get/Set Drive Alert LED Blink Mask

This command reads and writes the drive alert LED blink mask register. The register value
(1 byte) is encoded as a hexadecimal value.

Getter sequence:

- Command: "<samp>DLB</samp>"
- Response: "<samp>DLB=<i>VALUE</i></samp>" (where <samp><i>VALUE</i></samp> is a two-digit
  hexadecimal value)

Setter sequence:

- Command: "<samp>DLB=<i>VALUE</i></samp>"
- Response: "<samp>ACK</samp>"

#### Observations

The default value in DL2100 and PR4100 is "<samp>00</samp>" upon power up.

#### Drive Alert LED Blink Mask Register Value

The drive alert LED blink mask register contains a bitmask indicating the blink status of
the drive bay alert (red) LED.

- Bit 0: *unused* (always cleared)
- Bit 1: *unused* (always cleared)
- Bit 2: *unused* (always cleared)
- Bit 3: *unused* (always cleared)
- Bit 4: Set when drive alert LED (red) for bay 0 (right on DL2100, left on PR4100) is blinking, cleared when alert LED is off/not blinking.
- Bit 5: Set when drive alert LED (red) for bay 1 (left on DL2100) is blinking, cleared when alert LED is off/not blinking.
- Bit 6: Set when drive alert LED (red) for bay 2 is blinking, cleared when alert LED is off/not blinking.
- Bit 7: Set when drive alert LED (red) for bay 3 (right on PR4100) is blinking, cleared when alert LED is off/not blinking.

Instead of setting the drive enable mask register directly, the DLS/DLC setter commands
can be used to make (atomic?) bitwise modifications.


## References

[^WD-Community-PR-Firmware]: [Thread "*My Cloud PR4100 / PR2100 Firmware*" on WD Community](https://community.wd.com/t/my-cloud-pr4100-pr2100-firmware/200873)
[^WD-Community-PR-Command-Bruteforce]: [Post by TfL about "*Polling all possible 3 letter fields*" in "*My Cloud PR4100 / PR2100 Firmware*" on WD Community](https://community.wd.com/t/my-cloud-pr4100-pr2100-firmware/200873/226)
[^WD-Community-PR-Command-Examination]: [Post by dswv42 about "*BBC Command Coding*" in "*My Cloud PR4100 / PR2100 Firmware*" on WD Community](https://community.wd.com/t/my-cloud-pr4100-pr2100-firmware/200873/250)
[^WD-Community-PR-Command-Trace]: [Post by dswv42 about "*Command Trace of wdhwd on PR4100*" in "*My Cloud PR4100 / PR2100 Firmware*" on WD Community](https://community.wd.com/t/my-cloud-pr4100-pr2100-firmware/200873/252)
