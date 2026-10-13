<h1 align="center">Lenovo LOQ Custom RGB Controller</h1>

<p align="center">
  A custom, feature-rich controller for the 4-zone RGB keyboard found on <strong>Lenovo LOQ</strong> and <strong>Legion</strong> laptops. 
  It provides dynamic effects that interact with your typing, system audio, CPU load, screen content, and more.
</p>

---

## ✨ Features

- **System Tray GUI**: A minimal UI built with Tkinter and PyStray that lives in your system tray. Quick access to change modes or tweak settings seamlessly.
- **Global Hotkeys**: Switch between lighting modes on the fly using a customizable hotkey (default: `Ctrl+Shift+M`).
- **Startup Integration**: Effortlessly start the app automatically minimized to the system tray with elevated privileges.
- **Lightweight Executable**: Compile the Python scripts into a single standalone `.exe` file you can place anywhere.
- **Graceful Shutdown**: Automatic lights-off cleanup when the app is closed, the terminal is closed, or the system shuts down — no more stuck LEDs.
- **Sleep Detection**: Lights automatically turn off when your PC goes to sleep and resume when you wake it up.
- **18 Dynamic Lighting Modes**: From responsive typing gradients to audio visualizers to lightning storms, use your keyboard's LEDs as a canvas.

---

## 🎨 Available Modes

### Reactive & Utility Modes

1. ⌨️ **Type-Lighting (Reactive)**
   When you press a key, the corresponding keyboard zone instantly bursts with a random vibrant color and swiftly fades back down. Runs at 60fps for snappy, responsive feedback.

2. 🎵 **Audio Visualizer (Music Rhythm)**
   The lights bounce to the beat of any audio playing on your laptop (Spotify, YouTube, Games).
   - Zone 1 (Left) pulses **RED** to Bass frequencies.
   - Zone 2 (Mid-Left) pulses **GREEN** to Mid frequencies.
   - Zone 3 (Mid-Right) pulses **BLUE** to Treble frequencies.
   - Zone 4 (Right) pulses **CYAN** to overall volume (RMS).

3. 💾 **CPU Core Monitor**
   Uses your keyboard as a live dashboard. As CPU load increases, zones shift from Blue (Idle) → Green (Normal) → Red (Heavy Load).

4. 🖥️ **Screen Ambilight**
   Matches your keyboard lighting to your screen's colors in real time. The display is split into 4 vertical regions mapping to the 4 keyboard zones.

### Ambient & Animation Modes

5. 🌬️ **Breathing** — Slow pulse in Lenovo Blue.
6. 🌈 **Rainbow Wave** — Flowing wave of colors across all zones.
7. 🌌 **Aurora (Northern Lights)** — Shimmering green-blue-purple glow.
8. 🔥 **Fire / Flame** — Flickering orange-red fire with random flare-ups.
9. 💜 **Plasma Energy** — Organic plasma animation with drifting hues.
10. 💗 **Heartbeat** — Realistic cardiac "lub-dub" pulse with hue shift.
11. 🧬 **DNA Helix** — Two counter-rotating cyan/magenta helical waves.

### High-Energy & Effect Modes

12. 💻 **Matrix Digital Rain** — Cyber-green flashes resembling the Matrix.
13. 🪩 **Disco Strobe** — Beat-synced at 130 BPM with white strobe bursts.
14. ⛈️ **Lightning Storm** — Dramatic lightning strikes with afterglow.
15. 🤖 **Cyberpunk Glitch** — Neon palette with random glitch blackouts and flashes.
16. ☄️ **Meteor Bounce** — A meteor bouncing back and forth across zones.
17. 🌊 **Ripple** — Interactive ripples triggered by keypresses.
18. 🌑 **Off** — Turn off keyboard lighting completely.

---

## 🚀 Quick Start (Recommended)

1. Go to the [Releases](../../releases) page and download the latest `LenovoRGB-windows-x64.zip`
2. Extract the zip and run `LenovoRGB.exe` **as Administrator**
3. The app will appear in your system tray — right-click to change modes

> **Before running**, open **Lenovo Vantage** and set your RGB profile to **Static** or **Off**. Otherwise the app can't take control of the keyboard.

---

## 🛠️ Setup from Source

### Prerequisites

- Python 3.12 (required — pre-built `hidapi` wheels are only available for 3.12)
- `hidapi.dll` — the native HID library (see below)

### What is hidapi.dll and why do you need it?

`hidapi` is a C library that lets Python communicate directly with USB HID devices (like your keyboard's RGB controller). The Python package is just a wrapper around this native DLL. Without it, the app can't talk to the hardware.

**To get `hidapi.dll`:**
1. Go to https://github.com/libusb/hidapi/releases/latest
2. Download `hidapi-win.zip`
3. Extract it and copy `x64\hidapi.dll` into the project folder (`D:\...\LenovoRGB\`)

> Do not use 32-bit (`x86`) — Python on Windows is 64-bit.

### Option 1: Run as a GUI app

```bash
# Install dependencies (must be Python 3.12)
pip install -r requirements.txt

# Run as Administrator
python ui.py
```

> The app needs Administrator permissions to write raw USB HID payloads to the keyboard and to hook global keyboard events.

### Option 2: Run a single mode directly (no GUI)

Each mode has its own batch file. Right-click and **Run as administrator**:

| Batch File | Mode |
|---|---|
| `run_type_lighting.bat` | Type-Lighting |
| `run_audio_visualizer.bat` | Audio Visualizer |
| `run_cpu_monitor.bat` | CPU Monitor |
| `run_screen.bat` | Screen Ambilight |
| `run_breathing.bat` | Breathing |
| `run_aurora.bat` | Aurora |
| `run_fire.bat` | Fire |
| `run_glitch.bat` | Glitch |
| `run_matrix.bat` | Matrix |
| `run_meteor.bat` | Meteor |
| `run_ripple.bat` | Ripple |

Or run directly from an **Administrator** terminal:
```bash
python loq_rgb.py --mode breathing
python loq_rgb.py --mode audio
python loq_rgb.py --mode matrix
# etc.
```

### Option 3: Build the exe yourself

1. Place `hidapi.dll` (x64) in the project folder
2. Run:
   ```
   .\build_exe.bat
   ```
3. The exe will be in the `dist` folder

### Option 4: Run on startup

1. Build the exe first (Option 3)
2. Right-click `setup_startup.bat` → **Run as administrator**
3. The app will now launch automatically with admin privileges on every login

---

## ⚙️ Configuration

Right-click the system tray icon → **Open UI** → **Settings**:
- Set a custom **cycle mode shortcut** (default: `Ctrl+Shift+M`)
- Choose the **default mode** on startup
- Toggle **start minimized** to tray

---

## ⚠️ Troubleshooting

| Problem | Fix |
|---|---|
| **Lights not changing** | Open Lenovo Vantage and set RGB to **Static** or **Off** |
| **"Keyboard not found" error** | Make sure you're running as **Administrator** |
| **`hidapi.dll` not found** | Download `x64\hidapi.dll` from [libusb/hidapi releases](https://github.com/libusb/hidapi/releases/latest) and place it in the project folder |
| **Audio Visualizer not working** | Make sure audio is actively playing; the app uses Windows loopback |
| **Lights stuck after crash** | Restart the app and close it cleanly — `atexit` handlers will turn off the lights |
| **App won't start on Python 3.13+** | Downgrade to Python 3.12 — `hidapi` has no pre-built wheel for newer versions yet |

---

## License

MIT. See [LICENSE](LICENSE).
