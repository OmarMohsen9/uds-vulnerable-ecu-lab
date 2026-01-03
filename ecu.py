import can
import time
import isotp
import random
import struct
import logging

# =======================
# ANSI COLORS
# =======================
RESET = "\033[0m"
BOLD  = "\033[1m"

RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
CYAN   = "\033[36m"
GRAY   = "\033[90m"

def ecu(msg):   print(f"{CYAN}[ECU]{RESET} {msg}")
def rx(msg):    print(f"{BLUE}← RX{RESET} {msg}")
def tx(msg):    print(f"{GREEN}→ TX{RESET} {msg}")
def warn(msg):  print(f"{YELLOW}[WARN]{RESET} {msg}")
def err(msg):   print(f"{RED}[ERR]{RESET} {msg}")
def sec(msg):   print(f"{YELLOW}[SEC]{RESET} {msg}")
def obd(msg):   print(f"{GRAY}[OBD]{RESET} {msg}")

# =======================
# SETUP
# =======================
bus = can.interface.Bus(interface='socketcan', channel='vcan0')

phy_add = isotp.Address(
    isotp.AddressingMode.Normal_11bits,
    rxid=0x7E0,
    txid=0x7E8
)

stack = isotp.CanStack(bus=bus, address=phy_add)

# =======================
# GLOBAL STATE
# =======================
VIN = b"SAJDA41C62NA30290"

supported_dids = {
    0xF190: VIN,
    0xF18C: b"G05",
    0xF1A0: b"\x00"
}

supported_rids = {
    0x1234: "sum",
    0x1300: "mult"
}

ROUTINE_RESULTS = {}
ROUTINE_FUNCTIONS = {
    "sum":  lambda: bytes([0x00, 0x0F]),
    "mult": lambda: bytes([0x00, 0x12])
}

unlocked = False
active_seed = None
seed_time = 0.0
trial_count = 0
MAX_TRIALS = 3

STATIC_KEY = 0x11223344
UNLOCK_DURATION = 10

last_activity_time = time.time()
current_session = "Default"

ANTI_BRUTEFORCE_BIT = 0b00000001

