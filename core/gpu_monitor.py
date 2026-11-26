"""
GPU Server Monitor.
Reads live GPU metrics and historical usage from a local SQLite database.
Supports multi-server metrics, individual GPU card statistics, and mini-capsule quick stats.
"""

import os
import sqlite3
import datetime
import json
import time
import threading
from typing import Dict, Any, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor
import paramiko
from PyQt5.QtCore import QObject, QThread, pyqtSignal

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gpu_history.db")

DEFAULT_COLLECTOR_SERVERS = []

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


def _build_live_data(points: List[Dict[str, Any]], db_path: str) -> Dict[str, Any]:
    """Convert collected GPU points into the payload consumed by GPUView."""
    servers: Dict[str, Dict[str, Any]] = {}
    latest_time = ""

    for point in points:
        ip = point.get("ip", "")
        sid = get_server_id(ip)
        if sid not in ("8", "7"):
            continue

        raw_model = point.get("gpu_name") or "GPU"
        update_time = point.get("update_time") or ""
        if str(update_time) > latest_time:
            latest_time = str(update_time)

        if sid not in servers:
            servers[sid] = {
                "sid": sid,
                "ip": ip,
                "model": clean_gpu_name(raw_model),
                "cards": [],
                "max_vram_pct": 0.0,
                "update_time": update_time,
            }

        mem_used = int(point.get("memory_used") or 0)
        mem_total = int(point.get("memory_total") or 1)
        vram_pct = round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0.0
        user = point.get("top_user") or "Idle"
        is_busy = user not in ("Idle", "Unknown", None, "")
        card = {
            "index": str(point.get("gpu_index", "0")),
            "name": clean_gpu_name(raw_model),
            "memory_used": mem_used,
            "memory_total": mem_total,
            "memory_used_gb": round(mem_used / 1024, 1),
            "memory_total_gb": round(mem_total / 1024, 0),
            "vram_pct": vram_pct,
            "utilization": int(point.get("utilization") or 0),
            "power_draw": str(point.get("power_draw") or "0"),
            "power_limit": str(point.get("power_limit") or "0"),
            "user": user,
            "display_user": get_cn_name(user),
            "is_busy": is_busy,
        }
        servers[sid]["cards"].append(card)

    for server in servers.values():
        if server["cards"]:
            server["max_vram_pct"] = max(card["vram_pct"] for card in server["cards"])

    five_cards = []
    tt_lines = ["GPU 显存占用 (7号 L40S x3 · 8号 A100 x2):"]
    for target_sid in ("7", "8"):
        server = servers.get(target_sid)
        if not server:
            continue
        for card in server["cards"]:
            value = card["vram_pct"]
            color = get_hex_for_gpu_vram(value)
            user_text = f"[{card['display_user']}]" if card["is_busy"] else "[空闲]"
            description = (
                f"{target_sid}号·{server['model']}[{card['index']}]: "
                f"{value:.0f}% ({card['memory_used_gb']}/{card['memory_total_gb']}G, "
                f"{card['power_draw']}/{card['power_limit']}W) {user_text}"
            )
            tt_lines.append(f"• {description}")
            five_cards.append({
                "sid": target_sid,
                "index": card["index"],
                "label": f"{target_sid}-{card['index']}",
                "model": server["model"],
                "pct_str": f"{int(round(value))}%",
                "val": value,
                "color": color,
                "tooltip": description,
            })

    if latest_time:
        time_str = latest_time.split(" ")[-1] if " " in latest_time else latest_time
        try:
            latest_dt = datetime.datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")
            if (datetime.datetime.now() - latest_dt).total_seconds() > 60:
                time_str = f"{time_str} (过期)"
        except Exception:
            pass
    else:
        time_str = "--:--:--"

    return {
        "success": True,
        "servers": servers,
        "server_order": [sid for sid in ("8", "7") if sid in servers],
        "five_cards": five_cards,
        "five_cards_tt": "\n".join(tt_lines),
        "db_size_mb": get_db_size_mb(db_path),
        "last_update": time_str,
    }


