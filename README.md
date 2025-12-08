CORC BLE → IR Gateway Firmware (MicroPython)

Overview
This repository contains a minimal CORC firmware for a BLE-controlled IR gateway. An Android client discovers the device, connects over GATT, and sends UTF‑8 commands (e.g., POWER, VOL_UP, LEARN_<KEY>) to trigger IR actions. The current version focuses on the BLE side; IR TX/RX hooks are provided for you to integrate hardware-specific logic.

Status
- BLE service implemented in MicroPython (tested on Raspberry Pi Pico W and other boards with the `bluetooth` module).
- Command handlers are placeholders that print received commands; integrate your IR TX/RX routines where indicated.

Features
- CORC 128‑bit service UUID and a single RX characteristic (Write / Write Without Response).
- Simple, human‑readable command protocol over UTF‑8.
- Designed to work with the CORC Android app.

Hardware (suggested)
- Microcontroller with MicroPython and BLE support (e.g., Raspberry Pi Pico W).
- IR LED driver transistor (e.g., 2N2222, 220 Ω base resistor) and IR LED for transmit.
- Optional IR receiver module (e.g., VS1838B or TSOP38238) for learning.
- Appropriate resistors and wiring.

Repository layout
- main.py — MicroPython BLE service exposing an RX characteristic; prints received commands and calls stubs.
- requirements.txt — Type stubs for editor assistance (not used on-device).

Firmware setup (MicroPython)
1) Flash MicroPython to your board (e.g., Pico W). Follow the official getting-started guide for your board.
2) Copy `main.py` to the device using Thonny, rshell, or mpremote.
3) It will start automatically on boot as `main.py`.
4) Reset or power-cycle the board.

What the firmware does
- Starts BLE with device name: `CORC` (default; configurable in code).
- Advertises the CORC custom service in the scan response.
- Accepts UTF‑8 commands written to the RX characteristic.
- Prints the received command and calls a corresponding handler method where you can add IR logic.

BLE GATT details
- Service UUID (128‑bit): `B13A1000-9F2A-4F3B-9C8E-A7D4E3C8B125`
- RX Characteristic UUID: `B13A1001-9F2A-4F3B-9C8E-A7D4E3C8B125`
- RX properties: Write, Write Without Response
- Data format: short ASCII/UTF‑8 strings (e.g., `POWER`); keep packets under typical MTU limits.

Advertising
- Device name: `CORC`
- Flags: General Discoverable, BR/EDR Not Supported
- Scan Response: Complete List of 128‑bit Service UUIDs (includes the service UUID above)

Command protocol (strings)
Send one of the following UTF‑8 strings to the RX characteristic:
- `POWER`
- `VOL_UP`
- `VOL_DOWN`
- `CH_UP`
- `CH_DOWN`
- `MUTE`
- `LEARN_<KEY>` — e.g., `LEARN_POWER`, `LEARN_TV`, `LEARN_CUSTOM1`

On receipt, the device prints a log, e.g., `BLE: Received command: 'POWER'`. Implement the corresponding methods in `main.py` to transmit or learn IR codes.

Android client
- Recommended: CORC Android app (source of truth for GATT details)
  - Service UUID: `B13A1000-9F2A-4F3B-9C8E-A7D4E3C8B125`
  - RX Characteristic: `B13A1001-9F2A-4F3B-9C8E-A7D4E3C8B125`
  - Write Type: Write Without Response
- Repository: https://github.com/co-rc/remote-android
- First run flow per app docs: the app scans for devices advertising name `CORC`, connects, discovers services, and writes UTF‑8 commands.

Extending with IR functionality
In `main.py`, these placeholders are where to integrate your IR logic:
- `cmd_power`, `cmd_vol_up`, `cmd_vol_down`, `cmd_ch_up`, `cmd_ch_down`, `cmd_mute`
- `cmd_learn(key_name)`

Typical steps:
1) Add a PWM or PIO‑based IR transmitter routine and map commands to stored IR code sequences.
2) For learning: sample from an IR receiver, decode (NEC/RC5/etc.), and store the code under `key_name`.
3) Persist learned codes in flash or external storage.

Troubleshooting
- ImportError: No module named `bluetooth` when running on a PC
  - This code runs on MicroPython firmware on a microcontroller with BLE (e.g., Pico W). It will not import on desktop CPython.

- I cannot see the device when scanning
  - Ensure the board supports BLE, the firmware is MicroPython with BLE, and `main.py` is running. Power‑cycle after copying the file. Keep the name short to fit advertisement limits.

- Writes fail or time out
  - Use Write Without Response. Stay within typical BLE MTU (20 bytes default if MTU exchange didn’t occur).

Configuration
- Change the advertised name: `BleIrRemote("CORC")` in `main.py`.
- UUIDs must match the Android client expectations; keep the service and RX characteristic UUIDs as listed above.

License
This project is released under the MIT License. See LICENSE for details.
