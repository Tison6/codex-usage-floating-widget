<div align="center">

# ⚡ Codex Usage Floating Widget
### A Vibe-Coding Companion for Windows: Real-Time Bluetooth Battery & ChatGPT/Codex Quota Radar

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](https://www.microsoft.com/windows)
[![Framework](https://img.shields.io/badge/UI-PyQt5-41CD52.svg)](https://riverbankcomputing.com/software/pyqt/)

English | [简体中文](README_zh.md)

<br/>

<p align="center">
  <img src="assets/capsule-view.png" alt="Mini Capsule Mode" width="260" />
</p>
<p align="center">
  <em>Mini Capsule Mode (Click anywhere to expand seamlessly)</em>
</p>

<p align="center">
  <img src="assets/expanded-view.png" alt="Expanded Detailed Card" width="280" />
</p>
<p align="center">
  <em>Expanded Card Mode with 7-Day Sparkline, Rate-Limit Burn Benchmarks & Real-Time Peripheral Battery</em>
</p>

</div>

---

## 💡 Why This Widget? (The Vibe Coding Story)
When pairing wireless microphones like the **DJI Mic Mini** or **DJI Mic** for **Vibe Coding** (voice-driven programming, AI dictation, and hands-free prompt generation) alongside ChatGPT / OpenAI Codex, developers encounter two recurring pain points:
1. **Microphone Battery Anxiety**: Mid-thought dictation is abruptly broken when the microphone unexpectedly runs out of power.
2. **Opaque Rate Limits & Burn Rate**: Uncertainty about remaining 5-hour rolling windows and 7-day weekly quotas, lacking a visible pace guide.

**`codex-usage-floating-widget`** solves both problems in a single, lightweight, dark-acrylic desktop companion.

---

## ✨ Key Features

### 1. 🎙️ Vibe-Coding Peripheral Radar (DJI Mic Mini Priority)
- **Pinned DJI Microphone Priority**:
  - When a **DJI Mic Mini** or **DJI Mic** is connected, its battery is **strictly pinned to the front** of the mini capsule;
  - If no DJI microphone is connected, the widget intelligently falls back to monitoring whichever connected peripheral has the **lowest battery percentage**;
- **Native Hardware Access (< 15ms, 0% CPU)**:
  - Direct calls to Windows `SetupAPI` and `CfgMgr32` via Python `ctypes`, querying standard Bluetooth Battery Service (GATT Profile);
  - Zero background daemon overhead, zero polling lag;
  - Widely supports DJI Mics, mechanical keyboards (NuPhy, Keychron, Lofree Flow), mice (Logitech MX Master/Anywhere), headsets (Sony WH/WF series), and more.

### 2. 🤖 ChatGPT Plus / Codex Quota & State Tracker
- **Zero-Config Token Sync**:
  - Reads `%USERPROFILE%\.codex\auth.json` directly. Stays synchronized with your Codex CLI / ChatGPT Desktop session without manually inputting API tokens;
- **Dual-Quota Capsule Mode**:
  - Compact dot-separated format: `[ 🎙️ 90% | 🤖 16% · 23% 🟢 ]`;
  - Left number is 5-hour rolling limit remaining; right number is weekly quota remaining;
  - Both numbers dynamically and independently shift color based on consumption health (🟢 >50% healthy, 🟠 20%~50% caution, 🔴 <20% critical);
- **7-Day Sparkline Grid & Ideal Burn Baseline**:
  - Structured coordinate frame with 7-day vertical division ticks (`1d`, `3d`, `5d`, `7d`);
  - 10% horizontal fine grid lines with a 50% halfway dashed guideline;
  - **Ideal diagonal pacing guide (100% → 0% across 7 days)** to immediately spot over-consumption;
  - Reordered layout: Reset countdown (`倒计时`) on top, **bold exhaustion prediction** below (`font-weight: 700`);
  - Exact minute-level timestamps formatted as `倒计时: 3h13m (MM-DD HH:MM)` for both 5H and weekly windows;
- **Turn-Lifecycle Status Indicator (Zero Jitter / No False Flashing)**:
  - Tracks native session event streams (`task_started` → `task_complete` / `turn_aborted`) from `~/.codex/state_5.sqlite` and session rollout logs;
  - Displays a smooth rotating electric amber arc spinner (🟠) while Codex is actively thinking or executing tools;
  - Instantly snaps back to a glowing emerald green dot (🟢) the millisecond the turn completes;
  - Immune to tool-execution latency gaps or CPU sampling noise—completely eliminating the status light "flicker/jitter" problem.

### 3. 🪟 Fluid Desktop Interaction
- **Dark Frosted Glassmorphism**: Subtle translucent blur, refined borders, and gentle depth drop-shadows;
- **Click Anywhere to Expand**: Click any area of the mini capsule to instantly reveal the detailed card;
- **Auto-Collapse on Focus Loss**: Clicking outside anywhere on the desktop automatically folds the widget back into capsule mode;
- **Edge Magnetic Snapping**: Smoothly snaps to screen edges within a 25px threshold;
- **Clean Tray Lifecycle**: Frameless tool window (`Qt.Tool`) hidden from the taskbar; no accidental close buttons—exit cleanly via the system tray context menu.

---

## 🚀 Getting Started

### Prerequisites
- Windows 10 or Windows 11
- Python 3.8+ (Python 3.10 ~ 3.13 tested and supported)

```bash
git clone https://github.com/Tison6/codex-usage-floating-widget.git
cd codex-usage-floating-widget
pip install -r requirements.txt
```

### Launching
- **Silent Background Launch (No Console Window)**:
  Double-click **`run_silent.vbs`** or **`run.bat`**;
- **Debug / Terminal Mode**:
  Run **`run_debug.bat`** or execute:
  ```bash
  python main.py
  ```

---

## ⚙️ Context Menu & Controls

Right-click the widget or the system tray icon to access:
- **💊 Toggle Mini Capsule / Expanded Card**
- **📏 UI Scaling** (Compact 85% / Standard 100% / Large 115%)
- **📌 Always on Top**
- **🔒 Lock Window Position** (prevents accidental drag)
- **🔄 Refresh Now** (forces Bluetooth & Codex quota sync)
- **⚙️ Preferences...** (adjust polling intervals, opacity, launch on startup)
- **🗕 Hide to Tray / ✕ Exit Application**

---

## 📁 Project Structure

```
codex-usage-floating-widget/
├── main.py                  # Application entry point & High-DPI handling
├── config.example.json      # Default configuration template
├── requirements.txt         # Python dependencies
├── run_silent.vbs           # Silent background VBS launcher
├── run.bat                  # Portable Windows batch launcher
├── run_debug.bat            # Console debug launcher with error prompts
├── LICENSE                  # MIT License
├── README.md                # English Documentation
├── README_zh.md             # 中文说明文档
├── assets/                  # Screenshot previews
│   ├── capsule-view.png
│   └── expanded-view.png
├── core/
│   ├── bt_scanner.py        # Windows SetupAPI Bluetooth battery engine
│   ├── codex_client.py      # ChatGPT /wham/usage rate limit parser
│   ├── codex_activity_tracker.py # Turn-lifecycle state monitor (zero jitter)
│   ├── config_manager.py    # Local registry & config management
│   └── quota_tracker.py     # 7-day quota analytics & burn prediction
└── ui/
    ├── floating_widget.py   # Main frameless widget (snapping, auto-collapse)
    ├── battery_view.py      # Bluetooth peripheral list view
    ├── codex_view.py        # AI quota card & countdown view
    ├── sparkline_widget.py  # 7-day coordinate grid & baseline chart
    ├── status_light.py      # Dual-state glowing & rotating light
    ├── settings_dialog.py   # Preference settings modal
    ├── tray_manager.py      # Windows system tray integration
    └── styles.py            # QSS dark glassmorphism stylesheet
```

---

## ❓ FAQ

<details>
<summary><b>Q1: ChatGPT quota shows "Unauthorized" or failed to fetch?</b></summary>
<br/>
This widget reads your existing authorization credentials from <code>%USERPROFILE%\.codex\auth.json</code>. Ensure that you have installed the official Codex CLI or ChatGPT desktop application and logged in at least once so this file exists.
</details>

<details>
<summary><b>Q2: Bluetooth peripheral connected but battery is not showing?</b></summary>
<br/>
Windows natively supports battery queries for devices providing the standard Bluetooth Battery Service (GATT Profile). Devices connected strictly via proprietary 2.4GHz USB wireless dongles do not expose battery telemetry to Windows OS APIs.
</details>

<details>
<summary><b>Q3: How to exit or move the widget?</b></summary>
<br/>
- <b>Move</b>: Left-click and drag anywhere on the widget to reposition. It will auto-snap when near the screen border.
<br/>
- <b>Exit</b>: Right-click the system tray icon (or the widget itself) and select "✕ 退出程序" (Exit).
</details>

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
