"""
Server CPU, Memory & Disk Utilization Monitor via SSH.
Supports:
1. Windows servers ('quad', 'e5', '8375c') via typeperf streaming & wmic.
2. Linux GPU servers ('7号', '8号', '4号') via lightweight /proc and disk sampling.
Runs fully asynchronously in background threads with zero UI blocking.
"""

import io
import csv
import time
import socket
from typing import Dict, Any, List, Optional
import paramiko
from PyQt5.QtCore import QObject, QThread, pyqtSignal

import os
import json

DEFAULT_CPU_SERVERS = [
    {
        "id": "quad",
        "name": "server-quad",
        "host": "server-quad",
        "port": 22,
        "user": "SJTU",
        "password": "lab116",
        "type": "cpu"
    },
    {
        "id": "e5",
        "name": "server-e5",
        "host": "server-e5",
        "port": 22,
        "user": "SJTU",
        "password": "lab116",
        "type": "cpu"
    },
    {
        "id": "8375c",
        "name": "server-8375c",
        "host": "server-8375c",
        "port": 22,
        "user": "SJTU",
        "password": "lab116",
        "type": "cpu"
    }
]

DEFAULT_GPU_SERVERS = [
    {
        "id": "7",
        "name": "7号 · L40S",
        "ip": "192.168.120.7",
        "port": 22,
        "user": "xutianxiao",
        "key_path": r"C:/Users/xtx/.ssh/id_rsa_xtx",
        "type": "gpu"
    },
    {
        "id": "8",
        "name": "8号 · A100",
        "ip": "192.168.120.8",
        "port": 22,
        "user": "xutianxiao",
        "key_path": r"C:/Users/xtx/.ssh/id_rsa_xtx",
        "type": "gpu"
    },
    {
        "id": "4",
        "name": "4号 · 2080Ti",
        "ip": "192.168.120.4",
        "port": 22,
        "user": "xutianxiao",
        "key_path": r"C:/Users/xtx/.ssh/id_rsa_stu",
        "type": "gpu"
    }
]


def get_hex_for_cpu(val: float) -> str:
    """Return theme color based on CPU usage percentage."""
    if val < 0:
        return "#64748B"  # Offline / disconnected: Slate gray
    elif val < 10:
        return "#10B981"  # Normal (<10%): Emerald green
    elif val < 30:
        return "#F59E0B"  # Medium (10%~30%): Amber orange
    else:
        return "#EF4444"  # High (>=30%): Alert red


