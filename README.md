# CORC BLE → IR Gateway Firmware (MicroPython)

## Overview
This repository contains the CORC firmware for a BLE-controlled IR gateway, designed for Raspberry Pi Pico W. The device acts as a BLE peripheral (GATT server), receiving commands from an Android app and converting them into IR signals.

## Project Status
- **BLE Service**: Implemented using `uasyncio` and `bluetooth` module.
- **Async Design**: Follows a single-threaded async model. BLE IRQ callbacks are minimal and offload work to the async layer.
- **Platform**: Optimized for Raspberry Pi Pico W (MicroPython).

## Features
- **CORC Service**: Custom 128‑bit service UUID with command and response characteristics.
- **Async Protocol**: Handles connections, MTU exchange, and security updates asynchronously.
- **Reliability**: Designed for `write-with-response` operations and uses notifications for device-to-app communication.

## Hardware Requirements
- **Microcontroller**: Raspberry Pi Pico W.
- **IR Hardware**: IR LED transmitter (connected via transistor) and optional IR receiver for learning.

## Repository Layout
- `main.py`: Core firmware implementation including `CorcBlePeripheral` and async loop.
- `requirements.txt`: Type stubs for development (not required on-device).

## Setup
1. **Flash MicroPython**: Install the latest MicroPython firmware on your Pico W.
2. **Deploy Code**: Copy `main.py` to the root of the device (as `main.py`).
3. **Run**: Reset the board. The firmware starts automatically and begins advertising as `CORC`.

## BLE GATT Specification
- **Service UUID**: `B13A1000-9F2A-4F3B-9C8E-A7D4E3C8B125`
- **Command Characteristic**: `B13A1001-9F2A-4F3B-9C8E-A7D4E3C8B125`
  - Properties: Write, Write Without Response (Write with response preferred)
- **Response Characteristic**: (Notifications enabled for asynchronous responses)
- **Byte Order**: `LITTLE_ENDIAN` (as per `PROTOCOL_BYTE_ORDER`).

## Advertising
- **Device Name**: `CORC`
- **Flags**: General Discoverable, BR/EDR Not Supported.
- **Scan Response**: Includes the 128‑bit CORC Service UUID.

## Architecture & Guidelines
This project follows specific development guidelines defined in `.aiassistant/rules/guidelines.md`:
- **Concurrency**: `uasyncio`-based. No blocking in IRQ/event callbacks.
- **Memory**: Avoids dynamic allocations in hot paths; reuses buffers.
- **Error Handling**: Uses explicit result types/constants for expected failures.
- **State Management**: Maintains a clear connection state machine (see `BleConnection` class).

## Extending the Firmware
Implementation details for IR transmission and protocol handling should be added to the async tasks in `main.py`. Ensure that IR work does not stall BLE responsiveness by scheduling it from the async layer.

## Troubleshooting
- **Connection Issues**: Check if the device is advertising. Ensure your client supports 128-bit UUIDs.
- **Write Failures**: Ensure the write type matches the characteristic properties. Check for MTU limitations (the firmware handles MTU exchange but do not assume a specific size).

## License
Released under the MIT License. See `LICENSE` for details.
