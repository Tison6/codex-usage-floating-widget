"""
GPU Server Monitor.
Reads live GPU metrics and historical usage directly from D:/gpu_history.db.
Supports multi-server metrics, individual GPU card statistics, and mini-capsule quick stats.
"""

import os
import sqlite3
import datetime
import json
import time
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import paramiko
from PyQt5.QtCore import QObject, QThread, pyqtSignal

DB_FILE = r"D:/gpu_history.db"

DEFAULT_COLLECTOR_SERVERS = [
    {"ip": "192.168.120.7", "port": 22, "user": "xutianxiao", "key_path": r"C:/Users/xtx/.ssh/id_rsa_xtx"},
    {"ip": "192.168.120.8", "port": 22, "user": "xutianxiao", "key_path": r"C:/Users/xtx/.ssh/id_rsa_xtx"},
    {"ip": "192.168.120.4", "port": 22, "user": "xutianxiao", "key_path": r"C:/Users/xtx/.ssh/id_rsa_stu"},
]

def _load_user_mapping() -> Dict[str, str]:
    """Load local user mapping from data/user_mapping.json if present (gitignored)."""
    mapping_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "user_mapping.json")
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

USER_MAPPING = _load_user_mapping()


def clean_gpu_name(raw_name: str) -> str:
    """Clean redundant NVIDIA prefixes/suffixes."""
    name = raw_name.replace("NVIDIA", "").replace("GeForce", "").replace("RTX", "")
    for r in ["PCIe", "80GB", "24GB", "12GB"]:
        name = name.replace(r, "")
    return name.replace("TITAN", "Titan").strip()


def get_cn_name(pinyin: str) -> str:
    """Convert pinyin username to display name using local USER_MAPPING."""
    if not pinyin or pinyin in ("Idle", "Unknown", "None"):
        return "Idle"
    if str(pinyin).startswith("PID"):
        return pinyin
    return USER_MAPPING.get(pinyin, pinyin)


def get_hex_for_gpu_vram(val: float) -> str:
    """
    Return theme color based on GPU VRAM percentage:
    < 10%: Green (#10B981)
    10% <= val < 30%: Orange (#F59E0B)
    >= 30%: Red (#EF4444)
    < 0: Slate Gray (#64748B)
    """
    if val < 0:
        return "#64748B"
    elif val < 10:
        return "#10B981"
    elif val < 30:
        return "#F59E0B"
    else:
        return "#EF4444"


def get_db_size_mb(path: str = DB_FILE) -> str:
    """Return DB file size in MB."""
    try:
        if os.path.exists(path):
            return f"{os.path.getsize(path) / (1024 * 1024):.1f}"
    except Exception:
        pass
    return "0.0"


def get_server_id(ip: str) -> str:
    """Extract server number or identifier from IP / hostname."""
    if "." in ip:
        return ip.split(".")[-1]
    return ip


