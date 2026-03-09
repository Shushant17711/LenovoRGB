import hid
import time
import argparse
import sys
import os
import threading
import keyboard
import soundcard as sc
import numpy as np
import random
import psutil
import colorsys
import math
import tempfile

STOP_FILE = os.path.join(tempfile.gettempdir(), "loq_rgb_stop.txt")
stop_event = None

def is_stopped():
    if stop_event is not None and stop_event.is_set():
        return True
    if os.path.exists(STOP_FILE):
        return True
    return False

def sleep_interruptible(duration):
    loops = int(duration / 0.1)
    remainder = duration - (loops * 0.1)
    for _ in range(loops):
        if is_stopped():
            return True
        time.sleep(0.1)
    if is_stopped():
        return True
    if remainder > 0:
        time.sleep(remainder)
    return False

def kill_other_instances():
    """Instead of force killing, request graceful termination via STOP_FILE."""
    current_pid = os.getpid()
    
    # Check if any loq_rgb.py processes exist
    found_other = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and proc.pid != current_pid:
                cmdline = ' '.join(proc.info['cmdline']).lower()
                if 'loq_rgb.py' in cmdline and 'python' in proc.info['name'].lower():
                    found_other = True
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    if found_other:
        print("Signalling other instances to stop gracefully...")
        try:
            with open(STOP_FILE, 'w') as f:
                f.write("stop")
        except Exception:
            pass
            
        time.sleep(1.5) # Wait for them to clean up (unhook keyboard, turn off lights)
        
        if os.path.exists(STOP_FILE):
            try:
                os.remove(STOP_FILE)
            except Exception:
                pass

        # Force kill any zombies that didn't stop
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline'] and proc.pid != current_pid:
                    cmdline = ' '.join(proc.info['cmdline']).lower()
                    if 'loq_rgb.py' in cmdline and 'python' in proc.info['name'].lower():
                        print(f"Force terminating unresponsive instance (PID: {proc.pid})")
                        proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

VENDOR_ID = 0x048d
KNOWN_PIDS = [0xc995, 0xc994, 0xc993, 0xc985, 0xc984, 0xc983, 0xc975, 0xc973, 0xc965, 0xc963, 0xc955]

ZONE_MAP = {
    # Zone 0: leftmost
    'esc': 0, 'f1': 0, 'f2': 0, 'f3': 0, 'f4': 0, '`': 0, '1': 0, '2': 0, '3': 0, '4': 0,
    'tab': 0, 'q': 0, 'w': 0, 'e': 0, 'r': 0, 'caps lock': 0, 'a': 0, 's': 0, 'd': 0, 'f': 0,
    'left shift': 0, 'shift': 0, 'z': 0, 'x': 0, 'c': 0, 'v': 0, 'left ctrl': 0, 'ctrl': 0,
    'left windows': 0, 'windows': 0, 'left alt': 0, 'alt': 0,

    # Zone 1: middle-left
    'f5': 1, 'f6': 1, 'f7': 1, 'f8': 1, '5': 1, '6': 1, '7': 1, '8': 1,
    't': 1, 'y': 1, 'u': 1, 'i': 1, 'g': 1, 'h': 1, 'j': 1, 'k': 1,
    'b': 1, 'n': 1, 'm': 1, ',': 1, 'space': 1,

    # Zone 2: middle-right
    'f9': 2, 'f10': 2, 'f11': 2, 'f12': 2, '9': 2, '0': 2, '-': 2, '=': 2, 'backspace': 2,
    'o': 2, 'p': 2, '[': 2, ']': 2, '\\': 2, 'l': 2, ';': 2, "'": 2, 'enter': 2,
    '.': 2, '/': 2, 'right shift': 2, 'right alt': 2, 'right ctrl': 2, 'print screen': 2, 'prtscn': 2, 'menu': 2,

    # Zone 3: right (numpad/arrows)
    'insert': 3, 'delete': 3, 'home': 3, 'end': 3, 'page up': 3, 'page down': 3,
    'up': 3, 'down': 3, 'left': 3, 'right': 3, 'num lock': 3, 'divide': 3, 'multiply': 3, 'subtract': 3, 'add': 3, 'decimal': 3, 'clear': 3,
}

