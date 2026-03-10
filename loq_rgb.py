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
import atexit
import ctypes
import threading

usb_lock = threading.Lock()

global_kb = None
_ctrl_handler = None
EXITING = False
_CLEANED_UP = False

def cleanup_lights():
    global global_kb, _CLEANED_UP
    if _CLEANED_UP: return
    _CLEANED_UP = True
    
    if global_kb:
        try:
            # Main thread turns off the lights
            global_kb.colors = [[0,0,0], [0,0,0], [0,0,0], [0,0,0]]
            # Send OFF command directly via hardware
            payload = [0] * 33
            payload[0] = 0xcc; payload[1] = 0x16; payload[2] = 0x01; payload[3] = 1; payload[4] = 0
            for z in range(4):
                payload[5+z*3] = 0; payload[6+z*3] = 0; payload[7+z*3] = 0
            
            with usb_lock:
                global_kb.device.send_feature_report(payload)
        except:
            pass
    try:
        import keyboard
        keyboard.unhook_all()
    except:
        pass

atexit.register(cleanup_lights)

if os.name == 'nt':
    HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def console_ctrl_handler(ctrl_type):
        if ctrl_type in (0, 1, 2, 5, 6): # CTRL_C, BREAK, CLOSE, LOGOFF, SHUTDOWN
            global EXITING
            EXITING = True
            
            # Immediately execute hardware cleanup before OS kills drivers
            cleanup_lights()
            
            import os
            os._exit(0)
            return True
        return False
    _ctrl_handler = HandlerRoutine(console_ctrl_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_ctrl_handler, True)

STOP_FILE = os.path.join(tempfile.gettempdir(), "loq_rgb_stop.txt")
stop_event = None

def is_stopped():
    if globals().get('EXITING', False):
        return True
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
            with usb_lock:
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

def mode_screen(kb):
    print("Starting Screen Ambilight mode.")
    print("Note: Matches keyboard zones to your screen colors!")
    print("Press Ctrl+C to exit.")
    
    try:
        from PIL import ImageGrab
    except ImportError:
        print("Pillow (PIL) is not installed. Ambilight will not work.")
        return
        
    try:
        smooth_colors = [[0.0, 0.0, 0.0] for _ in range(4)]
        while not is_stopped():
            img = ImageGrab.grab()
            img = img.resize((64, 32)) 
            
            data = np.array(img).astype(np.float32) / 255.0
            chunk_width = 16
            
            for z in range(4):
                chunk = data[:, z*chunk_width:(z+1)*chunk_width, :]
                pixels = chunk.reshape(-1, 3)
                
                max_c = np.max(pixels, axis=1)
                min_c = np.min(pixels, axis=1)
                safe_max = np.where(max_c == 0, 1.0, max_c)
                sat = (max_c - min_c) / safe_max
                
                # Weight by saturation and value (brightness) to pick the most vibrant colors
                weights = (sat * max_c) ** 2 + 0.05
                weights_sum = np.sum(weights)
                
                if weights_sum > 0:
                    r_avg = np.sum(pixels[:,0] * weights) / weights_sum
                    g_avg = np.sum(pixels[:,1] * weights) / weights_sum
                    b_avg = np.sum(pixels[:,2] * weights) / weights_sum
                else:
                    r_avg, g_avg, b_avg = 0.0, 0.0, 0.0
                
                h, s, v = colorsys.rgb_to_hsv(r_avg, g_avg, b_avg)
                
                # Boost saturation explicitly so it's not washed out white
                s = min(1.0, s * 2.0)
                v = min(1.0, v * 1.2)
                
                r_new, g_new, b_new = colorsys.hsv_to_rgb(h, s, v)
                r_new, g_new, b_new = r_new * 255.0, g_new * 255.0, b_new * 255.0
                
                smooth_colors[z][0] += (r_new - smooth_colors[z][0]) * 0.3
                smooth_colors[z][1] += (g_new - smooth_colors[z][1]) * 0.3
                smooth_colors[z][2] += (b_new - smooth_colors[z][2]) * 0.3
                kb.colors[z] = [int(smooth_colors[z][0]), int(smooth_colors[z][1]), int(smooth_colors[z][2])]
                
            kb.apply_colors()
            if sleep_interruptible(0.05): break
    except KeyboardInterrupt:
        print("Exiting...")
    except Exception as e:
        print(f"Error in Screen Ambilight: {e}")

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

