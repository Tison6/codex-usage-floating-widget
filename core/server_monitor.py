"""
Server CPU Utilization Monitor via SSH & Windows typeperf streaming.
Monitors remote servers ('quad', 'e5', '8375c') in background threads with zero UI blocking.
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

DEFAULT_SERVERS = [
    {
        "id": "quad",
        "name": "server-quad",
        "host": "server-quad",
        "port": 22,
        "user": "",
        "password": ""
    },
    {
        "id": "e5",
        "name": "server-e5",
        "host": "server-e5",
        "port": 22,
        "user": "",
        "password": ""
    },
    {
        "id": "8375c",
        "name": "server-8375c",
        "host": "server-8375c",
        "port": 22,
        "user": "",
        "password": ""
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


class SingleServerWorker(QThread):
    """Background worker monitoring a single server's CPU percentage via streaming typeperf."""
    cpu_updated = pyqtSignal(str, float)  # server_id, cpu_percent (-1.0 if offline)
    status_updated = pyqtSignal(str, str)  # server_id, status ("connected", "connecting", "error")

    def __init__(self, server_cfg: Dict[str, Any], interval: int = 2):
        super().__init__()
        self.server_cfg = server_cfg
        self.interval = max(1, interval)
        self.server_id = server_cfg.get("id", server_cfg.get("name", "server"))
        self.name = server_cfg.get("name", self.server_id)
        self.host = server_cfg.get("host", self.name)
        self.port = int(server_cfg.get("port", 22))
        self.user = server_cfg.get("user", "admin")
        self.password = server_cfg.get("password", "")
        self._running = True
        self.client: Optional[paramiko.SSHClient] = None

    def stop(self):
        self._running = False
        if self.client:
            try:
                self.client.close()
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

                # Stream CPU usage with typeperf
                cmd = f'typeperf "\\Processor(_Total)\\% Processor Time" -si {self.interval}'
                stdin, stdout, stderr = self.client.exec_command(cmd, bufsize=1)

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
                    except (ValueError, IndexError):
                        continue

            except Exception:
                self.status_updated.emit(self.server_id, "error")
                self.cpu_updated.emit(self.server_id, -1.0)
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


class MultiServerMonitor(QObject):
    """Coordinates streaming CPU monitors for servers quad, e5, and 8375c."""
    servers_updated = pyqtSignal(dict)  # {"quad": float, "e5": float, "8375c": float}

    def __init__(self, server_list: Optional[List[Dict[str, Any]]] = None, interval: int = 2):
        super().__init__()
        if not server_list:
            # Check if scratch/server_monitor/config.json has credentials
            try:
                ext_cfg_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "server_monitor", "config.json"
                )
                if os.path.exists(ext_cfg_path):
                    with open(ext_cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        server_list = data.get("servers", [])
            except Exception:
                pass
        self.server_list = server_list or list(DEFAULT_SERVERS)
        self.interval = interval
        self.workers: Dict[str, SingleServerWorker] = {}
        self.latest_cpu: Dict[str, float] = {
            "quad": -1.0,
            "e5": -1.0,
            "8375c": -1.0
        }

    def start(self):
        self.stop()
        for s_cfg in self.server_list:
            sid = s_cfg.get("id", s_cfg.get("name"))
            worker = SingleServerWorker(s_cfg, interval=self.interval)
            worker.cpu_updated.connect(self._on_cpu_updated)
            self.workers[sid] = worker
            worker.start()

    def stop(self):
        for worker in self.workers.values():
            worker.stop()
            worker.wait(1000)
        self.workers.clear()

    def _on_cpu_updated(self, server_id: str, cpu_val: float):
        self.latest_cpu[server_id] = cpu_val
        self.servers_updated.emit(dict(self.latest_cpu))
