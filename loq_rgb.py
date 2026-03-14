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
            # If being killed by OS, the lock might be held by a dead thread. Try to acquire with timeout.
            acquired = usb_lock.acquire(timeout=0.5)
            try:
                global_kb.device.send_feature_report(payload)
            finally:
                if acquired:
                    usb_lock.release()
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
                # Exponential decay for more natural fade
                zone_brightness[z] = zone_brightness[z] * 0.92
                if zone_brightness[z] < 0.01:
                    zone_brightness[z] = 0.0
                kb.colors[z] = [int(c * zone_brightness[z]) for c in zone_colors[z]]
            kb.apply_colors()
            if sleep_interruptible(0.016): # 60 fps
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
    BUFFER_SIZE = 2048  # ~46ms — good balance of responsiveness and stability
    
    for m in mics:
        if is_stopped(): return
        try:
            with m.recorder(samplerate=SAMPLE_RATE) as mic:
                for _ in range(3):
                    if is_stopped(): return
                    data = mic.record(numframes=BUFFER_SIZE)
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
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        
        with loopback_mic.recorder(samplerate=SAMPLE_RATE) as mic:
            # Peak tracker for normalization — moderate decay
            peak_vals = [0.01, 0.01, 0.01, 0.01]
            # Final display colors (smoothed just enough to avoid flicker)
            display_colors = [[0.0, 0.0, 0.0] for _ in range(4)]
            
            # Hann window pre-computed
            window = np.hanning(BUFFER_SIZE)
            
            while not is_stopped():
                try:
                    data = mic.record(numframes=BUFFER_SIZE)
                    
                    if data is None or len(data) == 0:
                        if sleep_interruptible(0.01): break
                        continue
                    
                    mono = np.mean(data, axis=1)
                    
                    # --- Silence gate ---
                    rms_raw = np.sqrt(np.mean(mono**2))
                    if rms_raw < 0.0003:
                        # Silence: fade to black quickly
                        for z in range(4):
                            for c in range(3):
                                display_colors[z][c] *= 0.7
                                if display_colors[z][c] < 1.0:
                                    display_colors[z][c] = 0.0
                                kb.colors[z][c] = int(display_colors[z][c])
                        kb.apply_colors()
                        if sleep_interruptible(0.02): break
                        continue
                    
                    # Apply window and compute FFT
                    n = min(len(mono), BUFFER_SIZE)
                    mono_windowed = mono[:n] * window[:n]
                    fft = np.abs(np.fft.rfft(mono_windowed))
                    freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
                    
                    # --- Frequency band energy ---
                    bass_mask = (freqs >= 30) & (freqs < 300)
                    mid_mask = (freqs >= 300) & (freqs < 2500)
                    treble_mask = (freqs >= 2500) & (freqs < 10000)
                    
                    bass = np.sqrt(np.mean(fft[bass_mask]**2)) if np.any(bass_mask) else 0
                    mid = np.sqrt(np.mean(fft[mid_mask]**2)) if np.any(mid_mask) else 0
                    treble = np.sqrt(np.mean(fft[treble_mask]**2)) if np.any(treble_mask) else 0
                    rms = rms_raw
                    
                    raw_vals = [bass, mid, treble, rms]
                    
                    # --- Peak tracker: moderate decay ---
                    # Decay at 0.997/frame ≈ ~5 seconds to halve (responsive but not jumpy)
                    for i in range(4):
                        if raw_vals[i] > peak_vals[i]:
                            # New peak — jump up instantly
                            peak_vals[i] = raw_vals[i]
                        else:
                            peak_vals[i] *= 0.997
                        # Hard floor so we don't divide by near-zero
                        peak_vals[i] = max(peak_vals[i], 0.005)
                    
                    # --- Normalize and apply perceptual curve ---
                    normalized = [0.0, 0.0, 0.0, 0.0]
                    for i in range(4):
                        ratio = raw_vals[i] / peak_vals[i] if peak_vals[i] > 0 else 0
                        ratio = min(ratio, 1.0)
                        # Power 0.85 = mild expansion of low values, preserves dynamics
                        normalized[i] = ratio ** 0.85
                    
                    # --- Map to zone colors ---
                    bass_n = normalized[0]
                    mid_n = normalized[1]
                    treble_n = normalized[2]
                    rms_n = normalized[3]
                    
                    targets = [
                        [bass_n * 255, 0, 0],                           # Pure red bass
                        [0, mid_n * 255, 0],                             # Pure green mids
                        [0, 0, treble_n * 255],                          # Pure blue treble
                        [0, rms_n * 255, rms_n * 255],                   # Cyan overall
                    ]
                    
                    # --- Output smoothing: snappy attack, visible decay ---
                    for z in range(4):
                        for c in range(3):
                            current = display_colors[z][c]
                            target = targets[z][c]
                            if target > current:
                                # Fast attack — 75% jump toward target
                                display_colors[z][c] = current + (target - current) * 0.75
                            else:
                                # Fast decay — 35% toward target so lights visibly pulse
                                display_colors[z][c] = current + (target - current) * 0.35
                            # Floor to zero
                            if display_colors[z][c] < 2.0 and target < 1.0:
                                display_colors[z][c] = 0.0
                            kb.colors[z][c] = int(min(255, max(0, display_colors[z][c])))
                    
                    kb.apply_colors()
                    
                except Exception as e:
                    if sleep_interruptible(0.01): break
                    continue
                    
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
            per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
            
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
                p = min(zones_cpu[z], 100.0)
                # Blue (0.66) -> Cyan (0.5) -> Green (0.33) -> Yellow (0.16) -> Red (0.0)
                hue = (1.0 - (p / 100.0)) * 0.66
                # Better brightness scaling: always visible, scales with load
                brightness = 0.3 + (p / 100.0) * 0.7
                saturation = 0.9 + (p / 100.0) * 0.1
                r, g, b = colorsys.hsv_to_rgb(hue, saturation, brightness)
                kb.colors[z] = [int(r*255), int(g*255), int(b*255)]
                
            kb.apply_colors()
            if sleep_interruptible(0.3): break
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
                
                # Calculate average brightness across all pixels in this zone
                avg_brightness = np.mean(pixels)
                
                # BLACK SCREEN: if screen is very dark, output pure black
                if avg_brightness < 0.05:
                    r_new, g_new, b_new = 0.0, 0.0, 0.0
                # NEAR-BLACK: dim screen outputs a very faint tint at most
                elif avg_brightness < 0.10:
                    # Scale output proportionally to how far above the black threshold we are
                    dim_factor = (avg_brightness - 0.05) / 0.05  # 0.0 to 1.0
                    avg_r = np.mean(pixels[:, 0])
                    avg_g = np.mean(pixels[:, 1])
                    avg_b = np.mean(pixels[:, 2])
                    r_new = avg_r * 255.0 * dim_factor * 0.5
                    g_new = avg_g * 255.0 * dim_factor * 0.5
                    b_new = avg_b * 255.0 * dim_factor * 0.5
                else:
                    max_c = np.max(pixels, axis=1)
                    min_c = np.min(pixels, axis=1)
                    safe_max = np.where(max_c == 0, 1.0, max_c)
                    sat = (max_c - min_c) / safe_max
                    
                    # Check if the zone is mostly grayscale
                    avg_sat = np.mean(sat)
                    
                    if avg_sat < 0.12:
                        # Grayscale content: output a dim neutral warm tone instead of white
                        # This prevents dark IDEs, terminals, etc. from producing white
                        brightness = min(1.0, avg_brightness * 1.2)
                        r_new = brightness * 60.0   # Very dim warm tone
                        g_new = brightness * 50.0
                        b_new = brightness * 70.0
                    else:
                        # Colorful content: weight by saturation and brightness
                        # NO floor added — only saturated, bright pixels contribute
                        weights = (sat * max_c) ** 2
                        weights_sum = np.sum(weights)
                        
                        if weights_sum > 0.001:
                            r_avg = np.sum(pixels[:,0] * weights) / weights_sum
                            g_avg = np.sum(pixels[:,1] * weights) / weights_sum
                            b_avg = np.sum(pixels[:,2] * weights) / weights_sum
                        else:
                            r_avg = np.mean(pixels[:, 0])
                            g_avg = np.mean(pixels[:, 1])
                            b_avg = np.mean(pixels[:, 2])
                        
                        h, s, v = colorsys.rgb_to_hsv(r_avg, g_avg, b_avg)
                        
                        # Boost saturation for more vivid output
                        if s > 0.08:
                            s = min(1.0, s * 1.6)
                        
                        # Boost brightness moderately
                        v = min(1.0, v * 1.3)
                        
                        r_new, g_new, b_new = colorsys.hsv_to_rgb(h, s, v)
                        r_new, g_new, b_new = r_new * 255.0, g_new * 255.0, b_new * 255.0
                
                # Smooth color transitions — faster toward black, normal toward color
                for c_idx, c_new in enumerate([r_new, g_new, b_new]):
                    current = smooth_colors[z][c_idx]
                    if c_new < current:
                        # Decaying toward dark: use faster smoothing
                        alpha = 0.6
                    else:
                        # Rising toward bright: normal smoothing
                        alpha = 0.4
                    smooth_colors[z][c_idx] += (c_new - current) * alpha
                    # Snap to zero when close to avoid lingering glow
                    if smooth_colors[z][c_idx] < 3.0 and c_new == 0.0:
                        smooth_colors[z][c_idx] = 0.0
                        
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
        t = 0.0
        while not is_stopped():
            # Smoother breathing with ease-in-ease-out
            val = (math.sin(t) + 1) / 2
            val = val ** 0.8  # Slight ease for more natural breathing
            # Lenovo blue with proper scaling
            color = [int(val * 30), int(val * 190), int(val * 255)]
            for z in range(4):
                kb.colors[z] = color
            kb.apply_colors()
            
            t += 0.04
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_meteor(kb):
    print("Starting Meteor Bounce mode.")
    print("Press Ctrl+C to exit.")
    try:
        position = 0.0
        direction = 1.0
        speed = 0.12
        
        while not is_stopped():
            position += direction * speed
            # Proper boundaries: 0 to 3 (4 zones indexed 0-3)
            if position >= 3.0:
                position = 3.0
                direction = -1.0
            elif position <= 0.0:
                position = 0.0
                direction = 1.0
                
            for z in range(4):
                dist = abs(z - position)
                # Smoother falloff with tail effect
                intensity = max(0.0, 1.0 - (dist * 0.6)) ** 1.5
                
                if direction > 0:
                    # Cyan meteor moving right
                    kb.colors[z] = [int(30 * intensity), int(200 * intensity), int(255 * intensity)]
                else:
                    # Magenta meteor moving left
                    kb.colors[z] = [int(255 * intensity), int(30 * intensity), int(200 * intensity)]
                
            kb.apply_colors()
            if sleep_interruptible(0.025): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_aurora(kb):
    print("Starting Aurora mode (Northern Lights).")
    print("Press Ctrl+C to exit.")
    try:
        t = 0.0
        while not is_stopped():
            for z in range(4):
                # Multiple wave layers for realistic aurora
                v1 = math.sin(t * 0.4 + z * 0.8)
                v2 = math.sin(t * 0.6 - z * 0.4 + 2.0)
                v3 = math.sin(t * 0.9 + z * 1.2 + 4.0)
                
                # Aurora colors: green-blue-purple spectrum
                # Green dominant with blue and purple accents
                r = int(max(30, min(180, 60 + abs(v1) * 120)))
                g = int(max(100, min(255, 150 + abs(v2) * 105)))
                b = int(max(120, min(255, 180 + abs(v3) * 75)))
                
                kb.colors[z] = [r, g, b]
                
            kb.apply_colors()
            t += 0.04
            if sleep_interruptible(0.04): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_fire(kb):
    print("Starting Fire/Flame mode.")
    print("Press Ctrl+C to exit.")
    try:
        intensities = [0.6, 0.7, 0.5, 0.6]
        while not is_stopped():
            for z in range(4):
                # More dynamic flickering
                change = random.uniform(-0.2, 0.25)
                intensities[z] = max(0.3, min(1.0, intensities[z] + change))
                
                # Realistic fire colors: red-orange-yellow gradient
                base_intensity = intensities[z]
                r = int(255 * base_intensity)
                g = int(min(255, 80 + 120 * base_intensity))
                # Add occasional blue at base (hotter fire)
                b = int(random.uniform(0, 20) if random.random() < 0.1 else 0)
                
                # Occasional bright yellow-white flare
                if random.random() < 0.08:
                    flare = random.uniform(0.5, 1.0)
                    r = int(255 * flare)
                    g = int(220 * flare)
                    b = int(50 * flare)
                
                kb.colors[z] = [r, g, b]
            
            kb.apply_colors()
            if sleep_interruptible(0.05): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_glitch(kb):
    print("Starting Cyberpunk Glitch mode.")
    print("Press Ctrl+C to exit.")
    try:
        palette = [[0, 255, 255], [255, 0, 255], [255, 20, 147], [0, 191, 255], [255, 255, 0]]
        current_colors = [random.choice(palette) for _ in range(4)]
        glitch_timer = 0.0
        
        while not is_stopped():
            glitch_timer += 0.03
            
            # More frequent glitches
            if random.random() < 0.08:
                glitch_type = random.choice(["off", "white", "scramble", "invert"])
                if glitch_type == "off":
                    for z in range(4): kb.colors[z] = [0, 0, 0]
                elif glitch_type == "white":
                    for z in range(4): kb.colors[z] = [255, 255, 255]
                elif glitch_type == "invert":
                    for z in range(4): 
                        kb.colors[z] = [255 - current_colors[z][0], 255 - current_colors[z][1], 255 - current_colors[z][2]]
                elif glitch_type == "scramble":
                    for z in range(4): kb.colors[z] = random.choice(palette)
                
                kb.apply_colors()
                if sleep_interruptible(random.uniform(0.03, 0.08)): break
            else:
                # Normal color shifts
                for z in range(4):
                    if random.random() < 0.15:
                        current_colors[z] = random.choice(palette)
                    kb.colors[z] = current_colors[z]
                
                kb.apply_colors()
                if sleep_interruptible(0.08): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_rainbow(kb):
    print("Starting Rainbow Wave mode.")
    print("Press Ctrl+C to exit.")
    try:
        hue = 0.0
        while not is_stopped():
            for z in range(4):
                # Smoother wave across zones
                zone_hue = (hue + z * 0.25) % 1.0
                r, g, b = colorsys.hsv_to_rgb(zone_hue, 1.0, 1.0)
                kb.colors[z] = [int(r*255), int(g*255), int(b*255)]
            kb.apply_colors()
            
            hue = (hue + 0.008) % 1.0
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_plasma(kb):
    print("Starting Plasma Energy mode.")
    print("Press Ctrl+C to exit.")
    try:
        t = 0.0
        while not is_stopped():
            for z in range(4):
                # Multiple overlapping sine waves for organic plasma effect
                v1 = math.sin(t * 1.1 + z * 1.3)
                v2 = math.sin(t * 0.8 - z * 1.7 + 2.0)
                v3 = math.sin(t * 1.5 + z * 0.9 + 4.0)
                v4 = math.sin(t * 0.6 - z * 2.1 + 1.5)
                
                # Combine waves for hue (full spectrum)
                hue = ((v1 + v2 + v3 + v4) / 8.0 + 0.5 + t * 0.015) % 1.0
                # Dynamic saturation
                sat = 0.75 + 0.25 * ((v1 + v2) / 2.0)
                # Pulsing brightness
                val = 0.6 + 0.4 * ((v3 + v4 + 2.0) / 4.0)
                
                r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
                kb.colors[z] = [int(r * 255), int(g * 255), int(b * 255)]
            
            kb.apply_colors()
            t += 0.05
            if sleep_interruptible(0.03): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_heartbeat(kb):
    print("Starting Heartbeat mode.")
    print("Press Ctrl+C to exit.")
    try:
        cycle_time = 0.0
        cycle_hue = 0.0
        dt = 0.02
        
        while not is_stopped():
            # Cardiac cycle: ~1.0s total for more realistic heartbeat
            phase = cycle_time % 1.0
            
            if phase < 0.12:
                # First beat (lub) — sharp rise
                intensity = (math.sin((phase / 0.12) * math.pi) ** 0.6) * 0.95
            elif phase < 0.20:
                # Brief gap
                intensity = max(0.0, 0.2 - (phase - 0.12) * 2.0)
            elif phase < 0.32:
                # Second beat (dub) — slightly weaker
                intensity = 0.7 * (math.sin(((phase - 0.20) / 0.12) * math.pi) ** 0.6)
            else:
                # Rest period — gentle ambient glow
                rest_phase = (phase - 0.32) / 0.68
                intensity = 0.05 + 0.08 * math.sin(rest_phase * math.pi)
            
            # Hue drifts: blue -> purple -> red over ~10 seconds
            hue = 0.65 - cycle_hue * 0.65  # 0.65 (blue) down to 0.0 (red)
            
            for z in range(4):
                # Slight phase offset per zone for ripple effect
                zone_offset = z * 0.03
                zone_phase = (cycle_time + zone_offset) % 1.0
                
                if zone_phase < 0.12:
                    zi = (math.sin((zone_phase / 0.12) * math.pi) ** 0.6) * 0.95
                elif zone_phase < 0.20:
                    zi = max(0.0, 0.2 - (zone_phase - 0.12) * 2.0)
                elif zone_phase < 0.32:
                    zi = 0.7 * (math.sin(((zone_phase - 0.20) / 0.12) * math.pi) ** 0.6)
                else:
                    rest_phase = (zone_phase - 0.32) / 0.68
                    zi = 0.05 + 0.08 * math.sin(rest_phase * math.pi)
                
                r, g, b = colorsys.hsv_to_rgb(max(0.0, hue), 0.95, zi)
                kb.colors[z] = [int(r * 255), int(g * 255), int(b * 255)]
            
            kb.apply_colors()
            cycle_time += dt
            cycle_hue = (cycle_time / 10.0) % 1.0
            if sleep_interruptible(dt): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_matrix(kb):
    print("Starting Matrix Digital Rain mode.")
    print("Press Ctrl+C to exit.")
    try:
        # Each zone has its own flash brightness that decays
        flash = [0.0, 0.0, 0.0, 0.0]
        timers = [random.uniform(0.1, 0.6) for _ in range(4)]
        
        while not is_stopped():
            for z in range(4):
                timers[z] -= 0.025
                if timers[z] <= 0:
                    # New "character" flash
                    flash[z] = random.uniform(0.8, 1.0)
                    timers[z] = random.uniform(0.15, 0.8)
                else:
                    # Faster exponential decay for snappier effect
                    flash[z] *= 0.88
                    if flash[z] < 0.05:
                        flash[z] = 0.0
                
                # Matrix green with subtle variations
                g = int(flash[z] * 255)
                r = int(flash[z] * 15)
                b = int(flash[z] * 40)
                kb.colors[z] = [r, g, b]
            
            kb.apply_colors()
            if sleep_interruptible(0.025): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_disco(kb):
    print("Starting Disco Strobe mode.")
    print("Press Ctrl+C to exit.")
    try:
        beat_time = 0.0
        bpm = 130.0
        beat_interval = 60.0 / bpm
        beat_count = 0
        dt = 0.02
        
        # Vibrant disco palette
        palette = [
            [255, 0, 100], [0, 255, 150], [100, 0, 255],
            [255, 200, 0], [0, 180, 255], [255, 50, 0],
            [200, 0, 255], [0, 255, 50], [255, 100, 200],
        ]
        
        current = [random.choice(palette) for _ in range(4)]
        
        while not is_stopped():
            beat_time += dt
            
            if beat_time >= beat_interval:
                beat_time = beat_time - beat_interval
                beat_count += 1
                
                # Every 8th beat: synchronized white strobe burst
                if beat_count % 8 == 0:
                    for z in range(4):
                        kb.colors[z] = [255, 255, 255]
                    kb.apply_colors()
                    if sleep_interruptible(0.05): break
                    for z in range(4):
                        kb.colors[z] = [0, 0, 0]
                    kb.apply_colors()
                    if sleep_interruptible(0.03): break
                    continue
                
                # Normal beat: each zone snaps to a new random color
                for z in range(4):
                    current[z] = random.choice(palette)
            
            # Better fade curve - exponential for punchier beats
            progress = beat_time / beat_interval
            fade = max(0.2, (1.0 - progress) ** 0.7)
            for z in range(4):
                kb.colors[z] = [int(c * fade) for c in current[z]]
            
            kb.apply_colors()
            if sleep_interruptible(dt): break
    except KeyboardInterrupt:
        print("Exiting...")