def mode_meteor(kb):
    print("Starting Meteor Bounce mode.")
    print("Press Ctrl+C to exit.")
    try:
        position = 0.0
        direction = 1.0
        speed = 0.15
        
        while not is_stopped():
            position += direction * speed
            if position >= 4.0:
                position = 4.0
                direction = -1.0
            elif position <= -1.0:
                position = -1.0
                direction = 1.0
                
            for z in range(4):
                dist = abs(z - position)
                intensity = max(0.0, 1.0 - (dist * 0.8))
                
                if direction > 0:
                    kb.colors[z] = [int(50 * intensity), int(255 * intensity), int(255 * intensity)]
                else:
                    kb.colors[z] = [int(255 * intensity), int(50 * intensity), int(255 * intensity)]
                
            kb.apply_colors()
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_aurora(kb):
    print("Starting Aurora mode (Northern Lights).")
    print("Press Ctrl+C to exit.")
    try:
        t = 0.0
        while not is_stopped():
            for z in range(4):
                v1 = math.sin(t * 0.5 + z)
                v2 = math.sin(t * 0.8 - z * 0.5)
                v3 = math.sin(t * 1.2 + z * 1.5)
                
                r = min(150, int(abs(v1) * 100))
                g = min(255, max(50, int(abs(v2) * 255)))
                b = min(255, max(100, int(abs(v3) * 255)))
                
                kb.colors[z] = [r, g, b]
                
            kb.apply_colors()
            t += 0.05
            if sleep_interruptible(0.05): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_fire(kb):
    print("Starting Fire/Flame mode.")
    print("Press Ctrl+C to exit.")
    try:
        intensities = [0.5, 0.5, 0.5, 0.5]
        while not is_stopped():
            for z in range(4):
                change = random.uniform(-0.15, 0.15)
                intensities[z] = max(0.2, min(0.9, intensities[z] + change))
                r = 255
                g = int(120 * intensities[z])
                b = 0
                if random.random() < 0.05:
                    r, g, b = 255, 200, 50
                kb.colors[z] = [int(r * intensities[z]), int(g * intensities[z]), b]
            
            kb.apply_colors()
            if sleep_interruptible(0.06): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_glitch(kb):
    print("Starting Cyberpunk Glitch mode.")
    print("Press Ctrl+C to exit.")
    try:
        palette = [[0, 255, 255], [255, 0, 255], [255, 20, 147], [0, 191, 255]]
        current_colors = [random.choice(palette) for _ in range(4)]
        
        while not is_stopped():
            if random.random() < 0.05:
                glitch_type = random.choice(["off", "white", "scramble"])
                if glitch_type == "off":
                    for z in range(4): kb.colors[z] = [0, 0, 0]
                elif glitch_type == "white":
                    for z in range(4): kb.colors[z] = [200, 200, 200]
                elif glitch_type == "scramble":
                    for z in range(4): kb.colors[z] = random.choice(palette)
                
                kb.apply_colors()
                if sleep_interruptible(random.uniform(0.02, 0.1)): break
            else:
                for z in range(4):
                    if random.random() < 0.1:
                        current_colors[z] = random.choice(palette)
                    kb.colors[z] = current_colors[z]
                
                kb.apply_colors()
                if sleep_interruptible(0.1): break
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

