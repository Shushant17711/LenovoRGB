import tkinter as tk
from tkinter import ttk
import sys
import multiprocessing
import threading
import os
import pystray
from PIL import Image, ImageDraw
import time
import keyboard
import json

def create_image():
    # Simple icon with green square
    image = Image.new('RGBA', (64, 64), color=(30, 30, 30, 255))
    d = ImageDraw.Draw(image)
    d.rectangle([16, 16, 48, 48], fill=(0, 255, 0, 255))
    return image

current_process = None
stop_event = None

def run_mode(mode_name, stop_evt):
    # This runs in a separate initialized process
    import loq_rgb
    loq_rgb.stop_event = stop_evt
    sys.argv = ['loq_rgb.py', '--mode', mode_name]
    try:
        loq_rgb.main(from_ui=True)
    except Exception as e:
        print(f"Error running mode {mode_name}: {e}")

def apply_mode(mode):
    global current_process
    global stop_event
    
    # Gracefully stop previous mode
    if stop_event is not None:
        stop_event.set()
        
    if current_process and current_process.is_alive():
        current_process.join(timeout=2.0) # wait up to 2 seconds for clean exit
        if current_process.is_alive():
            print("Process did not exit cleanly, force terminating.")
            current_process.terminate()
            current_process.join()
    
    stop_event = multiprocessing.Event()
    
    if mode != "off":
        current_process = multiprocessing.Process(target=run_mode, args=(mode, stop_event))
        current_process.start()
    else:
        # Run brief process to apply off
        p = multiprocessing.Process(target=run_mode, args=("off", stop_event))
        p.start()
        p.join()