class GPULiveWorker(QThread):
    """Background worker for a one-shot or periodic latest-state query."""
    data_ready = pyqtSignal(dict)

    def __init__(self, db_path: str = DB_FILE, interval: int = 4, single_shot: bool = False):
        super().__init__()
        self.db_path = db_path
        self.interval = max(2, interval)
        self.single_shot = single_shot
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            data = self._query_latest()
            if self._running:
                self.data_ready.emit(data)

            if self.single_shot:
                break
            
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
            with sqlite3.connect(self.db_path, timeout=3) as conn:
                rows = conn.execute(
                    """
                    SELECT ip, gpu_index, gpu_name, memory_used, memory_total,
                           utilization, power_draw, power_limit, top_user, update_time
                    FROM gpu_status_latest
                    ORDER BY ip DESC, CAST(gpu_index AS INTEGER) ASC
                    """
                ).fetchall()
            points = [
                {
                    "ip": row[0],
                    "gpu_index": row[1],
                    "gpu_name": row[2],
                    "memory_used": row[3],
                    "memory_total": row[4],
                    "utilization": row[5],
                    "power_draw": row[6],
                    "power_limit": row[7],
                    "top_user": row[8],
                    "update_time": row[9],
                }
                for row in rows
            ]
            return _build_live_data(points, self.db_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def build_from_points(points: List[Dict[str, Any]], db_path: str) -> Dict[str, Any]:
        """Build the UI payload directly from freshly collected remote points."""
        return _build_live_data(points, db_path)


class GPUHistoryWorker(QThread):
    """Background worker fetching historical GPU occupancy intervals."""
    history_ready = pyqtSignal(list)

    def __init__(self, days: int = 1, db_path: str = DB_FILE):
        super().__init__()
        self.days = days
        self.db_path = db_path

    def run(self):
        intervals = self._compute_intervals()
        if not self.isInterruptionRequested():
            self.history_ready.emit(intervals)

    def _compute_intervals(self) -> List[Dict[str, Any]]:
        """Compute occupancy intervals for past N days."""
        if not os.path.exists(self.db_path):
            return []

        try:
            thresh = (datetime.datetime.now() - datetime.timedelta(days=self.days)).strftime("%Y-%m-%d %H:%M:%S")
            intervals: List[Dict[str, Any]] = []
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                cursor = conn.execute(
                    """
                    SELECT timestamp, ip, gpu_index, gpu_name, top_user
                    FROM gpu_history
                    WHERE timestamp > ?
                    ORDER BY ip DESC, CAST(gpu_index AS INTEGER) ASC, timestamp ASC
                    """,
                    (thresh,),
                )

                current_key = None
                current_model = "GPU"
                current_sid = ""
                current_gpu_idx = ""
                start_dt = None
                last_dt = None
                current_user = None

                def flush_interval():
                    if start_dt is None or last_dt is None:
                        return
                    if current_user in ("Idle", "Unknown", None, ""):
                        return
                    finish_dt = last_dt + datetime.timedelta(minutes=1)
                    duration_min = int(round((finish_dt - start_dt).total_seconds() / 60))
                    intervals.append({
                        "tag": f"{current_sid}号 {current_model}",
                        "task": f"{current_model} [{current_gpu_idx}]",
                        "sid": current_sid,
                        "gpu_index": current_gpu_idx,
                        "model": current_model,
                        "user": get_cn_name(current_user),
                        "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                        "finish": finish_dt.strftime("%Y-%m-%d %H:%M"),
                        "start_dt": start_dt,
                        "finish_dt": finish_dt,
                        "duration_min": max(1, duration_min),
                    })

                for row in cursor:
                    if self.isInterruptionRequested():
                        return []
                    timestamp, ip, gpu_idx, raw_model, row_user = row
                    sid = get_server_id(ip)
                    if sid not in ("8", "7"):
                        continue
                    try:
                        timestamp_dt = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    except (TypeError, ValueError):
                        continue

                    key = (ip, gpu_idx)
                    if key != current_key:
                        flush_interval()
                        current_key = key
                        current_model = clean_gpu_name(raw_model or "GPU")
                        current_sid = sid
                        current_gpu_idx = str(gpu_idx)
                        start_dt = timestamp_dt
                        last_dt = timestamp_dt
                        current_user = row_user
                        continue

                    gap_seconds = (timestamp_dt - last_dt).total_seconds()
                    if gap_seconds > 130 or row_user != current_user:
                        flush_interval()
                        start_dt = timestamp_dt
                        current_user = row_user
                    last_dt = timestamp_dt

                flush_interval()

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
    collected = pyqtSignal(dict)

    def __init__(self, db_path: str = DB_FILE, interval: int = 4, servers: Optional[List[Dict[str, Any]]] = None):
        super().__init__()
        self.db_path = db_path
        self.interval = max(3, interval)
        self.servers = list(DEFAULT_COLLECTOR_SERVERS) if servers is None else servers
        self._running = True
        self._last_history_time = 0.0
        self._client_lock = threading.Lock()
        self._active_clients: Set[paramiko.SSHClient] = set()
        self._server_clients = {}

    def stop(self):
        self._running = False
        with self._client_lock:
            clients = list(self._active_clients)
            self._active_clients.clear()
            self._server_clients.clear()
        for client in clients:
            try:
                client.close()
            except Exception:
                pass

    def _fetch_server(self, server: Dict[str, Any]) -> List[Dict[str, Any]]:
        ip = server["ip"]
        port = server.get("port", 22)
        user = server.get("user", "")
        key_path = os.path.expanduser(server.get("key_path") or "")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_points = []

        client = None
        server_key = (ip, port, user, key_path)
        try:
            if not self._running or not key_path or not os.path.exists(key_path):
                return []
            with self._client_lock:
                client = self._server_clients.get(server_key)
            transport = client.get_transport() if client is not None else None
            if transport is None or not transport.is_active() or not transport.is_authenticated():
                if client is not None:
                    client.close()
                    with self._client_lock:
                        self._active_clients.discard(client)
                        self._server_clients.pop(server_key, None)
                key = paramiko.RSAKey.from_private_key_file(key_path)
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                with self._client_lock:
                    if not self._running:
                        client.close()
                        return []
                    self._active_clients.add(client)
                    self._server_clients[server_key] = client
                client.connect(
                    ip, port=port, username=user, pkey=key,
                    timeout=2.5, banner_timeout=2.5, auth_timeout=2.5,
                )
                client.get_transport().set_keepalive(30)

            # 1. Query GPU basic metrics
            smi_cmd = "nvidia-smi --query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu,power.draw,power.limit --format=csv,noheader,nounits"
            _, stdout, _ = client.exec_command(smi_cmd, timeout=3)
            gpu_raw = stdout.read().decode("utf-8", errors="ignore").strip()

            # 2. Query compute processes with process_name
            proc_cmd = "nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv,noheader,nounits"
            _, stdout, _ = client.exec_command(proc_cmd, timeout=3)
            proc_raw = stdout.read().decode("utf-8", errors="ignore").strip()

            uuid_user_map = {}
            processes = []
            for line in proc_raw.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) < 4 or not parts[0].isdigit():
                    continue
                try:
                    uses_memory = float(parts[2]) > 1024
                except ValueError:
                    continue
                if parts[1] != "[Not Found]" and uses_memory:
                    processes.append((parts[0], parts[3]))
            if processes:
                pids = ",".join(dict.fromkeys(pid for pid, _ in processes))
                try:
                    _, stdout, _ = client.exec_command(f"ps -p {pids} -o pid=,user=", timeout=1.5)
                    owners = {}
                    for line in stdout.read().decode("utf-8", errors="ignore").splitlines():
                        parts = line.split()
                        if len(parts) == 2:
                            owners[parts[0]] = parts[1]
                    for pid, gpu_uuid in processes:
                        if pid in owners:
                            uuid_user_map[gpu_uuid] = owners[pid]
                except Exception:
                    pass

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
            if client is not None:
                with self._client_lock:
                    self._active_clients.discard(client)
                    if self._server_clients.get(server_key) is client:
                        self._server_clients.pop(server_key, None)
                try:
                    client.close()
                except Exception:
                    pass

        return data_points

    def run(self):
        self._init_db()
        executor = ThreadPoolExecutor(max_workers=max(1, len(self.servers)))
        try:
            while self._running:
                start_ts = time.time()
                all_data = []

                try:
                    for res in executor.map(self._fetch_server, self.servers):
                        all_data.extend(res)
                except Exception:
                    for server in self.servers:
                        if not self._running:
                            break
                        all_data.extend(self._fetch_server(server))

                if all_data and self._running:
                    self._write_points(all_data)
                    self.collected.emit(GPULiveWorker.build_from_points(all_data, self.db_path))

                elapsed = time.time() - start_ts
                sleep_needed = max(0.5, self.interval - elapsed)
                for _ in range(int(sleep_needed * 4)):
                    if not self._running:
                        break
                    self.msleep(250)
        finally:
            executor.shutdown(wait=True)
            self.stop()

    def _write_points(self, all_data: List[Dict[str, Any]]):
        """Persist one collection round without retaining any history rows in memory."""
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                latest_tuples = [
                    (
                        item["ip"],
                        item["gpu_index"],
                        item["gpu_name"],
                        item["memory_used"],
                        item["memory_total"],
                        item["utilization"],
                        item["power_draw"],
                        item["power_limit"],
                        item["top_user"],
                        item["update_time"],
                    )
                    for item in all_data
                ]
                conn.executemany(
                    """
                    INSERT INTO gpu_status_latest(
                        ip, gpu_index, gpu_name, memory_used, memory_total,
                        utilization, power_draw, power_limit, top_user, update_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ip, gpu_index) DO UPDATE SET
                        gpu_name = excluded.gpu_name,
                        memory_used = excluded.memory_used,
                        memory_total = excluded.memory_total,
                        utilization = excluded.utilization,
                        power_draw = excluded.power_draw,
                        power_limit = excluded.power_limit,
                        top_user = excluded.top_user,
                        update_time = excluded.update_time
                    """,
                    latest_tuples,
                )

                now_ts = time.time()
                if now_ts - self._last_history_time >= 60:
                    hist_tuples = [
                        (
                            item["update_time"],
                            item["ip"],
                            item["gpu_index"],
                            item["gpu_name"],
                            item["memory_used"],
                            item["memory_total"],
                            item["utilization"],
                            item["power_draw"],
                            item["power_limit"],
                            item["top_user"],
                        )
                        for item in all_data
                    ]
                    conn.executemany(
                        "INSERT INTO gpu_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                        hist_tuples,
                    )
                    self._last_history_time = now_ts
        except Exception:
            pass

    def _init_db(self):
        try:
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if not os.path.isdir(db_dir):
                return
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute('''CREATE TABLE IF NOT EXISTS gpu_status_latest
                             (ip TEXT, gpu_index TEXT, gpu_name TEXT,
                              memory_used INTEGER, memory_total INTEGER,
                              utilization INTEGER, power_draw TEXT, power_limit TEXT, top_user TEXT,
                              update_time TEXT,
                              PRIMARY KEY (ip, gpu_index))''')
                conn.execute('''CREATE TABLE IF NOT EXISTS gpu_history
                             (timestamp TEXT, ip TEXT, gpu_index TEXT, gpu_name TEXT,
                              memory_used INTEGER, memory_total INTEGER,
                              utilization INTEGER, power_draw TEXT, power_limit TEXT, top_user TEXT)''')
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_gpu_history_ts "
                    "ON gpu_history(timestamp)"
                )
                conn.execute("DROP INDEX IF EXISTS idx_gpu_history_timestamp")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_gpu_history_device_time "
                    "ON gpu_history(ip, gpu_index, timestamp)"
                )
        except Exception:
            pass