def mode_plasma(kb):
    print("Starting Plasma Energy mode.")
    print("Press Ctrl+C to exit.")
    try:
        t = 0.0
        while not is_stopped():
            for z in range(4):
                # Overlapping sine waves at different frequencies create organic plasma
                v1 = math.sin(t * 1.3 + z * 1.7)
                v2 = math.sin(t * 0.7 + z * 2.3 + 1.0)
                v3 = math.sin(t * 2.1 - z * 0.9 + 2.5)
                
                # Map combined waves to a hue that drifts continuously
                hue = ((v1 + v2 + v3) / 6.0 + 0.5 + t * 0.02) % 1.0
                sat = 0.8 + 0.2 * abs(math.sin(t * 0.5 + z))
                val = 0.5 + 0.5 * ((v1 * v2 + 1.0) / 2.0)
                
                r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
                kb.colors[z] = [int(r * 255), int(g * 255), int(b * 255)]
            
            kb.apply_colors()
            t += 0.06
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_heartbeat(kb):
    print("Starting Heartbeat mode.")
    print("Press Ctrl+C to exit.")
    try:
        cycle_time = 0.0
        cycle_hue = 0.0  # shifts from blue(0.6) toward red(0.0) over cycles
        
        while not is_stopped():
            # Cardiac cycle: ~1.2s total
            # Lub at t=0.0-0.15, Dub at t=0.25-0.35, rest until 1.2
            phase = cycle_time % 1.2
            
            if phase < 0.15:
                # First beat (lub) — sharp rise
                intensity = math.sin((phase / 0.15) * math.pi) ** 0.5
            elif phase < 0.25:
                # Brief gap
                intensity = max(0.0, 0.15 - (phase - 0.15) * 1.5)
            elif phase < 0.40:
                # Second beat (dub) — slightly weaker
                intensity = 0.75 * math.sin(((phase - 0.25) / 0.15) * math.pi) ** 0.5
            else:
                # Rest period — gentle ambient glow
                intensity = max(0.03, 0.1 * math.sin((phase - 0.4) * 1.5))
            
            # Hue drifts: blue -> purple -> red over ~8 seconds, then resets
            hue = 0.6 - cycle_hue * 0.6  # 0.6 (blue) down to 0.0 (red)
            r, g, b = colorsys.hsv_to_rgb(max(0.0, hue), 0.9, intensity)
            
            for z in range(4):
                # Slight phase offset per zone for a ripple effect
                zone_phase = (cycle_time + z * 0.04) % 1.2
                if zone_phase < 0.15:
                    zi = math.sin((zone_phase / 0.15) * math.pi) ** 0.5
                elif zone_phase < 0.25:
                    zi = max(0.0, 0.15 - (zone_phase - 0.15) * 1.5)
                elif zone_phase < 0.40:
                    zi = 0.75 * math.sin(((zone_phase - 0.25) / 0.15) * math.pi) ** 0.5
                else:
                    zi = max(0.03, 0.1 * math.sin((zone_phase - 0.4) * 1.5))
                
                r2, g2, b2 = colorsys.hsv_to_rgb(max(0.0, hue), 0.9, zi)
                kb.colors[z] = [int(r2 * 255), int(g2 * 255), int(b2 * 255)]
            
            kb.apply_colors()
            cycle_time += 0.025
            cycle_hue = (cycle_time / 8.0) % 1.0  # full hue shift every 8s
            if sleep_interruptible(0.025): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_matrix(kb):
    print("Starting Matrix Digital Rain mode.")
    print("Press Ctrl+C to exit.")
    try:
        # Each zone has its own flash brightness that decays
        flash = [0.0, 0.0, 0.0, 0.0]
        timers = [random.uniform(0.1, 0.8) for _ in range(4)]  # next flash time
        
        while not is_stopped():
            for z in range(4):
                timers[z] -= 0.03
                if timers[z] <= 0:
                    # New flash — random intensity
                    flash[z] = random.uniform(0.7, 1.0)
                    timers[z] = random.uniform(0.2, 1.2)
                else:
                    # Exponential decay
                    flash[z] *= 0.92
                
                # Green channel dominant, slight blue tint for "digital" feel
                g = int(flash[z] * 255)
                r = int(flash[z] * 20)
                b = int(flash[z] * 60)
                kb.colors[z] = [r, g, b]
            
            kb.apply_colors()
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_disco(kb):
    print("Starting Disco Strobe mode.")
    print("Press Ctrl+C to exit.")
    try:
        beat_time = 0.0
        bpm = 128.0
        beat_interval = 60.0 / bpm
        beat_count = 0
        
        # Vibrant disco palette
        palette = [
            [255, 0, 100], [0, 255, 150], [100, 0, 255],
            [255, 200, 0], [0, 180, 255], [255, 50, 0],
            [200, 0, 255], [0, 255, 50], [255, 100, 200],
        ]
        
        current = [random.choice(palette) for _ in range(4)]
        
        while not is_stopped():
            beat_time += 0.025
            
            if beat_time >= beat_interval:
                beat_time -= beat_interval
                beat_count += 1
                
                # Every 8th beat: synchronized white strobe burst
                if beat_count % 8 == 0:
                    for z in range(4):
                        kb.colors[z] = [255, 255, 255]
                    kb.apply_colors()
                    if sleep_interruptible(0.04): break
                    for z in range(4):
                        kb.colors[z] = [0, 0, 0]
                    kb.apply_colors()
                    if sleep_interruptible(0.04): break
                    continue
                
                # Normal beat: each zone snaps to a new random color
                for z in range(4):
                    current[z] = random.choice(palette)
            
            # Smooth fade between beats
            fade = max(0.3, 1.0 - (beat_time / beat_interval) * 0.7)
            for z in range(4):
                kb.colors[z] = [int(c * fade) for c in current[z]]
            
            kb.apply_colors()
            if sleep_interruptible(0.025): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_storm(kb):
    print("Starting Lightning Storm mode.")
    print("Press Ctrl+C to exit.")
    try:
        # Ambient dark base (deep indigo/purple)
        ambient = [[15, 5, 30], [10, 3, 25], [12, 4, 28], [8, 2, 22]]
        strike_active = False
        strike_zone = 0
        strike_phase = 0
        strike_timer = random.uniform(1.0, 3.0)
        
        # Current display colors (floats for smooth decay)
        display = [[15.0, 5.0, 30.0] for _ in range(4)]
        
        while not is_stopped():
            strike_timer -= 0.03
            
            if not strike_active and strike_timer <= 0:
                # Initiate a lightning strike
                strike_active = True
                strike_zone = random.randint(0, 3)
                strike_phase = 0
            
            if strike_active:
                strike_phase += 1
                
                if strike_phase <= 2:
                    # Initial bright flash on strike zone
                    display[strike_zone] = [255.0, 255.0, 255.0]
                elif strike_phase <= 4:
                    # Flash spreads to adjacent zones
                    for z in range(4):
                        dist = abs(z - strike_zone)
                        if dist <= 1:
                            brightness = 255.0 * (1.0 - dist * 0.3)
                            display[z] = [brightness, brightness, brightness * 0.95]
                elif strike_phase <= 6:
                    # Brief dark (between flashes)
                    for z in range(4):
                        display[z] = [20.0, 10.0, 40.0]
                elif strike_phase <= 8:
                    # Second flash (afterstrike) — dimmer, more blue
                    for z in range(4):
                        dist = abs(z - strike_zone)
                        if dist <= 2:
                            brightness = 180.0 * max(0.0, 1.0 - dist * 0.35)
                            display[z] = [brightness * 0.7, brightness * 0.7, brightness]
                elif strike_phase <= 15:
                    # Thunder afterglow — purple/violet fade
                    glow = max(0.0, 1.0 - (strike_phase - 8) / 7.0)
                    for z in range(4):
                        dist = abs(z - strike_zone)
                        local_glow = glow * max(0.0, 1.0 - dist * 0.25)
                        display[z] = [
                            ambient[z][0] + 100 * local_glow,
                            ambient[z][1] + 30 * local_glow,
                            ambient[z][2] + 150 * local_glow,
                        ]
                else:
                    strike_active = False
                    strike_timer = random.uniform(1.5, 4.0)
            else:
                # Ambient breathing — subtle undulation
                t = time.time()
                for z in range(4):
                    flicker = 0.8 + 0.2 * math.sin(t * 0.8 + z * 1.2)
                    display[z] = [ambient[z][0] * flicker, ambient[z][1] * flicker, ambient[z][2] * flicker]
            
            for z in range(4):
                kb.colors[z] = [int(min(255, max(0, display[z][c]))) for c in range(3)]
            
            kb.apply_colors()
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_dna(kb):
    print("Starting DNA Helix mode.")
    print("Press Ctrl+C to exit.")
    try:
        t = 0.0
        while not is_stopped():
            for z in range(4):
                # Two helical waves rotating in opposite directions
                wave_a = (math.sin(t * 2.0 + z * 1.5) + 1.0) / 2.0   # 0..1
                wave_b = (math.sin(-t * 2.0 + z * 1.5 + math.pi) + 1.0) / 2.0  # counter-rotating
                
                # Strand A = Cyan (0, 255, 255)
                r_a, g_a, b_a = 0, 255 * wave_a, 255 * wave_a
                # Strand B = Magenta (255, 0, 255)
                r_b, g_b, b_b = 255 * wave_b, 0, 255 * wave_b
                
                # Blend the two strands — where they cross creates white/lavender
                r = min(255, int(r_a + r_b))
                g = min(255, int(g_a + g_b))
                b = min(255, int(b_a + b_b))
                
                # Add a subtle brightness pulse where strands are close (crossing point)
                cross = wave_a * wave_b  # high when both are high = crossing
                boost = int(80 * cross)
                r = min(255, r + boost)
                g = min(255, g + boost)
                b = min(255, b + boost)
                
                kb.colors[z] = [r, g, b]
            
            kb.apply_colors()
            t += 0.04
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def main(from_ui=False):
    if not from_ui:
        kill_other_instances()
    parser = argparse.ArgumentParser(description="Lenovo LOQ 4-Zone RGB Custom Controller")
    parser.add_argument('--mode', type=str, choices=['type', 'audio', 'cpu', 'screen', 'breathing', 'meteor', 'aurora', 'fire', 'glitch', 'rainbow', 'plasma', 'heartbeat', 'matrix', 'disco', 'storm', 'dna', 'off'], default='type', help='Select RGB mode')
    args = parser.parse_args()

    global global_kb
    kb = LenovoKeyboard()
    global_kb = kb

    if args.mode == 'type':
        mode_type_lighting(kb)
    elif args.mode == 'audio':
        mode_audio_visualizer(kb)
    elif args.mode == 'cpu':
        mode_cpu_monitor(kb)
    elif args.mode == 'screen':
        mode_screen(kb)
    elif args.mode == 'breathing':
        mode_breathing(kb)
    elif args.mode == 'meteor':
        mode_meteor(kb)
    elif args.mode == 'aurora':
        mode_aurora(kb)
    elif args.mode == 'fire':
        mode_fire(kb)
    elif args.mode == 'glitch':
        mode_glitch(kb)
    elif args.mode == 'rainbow':
        mode_rainbow(kb)
    elif args.mode == 'plasma':
        mode_plasma(kb)
    elif args.mode == 'heartbeat':
        mode_heartbeat(kb)
    elif args.mode == 'matrix':
        mode_matrix(kb)
    elif args.mode == 'disco':
        mode_disco(kb)
    elif args.mode == 'storm':
        mode_storm(kb)
    elif args.mode == 'dna':
        mode_dna(kb)
    elif args.mode == 'off':
        kb.colors = [[0,0,0],[0,0,0],[0,0,0],[0,0,0]]
        kb.apply_colors()
        print("Lights turned off.")

if __name__ == '__main__':
    main()