def mode_storm(kb):
    print("Starting Lightning Storm mode.")
    print("Press Ctrl+C to exit.")
    try:
        # Ambient dark base (deep indigo/purple)
        ambient = [[12, 4, 25], [10, 3, 22], [11, 4, 24], [9, 3, 20]]
        strike_active = False
        strike_zone = 0
        strike_phase = 0
        strike_timer = random.uniform(1.5, 3.5)
        dt = 0.025
        
        # Current display colors (floats for smooth transitions)
        display = [[12.0, 4.0, 25.0] for _ in range(4)]
        
        while not is_stopped():
            strike_timer -= dt
            
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
                    # Slight illumination of adjacent zones
                    for z in range(4):
                        if z != strike_zone:
                            dist = abs(z - strike_zone)
                            glow = 100.0 / (dist + 1)
                            display[z] = [glow, glow, glow * 1.2]
                elif strike_phase <= 4:
                    # Flash spreads outward
                    for z in range(4):
                        dist = abs(z - strike_zone)
                        if dist <= 1:
                            brightness = 255.0 * (1.0 - dist * 0.4)
                            display[z] = [brightness, brightness, brightness * 0.98]
                        else:
                            display[z] = [50.0, 40.0, 70.0]
                elif strike_phase <= 6:
                    # Brief dark (between flashes)
                    for z in range(4):
                        display[z] = [15.0, 8.0, 35.0]
                elif strike_phase <= 9:
                    # Second flash (afterstrike) — dimmer, more blue-white
                    for z in range(4):
                        dist = abs(z - strike_zone)
                        brightness = 200.0 * max(0.0, 1.0 - dist * 0.3)
                        display[z] = [brightness * 0.75, brightness * 0.8, brightness]
                elif strike_phase <= 18:
                    # Thunder afterglow — purple/violet fade
                    fade_progress = (strike_phase - 9) / 9.0
                    glow = max(0.0, 1.0 - fade_progress) ** 1.5
                    for z in range(4):
                        dist = abs(z - strike_zone)
                        local_glow = glow * max(0.0, 1.0 - dist * 0.2)
                        display[z] = [
                            ambient[z][0] + 120 * local_glow,
                            ambient[z][1] + 40 * local_glow,
                            ambient[z][2] + 180 * local_glow,
                        ]
                else:
                    strike_active = False
                    strike_timer = random.uniform(2.0, 4.5)
            else:
                # Ambient breathing — subtle undulation
                t = time.time()
                for z in range(4):
                    flicker = 0.85 + 0.15 * math.sin(t * 0.6 + z * 1.1)
                    display[z] = [ambient[z][0] * flicker, ambient[z][1] * flicker, ambient[z][2] * flicker]
            
            for z in range(4):
                kb.colors[z] = [int(min(255, max(0, display[z][c]))) for c in range(3)]
            
            kb.apply_colors()
            if sleep_interruptible(dt): break
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
                wave_a = (math.sin(t * 1.8 + z * 1.3) + 1.0) / 2.0   # 0..1
                wave_b = (math.sin(-t * 1.8 + z * 1.3 + math.pi) + 1.0) / 2.0  # counter-rotating
                
                # Strand A = Cyan (0, 255, 255)
                r_a, g_a, b_a = 0, int(255 * wave_a), int(255 * wave_a)
                # Strand B = Magenta (255, 0, 255)
                r_b, g_b, b_b = int(255 * wave_b), 0, int(255 * wave_b)
                
                # Blend the two strands
                r = min(255, r_a + r_b)
                g = min(255, g_a + g_b)
                b = min(255, b_a + b_b)
                
                # Add brightness boost where strands cross (both high)
                cross = wave_a * wave_b
                boost = int(100 * (cross ** 1.5))
                r = min(255, r + boost)
                g = min(255, g + boost)
                b = min(255, b + boost)
                
                kb.colors[z] = [r, g, b]
            
            kb.apply_colors()
            t += 0.035
            if sleep_interruptible(0.025): break
    except KeyboardInterrupt:
        print("Exiting...")

