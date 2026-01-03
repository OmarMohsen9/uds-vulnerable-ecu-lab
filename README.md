# uds-vulnerable-ecu-lab

Virtual UDS (ISO 14229) ECU security lab demonstrating automotive diagnostic vulnerabilities: weak Security Access, session hijacking, brute-force attacks, and enumeration. Includes vulnerable ECU, legitimate tester, and attack tools on virtual CAN bus. Educational only.

## Overview

This repository provides a fully virtual, safe-to-use laboratory for exploring common security weaknesses in automotive diagnostic protocols (UDS and OBD-II).  

It simulates a real-world Electronic Control Unit (ECU) with intentionally vulnerable implementations of key UDS services — particularly Security Access (Service 27) — allowing you to observe, exploit, and understand how poor diagnostic security can be bypassed.

Everything runs on a virtual CAN bus (`vcan0`) using Python and SocketCAN — no hardware required.

Key goal:
- Demonstrate common UDS (ISO 14229) security vulnerabilities in a safe virtual environment
- Show practical attacks like weak seed/key bypass, session hijacking, and brute-force, along with mitigations
- Provide hands-on experience with real UDS services and OBD-II diagnostics

## Team Members
- [Mohamed Bedier](https://github.com/MohamedBedier)
- [Omar Mohsen](https://github.com/OmarMohsen9)

## Installation

### Prerequisites
- Linux (Ubuntu recommended for SocketCAN)
- Python 3.8+
- Virtual CAN interface (vcan)

### Install dependencies:
```bash
sudo apt update
sudo apt install git build-essential libsdl2-dev libsdl2-image-dev can-utils -y
pip3 install python-can python-isotp

# Clone ICSim Repository:
git clone https://github.com/zombieCraig/ICSim.git
cd ICSim

# Build Simulator:
make

#reboot
sudo reboot
```
### Setup virtual CAN bus:
```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```
### Running the Lab
1. Start the ECU (simulates the vulnerable vehicle ECU):
```bash
python3 ecu.py
```
* Logs to ecu.log.
* OBD is free; UDS requires security access.
  
2. Start the Tester (legitimate diagnostic tool):
```bash
python3 tester.py
```
* Interactive: Enter hex commands (e.g., `27 01` for seed request).
* Commands: `e` (enable keep-alive), `x` (disable), `q` (quit).
* Automatically handles security config reads and key derivation.

3. Start the Attacker (for vulnerability demos):
```bash
python3 attack.py
```
* Interactive console: `r` (toggle reverse-capture), `g` (test candidates), `m` (MITM), `b` (brute-force), `ed/er/ep` (enumerate DID/RID/PID), `z` (reset CAN), `h` (help), `q` (quit).
* Send raw hex payloads directly.
  
4. Open candump for better visualization of the CAN bus
```bash
candump vcan0
```
  
Run each in separate terminals. Use `tester.py` for normal ops, `attack.py` for exploits.

For detailed usage, see [Lab Manual](https://github.com/OmarMohsen9/uds-vulnerable-ecu-lab/blob/main/docs/lab_manual.md). For a more technical in-depth dive, see [Technical Documentation](https://github.com/OmarMohsen9/uds-vulnerable-ecu-lab/blob/main/docs/technical_documentation.md).
