import time
import logging
import isotp

def log(print_msg, level="info"):
    print(print_msg)
    level = level.lower()
    if level == "info":
        logging.info(print_msg)
    elif level == "warning":
        logging.warning(print_msg)
    elif level == "error":
        logging.error(print_msg)
    else:
        logging.info(print_msg)

def send_msg(stack,payload):
    stack.send(payload)
    log("request received, sending ISO-TP...")
    while stack.transmitting():
        stack.process()
        #time.sleep(0.005)

def rec_msg(stack):
    timeout = time.time() + 0.5  # 2-second timeout
    while time.time() < timeout:
        stack.process()
        if stack.available():
            return stack.recv()
    #log("response timeout","warning")

def send_and_receive(stack, payload, timeout=0.5):
    stack.send(payload)
    log(f"Sent: {payload.hex()}")

    start_time = time.time()
    while time.time() - start_time < timeout:
        stack.process()           # Keep the state machine alive
        time.sleep(0.001)
        
        if stack.available():
            response = stack.recv()
            return response
    
    #log("Response timeout!", "warning")
    return None

def reset_can_stack(old_stack, bus, address):
    try:
        old_stack.stop_sending()
        old_stack.stop_receiving()
    except:
        pass
    new_stack = isotp.CanStack(bus=bus, address=address)
    time.sleep(0.08)  # Let CAN bus settle
    return new_stack

