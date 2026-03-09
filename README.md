<h1 align="center">Lenovo LOQ Custom RGB Controller</h1>

<p align="center">
  A custom, feature-rich controller for the 4-zone RGB keyboard found on <strong>Lenovo LOQ</strong> and <strong>Legion</strong> laptops. 
  It provides dynamic effects that interact with your typing, system audio, CPU load, and more.
</p>

---

## ✨ Features

- **System Tray GUI**: A minimal UI built in Tkinter and PyStray that lives in your system tray. Quick access to change modes or tweak settings seamlessly.
- **Global Hotkeys**: Switch between lighting modes on the fly using a customizable hotkey (default: `Ctrl+Shift+M`).
- **Startup Integration**: Effortlessly start the app automatically minimized to the system tray with elevated privileges.
- **Lightweight Executable**: Compile the Python scripts into a single standalone `.exe` file you can place anywhere.
- **7 Dynamic Lighting Modes**: From responsive typing gradients to audio visualizers, use your keyboard's LEDs as a canvas.

---

## 🎨 Available Modes

1. ⌨️ **Type-Lighting (Reactive)**
   When you press a key, the specific keyboard zone will instantly burst with a random vibrant color and swiftly fade back down. Designed for rapid typing up to 60fps for snappy feedback.

2. 🎵 **Audio Visualizer (Music Rhythm)**
   The lights bounce to the beat of any audio playing on your laptop (Spotify, YouTube, Games).
   - Zone 1 (Left) pulses **RED** to Bass frequencies.
   - Zone 2 (Mid-Left) pulses **GREEN** to Mid frequencies.
   - Zone 3 (Mid-Right) pulses **BLUE** to Treble frequencies.
   - Zone 4 (Right) pulses **WHITE** to overall volume (RMS).

3. 💾 **CPU Core Monitor**
   Uses your keyboard as a live dashboard map. As your CPU load increases, zones shift from Blue (Idle) -> Green (Normal) -> Red (Heavy Load). Zones physically map to your CPU core groups.

4. 🍅 **Pomodoro Timer**
   A silent productivity timer. 
   - **Work (25min)**: The keyboard progressively turns bright green across the 4 zones.
   - **Break (5min)**: The keyboard flashes and turns solid blue to signify your short break.

5. 🌬️ **Breathing Color Cycle**
   A smooth, calming, and slow animation that pulses the whole keyboard in Lenovo Blue.

6. 💻 **Matrix Raining Code**
   Bursts of bright 'cyber-green' fade down the different strips of your keyboard at random intervals, resembling the raining code from The Matrix.

7. 🌈 **Rainbow Wave**
   A gorgeous, uninterrupted, flowing wave of colors smoothly cycling across all 4 zones.

8. 🌑 **Turn Off Lights**
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

---

## ⚙️ Configuration

- Right-click the system tray icon and go to **Open UI** -> **Settings**.
- Here you can:
  - Record a custom **Cycle Mode Shortcut** (e.g., `Right Alt + Numpad 4`).
  - Choose the **Default mode** applied instantly on startup.
  - Choose to start the app seamlessly **minimized** to the tray.

---

## ⚠️ Troubleshooting

- **No lights changing**: Make sure nothing else is controlling the RGB (like Lenovo Vantage/Legion Zone). Open Lenovo Vantage, set your lighting profile to **"Static"** or **Off**, and let the app takeover.
- **Audio Visualizer Not Working**: Ensure your audio output isn't exclusive. The script intercepts your default Windows loopback speaker device. Only plays when audio is actively outputted.
- **Missing or Locked Interface**: The script relies on the Lenovo hardware interface `0xff89:0x00cc`. You **must** run the script / `.exe` as Administrator to write direct raw USB HID payloads to your laptop.