class LenovoKeyboard:
    def __init__(self):
        self.device = None
        for device_dict in hid.enumerate():
            if device_dict['vendor_id'] == VENDOR_ID and device_dict['product_id'] in KNOWN_PIDS:
                if device_dict.get('usage_page', 0) == 0xff89 and device_dict.get('usage', 0) == 0x00cc:
                    try:
                        self.device = hid.device()
                        self.device.open_path(device_dict['path'])
                        self.device.set_nonblocking(1)
                        print(f"Connected to Lenovo Keyboard RGB Interface (PID: {hex(device_dict['product_id'])})")
                        break
                    except Exception as e:
                        print(f"Found but failed to open RGB interface {hex(device_dict['product_id'])}: {e}")
                        
        if not self.device:
            print("Lenovo 4-Zone RGB Keyboard not found or the specific RGB interface (0xff89:0xcc) was missing.")
            print("Please ensure you are running as Administrator and Lenovo Vantage RGB is set to Static/Off.")
            sys.exit(1)
            
        self.colors = [[0,0,0], [0,0,0], [0,0,0], [0,0,0]] # Zones 0-3 (R,G,B)
        self.apply_colors()
        
    def __del__(self):
        if self.device:
            self.colors = [[0,0,0], [0,0,0], [0,0,0], [0,0,0]]
            try:
                self.apply_colors()
            except:
                pass
            try:
                self.device.close()
            except:
                pass

    def apply_colors(self):
        payload = [0] * 33
        payload[0] = 0xcc
        payload[1] = 0x16
        payload[2] = 0x01 # Static Custom mode
        payload[3] = 1    # Speed
        payload[4] = 1    # Brightness (2=high, 1=low)

        for z in range(4):
            payload[5 + z*3] = int(min(255, max(0, self.colors[z][0])))
            payload[6 + z*3] = int(min(255, max(0, self.colors[z][1])))
            payload[7 + z*3] = int(min(255, max(0, self.colors[z][2])))

        try:
            self.device.send_feature_report(payload)
        except Exception as e:
            pass

# State for TypeLighting
zone_colors = [[0,0,0], [0,0,0], [0,0,0], [0,0,0]]
zone_brightness = [0.0, 0.0, 0.0, 0.0]

def get_random_color():
    colors = [
        [255, 0, 0], [0, 255, 0], [0, 0, 255], 
        [255, 255, 0], [0, 255, 255], [255, 0, 255],
        [255, 128, 0], [128, 0, 255]
    ]
    return list(random.choice(colors))

def on_key_event(e):
    if e.event_type == keyboard.KEY_DOWN:
        name = e.name.lower() if hasattr(e, 'name') and e.name else ''
        zone = ZONE_MAP.get(name, -1)
        
        # Override for numpad/arrow keys using scan codes
        if hasattr(e, 'scan_code') and e.scan_code in [71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 284, 309, 327, 328, 329, 331, 333, 335, 336, 337, 338, 339]:
            zone = 3
            
        if 'numpad' in name or (hasattr(e, 'is_keypad') and e.is_keypad):
            zone = 3
            
        if zone == -1:
            zone = random.randint(0, 3)
            
        # Always change color on new keypress if it's currently visible
        # This provides immediate visual feedback for rapid repeated presses
        if zone_brightness[zone] > 0.1:
            # Pick a new color that is different from the current one
            new_color = get_random_color()
            while new_color == zone_colors[zone]:
                new_color = get_random_color()
            zone_colors[zone] = new_color
        else:
            zone_colors[zone] = get_random_color()
            
        # Snap brightness back to max
        zone_brightness[zone] = 1.0

def mode_type_lighting(kb):
    print("Starting Type-Lighting Mode. Press keys to light up zones!")
    print("Press Ctrl+C to exit.")
    keyboard.hook(on_key_event)
    try:
        while not is_stopped():
            for z in range(4):
                zone_brightness[z] = max(0.0, zone_brightness[z] - 0.05) # Fade speed (much faster)
                kb.colors[z] = [int(c * zone_brightness[z]) for c in zone_colors[z]]
            kb.apply_colors()
            if sleep_interruptible(0.015): # ~60 fps update rate for faster reaction
                break
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        try:
            keyboard.unhook_all()
        except:
            pass