class GPULiveWorker(QThread):
    """Background worker continuously querying gpu_status_latest table."""
    data_ready = pyqtSignal(dict)

    def __init__(self, db_path: str = DB_FILE, interval: int = 4):
        super().__init__()
        self.db_path = db_path
        self.interval = max(2, interval)
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            data = self._query_latest()
            if self._running:
                self.data_ready.emit(data)
            
            # Non-blocking sleep in chunks
            for _ in range(self.interval * 4):
                if not self._running:
                    break
                self.msleep(250)

    def _query_latest(self) -> Dict[str, Any]:
        """Query gpu_status_latest from sqlite."""
        if not os.path.exists(self.db_path):
            return {"success": False, "error": f"Database file not found: {self.db_path}"}

        try:
            conn = sqlite3.connect(self.db_path, timeout=3)
            cursor = conn.cursor()
            query = """
            SELECT ip, gpu_index, gpu_name, memory_used, memory_total,
                   utilization, power_draw, power_limit, top_user, update_time
            FROM gpu_status_latest
            ORDER BY ip DESC, cast(gpu_index as integer) ASC
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            servers: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                ip, idx, raw_model, mem_u, mem_t, util, p_draw, p_lim, user, t = r
                sid = get_server_id(ip)
                if sid not in ("8", "7"):
                    continue

                if sid not in servers:
                    servers[sid] = {
                        "sid": sid,
                        "ip": ip,
                        "model": clean_gpu_name(raw_model),
                        "cards": [],
                        "max_vram_pct": 0.0,
                        "update_time": t
                    }

                mem_u_val = int(mem_u) if mem_u is not None else 0
                mem_t_val = int(mem_t) if mem_t is not None else 1
                vram_pct = round(mem_u_val / mem_t_val * 100, 1) if mem_t_val > 0 else 0.0
                is_busy = user not in ("Idle", "Unknown", None, "")

                servers[sid]["cards"].append({
                    "index": str(idx),
                    "name": clean_gpu_name(raw_model),
                    "memory_used": mem_u_val,
                    "memory_total": mem_t_val,
                    "memory_used_gb": round(mem_u_val / 1024, 1),
                    "memory_total_gb": round(mem_t_val / 1024, 0),
                    "vram_pct": vram_pct,
                    "utilization": int(util) if util is not None else 0,
                    "power_draw": str(p_draw or "0"),
                    "power_limit": str(p_lim or "0"),
                    "user": user or "Idle",
                    "display_user": get_cn_name(user),
                    "is_busy": is_busy
                })

            # Calculate server max VRAM %
            for sid, sinfo in servers.items():
                if sinfo["cards"]:
                    sinfo["max_vram_pct"] = max(c["vram_pct"] for c in sinfo["cards"])
                else:
                    sinfo["max_vram_pct"] = 0.0

            server_order = [s for s in ["8", "7"] if s in servers]

            # Build 5 individual GPU cards list (7号 3 cards + 8号 2 cards)
            five_cards = []
            tt_lines = ["GPU 显存占用 (7号 L40S x3 · 8号 A100 x2):"]

            for target_sid in ["7", "8"]:
                s = servers.get(target_sid)
                if s:
                    for c in s["cards"]:
                        val = c["vram_pct"]
                        col = get_hex_for_gpu_vram(val)
                        u_str = f"[{c['display_user']}]" if c["is_busy"] else "[空闲]"
                        desc = f"{target_sid}号·{s['model']}[{c['index']}]: {val:.0f}% ({c['memory_used_gb']}/{c['memory_total_gb']}G, {c['power_draw']}/{c['power_limit']}W) {u_str}"
                        tt_lines.append(f"• {desc}")
                        five_cards.append({
                            "sid": target_sid,
                            "index": c["index"],
                            "label": f"{target_sid}-{c['index']}",
                            "model": s["model"],
                            "pct_str": f"{int(round(val))}%",
                            "val": val,
                            "color": col,
                            "tooltip": desc
                        })

            latest_time = ""
            for r in rows:
                t = r[9]
                if t and str(t) > latest_time:
                    latest_time = str(t)

            if latest_time:
                time_str = latest_time.split(" ")[-1] if " " in latest_time else latest_time
                try:
                    dt = datetime.datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")
                    if (datetime.datetime.now() - dt).total_seconds() > 60:
                        time_str = f"{time_str} (过期)"
                except Exception:
                    pass
            else:
                time_str = "--:--:--"

            return {
                "success": True,
                "servers": servers,
                "server_order": server_order,
                "five_cards": five_cards,
                "five_cards_tt": "\n".join(tt_lines),
                "db_size_mb": get_db_size_mb(self.db_path),
                "last_update": time_str
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class GPUHistoryWorker(QThread):
    """Background worker fetching historical GPU occupancy intervals."""
    history_ready = pyqtSignal(list)

    def __init__(self, days: int = 1, db_path: str = DB_FILE):
        super().__init__()
        self.days = days
        self.db_path = db_path

    def run(self):
        intervals = self._compute_intervals()
        self.history_ready.emit(intervals)

    def _compute_intervals(self) -> List[Dict[str, Any]]:
        """Compute occupancy intervals for past N days."""
        if not os.path.exists(self.db_path):
            return []

        try:
            thresh = (datetime.datetime.now() - datetime.timedelta(days=self.days)).strftime("%Y-%m-%d %H:%M:%S")
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()
            query = """
            SELECT timestamp, ip, gpu_index, gpu_name, top_user
            FROM gpu_history
            WHERE timestamp > ?
            ORDER BY ip DESC, cast(gpu_index as integer) ASC, timestamp ASC
            """
            cursor.execute(query, (thresh,))
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return []

            # Group rows by (ip, gpu_index)
            from collections import defaultdict
            grouped = defaultdict(list)
            for r in rows:
                sid = get_server_id(r[1])
                if sid in ("8", "7"):
                    grouped[(r[1], r[2])].append(r)

            intervals: List[Dict[str, Any]] = []
            for (ip, gpu_idx), group in grouped.items():
                if not group:
                    continue

                raw_model = group[0][3] or "GPU"
                gpu_model = clean_gpu_name(raw_model)
                sid = get_server_id(ip)
                server_tag = f"{sid}号 {gpu_model}"
                gpu_label = f"{gpu_model} [{gpu_idx}]"

                start_dt = datetime.datetime.strptime(group[0][0], "%Y-%m-%d %H:%M:%S")
                last_dt = start_dt
                curr_user = group[0][4]

                for i in range(1, len(group)):
                    row = group[i]
                    ts = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                    row_user = row[4]
                    diff_sec = (ts - last_dt).total_seconds()

                    is_active = curr_user not in ("Idle", "Unknown", None, "")

                    if diff_sec > 130 or row_user != curr_user:
                        if is_active:
                            finish_dt = last_dt + datetime.timedelta(minutes=1)
                            dur_min = int(round((finish_dt - start_dt).total_seconds() / 60))
                            intervals.append({
                                "tag": server_tag,
                                "task": gpu_label,
                                "sid": sid,
                                "gpu_index": gpu_idx,
                                "model": gpu_model,
                                "user": get_cn_name(curr_user),
                                "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                                "finish": finish_dt.strftime("%Y-%m-%d %H:%M"),
                                "start_dt": start_dt,
                                "finish_dt": finish_dt,
                                "duration_min": max(1, dur_min)
                            })
                        start_dt = ts
                        curr_user = row_user
                    last_dt = ts

                is_active = curr_user not in ("Idle", "Unknown", None, "")
                if is_active:
                    finish_dt = last_dt + datetime.timedelta(minutes=1)
                    dur_min = int(round((finish_dt - start_dt).total_seconds() / 60))
                    intervals.append({
                        "tag": server_tag,
                        "task": gpu_label,
                        "sid": sid,
                        "gpu_index": gpu_idx,
                        "model": gpu_model,
                        "user": get_cn_name(curr_user),
                        "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                        "finish": finish_dt.strftime("%Y-%m-%d %H:%M"),
                        "start_dt": start_dt,
                        "finish_dt": finish_dt,
                        "duration_min": max(1, dur_min)
                    })

            # Sort intervals descending by finish time
            intervals.sort(key=lambda x: x["finish_dt"], reverse=True)
            return intervals

        except Exception:
            return []


class GPUCollectorWorker(QThread):
    """
    Background worker periodically querying remote GPU servers via SSH,
    parsing live GPU and process metrics, and writing directly to D:/gpu_history.db.
    Ensures the floating widget has 100% live GPU metrics without relying on external scripts.
    """
    collected = pyqtSignal()

    def __init__(self, db_path: str = DB_FILE, interval: int = 4, servers: Optional[List[Dict[str, Any]]] = None):
        super().__init__()
        self.db_path = db_path
        self.interval = max(3, interval)
        self.servers = servers or DEFAULT_COLLECTOR_SERVERS
        self._running = True
        self._last_history_time = 0.0

    def stop(self):
        self._running = False

    def _fetch_server(self, server: Dict[str, Any]) -> List[Dict[str, Any]]:
        ip = server["ip"]
        port = server.get("port", 22)
        user = server.get("user", "xutianxiao")
        key_path = server.get("key_path")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_points = []

        try:
            if not os.path.exists(key_path):
                return []
            k = paramiko.RSAKey.from_private_key_file(key_path)
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(ip, port=port, username=user, pkey=k, timeout=2.5, banner_timeout=2.5, auth_timeout=2.5)

            # 1. Query GPU basic metrics
            smi_cmd = "nvidia-smi --query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu,power.draw,power.limit --format=csv,noheader,nounits"
            _, stdout, _ = c.exec_command(smi_cmd, timeout=3)
            gpu_raw = stdout.read().decode("utf-8", errors="ignore").strip()

            # 2. Query compute processes with process_name
            proc_cmd = "nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv,noheader,nounits"
            _, stdout, _ = c.exec_command(proc_cmd, timeout=3)
            proc_raw = stdout.read().decode("utf-8", errors="ignore").strip()

            uuid_user_map = {}
            if proc_raw:
                for line in proc_raw.splitlines():
                    if not line.strip():
                        continue
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 4:
                        pid = parts[0]
                        pname = parts[1]
                        try:
                            mem_used_proc = float(parts[2])
                        except Exception:
                            mem_used_proc = 0.0
                        g_uuid = parts[3]

                        if pname != "[Not Found]" and mem_used_proc > 1024:
                            try:
                                _, out_u, _ = c.exec_command(f"ps -p {pid} -o user=", timeout=1.5)
                                u_str = out_u.read().decode("utf-8", errors="ignore").strip()
                                if u_str:
                                    uuid_user_map[g_uuid] = u_str
                            except Exception:
                                pass

            c.close()

            if gpu_raw:
                for line in gpu_raw.splitlines():
                    if not line.strip():
                        continue
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 8:
                        try:
                            g_idx = parts[0]
                            g_uuid = parts[1]
                            g_name = parts[2].replace("NVIDIA ", "").replace("GeForce ", "").replace("RTX ", "").strip()
                            mem_used = int(float(parts[3]))
                            mem_total = int(float(parts[4]))
                            util = int(float(parts[5]))
                            power_draw = str(int(float(parts[6])))
                            power_limit = str(int(float(parts[7])))

                            user_from_map = uuid_user_map.get(g_uuid)
                            if user_from_map:
                                top_user = user_from_map
                            elif util > 15 or mem_used > 5120:
                                top_user = "Busy"
                            else:
                                top_user = "Idle"

                            data_points.append({
                                "ip": ip,
                                "gpu_index": g_idx,
                                "gpu_name": g_name,
                                "memory_used": mem_used,
                                "memory_total": mem_total,
                                "utilization": util,
                                "power_draw": power_draw,
                                "power_limit": power_limit,
                                "top_user": top_user,
                                "update_time": current_time
                            })
                        except Exception:
                            pass
        except Exception:
            pass

        return data_points

    def run(self):
        self._init_db()

        while self._running:
            start_ts = time.time()
            all_data = []

            try:
                with ThreadPoolExecutor(max_workers=len(self.servers)) as executor:
                    results = executor.map(self._fetch_server, self.servers)
                    for res in results:
                        all_data.extend(res)
            except Exception:
                for s in self.servers:
                    all_data.extend(self._fetch_server(s))

            if all_data and self._running:
                try:
                    conn = sqlite3.connect(self.db_path, timeout=5)
                    c = conn.cursor()

                    latest_tuples = [
                        (d["ip"], d["gpu_index"], d["gpu_name"], d["memory_used"], d["memory_total"],
                         d["utilization"], d["power_draw"], d["power_limit"], d["top_user"], d["update_time"])
                        for d in all_data
                    ]
                    c.executemany("REPLACE INTO gpu_status_latest VALUES (?,?,?,?,?,?,?,?,?,?)", latest_tuples)

                    now_ts = time.time()
                    if now_ts - self._last_history_time >= 60:
                        hist_tuples = [
                            (d["update_time"], d["ip"], d["gpu_index"], d["gpu_name"],
                             d["memory_used"], d["memory_total"], d["utilization"],
                             d["power_draw"], d["power_limit"], d["top_user"])
                            for d in all_data
                        ]
                        c.executemany("INSERT INTO gpu_history VALUES (?,?,?,?,?,?,?,?,?,?)", hist_tuples)
                        self._last_history_time = now_ts

                    conn.commit()
                    conn.close()
                    self.collected.emit()
                except Exception:
                    pass

            elapsed = time.time() - start_ts
            sleep_needed = max(0.5, self.interval - elapsed)
            for _ in range(int(sleep_needed * 4)):
                if not self._running:
                    break
                self.msleep(250)

    def _init_db(self):
        try:
            if not os.path.exists(os.path.dirname(self.db_path)):
                return
            conn = sqlite3.connect(self.db_path, timeout=5)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS gpu_status_latest
                         (ip TEXT, gpu_index TEXT, gpu_name TEXT,
                          memory_used INTEGER, memory_total INTEGER, 
                          utilization INTEGER, power_draw TEXT, power_limit TEXT, top_user TEXT,
                          update_time TEXT,
                          PRIMARY KEY (ip, gpu_index))''')
            c.execute('''CREATE TABLE IF NOT EXISTS gpu_history
                         (timestamp TEXT, ip TEXT, gpu_index TEXT, gpu_name TEXT,
                          memory_used INTEGER, memory_total INTEGER, 
                          utilization INTEGER, power_draw TEXT, power_limit TEXT, top_user TEXT)''')
            conn.commit()
            conn.close()
        except Exception:
            pass


class GPUMonitor(QObject):
    """Coordinates real-time GPU metrics, background collection, and history queries."""
    realtime_updated = pyqtSignal(dict)
    history_updated = pyqtSignal(list)

    def __init__(self, db_path: str = DB_FILE, interval: int = 4):
        super().__init__()
        self.db_path = db_path
        self.interval = interval
        self.collector_worker: Optional[GPUCollectorWorker] = None
        self.live_worker: Optional[GPULiveWorker] = None
        self.history_worker: Optional[GPUHistoryWorker] = None
        self.latest_data: Dict[str, Any] = {}

    def start(self):
        """Start real-time monitoring and background collection worker."""
        self.stop()
        self.collector_worker = GPUCollectorWorker(self.db_path, interval=4)
        self.collector_worker.collected.connect(self._on_collector_done)
        self.collector_worker.start()

        self.live_worker = GPULiveWorker(self.db_path, self.interval)
        self.live_worker.data_ready.connect(self._on_live_data)
        self.live_worker.start()

    def stop(self):
        """Stop worker threads."""
        if self.collector_worker:
            self.collector_worker.stop()
            self.collector_worker.wait(1000)
            self.collector_worker = None
        if self.live_worker:
            self.live_worker.stop()
            self.live_worker.wait(1000)
            self.live_worker = None
        if self.history_worker:
            self.history_worker.wait(500)
            self.history_worker = None

    def fetch_history_async(self, days: int = 1):
        """Fetch history occupancy intervals asynchronously."""
        if self.history_worker and self.history_worker.isRunning():
            return
        self.history_worker = GPUHistoryWorker(days=days, db_path=self.db_path)
        self.history_worker.history_ready.connect(self._on_history_data)
        self.history_worker.start()

    def _on_collector_done(self):
        if self.live_worker:
            data = self.live_worker._query_latest()
            if data.get("success"):
                self._on_live_data(data)

    def _on_live_data(self, data: Dict[str, Any]):
        self.latest_data = data
        self.realtime_updated.emit(data)

    def _on_history_data(self, intervals: List[Dict[str, Any]]):
        self.history_updated.emit(intervals)
