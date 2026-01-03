# Technical Documentation: Virtual ECU Implementation

## OBD Mode Explanation and Why Not Secured
OBD-II (On-Board Diagnostics) mode handles emissions-related data (e.g., RPM, Speed, VIN) via services like 0x01/0x09. In this ECU:
- It's "free" (no security) for compliance with regulations (e.g., EPA/CARB require open access for emissions checks).
- Why not secured? OBD is designed for universal tools (e.g., scan tools at inspections). Securing it could hinder diagnostics, but this exposes sensitive data (e.g., VIN) to anyone on the CAN bus. In real ECUs, OBD is often read-only and limited, but here it's fully open, simulating legacy/vulnerable designs. Risk: Data leakage without authentication.

## Services Listed: What Each Stands For and Does
- **0x01 (Show Current Data)[OBD]**: Reads real-time vehicle data (PIDs like 0x0C RPM=6904, 0x0D Speed=50 km/h).
- **0x09 (Vehicle Information)[OBD]**: Reads static info (PID 0x02 VIN).
- **0x10 (Diagnostic Session Control)[UDS]**: Switches sessions (Default: basic; Extended/Programming: advanced, requires unlock).
- **0x11 (ECU Reset)[UDS]**: Resets ECU state (clears security/session).
- **0x22 (Read Data By Identifier)[UDS]**: Reads ECU-specific data (DIDs: F190 VIN, F18C Model, F1A0 Security Config).
- **0x27 (Security Access)[UDS]**: Authenticates for protected services (seed challenge-response with XOR key).
- **0x2E (Write Data By Identifier)[UDS]**: Writes data (only F1A0 for config; 1-byte, requires unlock).
- **0x31 (Routine Control)[UDS]**: Executes/stops routines (RIDs: 1234 sum→0x000F, 1300 mult→0x0012; stores results).
- **0x3E (Tester Present)[UDS]**: Keeps session active (prevents timeout).

## NRC Meanings
See [Lab Manual](https://github.com/OmarMohsen9/uds-vulnerable-ecu-lab/blob/main/docs/lab_manual.md) for list. In context:
- 0x13/0x12: Protects against malformed requests.
- 0x33: Enforces security levels.
- 0x35-0x37: Anti-brute-force mechanisms (invalid key, too many tries, delay).
- Used to gracefully reject invalid ops, but weak if no rate-limiting.

## Vulnerabilities
- **Static/Predictable Key (V-01)**: XOR with fixed 0x11223344; seed range 0x11-0x1CF. Easily reversed or brute-forced.
- **No Mandatory Delays (V-02)**: Allows rapid attacks unless anti-BF enabled.
- **Session Hijacking (V-03)**: Post-unlock, any tool can command (no binding to tester).
- **Enumerable Identifiers (V-04)**: Scan reveals supported DIDs/RIDs/PIDs, aiding further attacks.
- **Writable Security Config (V-05)**: F1A0 can disable protections after minimal unlock.
- **Lack of Auth/Encryption (V-06)**: No MAC/HMAC; open to replay/injection on bus.

## How We Secured Those Vulnerabilities (Mitigations in Code/Recommendations)
- **Static Key**: In `ecu.py`, XOR is simple; mitigate by replacing with AES-CMAC or OEM algo. Add: Use `secrets` for 32-bit seeds.
- **Predictable Seed/Delays**: Enable anti-BF (F1A0 bit 0x01) for 3-trial limit + 1s timeout. Code: `timeout = 1 if anti_bf else 10000`. Recommend: 5s delay per ISO, exponential backoff.
- **Hijacking**: Code checks `unlocked` but no tester ID. Mitigate: Add session nonce or bind to source ID (extend `handle_27`).
- **Enumeration**: No built-in rate-limit; mitigate by adding response delays or blacklisting rapid scans in `ecu.py`.
- **Writable Config**: Restrict writes to higher sessions. Code: Check `current_session == "Programming"` in `handle_2E`.
- **Auth/Encryption**: Recommend UDSec (ISO 15764) extension. In code: Add HMAC to responses (e.g., via `hmac` lib).
- Overall: Modify `STATIC_KEY` to dynamic, increase `MAX_TRIALS` to 5, log attempts. For full security: Implement certificates or hardware keys.

This doc aids in understanding and hardening the ECU simulation.