def mode_audio_visualizer(kb):
    print("Starting Audio Visualizer mode. Note: Make sure music is playing!")
    print("Press Ctrl+C to exit.")
    
    # Get all loopback mics
    mics = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
            
    if not mics:
        print("Error: No audio output devices found to loopback from.")
        return

    print("Searching for an active audio stream...")
    active_mic = None
    SAMPLE_RATE = 44100
    
    for m in mics:
        if is_stopped(): return
        try:
            with m.recorder(samplerate=SAMPLE_RATE) as mic:
                # Read a few frames to see if it's dead silence or real audio
                for _ in range(3):
                    if is_stopped(): return
                    data = mic.record(numframes=1024)
                    rms = np.sqrt(np.mean(np.mean(data, axis=1)**2))
                    if rms > 0.0001:
                        active_mic = m
                        break
            if active_mic:
                break
        except Exception:
            pass
            
    if active_mic:
        loopback_mic = active_mic
        print(f"Found active audio on: {loopback_mic.name}")
    else:
        loopback_mic = mics[0]
        print(f"No active audio detected. Defaulting to: {loopback_mic.name}")
        
    try:
        with loopback_mic.recorder(samplerate=SAMPLE_RATE) as mic:
            smooth_colors = [[0,0,0] for _ in range(4)]
            max_vals = [0.001, 0.001, 0.001, 0.001] # bass, mid, treble, rms
            while not is_stopped():
                data = mic.record(numframes=1024)
                mono = np.mean(data, axis=1) # mix to mono
                
                # compute FFT
                fft = np.abs(np.fft.rfft(mono))
                # frequency bins
                bass = np.mean(fft[0:6]) if len(fft) > 6 else 0
                mid = np.mean(fft[6:40]) if len(fft) > 40 else 0
                treble = np.mean(fft[40:150]) if len(fft) > 150 else 0
                
                rms = np.sqrt(np.mean(mono**2))
                
                # Auto-calibrate max values
                max_vals[0] = max(bass, max_vals[0] * 0.999)
                max_vals[1] = max(mid, max_vals[1] * 0.999)
                max_vals[2] = max(treble, max_vals[2] * 0.999)
                max_vals[3] = max(rms, max_vals[3] * 0.999)

                def scale(val, max_val):
                    ratio = (val / max_val) if max_val > 0 else 0
                    ratio = ratio ** 1.5
                    return int(min(ratio * 255.0, 255))
                
                targets = [
                    [scale(bass, max_vals[0]), 0, 0],             # Red Bass
                    [0, scale(mid, max_vals[1]), 0],              # Green Mid
                    [0, 0, scale(treble, max_vals[2])],           # Blue Treble
                    [scale(rms, max_vals[3])] * 3                 # White Master
                ]
                
                for z in range(4):
                    for c in range(3):
                        if targets[z][c] > smooth_colors[z][c]:
                            smooth_colors[z][c] = targets[z][c] # attack instantly
                        else:
                            smooth_colors[z][c] = max(0, smooth_colors[z][c] - 15) # decay smoothly
                        kb.colors[z][c] = int(smooth_colors[z][c])
                
                kb.apply_colors()
    except KeyboardInterrupt:
        print("Exiting...")
    except Exception as e:
        print(f"Error initializing audio capture: {e}")

def mode_cpu_monitor(kb):
    print("Starting Advanced CPU Core Monitor mode.")
    print("Zones physically map to your CPU core groups.")
    print("Blue = Idle, Green = Normal, Red = High Load.")
    print("Press Ctrl+C to exit.")
    
    psutil.cpu_percent(interval=None, percpu=True)
    try:
        while not is_stopped():
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)
            
            zones_cpu = [0.0, 0.0, 0.0, 0.0]
            if len(per_cpu) >= 4:
                chunk = math.ceil(len(per_cpu) / 4)
                for z in range(4):
                    slice_cpu = per_cpu[z*chunk : (z+1)*chunk]
                    if slice_cpu:
                        zones_cpu[z] = sum(slice_cpu) / len(slice_cpu)
            else:
                for z in range(4): 
                    zones_cpu[z] = sum(per_cpu)/len(per_cpu) if per_cpu else 0.0
            
            for z in range(4):
                p = zones_cpu[z]
                hue = (1.0 - (min(p, 100.0) / 100.0)) * 0.66
                brightness = max(0.2, min(p / 20.0, 1.0))
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, brightness)
                kb.colors[z] = [int(r*255), int(g*255), int(b*255)]
                
            kb.apply_colors()
            if sleep_interruptible(0.5): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_pomodoro(kb):
    WORK_MINUTES = 25
    BREAK_MINUTES = 5
    print("Starting Pomodoro Timer.")
    print(f"Work phase: {WORK_MINUTES} minutes. (4 Zones indicate progress)")
    print("Press Ctrl+C to exit.")
    
    try:
        # Work phase
        total_seconds = WORK_MINUTES * 60
        for remaining in range(total_seconds, 0, -1):
            if is_stopped(): return
            elapsed = total_seconds - remaining
            progress = elapsed / total_seconds # 0.0 to 1.0
            
            for z in range(4):
                if progress >= (z + 1) * 0.25:
                    kb.colors[z] = [0, 255, 0] # Zone complete (Solid Green)
                elif progress >= z * 0.25:
                    # Current active zone (Pulsing Red)
                    pulse = (math.sin(elapsed * math.pi) + 1) / 2 # 0 to 1
                    kb.colors[z] = [int(100 + 155 * pulse), 0, 0]
                else:
                    kb.colors[z] = [30, 0, 0] # Zone upcoming (Dim Red)
                    
            kb.apply_colors()
            if sleep_interruptible(1): return
            
        print("Break Time!")
        # Flash briefly
        for _ in range(3):
            if is_stopped(): return
            for z in range(4): kb.colors[z] = [255, 255, 255]
            kb.apply_colors()
            if sleep_interruptible(0.5): return
            for z in range(4): kb.colors[z] = [0, 0, 0]
            kb.apply_colors()
            if sleep_interruptible(0.5): return
            
        # Break phase
        total_break = BREAK_MINUTES * 60
        for remaining in range(total_break, 0, -1):
            if is_stopped(): return
            elapsed = total_break - remaining
            progress = elapsed / total_break
            
            for z in range(4):
                if progress >= (z + 1) * 0.25:
                    kb.colors[z] = [0, 0, 0] # Zone complete (Off)
                elif progress >= z * 0.25:
                    pulse = (math.sin(elapsed * math.pi) + 1) / 2
                    kb.colors[z] = [0, 0, int(100 + 155 * pulse)]
                else:
                    kb.colors[z] = [0, 0, 255] # Zone upcoming (Solid Blue)
            
            kb.apply_colors()
            if sleep_interruptible(1): return
            
        print("Pomodoro Complete.")
    except KeyboardInterrupt:
        print("Exiting...")

