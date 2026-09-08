<div align="center">

# ⚡ Codex Usage Floating Widget
### A Vibe-Coding Companion for Windows: Real-Time Bluetooth Battery & ChatGPT/Codex Quota Radar

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](https://www.microsoft.com/windows)
[![Framework](https://img.shields.io/badge/UI-PyQt5-41CD52.svg)](https://riverbankcomputing.com/software/pyqt/)

[**简体中文**](#-中文文档) | [**English**](#-english-documentation)

<br/>

<p align="center">
  <img src="assets/capsule-view.png" alt="Mini Capsule Mode" style="max-height: 40px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);" />
</p>
<p align="center">
  <em>Mini Capsule Mode (Click anywhere to expand / 点击任意区域秒级展开)</em>
</p>

<p align="center">
  <img src="assets/expanded-view.png" alt="Expanded Detailed Card" width="280" style="border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5);" />
</p>
<p align="center">
  <em>Expanded Card Mode with 7-Day Sparkline & Real-Time Peripheral Battery<br/>展开卡片视图：外设电量列表 + 7天限额消耗基准曲线</em>
</p>

</div>

---

<a name="中文文档"></a>
## 🇨🇳 中文文档

### 💡 为什么需要它？(The Vibe Coding Story)
在使用 **大疆麦克风（DJI Mic Mini / DJI Mic）** 进行 **语音编程（Vibe Coding）**、灵感口述或高强度与 ChatGPT / OpenAI Codex 协同编写代码时，开发者最常遇到的两个痛点：
1. **录音设备电量焦虑**：全神贯注编程时，麦克风突然没电断联，打断开发心流；
2. **AI 限额盲盒**：不知道 5 小时滚动限额或周限额何时耗尽，缺少平稳的消耗节奏指引。

**`codex-usage-floating-widget`** 正是为此而生的一款轻量、优雅、暗黑毛玻璃质感的 Windows 桌面小组件。

---

### ✨ 核心亮点

#### 1. 🎙️ 为 Vibe Coding 打造的外设电量雷达
- **大疆麦克风专属优先级（DJI Mic Mini Priority）**：
  - 检测到 DJI Mic Mini / DJI Mic 连接时，**自动固定置顶在胶囊最前端**，电量随时在视线边缘一览无余；
  - 若未连接麦克风，则智能回退为**展示当前所有在线外设中电量最低的设备**；
- **底层硬件直连，零资源消耗**：
  - 基于 Python 原生 `ctypes` 调用 Windows `SetupAPI` 与 `CfgMgr32` 读取硬件电量属性，单次扫描耗时 `< 15ms`，空闲时 CPU 占用稳定为 `0%`；
  - 广泛支持 DJI Mic 系列、机械键盘（Flow84、Keychron、Lofree）、无线鼠标（罗技 MX Master / Anywhere 系列）、索尼降噪耳机等。

#### 2. 🤖 ChatGPT Plus / Codex 额度与状态监测
- **零配置凭据同步**：
  - 自动读取本地 `%USERPROFILE%\.codex\auth.json` 鉴权凭证，与 Codex CLI / ChatGPT 桌面端无缝联动，免除手动配置 Token；
- **纯净双显胶囊（Dual-Quota Capsule）**：
  - 胶囊模式以最精炼的点分数字格式呈现：`[ 🎙️ 50% | 🤖 100% · 84% 🟢 ]`；
  - 左侧为 5 小时滚动限额剩余，右侧为周限额剩余，两个数字**独立根据健康度动态变色**（绿色充足 / 橙色适中 / 红色预警）；
- **7天消耗速率坐标折线图（Sparkline Grid）**：
  - 规范的坐标边框与 X 轴 7 等分天数网格（`1d` / `3d` / `5d` / `7d`）；
  - Y 轴每 10% 水平细线与 50% 半程基准虚线；
  - **副对角线理想匀速消耗基准（100% 降至 0%）**，直观对比当前实际消耗是否超速；
  - 动态计算预计耗尽时间与精确到分钟的周期重置倒计时（`MM-DD HH:MM`）；
- **原生 Session Rollout 事件流状态追踪（告别指示灯反复横跳）**：
  - 直接监听本地 `~/.codex/sessions/` 活跃会话 JSONL 事件流（`task_started`、`reasoning`、`custom_tool_call`、`task_complete`）；
  - 模型深度思考与流式输出期间稳定保持活力橙旋转（🟠 运行中），生成完毕瞬间切回翠绿微光（🟢 就绪），100% 免疫 CPU 采样噪点。

#### 3. 🪟 自然沉浸的桌面交互美学
- **暗黑毛玻璃质感**：高透半透明卡片、微光边框与动态深度阴影；
- **点窗即开**：点击迷你胶囊任意位置即可瞬间展开完整卡片；
- **失焦自动收起**：点击桌面其他任意窗口，卡片自动折叠收起为迷你胶囊；
- **边缘智能吸附**：鼠标拖拽至屏幕边缘 25px 范围内自动磁吸贴边；
- **任务栏免打扰**：采用 `Qt.Tool` 属性，不占用 Windows 任务栏位置，不干扰 `Alt+Tab`。

---

### 🚀 快速使用

#### 1. 环境准备
确保您的电脑安装了 Python 3.8+（支持 Python 3.10 ~ 3.13）：

```bash
git clone https://github.com/your-username/codex-usage-floating-widget.git
cd codex-usage-floating-widget
pip install -r requirements.txt
```

#### 2. 运行启动
- **日常便捷启动（静默无黑框）**：
  双击运行 **`run_silent.vbs`** 或 **`run.bat`**；
- **终端启动（查看调试日志）**：
  双击 **`run_debug.bat`** 或运行命令：
  ```bash
  python main.py
  ```

---

### ⚙️ 快捷操作与右键菜单

在小组件或系统托盘图标上点击**鼠标右键**：
- **💊 切换迷你胶囊 / 展开面板**
- **📏 窗口缩放尺寸**（紧凑 85% / 标准 100% / 放大 115%）
- **📌 窗口置顶（Always on Top）**
- **🔒 锁定窗口位置（防止误触移动）**
- **🔄 立即刷新用量与外设数据**
- **⚙️ 偏好设置...**（调整刷新频率、透明度、开机自启）
- **🗕 隐藏到托盘 / ✕ 退出程序**

---

<a name="english-documentation"></a>
## 🌐 English Documentation

### 💡 Why This Widget?
When pairing wireless microphones like the **DJI Mic Mini** or **DJI Mic 2** for **Vibe Coding** (voice-driven programming) alongside ChatGPT / OpenAI Codex, developers encounter two recurring pain points:
1. **Microphone Battery Anxiety**: Mid-sentence dictation is abruptly broken by an empty battery.
2. **Opaque Rate Limits**: Unclear remaining 5-hour rolling limits and 7-day weekly quotas.

**`codex-usage-floating-widget`** provides an elegant, translucent glassmorphism widget pinned cleanly on your desktop to solve both problems simultaneously.

---

### ✨ Key Features

#### 1. 🎙️ Vibe-Coding Peripheral Radar (DJI Mic Mini First)
- **Pinned Priority**: When a DJI Mic Mini / DJI Mic is connected, its battery percentage is **strictly pinned to the front** of the mini capsule;
- **Lowest-Battery Smart Fallback**: If no mic is connected, the widget automatically monitors whichever connected peripheral has the lowest remaining battery;
- **Native Hardware Access**: Directly calls Windows `SetupAPI` and `CfgMgr32` via Python `ctypes` (`< 15ms` per scan, `0%` idle CPU usage);
- **Multi-Device Support**: DJI Mics, mechanical keyboards (Keychron, NuPhy, Lofree Flow), wireless mice (Logitech MX Master), Sony headsets, etc.

#### 2. 🤖 ChatGPT Plus / Codex Quota & State Tracker
- **Zero-Config Credential Sync**: Automatically reads local `%USERPROFILE%\.codex\auth.json` to stay in sync with Codex CLI and ChatGPT Desktop;
- **Dual-Quota Capsule**: Displays both limits in an ultra-compact dot-separated format: `[ 🎙️ 50% | 🤖 100% · 84% 🟢 ]`;
- **Individual Dynamic Colors**: Quotas dynamically shift color according to health status (>50% Green, 20%~50% Amber, <20% Red);
- **7-Day Sparkline Grid & Ideal Baseline**:
  - Full coordinate frame with 7-day vertical ticks (`1d`, `3d`, `5d`, `7d`);
  - 10% horizontal grid lines with a 50% halfway dashed guide;
  - Ideal pace diagonal benchmark (100% $\to$ 0% across 7 days);
  - Exact minute-level countdowns (`MM-DD HH:MM`) and exhaustion predictions;
- **Native Session Rollout Event Monitor**:
  - Direct atomic monitoring of `~/.codex/sessions/*.jsonl` event streams (`task_started`, `reasoning`, `custom_tool_call`, `task_complete`);
  - Smooth orange spinning indicator (🟠) during deep thinking and streaming, snapping immediately back to emerald green (🟢) when idle—completely free of CPU-jitter false triggers.

#### 3. 🪟 Fluid Desktop Interaction
- **Dark Translucent Aesthetic**: Subtle frosted acrylic glassmorphism with dynamic drop shadow;
- **Click-to-Expand**: Click anywhere on the mini capsule to open the full dashboard;
- **Auto-Collapse on Focus Loss**: Clicking another application automatically folds the card back into the capsule;
- **Magnetic Edge Snapping**: Draggable anywhere, snapping smoothly within 25px of screen boundaries;
- **Taskbar-Free**: Configured with `Qt.Tool` to avoid cluttering your taskbar or Alt+Tab switcher.

---

### 🚀 Getting Started

#### Prerequisites
- Windows 10 or Windows 11
- Python 3.8+ (Python 3.10 ~ 3.13 recommended)

```bash
git clone https://github.com/your-username/codex-usage-floating-widget.git
cd codex-usage-floating-widget
pip install -r requirements.txt
```

#### Launching
- **Silent Background Launch**: Double-click `run_silent.vbs` or `run.bat`;
- **Console Debug Mode**: Run `run_debug.bat` or execute:
  ```bash
  python main.py
  ```

---

### 📁 Project Architecture

```
codex-usage-floating-widget/
├── main.py                  # Application entry point
├── config.example.json      # Default configuration template
├── requirements.txt         # Python dependencies
├── run_silent.vbs           # Silent background VBS launcher
├── run.bat                  # Portable Windows batch launcher
├── run_debug.bat            # Console debug launcher with error prompts
├── LICENSE                  # MIT License
├── assets/                  # Screenshot previews for GitHub
│   ├── capsule-view.png
│   └── expanded-view.png
├── core/
│   ├── bt_scanner.py        # Windows SetupAPI Bluetooth battery engine
│   ├── codex_client.py      # ChatGPT /wham/usage rate limit parser
│   ├── codex_activity_tracker.py # Session rollout event state monitor
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

### ❓ FAQ for External Users / 常见问题排查

<details>
<summary><b>Q1: ChatGPT 额度提示“未认证”或获取失败？ / "Unauthorized" or quota fetch failed?</b></summary>
<br/>
本项目通过读取本地 OpenAI Codex CLI 或桌面客户端的本地认证文件获取额度数据。请确保已在终端运行过 <code>codex</code> 命令并完成登录，或检查 <code>~/.codex/auth.json</code> 文件是否存在。
<br/><i>This tool queries your quota using the local session token managed by the Codex CLI / Desktop app. Ensure you have logged in via the Codex CLI at least once so that <code>~/.codex/auth.json</code> exists.</i>
</details>

<details>
<summary><b>Q2: 蓝牙设备已连接但没有显示电量？ / Bluetooth device connected but no battery shown?</b></summary>
<br/>
Windows 原生仅支持具备“电池服务（Battery Service GATT Profile）”或上报标准 PnP 电池属性的蓝牙设备。部分使用专有 2.4GHz 接收器（非蓝牙模式）的键鼠可能不向 Windows 系统上报电池指标。
<br/><i>Windows can only query battery levels for devices supporting the standard Bluetooth Battery Service (GATT Profile). Devices connected via proprietary 2.4GHz USB dongles typically do not report battery stats to the OS.</i>
</details>

<details>
<summary><b>Q3: 双击没有反应？ / Nothing happens after double-clicking?</b></summary>
<br/>
请先双击运行 <code>run_debug.bat</code> 查看控制台输出。若缺少依赖包，请在终端执行 <code>pip install -r requirements.txt</code>。
<br/><i>Run <code>run_debug.bat</code> to inspect terminal error messages. If dependencies are missing, run <code>pip install -r requirements.txt</code>.</i>
</details>

---

### 📄 License

This project is open-sourced under the [MIT License](LICENSE).