def on_key_event_ripple(e):
    if e.event_type == keyboard.KEY_DOWN:
        name = e.name.lower() if hasattr(e, 'name') and e.name else ''
        zone = ZONE_MAP.get(name, -1)
        
        if hasattr(e, 'scan_code') and e.scan_code in [71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 284, 309, 327, 328, 329, 331, 333, 335, 336, 337, 338, 339]:
            zone = 3
            
        if 'numpad' in name or (hasattr(e, 'is_keypad') and e.is_keypad):
            zone = 3
            
        if zone == -1:
            zone = random.randint(0, 3)

        color = get_random_color()
        ripple_events.append({'origin': zone, 'time': 0.0, 'color': color})

# State for Ripple mode
ripple_events = []

def mode_ripple(kb):
    print("Starting Interactive Ripple mode. Press keys to trigger ripples!")
    print("Press Ctrl+C to exit.")
    keyboard.hook(on_key_event_ripple)
    try:
        dt = 0.025
        while not is_stopped():
            colors = [[0.0, 0.0, 0.0] for _ in range(4)]
            
            for evt in list(ripple_events):
                evt['time'] += dt
                # Ripple speed: 4.5 zones per second
                speed = 4.5
                radius = evt['time'] * speed
                width = 1.2  # Ripple width
                
                for z in range(4):
                    dist = abs(z - evt['origin'])
                    diff = abs(dist - radius)
                    if diff < width:
                        # Smoother intensity curve
                        intensity = (1.0 - (diff / width)) ** 1.8
                        # Exponential fade out
                        fade = max(0.0, (1.0 - evt['time'] / 1.0) ** 1.2)
                        for c in range(3):
                            colors[z][c] += evt['color'][c] * intensity * fade
                
                # Remove old ripples
                if evt['time'] > 1.1:
                    try:
                        ripple_events.remove(evt)
                    except ValueError:
                        pass
                
            for z in range(4):
                kb.colors[z] = [min(255, int(colors[z][c])) for c in range(3)]
                
            kb.apply_colors()
            if sleep_interruptible(dt):
                break
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        try:
            keyboard.unhook_all()
        except:
            pass

def main(from_ui=False):
    if not from_ui:
        kill_other_instances()
    parser = argparse.ArgumentParser(description="Lenovo LOQ 4-Zone RGB Custom Controller")
    parser.add_argument('--mode', type=str, choices=['type', 'audio', 'cpu', 'screen', 'breathing', 'meteor', 'aurora', 'fire', 'glitch', 'rainbow', 'plasma', 'heartbeat', 'matrix', 'disco', 'storm', 'dna', 'ripple', 'off'], default='type', help='Select RGB mode')
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
    elif args.mode == 'ripple':
        mode_ripple(kb)
    elif args.mode == 'off':
        kb.colors = [[0,0,0],[0,0,0],[0,0,0],[0,0,0]]
        kb.apply_colors()
        print("Lights turned off.")

if __name__ == '__main__':
    main()
