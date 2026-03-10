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
- **16 Dynamic Lighting Modes**: From responsive typing gradients to audio visualizers to lightning storms, use your keyboard's LEDs as a canvas.

---

## 🎨 Available Modes

### Reactive & Utility Modes

1. ⌨️ **Type-Lighting (Reactive)**
   When you press a key, the corresponding keyboard zone instantly bursts with a random vibrant color and swiftly fades back down. Runs at 60fps for snappy, responsive feedback. Repeated key presses always trigger a new color.

2. 🎵 **Audio Visualizer (Music Rhythm)**
   The lights bounce to the beat of any audio playing on your laptop (Spotify, YouTube, Games).
   - Zone 1 (Left) pulses **RED** to Bass frequencies.
   - Zone 2 (Mid-Left) pulses **GREEN** to Mid frequencies.
   - Zone 3 (Mid-Right) pulses **BLUE** to Treble frequencies.
   - Zone 4 (Right) pulses **WHITE** to overall volume (RMS).

3. 💾 **CPU Core Monitor**
   Uses your keyboard as a live dashboard. As your CPU load increases, zones shift from Blue (Idle) → Green (Normal) → Red (Heavy Load). Zones map to your CPU core groups.

4. 🖥️ **Screen Ambilight**
   Matches your keyboard lighting to your screen's colors in real time. The display is split into 4 vertical regions that map to the 4 keyboard zones. Colors are saturation-boosted for vibrant output.

5. 🍅 **Pomodoro Timer**
   A silent productivity timer. 
   - **Work (25min)**: The keyboard progressively turns bright green across the 4 zones.
   - **Break (5min)**: The keyboard flashes and turns solid blue to signify your short break.

### Ambient & Animation Modes

6. 🌬️ **Breathing Color Cycle**
   A smooth, calming, slow animation that pulses the whole keyboard in Lenovo Blue.

7. 🌈 **Rainbow Wave**
   A gorgeous, uninterrupted, flowing wave of colors smoothly cycling across all 4 zones.

8. 🌌 **Aurora (Northern Lights)**
   Overlapping sine waves generate an organic, shimmering green-blue-purple glow that drifts across the keyboard like real northern lights.

9. 🔥 **Fire / Flame**
   Flickering orange-red fire effect with random intensity fluctuations and occasional bright yellow flare-ups on each zone.

10. 💜 **Plasma Energy**
    Overlapping multi-frequency sine waves create an organic plasma-like animation with continuously drifting hues across all zones.

11. 💗 **Heartbeat**
    Realistic cardiac rhythm — a sharp "lub-dub" double pulse followed by rest. The hue gently shifts from blue through purple to red over an 8-second cycle, with a subtle ripple effect across zones.

12. 🧬 **DNA Helix**
    Two counter-rotating helical waves (Cyan and Magenta) weave across the keyboard. Where the strands cross, they blend into white/lavender with a brightness boost.

### High-Energy & Effect Modes

13. 💻 **Matrix Digital Rain**
    Bursts of bright cyber-green flash and decay at random intervals across the zones, resembling the iconic raining code from The Matrix.

14. 🪩 **Disco Strobe**
    Beat-synced at 128 BPM — each zone snaps to a vivid color every beat, with smooth fading in between. Every 8th beat triggers a synchronized white strobe burst.

15. ⛈️ **Lightning Storm**
    Dark indigo/purple ambient breathing interrupted by dramatic multi-phase lightning strikes — a bright initial flash, spread to adjacent zones, a brief dark gap, a dimmer blue afterstrike, and a violet afterglow fade.

16. 🤖 **Cyberpunk Glitch**
    Neon cyan, magenta, hot-pink, and deep-sky-blue palette with random glitch events — sudden blackouts, white flashes, and color scrambles for a futuristic cyberpunk aesthetic.

17. ☄️ **Meteor Bounce**
    A light "meteor" bounces back and forth across the 4 zones with a trailing glow. Changes color between cyan and magenta depending on direction.

18. 🌑 **Turn Off Lights**
    Completely shut off your keyboard illumination when needed.

---

## 🛠️ Setup & Installation

### Option 1: Running as a Python script

1. Open a command prompt in this directory and install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
2. Double-click `ui.py` or run `python ui.py` from your terminal. 
   *(Note: The app needs Administrator permissions because it reads global keyboard events for the Type-Lighting mode & Hotkeys!)*

### Option 2: Build into a Standalone Executable (Recommended)

1. Ensure the requirements are installed (`pip install -r requirements.txt`).
2. If you don't have `pyinstaller`, install it using `pip install pyinstaller`.
3. Double-click the **`build_exe.bat`** file.
4. Wait for the build to finish. Your new standalone executable (`LenovoRGB.exe`) will be generated inside the `dist` folder!

### Option 3: Run Automatically on Startup

1. First, build the executable (Option 2) so that `dist\LenovoRGB.exe` exists.
2. Right-click **`setup_startup.bat`** and click **"Run as Administrator"**.
3. It will configure an advanced Windows Scheduled Task so the program runs silently in the background with admin privileges the moment you log in.

### Option 4: Run Individual Modes via Batch Files

You can run specific modes directly from included `.bat` files without the full GUI:

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
| `run_meteor.bat` | Meteor |

Each batch file will request administrator privileges automatically.

---

## ⚙️ Configuration

- Right-click the system tray icon and go to **Open UI** → **Settings**.
- Here you can:
  - Record a custom **Cycle Mode Shortcut** (e.g., `Ctrl+Shift+M`).
  - Choose the **Default mode** applied instantly on startup.
  - Choose to start the app seamlessly **minimized** to the tray.

---

## ⚠️ Troubleshooting

- **No lights changing**: Make sure nothing else is controlling the RGB (like Lenovo Vantage/Legion Zone). Open Lenovo Vantage, set your lighting profile to **"Static"** or **Off**, and let the app takeover.
- **Audio Visualizer Not Working**: Ensure your audio output isn't exclusive. The script intercepts your default Windows loopback speaker device. Only plays when audio is actively outputted.
- **Lights stuck on after closing**: This should be fixed — the app now uses `atexit` handlers and Windows Console Ctrl handlers to turn lights off on exit. If lights are still stuck after a crash, just restart the app briefly and close it cleanly.
- **Missing or Locked Interface**: The script relies on the Lenovo hardware interface `0xff89:0x00cc`. You **must** run the script / `.exe` as Administrator to write direct raw USB HID payloads to your laptop.
