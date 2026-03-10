import ctypes
import os
import time

log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_log.txt")

def log(msg):
    with open(log_file, "a") as f:
        f.write(msg + "\n")

log("Started")

if os.name == 'nt':
    HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def console_ctrl_handler(ctrl_type):
        log(f"Received ctrl_type: {ctrl_type}")
        time.sleep(1)
        log("Handler finished sleep")
        return True
    
    # Must keep reference
    _ctrl_handler = HandlerRoutine(console_ctrl_handler)
    success = ctypes.windll.kernel32.SetConsoleCtrlHandler(_ctrl_handler, True)
    log(f"SetConsoleCtrlHandler success: {success}")

while True:
    time.sleep(1)