class SingleWindowsServerWorker(QThread):
    """Background worker monitoring a Windows server's CPU via typeperf and RAM/Disk via wmic."""
    cpu_updated = pyqtSignal(str, float)
    stats_updated = pyqtSignal(str, dict)
    status_updated = pyqtSignal(str, str)

    def __init__(self, server_cfg: Dict[str, Any], interval: int = 2):
        super().__init__()
        self.server_cfg = server_cfg
        self.interval = max(1, interval)
        self.server_id = server_cfg.get("id", server_cfg.get("name", "server"))
        self.name = server_cfg.get("name", self.server_id)
        self.host = server_cfg.get("host", self.name)
        self.port = int(server_cfg.get("port", 22))
        self.user = server_cfg.get("user", "SJTU")
        self.password = server_cfg.get("password", "lab116")
        self._running = True
        self.client: Optional[paramiko.SSHClient] = None
        self._last_stats: Dict[str, Any] = {
            "id": self.server_id,
            "name": self.name,
            "type": "cpu",
            "cpu": -1.0,
            "mem_used": 0.0,
            "mem_total": 0.0,
            "mem_pct": 0.0,
            "disk_free": 0.0,
            "disk_total": 0.0,
            "status": "connecting"
        }

    def stop(self):
        self._running = False
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

    def _query_wmic_stats(self):
        """Query memory and all fixed disks free space via WMIC on another channel."""
        if not self.client:
            return
        try:
            cmd = 'wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value & wmic logicaldisk where DriveType=3 get Caption,FreeSpace,Size,VolumeName /format:csv'
            stdin, stdout, stderr = self.client.exec_command(cmd, timeout=5)
            raw = stdout.read()
            try:
                out = raw.decode('gbk')
            except Exception:
                out = raw.decode('utf-8', errors='ignore')

            res = {}
            csv_lines = []
            is_csv = False
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                if 'FreePhysicalMemory' in line or 'TotalVisibleMemorySize' in line:
                    if '=' in line:
                        k, v = line.split('=', 1)
                        res[k.strip()] = v.strip()
                if 'Caption' in line and 'FreeSpace' in line:
                    is_csv = True
                if is_csv:
                    csv_lines.append(line)

            tot_k = float(res.get('TotalVisibleMemorySize', 1))
            free_k = float(res.get('FreePhysicalMemory', 0))
            used_k = max(0.0, tot_k - free_k)
            mem_u_g = round(used_k / 1048576, 1)
            mem_t_g = round(tot_k / 1048576, 1)
            mem_pct = round(used_k * 100.0 / tot_k, 1) if tot_k > 0 else 0.0

            disks = []
            if csv_lines:
                reader = csv.DictReader(csv_lines)
                for r in reader:
                    if 'Caption' in r and r['Caption']:
                        disks.append({
                            'drive': r['Caption'],
                            'free_gb': float(r.get('FreeSpace', 0)) / (1024**3),
                            'total_gb': float(r.get('Size', 0)) / (1024**3),
                            'name': r.get('VolumeName', '')
                        })

            # Format primary disk & tooltip
            primary = None
            if self.server_id == '8375c':
                primary = next((d for d in disks if d['drive'].upper() == 'E:'), None)
            if not primary:
                primary = next((d for d in disks if d['drive'].upper() == 'D:'), None)
            if not primary and disks:
                primary = max(disks, key=lambda d: d['free_gb'])

            if primary:
                f_gb = primary['free_gb']
                drv = primary['drive']
                if f_gb >= 1000:
                    disk_str = f"💾 {drv} {f_gb / 1024:.2f}T"
                else:
                    disk_str = f"💾 {drv} {f_gb:.1f}G"
                disk_free_g = round(f_gb, 1)
                disk_tot_g = round(primary['total_gb'], 1)
            else:
                disk_str = "💾 -- 剩余"
                disk_free_g = 0.0
                disk_tot_g = 0.0

            tt_lines = [f"硬盘空间 ({self.name}):"]
            for d in disks:
                c = d['drive']
                fg = d['free_gb']
                tg = d['total_gb']
                pct = (fg / tg * 100) if tg > 0 else 0
                tag = " (主要数据盘)" if d == primary else ""
                vn = d.get('name', '')
                vname = f" [{vn}]" if vn else ""
                if fg >= 1000:
                    tt_lines.append(f"• {c} {fg/1024:.2f}TB / {tg/1024:.2f}TB 可用 ({pct:.1f}%){vname}{tag}")
                else:
                    tt_lines.append(f"• {c} {fg:.1f}GB / {tg:.0f}GB 可用 ({pct:.1f}%){vname}{tag}")
            disk_tooltip = "\n".join(tt_lines)

            self._last_stats.update({
                "mem_used": mem_u_g,
                "mem_total": mem_t_g,
                "mem_pct": mem_pct,
                "disk_free": disk_free_g,
                "disk_total": disk_tot_g,
                "disk_str": disk_str,
                "disk_tooltip": disk_tooltip,
            })
            self.stats_updated.emit(self.server_id, dict(self._last_stats))
        except Exception:
            pass

    def run(self):
        while self._running:
            try:
                self.status_updated.emit(self.server_id, "connecting")
                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    timeout=5,
                    banner_timeout=5,
                    auth_timeout=5
                )

                transport = self.client.get_transport()
                if transport:
                    transport.set_keepalive(15)

                self.status_updated.emit(self.server_id, "connected")
                self._last_stats["status"] = "connected"

                # Initial WMIC query
                self._query_wmic_stats()

                # Stream CPU usage with typeperf
                cmd = f'typeperf "\\Processor(_Total)\\% Processor Time" -si {self.interval}'
                stdin, stdout, stderr = self.client.exec_command(cmd, bufsize=1)

                cycle_count = 0
                while self._running:
                    line = stdout.readline()
                    if not line:
                        break

                    line_str = line.strip()
                    if not line_str or line_str.startswith('"(') or line_str.startswith('"(PDH'):
                        continue

                    try:
                        reader = csv.reader(io.StringIO(line_str))
                        row = next(reader)
                        if len(row) >= 2:
                            cpu_val = max(0.0, min(100.0, float(row[1])))
                            self.cpu_updated.emit(self.server_id, cpu_val)
                            self._last_stats["cpu"] = cpu_val
                            self.stats_updated.emit(self.server_id, dict(self._last_stats))
                    except (ValueError, IndexError):
                        continue

                    cycle_count += 1
                    # Refresh RAM and Disk every 10 samples (~20 seconds)
                    if cycle_count % 10 == 0:
                        self._query_wmic_stats()

            except Exception:
                self.status_updated.emit(self.server_id, "error")
                self._last_stats["status"] = "error"
                self._last_stats["cpu"] = -1.0
                self.cpu_updated.emit(self.server_id, -1.0)
                self.stats_updated.emit(self.server_id, dict(self._last_stats))
            finally:
                if self.client:
                    try:
                        self.client.close()
                    except Exception:
                        pass
                    self.client = None

            # Retry backoff
            for _ in range(4):
                if not self._running:
                    break
                time.sleep(1)


