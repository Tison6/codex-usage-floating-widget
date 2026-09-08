# ⚡ Windows 桌面悬浮小组件 (Desktop Floating Widget)

一款专为 Windows 打造的轻量、暗黑毛玻璃质感、现代化桌面悬浮小组件。  
集成了**蓝牙外设电量监控（支持大疆麦克风优先策略）**与 **ChatGPT Plus / Codex 限额用量分析（7天燃烧折线图 + 原生工作状态指示灯）**。

---

## ✨ 核心特性

### 1. 🔋 实时蓝牙设备电量监控
- **底层硬件直连**：通过 Python 原生 `ctypes` 调用 Windows `SetupAPI` 与 `CfgMgr32`，单次扫描耗时 `< 15ms`，日常空闲 CPU 占用 `0%`。
- **智能设备匹配**：支持罗技（MX Master/Anywhere）、Lofree/Keychron 机械键盘、索尼（WH-1000XM/LinkBuds）、大疆麦克风（DJI Mic）、无线耳机等常见蓝牙外设。
- **智能优先策略**：
  - **大疆麦克风优先**：当检测到连接了大疆麦克风时，胶囊面板优先固定展示麦克风电量；
  - **最低电量回退**：若麦克风未连接，则自动挑选当前在线设备中电量最低的那台进行预警展示。
- **健康分级变色**：电量根据剩余百分比自动分级变色（🟢 充足 >50% / 🟡 适中 20%~50% / 🔴 紧张 <20%）。

### 2. 🤖 ChatGPT Plus / Codex 限额与会话状态监控
- **零配置凭据绑定**：自动读取本地 `~/.codex/auth.json` 鉴权凭证，与 Codex CLI / ChatGPT 桌面端实时无缝联动。
- **纯净双显胶囊**：迷你模式下紧凑呈现 5H 滚动限额与 7天周限额（例如 `[ 🎙️ 50% | 🤖 100% · 84% 🟢 ]`），各自独立动态变色。
- **7天消耗速率折线图（Sparkline Grid）**：
  - 规范的坐标边框与 X 轴 7 等分天数竖线（`1d` / `3d` / `5d` / `7d`）；
  - Y 轴每 10% 细线与 50% 基准虚线；
  - 副对角线理想匀速基准线（从 100% 匀速降至 0%）；
  - 动态计算预计耗尽时间与精确到分钟的重置倒计时（`MM-DD HH:MM`）。
- **原生 Session Rollout 事件流状态追踪**：
  - 抛弃易抖动的 CPU 采样，直接监听 `~/.codex/sessions/` 活跃会话 JSONL 事件流；
  - 提问生成时稳定保持活力橙旋转（🟠 运行处理中，不抖动不跳绿）；
  - 回复完成后瞬间切回常驻翠绿微光（🟢 空闲就绪）。

### 3. 🪟 沉浸式桌面交互美学
- **暗黑毛玻璃质感**：半透明圆角卡片、微光边框与平滑阴影。
- **极简自然交互**：
  - **点窗即开**：点击迷你胶囊任意位置即可秒级展开完整卡片；
  - **失焦自动收起**：点击桌面其他应用窗口时，卡片自动优雅折叠回迷你胶囊；
  - **物理拖拽与吸附**：按住即可自由拖动，靠近屏幕边缘 25px 自动磁吸贴边。
- **任务栏隐藏与系统托盘**：使用 `Qt.Tool` 属性隐藏 Windows 任务栏占位与 Alt+Tab 干扰，右键托盘支持开机自启动与快速退出。

---

## 🚀 快速开始

### 1. 环境准备
确保已安装 Python 3.8+（推荐 Python 3.10 ~ 3.13）：

```bash
git clone https://github.com/your-username/desktop-floating-widget.git
cd desktop-floating-widget
pip install -r requirements.txt
```

### 2. 启动运行
- **命令行启动**：
  ```bash
  python main.py
  ```
- **Windows 便捷启动**：
  - 双击 `run_silent.vbs`：后台静默启动（无 CMD 黑框）；
  - 双击 `run.bat`：控制台快速启动。

---

## ⚙️ 快捷操作与右键菜单

在悬浮小组件或系统托盘图标上点击**鼠标右键**，可调出控制菜单：
- **💊 切换迷你 / 展开模式**
- **📏 窗口缩放尺寸**（紧凑 85% / 标准 100% / 放大 115%）
- **📌 窗口置顶（Always on Top）**
- **🔒 锁定窗口位置（防止误触移动）**
- **🔄 立即刷新数据**
- **⚙️ 偏好设置...**（调节透明度、扫描频率、凭证路径、开机自启）
- **🗕 隐藏到系统托盘**
- **✕ 退出程序**

---

## 📁 目录架构

```
desktop-floating-widget/
├── main.py                  # 程序主入口
├── config.example.json      # 默认配置文件模板
├── requirements.txt         # Python 依赖清单
├── run_silent.vbs           # Windows 静默启动脚本
├── run.bat                  # 便捷启动脚本
├── LICENSE                  # 开源许可证 (MIT)
├── core/
│   ├── bt_scanner.py        # Windows SetupAPI 蓝牙设备与电量探测引擎
│   ├── codex_client.py      # ChatGPT/Codex /wham/usage 额度查询与凭据解析
│   ├── codex_activity_tracker.py # Session Rollout 事件流实时工作状态监测
│   ├── config_manager.py    # 注册表与配置文件管理
│   └── quota_tracker.py     # 7天周期用量持久化与耗尽分析
└── ui/
    ├── floating_widget.py   # 悬浮窗主窗口 (毛玻璃、拖动吸附、失焦自动收起)
    ├── battery_view.py      # 蓝牙外设列表展示组件
    ├── codex_view.py        # 额度卡片与时间倒计时组件
    ├── sparkline_widget.py  # 7天坐标网格与理想基准折线图
    ├── status_light.py      # 呼吸灯与旋转指示灯
    ├── settings_dialog.py   # 偏好设置对话框
    ├── tray_manager.py      # Windows 系统托盘管理
    └── styles.py            # QSS 样式表与暗黑主题
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
