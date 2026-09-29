<div align="center">

# ⚡ Codex Usage Floating Widget
### 专为语音编程（Vibe Coding）打造的 Windows 桌面悬浮雷达：外设电量、ChatGPT/Codex 配额与 AI 中转站实时实测

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](https://www.microsoft.com/windows)
[![Framework](https://img.shields.io/badge/UI-PyQt5-41CD52.svg)](https://riverbankcomputing.com/software/pyqt/)

[English](README.md) | 简体中文

<br/>

<p align="center">
  <img src="assets/capsule-view.png" alt="Mini Capsule Mode" width="280" />
</p>
<p align="center">
  <em>💊 迷你胶囊模式（鼠标停靠与桌面常驻，点击任意区域秒级展开）</em>
</p>

<p align="center">
  <img src="assets/square-view.png" alt="Square API Relay Mode" width="600" />
</p>
<p align="center">
  <em>⚡ 双栏展开卡片（Square API 视图）：左侧外设电量 + 7天限额消耗基准曲线，右侧 Square API 24h 官方模型实测基准</em>
</p>

<p align="center">
  <img src="assets/aihub-view.png" alt="AIHub Relay Mode" width="600" />
</p>
<p align="center">
  <em>🟢 双栏展开卡片（AIHub 视图）：真实倍率、缓存命中率实时排序与右侧内嵌实测缩略图</em>
</p>

<p align="center">
  <img src="assets/pelican-viewer.png" alt="Pelican Image Viewer Dialog" width="600" />
</p>
<p align="center">
  <em>🎨 在线鹈鹕实测图画廊：3列自适应网格、实时在线分页加载、带精确生成时间戳与无缝缩放</em>
</p>

</div>

---

## 💡 为什么需要它？(The Vibe Coding Story)
在使用 **大疆麦克风（DJI Mic Mini / DJI Mic）** 进行 **语音编程（Vibe Coding）**、灵感口述或高强度与 ChatGPT / OpenAI Codex 协同编写代码时，开发者最常遇到的痛点：
1. **麦克风电量焦虑**：全神贯注口述编程时，无线麦克风突然没电断联，彻底打断心流；
2. **AI 限额盲盒**：不知道 5 小时滚动限额或周限额何时耗尽，缺少平稳的消耗节奏指引；
3. **中转站选型困难与模型降智担忧**：中转站供应商鱼龙混杂，倍率虚标、首字延迟（TTFT）飘忽，且担心模型被降智（是否通过经典“鹈鹕骑自行车”SVG 绘图测试难以查证）。

**`codex-usage-floating-widget`** 正是为此而生的一款轻量、优雅、暗黑毛玻璃质感的 Windows 桌面小组件。

---

## ✨ 核心亮点

### 1. 🎙️ 为 Vibe Coding 打造的外设电量雷达
- **大疆麦克风专属置顶（DJI Mic Mini Priority）**：
  - 检测到 DJI Mic Mini / DJI Mic 连接时，**自动固定置顶在胶囊最前端**，电量随时在视线边缘一览无余；
  - 若未连接麦克风，则智能回退为**展示当前所有在线外设中电量最低的设备**；
- **底层硬件直连，零资源消耗（< 15ms, 0% CPU）**：
  - 基于 Python 原生 `ctypes` 调用 Windows `SetupAPI` 与 `CfgMgr32` 读取硬件电量属性，单次扫描耗时 `< 15ms`，空闲时 CPU 占用稳定为 `0%`；
  - 广泛支持 DJI Mic 系列、机械键盘（NuPhy、Keychron、Lofree Flow）、无线鼠标（罗技 MX Master / Anywhere 系列）、索尼降噪耳机等。

### 2. 🤖 ChatGPT Plus / Codex 额度与状态监测
- **零配置凭据同步**：
  - 自动读取本地 `%USERPROFILE%\.codex\auth.json` 鉴权凭证，与 Codex CLI / ChatGPT 桌面端无缝联动，免除手动输入 Token；
- **纯净双显胶囊（Dual-Quota Capsule）**：
  - 胶囊模式以最精炼的点分数字格式呈现：`[ 🎙️ 90% | 🤖 16% · 23% 🟢 ]`；
  - 左侧为 5 小时滚动限额剩余，右侧为周限额剩余，两个数字**独立根据健康度动态变色**（🟢 充足 / 🟠 适中 / 🔴 预警）；
- **7天消耗速率坐标折线图（Sparkline Grid）与耗尽预测**：
  - 规范的坐标边框与 X 轴 7 等分天数网格（`1d` / `3d` / `5d` / `7d`）；
  - Y 轴每 10% 水平细线与 50% 半程基准虚线；
  - **副对角线理想匀速消耗基准（100% 降至 0%）**，直观对比当前实际消耗是否超速；
  - 倒计时置于上方，**预计耗尽时间置于下方并加粗突出**（`font-weight: 700`）；
  - 5H 滚动窗口与周限额均支持精确到分钟与具体日期的倒计时显示：`倒计时: 3h13m (MM-DD HH:MM)`；
- **原生轮次生命周期状态追踪（彻底告别指示灯反复横跳）**：
  - 基于会话运行记录的**原生轮次生命周期（Turn Lifecycle: `task_started` → `task_complete` / `turn_aborted`）**状态机；
  - 遇到耗时工具调用或长推理时，指示灯**稳定保持橙色旋转（🟠 运行中）**；
  - 一旦 Codex 完成回答并写入 `task_complete`，瞬间切回**稳定翡翠绿呼吸光（🟢 就绪）**；
  - 配套内存级 `(mtime, size)` 差值缓存，100% 免疫 CPU 采样噪点与工具延迟波动，日常检测零磁盘消耗。

### 3. 🌐 中转站监控、官方实测爬虫与鹈鹕画廊
- **CC Switch 额度异常彻底解决（零冲突双源回退）**：
  - 针对使用 CC Switch 切换到第三方中转 API 时，`~/.codex/auth.json` 被覆盖导致官方 Codex 额度显示“异常”的问题，悬浮窗内置 SQLite 双源解析器；
  - 自动从 `%USERPROFILE%\.cc-switch\cc-switch.db` 回退读取官方凭据，**无论 CC Switch 切到哪家中转站，悬浮窗左侧的官方 Codex 剩余额度与倒计时始终正常显示**；
- **Square API 官方模型性能实测监控 (`api.squarefaceicon.org`)**：
  - 实时爬取对齐 Square 官方定价与模型广场详情页中的 **24小时真实测速指标**；
  - 精准展示：**分组与关注模型、综合倍率、生成速度 (t/s)、首字延迟 (TTFT)、总延迟及成功率柱状进度条**；
  - 内置便捷勾选弹窗，可自由配置想要重点关注的分组及每个分组对应的具体模型（如 `GPT-6 Astra`、`DS-v4.1 Flash`、`Claude Opus 5.5` 等）；
  - 支持查看分组基础倍率与模型倍率拆解。
- **AIHub 供应商实测与鹈鹕图库 (`aihub.top`)**：
  - 实时抓取各供应商的真实换算倍率、缓存命中率、TTFT 及最新实测缩略图；
  - **交互式监控勾选**：可在弹窗中查看各供应商的真实参数，自由勾选需要重点监控的优质供应商；
  - **鹈鹕实测图画廊（Pelican Viewer Dialog）**：
    - 点击任意供应商的“📷 实测”缩略图，即可呼出全屏历史画廊；
    - 在线动态拉取该供应商的历史实测记录，以 3 列网格排布，带清晰抓取时间戳；
    - **完全在内存中异步解码展示，零落盘零垃圾文件**；
    - 采用单例守护线程池与独立 Session 隔离，彻底消除 Qt/Python GIL 析构卡顿与死锁。

<table align="center">
  <tr>
    <td align="center"><img src="assets/square-filter.png" width="340" /><br/><b>Square 关注分组与模型勾选器</b></td>
    <td align="center"><img src="assets/aihub-filter.png" width="340" /><br/><b>AIHub 供应商参数筛选勾选器</b></td>
  </tr>
</table>

### 4. 🪟 自然沉浸的桌面交互美学
- **暗黑毛玻璃质感**：高透半透明卡片、微光边框与动态深度阴影；
- **双栏并列视图**：左侧设备与官方配额，右侧中转站指标，信息密度极高且舒展不拥挤；
- **点窗即开**：点击迷你胶囊任意位置即可瞬间展开完整双栏卡片；
- **失焦自动折叠**：点击桌面其他任意窗口，卡片自动平滑收起为迷你胶囊；
- **边缘智能吸附**：鼠标拖拽至屏幕边缘 25px 范围内自动磁吸贴边；
- **任务栏免打扰**：采用 `Qt.Tool` 属性，不占用 Windows 任务栏位置，不干扰 `Alt+Tab`；
- **纯粹关闭交互**：卡片内无误触叉号，日常安静常驻，退出统一在系统托盘右键完成。

---

## 🔒 隐私与凭证安全说明（Privacy & Sanitization）

- **完全脱敏开源**：本项目代码仓库中**绝不包含任何硬编码的个人密钥、Token、密码或邮箱地址**；
- **本地凭证隔离**：
  - 本地运行时，您的配置保存于根目录的 `config.json`，该文件已被 `.gitignore` 严格忽略，不会被提交或上传；
  - 您可以参考 `config.example.json` 按需填入中转站的 API Key 或配置项；
- **只读查询机制**：
  - 所有的 API 查询与图片抓取均为只读请求，绝不主动发起任何消耗额度的推理对话请求。

---

## 🚀 快速使用

### 1. 环境准备
确保您的电脑安装了 Python 3.8+（支持 Python 3.10 ~ 3.13）：

```bash
git clone https://github.com/Tison6/codex-usage-floating-widget.git
cd codex-usage-floating-widget
pip install -r requirements.txt
```

### 2. 配置说明
复制一份配置示例文件：
```bash
copy config.example.json config.json
```
根据需要编辑 `config.json`（非必填，均有优雅的空状态与公共接口回退）。

### 3. 运行启动
- **日常便捷启动（静默无黑框）**：
  双击运行 **`run_silent.vbs`** 或 **`run.bat`**；
- **终端启动（查看调试日志）**：
  双击 **`run_debug.bat`** 或运行命令：
  ```bash
  python main.py
  ```

---

## ⚙️ 快捷操作与右键菜单

在小组件或系统托盘图标上点击**鼠标右键**：
- **💊 切换迷你胶囊 / 展开面板**
- **📏 窗口缩放尺寸**（紧凑 85% / 标准 100% / 放大 115%）
- **📌 窗口置顶（Always on Top）**
- **🔒 锁定窗口位置（防止误触移动）**
- **🔄 立即刷新用量与外设数据**
- **⚙️ 偏好设置...**（调整刷新频率、透明度、开机自启）
- **🗕 隐藏到托盘 / ✕ 退出程序**

---

## 📁 项目架构

```
codex-usage-floating-widget/
├── main.py                  # 应用入口、单例保护与 High-DPI 缩放适配
├── config.example.json      # 脱敏默认配置模板
├── requirements.txt         # Python 依赖清单
├── run_silent.vbs           # 静默后台启动脚本（无黑色控制台窗口）
├── run.bat                  # 便携式批处理启动入口
├── run_debug.bat            # 调试启动入口（遇错暂停输出）
├── LICENSE                  # MIT 开源许可证
├── README.md                # 英文说明文档
├── README_zh.md             # 中文说明文档
├── assets/                  # 截图预览资源
│   ├── capsule-view.png     # 迷你胶囊外观
│   ├── square-view.png      # Square 展开双栏视图
│   ├── aihub-view.png       # AIHub 展开双栏视图
│   ├── pelican-viewer.png   # 在线鹈鹕画廊弹窗
│   ├── square-filter.png    # Square 关注项勾选弹窗
│   └── aihub-filter.png     # AIHub 供应商筛选弹窗
├── core/
│   ├── bt_scanner.py        # Windows SetupAPI 蓝牙电量扫描引擎
│   ├── codex_client.py      # ChatGPT /wham/usage 配额解析与 CC-Switch SQLite 回退
│   ├── codex_activity_tracker.py # 原生轮次生命周期监控（无横跳指示灯）
│   ├── config_manager.py    # 本地配置注册与管理
│   ├── quota_tracker.py     # 7天配额消耗分析与耗尽预测
│   ├── square_client.py     # Square API 官方模型广场与 24h 性能爬虫
│   └── aihub_client.py      # AIHub 公共供应商与实测接口客户端
└── ui/
    ├── floating_widget.py   # 无边框悬浮主窗体（双栏布局、磁吸贴边、失焦自动收起）
    ├── battery_view.py      # 蓝牙外设列表展示组件
    ├── codex_view.py        # AI 配额卡片与倒计时视图
    ├── sparkline_widget.py  # 7天坐标网格与理想基准折线图
    ├── status_light.py      # 双状态呼吸绿点与活力橙旋转指示灯
    ├── relay_view.py        # 中转站双选项卡视图与缩略图管理器
    ├── square_filter_dialog.py # Square & AIHub 交互式勾选对话框
    ├── pelican_viewer.py    # 鹈鹕实测图在线画廊弹窗与单例异步管理器
    ├── settings_dialog.py   # 偏好设置弹窗
    ├── tray_manager.py      # Windows 系统托盘管理
    └── styles.py            # QSS 暗黑毛玻璃样式表
```

---

## ❓ 常见问题排查（FAQ）

<details>
<summary><b>Q1: ChatGPT 额度提示“未认证”或获取失败？</b></summary>
<br/>
本项目通过读取本地 OpenAI Codex CLI 或桌面客户端的本地认证文件获取额度数据。请确保已在终端运行过 <code>codex</code> 命令并完成登录，或检查 <code>%USERPROFILE%\.codex\auth.json</code> 文件是否存在。若使用了 CC Switch 切换中转站，本工具会自动尝试从 <code>%USERPROFILE%\.cc-switch\cc-switch.db</code> 中找回官方原版凭据。
</details>

<details>
<summary><b>Q2: 蓝牙设备已连接但没有显示电量？</b></summary>
<br/>
Windows 原生仅支持具备“电池服务（Battery Service GATT Profile）”或上报标准 PnP 电池属性的蓝牙设备。部分使用专有 2.4GHz 接收器（非标准蓝牙模式）的键鼠可能不向 Windows 系统上报电池指标。
</details>

<details>
<summary><b>Q3: 实测图加载会消耗本地磁盘吗？</b></summary>
<br/>
不会。所有鹈鹕实测图片和缩略图均采用内存缓存（In-Memory QImage Decoding）机制，并在独立后台线程池中平滑解码，关闭弹窗自动安全释放，绝不在磁盘产生大量垃圾文件。
</details>

<details>
<summary><b>Q4: 如何移动窗口或退出程序？</b></summary>
<br/>
- <b>移动</b>：鼠标左键按住窗口任意空白区域拖拽即可，移至屏幕边缘时会自动磁吸吸附。<br/>
- <b>退出</b>：在系统托盘图标或窗口上点击鼠标右键，选择“✕ 退出程序”即可完全退出。
</details>

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。