# Alias SingleServerWorker to SingleWindowsServerWorker for backward compatibility
SingleServerWorker = SingleWindowsServerWorker


class SingleLinuxServerWorker(QThread):
    """Background worker monitoring a Linux GPU server's CPU, Memory and Disk via SSH."""
    cpu_updated = pyqtSignal(str, float)
    stats_updated = pyqtSignal(str, dict)
    status_updated = pyqtSignal(str, str)

    def __init__(self, server_cfg: Dict[str, Any], interval: int = 3):
        super().__init__()
        self.server_cfg = server_cfg
        self.interval = max(2, interval)
        self.server_id = server_cfg.get("id")
        self.name = server_cfg.get("name", self.server_id)
        self.ip = server_cfg.get("ip")
        self.port = int(server_cfg.get("port", 22))
        self.user = server_cfg.get("user", "xutianxiao")
        self.key_path = server_cfg.get("key_path")
        self._running = True
        self.client: Optional[paramiko.SSHClient] = None
        self._last_stats: Dict[str, Any] = {
            "id": self.server_id,
            "name": self.name,
            "type": "gpu",
            "cpu": -1.0,
            "mem_used": 0.0,
            "mem_total": 0.0,
            "mem_pct": 0.0,
            "disk_free": 0.0,
            "disk_total": 0.0,
            "status": "connecting"
        }

    def stop(self):
        self._running = False
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

    def run(self):
        script = """
import os, time, shutil, json
try:
    with open("/proc/stat") as f:
        f1 = [float(x) for x in f.readline().split()[1:5]]
    time.sleep(0.3)
    with open("/proc/stat") as f:
        f2 = [float(x) for x in f.readline().split()[1:5]]
    cpu = round(100.0 * (1.0 - (f2[3]-f1[3])/(sum(f2)-sum(f1))), 1)

    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            p = line.split(":")
            if len(p)==2:
                mem[p[0].strip()] = float(p[1].split()[0])
    tot_k = mem.get("MemTotal", 1)
    avail_k = mem.get("MemAvailable", mem.get("MemFree", 0))
    used_k = tot_k - avail_k
    mem_u_g = round(used_k / 1048576, 1)
    mem_t_g = round(tot_k / 1048576, 1)
    mem_pct = round(used_k * 100.0 / tot_k, 1)

    paths = ["/", "/mnt/Data", "/mnt/Data_solid", "/data", "/home"]
    disks = []
    seen = set()
    for p in paths:
        if os.path.exists(p):
            dev = os.stat(p).st_dev
            if dev in seen:
                continue
            seen.add(dev)
            t_b, u_b, f_b = shutil.disk_usage(p)
            disks.append({
                "mount": p,
                "free_gb": round(f_b / (1024**3), 1),
                "total_gb": round(t_b / (1024**3), 1)
            })

    primary = next((d for d in disks if "Data" in d["mount"]), None)
    if not primary and disks:
        primary = disks[0]

    if primary:
        f_gb = primary["free_gb"]
        t_gb = primary["total_gb"]
        m = primary["mount"]
        prefix = "Data: " if "Data" in m else ""
        if f_gb >= 1000:
            disk_str = f"💾 {prefix}{f_gb/1024:.2f}T"
        else:
            disk_str = f"💾 {prefix}{f_gb:.1f}G"
        disk_free_g = f_gb
        disk_tot_g = t_gb
    else:
        disk_str = "💾 -- 剩余"
        disk_free_g = 0.0
        disk_tot_g = 0.0

    tt_lines = ["硬盘空间:"]
    for d in disks:
        fg = d["free_gb"]
        tg = d["total_gb"]
        pct = round(fg * 100.0 / tg, 1) if tg > 0 else 0
        tag = " (主要数据盘)" if d == primary else ""
        m_path = d["mount"]
        if fg >= 1000:
            tt_lines.append(f"• {m_path}: {fg/1024:.2f}TB / {tg/1024:.2f}TB 可用 ({pct}%){tag}")
        else:
            tt_lines.append(f"• {m_path}: {fg:.1f}GB / {tg:.0f}GB 可用 ({pct}%){tag}")
    disk_tooltip = "\\n".join(tt_lines)

    print(json.dumps({
        "cpu": cpu,
        "mem_used": mem_u_g,
        "mem_total": mem_t_g,
        "mem_pct": mem_pct,
        "disk_free": disk_free_g,
        "disk_total": disk_tot_g,
        "disk_str": disk_str,
        "disk_tooltip": disk_tooltip
    }))
except Exception as e:
    print(json.dumps({"error": str(e)}))
"""
        py_cmd = "python3 -c " + chr(39) + script.strip() + chr(39)
        while self._running:
            try:
                self.status_updated.emit(self.server_id, "connecting")
                k = paramiko.RSAKey.from_private_key_file(self.key_path)
                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.client.connect(
                    hostname=self.ip,
                    port=self.port,
                    username=self.user,
                    pkey=k,
                    timeout=4
                )

                transport = self.client.get_transport()
                if transport:
                    transport.set_keepalive(15)

                self.status_updated.emit(self.server_id, "connected")
                self._last_stats["status"] = "connected"

                while self._running:
                    stdin, stdout, stderr = self.client.exec_command(py_cmd, timeout=5)
                    out = stdout.read().decode().strip()
                    if out:
                        try:
                            d = json.loads(out)
                            if "cpu" in d:
                                cpu_val = float(d["cpu"])
                                self._last_stats.update({
                                    "cpu": cpu_val,
                                    "mem_used": float(d.get("mem_used", 0)),
                                    "mem_total": float(d.get("mem_total", 0)),
                                    "mem_pct": float(d.get("mem_pct", 0)),
                                    "disk_free": float(d.get("disk_free", 0)),
                                    "disk_total": float(d.get("disk_total", 0)),
                                    "disk_str": d.get("disk_str", ""),
                                    "disk_tooltip": d.get("disk_tooltip", ""),
                                    "status": "connected"
                                })
                                self.cpu_updated.emit(self.server_id, cpu_val)
                                self.stats_updated.emit(self.server_id, dict(self._last_stats))
                        except Exception:
                            pass

                    # Sleep between queries
                    for _ in range(self.interval * 4):
                        if not self._running:
                            break
                        self.msleep(250)

            except Exception as e:
                self.status_updated.emit(self.server_id, "error")
                self._last_stats["status"] = "error"
                self._last_stats["cpu"] = -1.0
                self.cpu_updated.emit(self.server_id, -1.0)
                self.stats_updated.emit(self.server_id, dict(self._last_stats))
            finally:
                if self.client:
                    try:
                        self.client.close()
                    except Exception:
                        pass
                    self.client = None

            # Retry backoff
            for _ in range(4):
                if not self._running:
                    break
                self.msleep(1000)


