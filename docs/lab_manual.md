# UDS ECU Security Lab Manual

This manual provides hands-on instructions for using the lab, based on `tester.py` and `attack.py` expected behaviors. It covers what you can do/expect, best secure mode configurations, services/sub-functions, NRCs, attacks, and more.

## What You Can Do/Expect from This Lab
- **Simulate Real-World Diagnostics**: Interact with a virtual ECU via OBD-II (free) and UDS (secured).
- **Learn Vulnerabilities**: Demonstrate weak security access, session hijacking, brute-force, enumeration.
- **Expectations**: All runs on virtual CAN (vcan0). Logs in `*.log` files. Colored console output for TX/RX. Security starts locked; unlock via Service 27.
- **Extensions**: Modify `ecu.py` for custom DIDs/RIDs. Add real hardware (e.g., CAN USB adapter) by changing interface.

## Instructions for Tester.py (Legitimate Tool)
- Run: `python3 tester.py`
- Input hex payloads (e.g., `27 01` for seed request, `27 02 11 22 33 44` for key).
- Auto-handles seed/key: On `67 01`, computes key (XOR `0x11223344`; multi-op XORs extra `0xA55AA55A` if enabled).
- `e`: Enable auto TesterPresent (3E 80) every 4s.
- `x`: Disable auto keep-alive.
- `q`: Quit.
- After writing F1A0 (e.g., `2E F1 A0 01`), auto re-reads config.
- On session/reset (10/11), rebuilds stack.

## Instructions for Attack.py (Attack Tool)
- Run: `python3 attack.py`
- Sniffs CAN traffic passively.
- Commands:
  - `r`: Toggle reverse-capture (captures seed/key for algorithm reverse-engineering).
  - `g`: Test generated candidates against ECU.
  - `m`: MITM mode – Waits for unlock, hijacks session with `10 03`, spams TesterPresent to lock out original.
  - `b`: Brute-force seed (tries 0x11-0x1CF XOR static key).
  - `ed`: Enumerate DIDs (F100-F200).
  - `er`: Enumerate RIDs (1200-1400).
  - `ep`: Enumerate PIDs (00-FF).
  - `z`: Flush CAN/ISO-TP buffers.
  - `h`: Show menu.
  - `q`: Quit.
- Send raw hex (e.g., `3E 80`).
- In reverse mode: Captures seed/key, generates candidates (XOR, add, sub, mul patterns).

## Best Secure Mode Configurations
- Enable Anti-Bruteforce: Write DID F1A0 = 0x01 (limits to 3 trials, 1s timeout).
- Enable Multi-Op: F1A0 = 0x02 (adds extra XOR for key derivation).
- Both: F1A0 = 0x03.
- Read F1A0 first: `22 F1 A0`.
- Best: Enable both + modify `ecu.py` for stronger RNG (e.g., `secrets.token_bytes`), delays on fails, session binding.

## Services List and Sub-Functions
- **0x01 (OBD Current Data)**: Sub: PID (e.g., 0x0C RPM, 0x0D Speed). Free access.
- **0x09 (OBD Vehicle Info)**: Sub: PID (e.g., 0x02 VIN). Free.
- **0x10 (Diagnostic Session)**: Sub: 0x01 (Default), 0x02 (Extended), 0x03 (Programming). Requires unlock for 0x02/03.
- **0x11 (ECU Reset)**: Sub: 0x01/02/03. Clears security/session.
- **0x22 (Read Data by ID)**: Sub: DID (e.g., F190 VIN, F18C Model, F1A0 Config). Restricted in default session.
- **0x27 (Security Access)**: Sub: 0x01 (Seed Request), 0x02 (Key Send). Uses XOR static key.
- **0x2E (Write Data by ID)**: Sub: DID (only F1A0 supported, 1-byte value). Requires unlock.
- **0x31 (Routine Control)**: Sub: 0x01 (Start), 0x03 (Results). RIDs: 0x1234 (sum), 0x1300 (mult).
- **0x3E (Tester Present)**: Sub: 0x00 (Response), 0x80 (No Response).

## NRCs (Negative Response Codes)
- 0x11: Service Not Supported.
- 0x12: Sub-Function Not Supported.
- 0x13: Incorrect Message Length.
- 0x22: Conditions Not Correct (e.g., wrong session).
- 0x24: Request Sequence Error.
- 0x31: Request Out of Range (unsupported DID/RID).
- 0x33: Security Access Denied.
- 0x35: Invalid Key.
- 0x36: Exceed Number of Attempts.
- 0x37: Required Time Delay Not Expired.
- 0x7F: General Reject (with service/code).

## Attacks List
- **Reverse-Engineering Key Algo**: Capture one seed/key, generate patterns, test.
- **MITM Session Hijack**: Wait for unlock, inject privileged session (10 03).
- **Brute-Force Seed/Key**: Limited range (0x11-1CF); disabled by anti-BF.
- **Enumeration**: Scan DIDs/RIDs/PIDs for supported identifiers.
- **Config Downgrade**: After unlock, write F1A0=0x00 to disable protections.
- **DoS via Spam**: Flood TesterPresent to disrupt.

## Troubleshooting
- No response? Check vcan0 up, stacks on correct IDs (7E0/7E8).
- Timeout? Increase in code or check bus load.
- Logs: Check `ecu.log`/`tester.log` for errors.

This lab teaches secure diagnostics - use for educational purposes only