# =======================
# LOGGING
# =======================
logging.basicConfig(
    filename='ecu.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

print(f"{BOLD}{CYAN}")
print("════════════════════════════════════")
print("      COMBINED ECU STARTED")
print("   OBD = FREE | UDS = SECURED")
print("════════════════════════════════════")
print(f"{RESET}")

# =======================
# NRC
# =======================
def nrc(service, code):
    warn(f"NRC → 7F {service:02X} {code:02X}")
    return bytes([0x7F, service, code])

# =======================
# OBD HANDLER
# =======================
def handle_obd_request(data: bytes) -> bool:
    if len(data) < 2:
        return False

    mode, pid = data[0], data[1]

    if mode == 0x01:
        if pid == 0x0C:
            rpm = 6904
            val = rpm * 4
            stack.send(bytes([0x41, 0x0C, val >> 8 & 0xFF, val & 0xFF]))
            obd(f"RPM = {rpm}")
            return True

        if pid == 0x0D:
            speed = 50
            stack.send(bytes([0x41, 0x0D, speed]))
            obd(f"Speed = {speed} km/h")
            return True

    if mode == 0x09 and pid == 0x02:
        stack.send(bytes([0x49, 0x02, 0x01]) + VIN)
        obd("VIN sent (09 02)")
        return True

    return False

# =======================
# SECURITY ACCESS (27)
# =======================
def handle_27_security_access(data: bytes) -> bytes:
    global unlocked, active_seed, seed_time, trial_count, last_activity_time

    if len(data) < 2:
        return nrc(0x27, 0x13)

    sub = data[1]
    config = supported_dids[0xF1A0][0]
    anti_bf = bool(config & ANTI_BRUTEFORCE_BIT)
    timeout = 1 if anti_bf else 10000

    if sub == 0x01:
        seed = 0 if unlocked else random.randint(0x11, 0x1CF)
        active_seed = seed
        seed_time = time.time()
        trial_count = 0
        sec(f"Seed = {seed:08X} | AntiBF={anti_bf} | Timeout={timeout}s")
        return bytes([0x67, 0x01]) + struct.pack(">I", seed)

    if sub == 0x02:
        if len(data) != 6:
            return nrc(0x27, 0x13)
        if unlocked:
            return bytes([0x67, 0x02])
        if active_seed is None:
            return nrc(0x27, 0x35)

        if time.time() - seed_time > timeout:
            warn("Seed expired")
            active_seed = None
            return nrc(0x27, 0x37)

        if anti_bf and trial_count >= MAX_TRIALS:
            warn("Too many wrong attempts")
            active_seed = None
            return nrc(0x27, 0x36)

        key = struct.unpack(">I", data[2:6])[0]
        expected = active_seed ^ STATIC_KEY

        sec(f"Key={key:08X} Expected={expected:08X} Trial={trial_count}")

        if key == expected:
            unlocked = True
            active_seed = None
            sec("UNLOCKED")
            return bytes([0x67, 0x02])

        trial_count += 1
        return nrc(0x27, 0x35)

    return nrc(0x27, 0x12)
def handle_10_session_control(data: bytes) -> bytes:
    global current_session, last_activity_time
    if len(data) < 2:
        return nrc(0x10, 0x13)
    sub = data[1]
    if sub == 0x01:
        current_session = "Default"
        last_activity_time = time.time()
        return bytes([0x50, 0x01])
    if sub in (0x02, 0x03):
        if not unlocked:
            return nrc(0x10, 0x33)  # securityAccessRequired
        current_session = "Programming" if sub == 0x03 else "Extended"
        last_activity_time = time.time()
        return bytes([0x50, sub])
    return nrc(0x10, 0x12)


def handle_11_ecu_reset(data: bytes) -> bytes:
    global unlocked, current_session, active_seed, last_activity_time
    if len(data) < 2:
        return nrc(0x11, 0x13)
    sub = data[1]
    if sub in (0x01, 0x02, 0x03):
        unlocked = False
        current_session = "Default"
        active_seed = None
        last_activity_time = time.time()
        logging.info(f"[ECU] ECU Reset {sub:02X} → cleared security & session")
        return bytes([0x51, sub])
    return nrc(0x11, 0x12)


def handle_3E_tester_present(data: bytes) -> bytes | None:
    global last_activity_time
    if len(data) < 2 or data[1] not in (0x00, 0x80):
        return nrc(0x3E, 0x12 if len(data) >= 2 else 0x13)
    last_activity_time = time.time()
    if data[1] == 0x00:
        return bytes([0x7E, 0x00])
    return None


def handle_22_read_did(data: bytes) -> bytes:
    if len(data) != 3:
        return nrc(0x22, 0x13)
    did = (data[1] << 8) | data[2]
    if did not in supported_dids:
        return nrc(0x22, 0x31)
    if did in (0xF190, 0xF18C) and current_session == "Default":
        return nrc(0x22, 0x33)
    value = supported_dids[did]
    return bytes([0x62]) + data[1:3] + value


# Replace your handle_2E_write_did with this ultra-clean version (1-byte only)
def handle_2E_write_did(data: bytes) -> bytes:
    if len(data) < 3:
        return nrc(0x2E, 0x13)
    did = (data[1] << 8) | data[2]
    value = data[3:]

    if did != 0xF1A0:
        return nrc(0x2E, 0x31)
    if not unlocked:
        return nrc(0x2E, 0x33)

    # Accept exactly 1 byte — reject anything else
    if len(value) != 1:
        return nrc(0x2E, 0x13)  # incorrectMessageLength

    supported_dids[0xF1A0] = value  # store the single byte
    enabled = "ENABLED" if (value[0] & 0x01) else "DISABLED"

    print(f"[ECU] ANTI-BRUTEFORCE → {enabled} | F1A0 now = {value[0]:02X}h]")
    logging.info(f"Anti-bruteforce {enabled} — F1A0 set to {value[0]:02X}h")

    return bytes([0x6E, 0xF1, 0xA0])


def handle_31_routine_control(data: bytes) -> bytes:
    if len(data) < 4:
        return nrc(0x31, 0x13)
    sub = data[1]
    rid = (data[2] << 8) | data[3]
    if sub not in (0x01, 0x03):
        return nrc(0x31, 0x12)
    if rid not in supported_rids:
        return nrc(0x31, 0x31)
    name = supported_rids[rid]
    func = ROUTINE_FUNCTIONS[name]
    if sub == 0x01:
        if rid == 0x5678:
            if current_session not in ("Extended", "Programmer"):
                return nrc(0x31, 0x22)
        result = func()
        ROUTINE_RESULTS[rid] = result
        return bytes([0x71, 0x01]) + data[2:4] + result
    if sub == 0x03:
        if rid not in ROUTINE_RESULTS:
            return nrc(0x31, 0x24)
        return bytes([0x71, 0x03]) + data[2:4] + ROUTINE_RESULTS[rid]
    return nrc(0x31, 0x12)

# =======================
# MAIN LOOP
# =======================
while True:
    stack.process()
    time.sleep(0.001)

    if not stack.available():
        continue

    msg = stack.recv()
    rx(msg.hex().upper())

    if handle_obd_request(msg):
        continue

    sid = msg[0]
    response = None

    if sid == 0x27:
        response = handle_27_security_access(msg)
    elif sid == 0x10:
        response = handle_10_session_control(msg)
    elif sid == 0x11:
        response = handle_11_ecu_reset(msg)
    elif sid == 0x3E:
        response = handle_3E_tester_present(msg)
    elif sid == 0x22:
        response = handle_22_read_did(msg)
    elif sid == 0x2E:
        response = handle_2E_write_did(msg)
    elif sid == 0x31:
        response = handle_31_routine_control(msg)
    else:
        response = nrc(sid, 0x11)

    if response:
        tx(response.hex().upper())
        stack.send(response)