class MultiServerMonitor(QObject):
    """
    Coordinates streaming and periodic monitors for:
    1. 3 CPU servers (quad, e5, 8375c)
    2. 3 GPU servers (7号, 8号, 4号)
    Emits both real-time CPU summary (for Mini mode) and complete host stats (for Expanded mode).
    """
    servers_updated = pyqtSignal(dict)      # Backward-compatible CPU dict: {"quad": float, ..., "7": float, ...}
    host_stats_updated = pyqtSignal(dict)   # Full server dict: {sid: {cpu, mem_used, mem_total, mem_pct, disk_free, ...}}

    def __init__(self, cpu_server_list: Optional[List[Dict[str, Any]]] = None, gpu_server_list: Optional[List[Dict[str, Any]]] = None, interval: int = 2):
        super().__init__()
        self.cpu_servers = cpu_server_list or list(DEFAULT_CPU_SERVERS)
        self.gpu_servers = gpu_server_list or list(DEFAULT_GPU_SERVERS)
        self.interval = interval

        self.workers: Dict[str, QThread] = {}
        self.latest_cpu: Dict[str, float] = {
            # CPU servers
            "quad": -1.0,
            "e5": -1.0,
            "8375c": -1.0,
            # GPU servers
            "7": -1.0,
            "8": -1.0,
            "4": -1.0
        }
        self.latest_host_stats: Dict[str, Dict[str, Any]] = {}

        # Pre-populate host stats structure
        for s in self.gpu_servers:
            sid = s.get("id")
            self.latest_host_stats[sid] = {
                "id": sid, "name": s.get("name", sid), "type": "gpu",
                "cpu": -1.0, "mem_used": 0.0, "mem_total": 0.0, "mem_pct": 0.0,
                "disk_free": 0.0, "disk_total": 0.0, "status": "connecting"
            }
        for s in self.cpu_servers:
            sid = s.get("id")
            self.latest_host_stats[sid] = {
                "id": sid, "name": s.get("name", sid), "type": "cpu",
                "cpu": -1.0, "mem_used": 0.0, "mem_total": 0.0, "mem_pct": 0.0,
                "disk_free": 0.0, "disk_total": 0.0, "status": "connecting"
            }

    def start(self):
        self.stop()
        # 1. Start Windows CPU workers
        for s_cfg in self.cpu_servers:
            sid = s_cfg.get("id", s_cfg.get("name"))
            worker = SingleWindowsServerWorker(s_cfg, interval=self.interval)
            worker.cpu_updated.connect(self._on_cpu_updated)
            worker.stats_updated.connect(self._on_stats_updated)
            self.workers[sid] = worker
            worker.start()

        # 2. Start Linux GPU host workers
        for s_cfg in self.gpu_servers:
            sid = s_cfg.get("id")
            worker = SingleLinuxServerWorker(s_cfg, interval=3)
            worker.cpu_updated.connect(self._on_cpu_updated)
            worker.stats_updated.connect(self._on_stats_updated)
            self.workers[sid] = worker
            worker.start()

    def stop(self):
        for worker in self.workers.values():
            if hasattr(worker, "stop"):
                worker.stop()
            worker.wait(800)
        self.workers.clear()

    def _on_cpu_updated(self, server_id: str, cpu_val: float):
        self.latest_cpu[server_id] = cpu_val
        self.servers_updated.emit(dict(self.latest_cpu))

    def _on_stats_updated(self, server_id: str, stats: dict):
        self.latest_host_stats[server_id] = stats
        self.host_stats_updated.emit(dict(self.latest_host_stats))
