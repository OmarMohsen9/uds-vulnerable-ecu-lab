# Virtual UDS ECU Security Lab

A virtual lab for exploring UDS (ISO 14229) and OBD-II vulnerabilities in a simulated automotive ECU.

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

Run each in separate terminals. Use `tester.py` for normal ops, `attack.py` for exploits.

For detailed usage, see docs/lab_manual.md. For a more technical in-depth dive, see docs/technical_documentation.md.