def mode_breathing(kb):
    print("Starting Breathing mode (Lenovo Blue).")
    print("Press Ctrl+C to exit.")
    try:
        intensity = 0.0
        while not is_stopped():
            val = (math.sin(intensity) + 1) / 2 # 0.0 to 1.0
            color = [0, int(val * 190), int(val * 255)] # Blue-ish breathing
            for z in range(4):
                kb.colors[z] = color
            kb.apply_colors()
            
            intensity += 0.05
            if sleep_interruptible(0.05): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_matrix(kb):
    print("Starting Smooth Matrix Raining Code mode.")
    print("Press Ctrl+C to exit.")
    
    drops = [0, 0, 0, 0]
    
    try:
        while not is_stopped():
            if random.random() < 0.2: # 20% chance per tick
                z = random.randint(0, 3)
                drops[z] = 255
                
            for z in range(4):
                if drops[z] > 200:
                    kb.colors[z] = [150, 255, 150]
                else:
                    kb.colors[z] = [0, max(20, drops[z]), 0]
                
                drops[z] -= 10
                if drops[z] < 0:
                    drops[z] = 0
                    
            kb.apply_colors()
            if sleep_interruptible(0.05): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_rainbow(kb):
    print("Starting Rainbow Wave mode.")
    print("Press Ctrl+C to exit.")
    try:
        hue = 0.0
        while not is_stopped():
            for z in range(4):
                r, g, b = colorsys.hsv_to_rgb((hue + z * 0.15) % 1.0, 1.0, 1.0)
                kb.colors[z] = [int(r*255), int(g*255), int(b*255)]
            kb.apply_colors()
            
            hue += 0.01
            if hue > 1.0:
                hue -= 1.0
            if sleep_interruptible(0.05): break
    except KeyboardInterrupt:
        print("Exiting...")

def main(from_ui=False):
    if not from_ui:
        kill_other_instances()
    parser = argparse.ArgumentParser(description="Lenovo LOQ 4-Zone RGB Custom Controller")
    parser.add_argument('--mode', type=str, choices=['type', 'audio', 'cpu', 'pomodoro', 'breathing', 'matrix', 'rainbow', 'off'], default='type', help='Select RGB mode')
    args = parser.parse_args()

    kb = LenovoKeyboard()

    if args.mode == 'type':
        mode_type_lighting(kb)
    elif args.mode == 'audio':
        mode_audio_visualizer(kb)
    elif args.mode == 'cpu':
        mode_cpu_monitor(kb)
    elif args.mode == 'pomodoro':
        mode_pomodoro(kb)
    elif args.mode == 'breathing':
        mode_breathing(kb)
    elif args.mode == 'matrix':
        mode_matrix(kb)
    elif args.mode == 'rainbow':
        mode_rainbow(kb)
    elif args.mode == 'off':
        kb.colors = [[0,0,0],[0,0,0],[0,0,0],[0,0,0]]
        kb.apply_colors()
        print("Lights turned off.")

if __name__ == '__main__':
    main()
