<div align="center">

# ⚡ Codex Vibe Monitor
### 专为语音编程（Vibe Coding）打造的 Windows 桌面悬浮雷达：外设电量、ChatGPT/Codex 配额、AI 中转站实测与 GPU 集群监控

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](https://www.microsoft.com/windows)
[![Framework](https://img.shields.io/badge/UI-PyQt5-41CD52.svg)](https://riverbankcomputing.com/software/pyqt/)

简体中文 | [English](README_en.md)

<br/>

<p align="center">
  <img src="assets/capsule-view.png" alt="Mini Capsule Mode" width="220" />
</p>
<p align="center">
  <em>💊 极简微型胶囊模式（无 % 极简点分数字、未加粗 9px 现代字体、双行对称 6 单位布局、点击任意处即刻展开）</em>
</p>

<p align="center">
  <img src="assets/square-view.png" alt="Square API Relay & GPU Mode" width="750" />
</p>
<p align="center">
  <em>⚡ 三列联动展开卡片（Square API 视图）：左列外设电量 + 7天限额消耗基准曲线，中列 Square API 官方 24h 模型实测与计费倍率，右列 GPU 集群 5 卡实时状态</em>
</p>

<p align="center">
  <img src="assets/aihub-view.png" alt="AIHub Relay & GPU Mode" width="750" />
</p>
<p align="center">
  <em>🟢 三列联动展开卡片（AIHub 视图）：实时倍率、缓存命中率排序、内嵌鹈鹕测图缩略图、自动/手动双模筛选</em>
</p>

<p align="center">
  <img src="assets/gpu-hist-view.png" alt="GPU History Gantt Chart" width="750" />
</p>
<p align="center">
  <em>📊 GPU 历史占用甘特图（Gantt Chart）：24h / 7天 全卡历史任务时间线追溯、无重叠时钟刻度、任务提交人及进程悬停</em>
</p>

<p align="center">
  <img src="assets/pelican-viewer.png" alt="Pelican Image Viewer Dialog" width="650" />
</p>
<p align="center">
  <em>🎨 在线鹈鹕实测图画廊：3列自适应网格、实时在线异步流式加载、生成时间戳与无缝缩放检视</em>
</p>

</div>

---

## 💡 为什么需要它？(The Vibe Coding Story)
在使用 **大疆无线麦克风（DJI Mic Mini / DJI Mic）** 配合 ChatGPT / OpenAI Codex 进行 **语音编程（Vibe Coding）**、灵感口述及高强度智能体结对编程时，开发者常遇到四重痛点：
1. **无线电量焦虑**：全神贯注口述编程时，无线麦克风突发低电断连，彻底打断心流；
2. **AI 限额盲盒**：不清楚 5 小时滚动限额或周限额何时耗尽，缺少平稳的消耗节奏指引；
3. **中转站选型困难与模型降智担忧**：第三方中转站倍率虚标、首字延迟（TTFT）飘忽，且难以查证模型是否通过经典“鹈鹕骑自行车”SVG 绘图测试；
4. **GPU 算力集群调度盲区**：训练或推理过程中无法随时在桌面一眼感知远程显卡显存占用、功率负载与任务排队情况。

**`codex-usage-floating-widget`** 正是为此而生的一款极简、优雅、暗黑毛玻璃质感的 Windows 桌面小组件。

---

## ✨ 核心亮点

### 1. 💊 极简微型胶囊模式（Mini Capsule Mode）
- **无 `%` 极简视觉美学**：彻底消除冗余的 `%` 符号，数值间通过纤细半透明的点分符 `·` 优雅连接；
- **现代无衬线未加粗排版**：采用 `9px` 现代无衬线常规字重（Regular），告别粗体重压感；
- **高密度双行对称 6 单位布局**：
  - **第一行**：`🎙️ 50 | 🟩 0 · 0 · 0 · 3 · 0`（置顶麦克风电量 + NVIDIA 5 块 GPU 显存快速概览）；
  - **第二行**：`🌸 32 · 12 🟠 | 🔲 35 · 29 · 1`（ChatGPT 5H 与周限额健康色 + 3 台服务器 CPU 实时利用率）；
- **极致紧凑零多余留白**：依缩放比例动态微调（在 `0.8` 缩放倍率下仅宽 `152px`、高 `35px`），左右边距完美对称，两位数极限测试零溢出；
- **全局手势交互**：按住小组件任意空白处可自由拖拽吸附屏幕边缘；单击胶囊任意区域瞬间无缝展开为全能看板。

### 2. 🎙️ 为 Vibe Coding 打造的外设电量雷达
- **大疆麦克风专属置顶（DJI Mic Priority）**：
  - 检测到 DJI Mic Mini / DJI Mic 连接时，**自动固定置顶在胶囊最前端**，电量随时在视线边缘一览无余；
  - 若未连接麦克风，则智能回退为**展示当前所有在线外设中电量最低的设备**；
- **底层硬件直连，零资源消耗（< 15ms, 0% CPU）**：
  - 基于 Python 原生 `ctypes` 调用 Windows `SetupAPI` 与 `CfgMgr32` 读取硬件电量属性，单次扫描耗时 `< 15ms`，空闲时 CPU 占用稳定为 `0%`；
  - 广泛支持 DJI Mic 系列、机械键盘（NuPhy、Keychron、Lofree Flow）、无线鼠标（罗技 MX Master / Anywhere 系列）、索尼降噪耳机等。

### 3. 🤖 ChatGPT Plus / Codex 额度与状态监测
- **零配置凭据同步**：
  - 自动读取本地 `%USERPROFILE%\.codex\auth.json` 鉴权凭证，与 Codex CLI / ChatGPT 桌面端无缝联动，免除手动输入 Token；
- **CC Switch 额度异常彻底解决（零冲突双源回退）**：
  - 自动从 `%USERPROFILE%\.cc-switch\cc-switch.db` 回退读取官方凭据，**无论 CC Switch 切到哪家中转站，悬浮窗左侧的官方 Codex 剩余额度与倒计时始终正常显示**；
- **7天消耗速率坐标折线图（Sparkline Grid）与耗尽预测**：
  - 规范的坐标边框与 X 轴 7 等分天数网格（`1d` / `3d` / `5d` / `7d`）；
  - **副对角线理想匀速消耗基准（100% 降至 0%）**，直观对比当前实际消耗是否超速；
  - 倒计时置于上方，预计耗尽时间置于下方突出；精确到分钟与具体日期；
- **原生轮次生命周期状态追踪（彻底告别指示灯反复横跳）**：
  - 基于会话运行记录的**原生轮次生命周期（Turn Lifecycle: `task_started` → `task_complete` / `turn_aborted`）**状态机；
  - 遇到耗时工具调用或长推理时，指示灯**稳定保持橙色旋转（🟠 运行中）**；
  - 一旦 Codex 完成回答并写入 `task_complete`，瞬间切回**稳定翡翠绿呼吸光（🟢 就绪）**。

### 4. 🌐 中转站监控、官方实测爬虫与鹈鹕画廊
- **Square API 官方模型性能实测监控**：
  - 实时爬取对齐 Square 官方定价与模型广场详情页中的 **24小时真实测速指标**；
  - 精准展示：**分组与关注模型、综合倍率、输出 Token 计费价格（$/M）、生成速度 (t/s)、首字延迟 (TTFT)、总延迟及成功率柱状进度条**；
  - 多模型分组拆行独立展示，支持多维勾选与模型匹配过滤；
- **AIHub 供应商实测与鹈鹕图库**：
  - 实时抓取各供应商真实换算倍率、缓存命中率、TTFT 及最新实测缩略图；
  - **自动筛选与手动模式无缝切换**：可配置复合过滤阈值（成功率、缓存率、真实倍率区间），支持每分钟自动刷新；
  - **在线鹈鹕实测图画廊（Pelican Viewer Dialog）**：
    - 点击任意供应商缩略图一键呼出 3 列画廊；
    - 在线异步解码渲染，零落盘零垃圾文件，全量回溯防降智实测记录。

### 5. 🖥️ GPU 集群监控与历史占用甘特图
- **5 块高性能 GPU 实时监控（7号 L40S ×3 · 8号 A100 ×2）**：
  - 实时获取显存利用率（GB / 百分比）、实时功耗与功耗墙（W）、核心利用率；
  - 正在使用的任务进程标识（用户名 / PID）一目了然；
  - 依据显存利用率实施三阶健康色阶渲染（<10% 绿色 / 10%~30% 橙色 / ≥30% 红色报警）；
- **24小时 / 7天 历史占用甘特图（History Gantt Chart）**：
  - 清晰复刻服务器资源占用时间线，回溯每块 GPU 的使用时段与提交人；
  - 悬停即时提示显存与任务明细，精准掌握计算卡空闲窗口。

---

## 🚀 快速上手

### 环境准备
- 操作系统：Windows 10 / 11 (64-bit)
- Python 版本：Python 3.8 或更高版本

### 安装步骤
```bash
# 1. 克隆代码仓库
git clone https://github.com/Tison6/codex-usage-floating-widget.git
cd codex-usage-floating-widget

# 2. 安装必要依赖
pip install -r requirements.txt

# 3. 启动小组件
python main.py
```

### 开机自启与后台运行
- 双击根目录下的 **`run_silent.vbs`** 即可在后台静默运行（无任何黑框命令行窗口）；
- 右键点击悬浮窗选择 **“偏好设置”**，可开启 **“开机自动启动”** 开关。

---

## 🔒 隐私与安全说明 (Privacy & Security)

本项目在开源设计上严格遵循**零隐私泄露（Zero Privacy Leakage）**原则：
- **无凭据外泄**：代码库中不包含任何个人 API Key、OAuth Access Token、密码或内部私网 IP；
- **配置隔离**：所有鉴权凭证、服务器连接配置均保存在本地 `config.json` 中，默认被 `.gitignore` 彻底隔离；
- **脱敏映射**：本地用户名映射均保存在本地 `data/user_mapping.json` 中，仅供本地机器渲染使用，绝不会随代码提交至公开仓库。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