class LenovoRGBApp:
    def __init__(self, root):
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        self.config = self.load_config()
        self.root = root
        self.root.title("Lenovo LOQ RGB")
        self.root.geometry("280x150")
        self.root.resizable(False, False)
        
        self.modes = ['type', 'audio', 'cpu', 'screen', 'breathing', 'meteor', 'aurora', 'fire', 'glitch', 'rainbow', 'plasma', 'heartbeat', 'matrix', 'disco', 'storm', 'dna', 'off']
        self.mode_var = tk.StringVar(value='type')
        
        # Style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Widgets
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        lbl = ttk.Label(main_frame, text="Select Lighting Mode:")
        lbl.pack(pady=(0, 10))
        
        self.dropdown = ttk.Combobox(main_frame, textvariable=self.mode_var, values=self.modes, state="readonly", width=15)
        self.dropdown.pack(pady=5)
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        
        self.apply_btn = ttk.Button(btn_frame, text="Apply", command=self.on_apply)
        self.apply_btn.pack(side=tk.LEFT, padx=5)
        
        self.hide_btn = ttk.Button(btn_frame, text="Hide to Tray", command=self.hide_window)
        self.hide_btn.pack(side=tk.LEFT, padx=5)

        self.settings_btn = ttk.Button(btn_frame, text="Settings", command=self.open_settings)
        self.settings_btn.pack(side=tk.LEFT, padx=5)
        
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.icon = None
        
        # Start the default mode automatically
        default_mode = self.config.get("default_mode", "type")
        self.mode_var.set(default_mode)
        apply_mode(default_mode)
        
        # Register the global shortcut to cycle modes
        self.bind_shortcut()

        if self.config.get("startup_minimized", True):
            self.root.withdraw()
            self.root.after(100, self.show_tray_icon)

    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {
                "startup_minimized": True,
                "default_mode": "type",
                "shortcut": "ctrl+shift+m"
            }

    def save_config(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def bind_shortcut(self):
        # Remove previous hook if any
        if hasattr(self, '_shortcut_hook') and self._shortcut_hook is not None:
            try:
                keyboard.unhook(self._shortcut_hook)
            except:
                pass
            self._shortcut_hook = None
        try:
            keyboard.unhook_all_hotkeys()
        except:
            pass

        shortcut = self.config.get("shortcut", "ctrl+shift+m")
        if not shortcut:
            return

        # Parse shortcut into modifier keys and the trigger key
        parts = [p.strip().lower() for p in shortcut.split('+')]
        modifier_names = {'ctrl', 'shift', 'alt', 'left ctrl', 'right ctrl',
                          'left shift', 'right shift', 'left alt', 'right alt',
                          'left windows', 'right windows', 'windows'}
        modifiers = [p for p in parts if p in modifier_names]
        trigger_keys = [p for p in parts if p not in modifier_names]

        if not trigger_keys:
            # All parts are modifiers, fall back to original method
            try:
                keyboard.add_hotkey(shortcut, self.cycle_mode, suppress=False)
            except Exception as e:
                print(f"Warning: Failed to bind hotkey '{shortcut}': {e}")
            return

        trigger_key = trigger_keys[-1]  # Use the last non-modifier as trigger

        def on_trigger(event):
            if event.event_type != 'down':
                return
            # Check that ALL required modifiers are currently held
            for mod in modifiers:
                if not keyboard.is_pressed(mod):
                    return
            # Check no extra modifiers are pressed (to avoid triggering on superset combos)
            self.cycle_mode()

        try:
            self._shortcut_hook = keyboard.on_press_key(trigger_key, on_trigger, suppress=False)
        except Exception as e:
            print(f"Warning: Failed to bind hotkey '{shortcut}': {e}")

    def open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.geometry("280x280")
        settings_win.resizable(False, False)
        settings_win.transient(self.root)
        settings_win.grab_set()

        main_frame = ttk.Frame(settings_win, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        min_var = tk.BooleanVar(value=self.config.get("startup_minimized", True))
        ttk.Checkbutton(main_frame, text="Start Minimized in Tray", variable=min_var).pack(pady=5, anchor=tk.W)

        ttk.Label(main_frame, text="Default Mode:").pack(pady=(10, 2), anchor=tk.W)
        def_mode_var = tk.StringVar(value=self.config.get("default_mode", "type"))
        ttk.Combobox(main_frame, textvariable=def_mode_var, values=self.modes, state="readonly").pack(fill=tk.X)

        ttk.Label(main_frame, text="Cycle Shortcut:").pack(pady=(10, 2), anchor=tk.W)
        shortcut_sv = tk.StringVar(value=self.config.get("shortcut", "ctrl+shift+m"))
        sc_entry = ttk.Entry(main_frame, textvariable=shortcut_sv, state="readonly")
        sc_entry.pack(fill=tk.X)

        def record_shortcut():
            sc_entry.config(state="normal")
            shortcut_sv.set("Recording...")
            sc_entry.config(state="readonly")
            settings_win.update()
            
            def on_key():
                try:
                    hotkey = keyboard.read_hotkey(suppress=False)
                    sc_entry.config(state="normal")
                    shortcut_sv.set(hotkey)
                    sc_entry.config(state="readonly")
                except Exception:
                    sc_entry.config(state="normal")
                    shortcut_sv.set(self.config.get("shortcut", "ctrl+shift+m"))
                    sc_entry.config(state="readonly")
            threading.Thread(target=on_key, daemon=True).start()

        ttk.Button(main_frame, text="Record New Shortcut", command=record_shortcut).pack(pady=5)

        def save():
            self.config["startup_minimized"] = min_var.get()
            self.config["default_mode"] = def_mode_var.get()
            old_shortcut = self.config.get("shortcut", "")
            self.config["shortcut"] = shortcut_sv.get()
            self.save_config()
            
            if old_shortcut != self.config["shortcut"]:
                self.bind_shortcut()
                
            settings_win.destroy()

        ttk.Button(main_frame, text="Save Settings", command=save).pack(pady=(15, 0))

    def cycle_mode(self):
        try:
            current_idx = self.modes.index(self.mode_var.get())
        except ValueError:
            current_idx = 0
            
        next_idx = (current_idx + 1) % len(self.modes)
        next_mode = self.modes[next_idx]
        # set_mode_from_tray safely shuts down previous processes and starts the new one
        self.root.after(0, self.set_mode_from_tray, next_mode)
    def on_apply(self):
        mode = self.mode_var.get()
        apply_mode(mode)
        
    def hide_window(self):
        self.root.withdraw()
        self.show_tray_icon()
        
    def show_window(self, icon=None, item=None):
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
        self.root.after(0, self.root.deiconify)
        
    def exit_app(self, icon=None, item=None):
        global current_process
        global stop_event
        
        if stop_event is not None:
            stop_event.set()
            
        if current_process and current_process.is_alive():
            current_process.join(timeout=2.0)
            if current_process.is_alive():
                current_process.terminate()
                current_process.join()
            
        # Ensure we turn off lights on exit
        apply_mode("off")
            
        if self.icon is not None:
            self.icon.stop()
        self.root.quit()
        os._exit(0)

    def set_mode_from_tray(self, mode):
        self.mode_var.set(mode)
        apply_mode(mode)

    def show_tray_icon(self):
        image = create_image()
        
        def create_menu_item(mode_name):
            def action(icon, item):
                self.set_mode_from_tray(mode_name)
            def checked(item):
                return self.mode_var.get() == mode_name

            return pystray.MenuItem(
                mode_name.capitalize(),
                action,
                checked=checked,
                radio=True
            )
        
        mode_items = [create_menu_item(m) for m in self.modes]
        mode_menu = pystray.Menu(*mode_items)
        
        menu = pystray.Menu(
            pystray.MenuItem('Open UI', self.show_window, default=True),
            pystray.MenuItem('Modes', mode_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Exit', self.exit_app)
        )
        
        self.icon = pystray.Icon("LenovoRGB", image, "Lenovo LOQ RGB", menu)
        try:
            self.icon.run_detached()
        except Exception as e:
            print(f"Failed to show tray icon: {e}")
            import traceback
            traceback.print_exc()

def main():
    multiprocessing.freeze_support()
    
    # Handle pyinstaller --noconsole swallow
    if sys.stdout is None:
        try:
            sys.stdout = open('error.log', 'a')
        except:
            sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        try:
            sys.stderr = open('error.log', 'a')
        except:
            sys.stderr = open(os.devnull, 'w')
        
    root = tk.Tk()
    app = LenovoRGBApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