class GPUMonitor(QObject):
    """Coordinates real-time GPU metrics, background collection, and history queries."""
    realtime_updated = pyqtSignal(dict)
    history_updated = pyqtSignal(list)

    def __init__(self, db_path: str = DB_FILE, interval: int = 4, servers: Optional[List[Dict[str, Any]]] = None):
        super().__init__()
        self.db_path = db_path
        self.interval = interval
        self.servers = servers
        self.collector_worker: Optional[GPUCollectorWorker] = None
        self.live_worker: Optional[GPULiveWorker] = None
        self.history_worker: Optional[GPUHistoryWorker] = None
        self.latest_data: Dict[str, Any] = {}

    def start(self):
        """Start real-time monitoring and background collection worker."""
        self.stop()
        if self.collector_worker is not None:
            return
        self.collector_worker = GPUCollectorWorker(self.db_path, interval=4, servers=self.servers)
        self.collector_worker.collected.connect(self._on_collector_data)
        self.collector_worker.start()
        self.refresh_live()

    def stop(self):
        """Stop worker threads."""
        workers = [
            ("collector_worker", self.collector_worker),
            ("live_worker", self.live_worker),
            ("history_worker", self.history_worker),
        ]
        workers = [(name, worker) for name, worker in workers if worker is not None]

        for name, worker in workers:
            try:
                if name == "history_worker":
                    worker.requestInterruption()
                else:
                    worker.stop()
            except RuntimeError:
                pass

        deadline = time.monotonic() + 5.0
        for name, worker in workers:
            try:
                remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                if remaining_ms:
                    worker.wait(remaining_ms)
                running = worker.isRunning()
            except RuntimeError:
                running = False
            if not running:
                setattr(self, name, None)

    def refresh_live(self):
        """Read the current SQLite snapshot once without starting a polling loop."""
        if self.live_worker:
            try:
                if self.live_worker.isRunning():
                    return
            except RuntimeError:
                self.live_worker = None

        worker = GPULiveWorker(self.db_path, self.interval, single_shot=True)
        self.live_worker = worker
        worker.data_ready.connect(self._on_live_data)
        worker.finished.connect(self._on_live_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def fetch_history_async(self, days: int = 1):
        """Fetch history occupancy intervals asynchronously."""
        if self.history_worker:
            try:
                if self.history_worker.isRunning():
                    return
            except RuntimeError:
                self.history_worker = None

        worker = GPUHistoryWorker(days=days, db_path=self.db_path)
        self.history_worker = worker
        worker.history_ready.connect(self._on_history_data)
        worker.finished.connect(self._on_history_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_collector_data(self, data: Dict[str, Any]):
        """Render the collector payload directly, avoiding a duplicate SQLite read."""
        if data.get("success"):
            self._on_live_data(data)

    def _on_live_data(self, data: Dict[str, Any]):
        self.latest_data = data
        self.realtime_updated.emit(data)

    def _on_history_data(self, intervals: List[Dict[str, Any]]):
        self.history_updated.emit(intervals)

    def _on_live_finished(self):
        worker = self.sender()
        if worker is self.live_worker:
            self.live_worker = None

    def _on_history_finished(self):
        worker = self.sender()
        if worker is self.history_worker:
            self.history_worker = None
