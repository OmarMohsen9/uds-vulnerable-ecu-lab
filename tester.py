import funcs
import isotp
import can
import time
import sys, select

# =======================
# ANSI COLOR DEFINITIONS
# =======================
RESET   = "\033[0m"
BOLD    = "\033[1m"

RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
CYAN    = "\033[36m"
GRAY    = "\033[90m"

def info(msg):    print(f"{CYAN}[INFO]{RESET} {msg}")
def ok(msg):      print(f"{GREEN}[OK]{RESET} {msg}")
def warn(msg):    print(f"{YELLOW}[WARN]{RESET} {msg}")
def err(msg):     print(f"{RED}[ERR]{RESET} {msg}")
def tx(msg):      print(f"{GREEN}→ TX{RESET} {msg}")
def rx(msg):      print(f"{BLUE}← RX{RESET} {msg}")

# =======================
# CAN / ISO-TP SETUP
# =======================
bus = can.interface.Bus(interface='socketcan', channel='vcan0')

phy_add = isotp.Address(
    isotp.AddressingMode.Normal_11bits,
    rxid=0x7E8,
    txid=0x7E0
)

stack = isotp.CanStack(bus=bus, address=phy_add)

# =======================
# GLOBAL STATE
# =======================
auto_keepalive = False
last_keepalive_sent = 0.0
KEEPALIVE_INTERVAL = 4.0

F1A0_VALUE = 0x00
MULTI_OP_ENABLED = False
ANTI_BF_ENABLED = False

STATIC_KEY1 = 0x11223344
STATIC_KEY2 = 0xA55AA55A

# =======================
# LOGGING
# =======================
funcs.logging.basicConfig(
    filename='tester.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=funcs.logging.INFO
)

# =======================
# SECURITY CONFIG
# =======================
def read_security_config():
    global F1A0_VALUE, MULTI_OP_ENABLED, ANTI_BF_ENABLED

    resp = funcs.send_and_receive(stack, b'\x22\xF1\xA0', timeout=1.0)
    if resp and resp[:3] == b'\x62\xF1\xA0' and len(resp) >= 4:
        F1A0_VALUE = resp[3]
        MULTI_OP_ENABLED = bool(F1A0_VALUE & 0b10)
        ANTI_BF_ENABLED  = bool(F1A0_VALUE & 0b01)

        modes = []
        if ANTI_BF_ENABLED: modes.append("ANTI-BRUTEFORCE")
        if MULTI_OP_ENABLED: modes.append("MULTI-OP")
        if not modes: modes.append("LAB MODE")

        ok(f"Security config → F1A0=0x{F1A0_VALUE:02X} | {' | '.join(modes)}")
    else:
        warn("Failed to read F1A0 → assuming LAB MODE")
        F1A0_VALUE = 0x00
        MULTI_OP_ENABLED = False
        ANTI_BF_ENABLED = False

# =======================
# MAIN
# =======================
if __name__ == "__main__":

    print(f"{BOLD}{CYAN}")
    print("════════════════════════════════════")
    print("        OBD / UDS TESTER READY")
    print("════════════════════════════════════")
    print(f"{RESET}")
    print("hex = send OBD/UDS command")
    print("e   = enable auto 3E 80 keep-alive")
    print("x   = disable auto keep-alive")
    print("q   = quit\n")

    while True:
        stack.process()
        time.sleep(0.001)

        # === AUTO KEEP-ALIVE ===
        if auto_keepalive:
            now = time.time()
            if now - last_keepalive_sent >= KEEPALIVE_INTERVAL:
                try:
                    stack.send(b'\x3E\x80')
                    tx("3E 80 (auto keep-alive)")
                    last_keepalive_sent = now
                except:
                    err("Failed to send keep-alive")

        # === NON-BLOCKING INPUT ===
        if select.select([sys.stdin], [], [], 0)[0]:
            user_in = sys.stdin.readline().strip()
            if not user_in:
                continue

            cmd = user_in.lower()

            if cmd == "q":
                info("Exiting tester")
                break

            if cmd == "e":
                auto_keepalive = True
                last_keepalive_sent = time.time() - KEEPALIVE_INTERVAL
                ok("Auto keep-alive ENABLED (4s)")
                continue

            if cmd == "x":
                auto_keepalive = False
                warn("Auto keep-alive DISABLED")
                continue

            # === HEX PAYLOAD ===
            cleaned = user_in.replace(" ", "").replace("0x", "")
            if len(cleaned) % 2 != 0 or not all(c in "0123456789abcdefABCDEF" for c in cleaned):
                err("Invalid hex input")
                continue

            payload = bytes.fromhex(cleaned)
            tx(" ".join(f"{b:02X}" for b in payload))

            response = funcs.send_and_receive(stack, payload)
            if response:
                rx(" ".join(f"{b:02X}" for b in response))
            else:
                warn("TIMEOUT")
                continue

            # === SEED / KEY HANDLING ===
            if response[:2] == b'\x67\x01' and len(response) >= 6:
                seed = int.from_bytes(response[2:6], 'big')

                if seed == 0:
                    ok("Already unlocked")
                else:
                    info(f"Seed = 0x{seed:08X}")

                    key = seed ^ STATIC_KEY1
                    if MULTI_OP_ENABLED:
                        key ^= STATIC_KEY2
                        info("Multi-op key derivation")
                    else:
                        info("Standard key derivation")

                    key &= 0xFFFFFFFF
                    tx(f"Key = 0x{key:08X}")

                    unlock = funcs.send_and_receive(
                        stack,
                        b'\x27\x02' + key.to_bytes(4, 'big'),
                        timeout=2.0
                    )

                    if unlock == b'\x67\x02':
                        ok("UNLOCK SUCCESS")
                    else:
                        err(f"Unlock failed → {unlock.hex() if unlock else 'TIMEOUT'}")

            # === F1A0 WRITE ===
            if payload[:3] == b'\x2E\xF1\xA0':
                warn("F1A0 written → re-reading config")
                time.sleep(0.3)
                read_security_config()

            # === SESSION / RESET ===
            if response[0] in (0x50, 0x51):
                warn("Session change/reset → rebuilding stack")
                stack = funcs.reset_can_stack(stack, bus, phy_add)
                time.sleep(0.5)
                read_security_config()
