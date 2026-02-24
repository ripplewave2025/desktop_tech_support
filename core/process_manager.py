#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process Manager — Launch, find, monitor, and terminate processes.

Uses psutil for cross-platform process control and system monitoring.
"""

import os
import time
from typing import Optional, List, Dict, Any

import psutil


class ProcessInfo:
    """Structured info about a running process."""

    def __init__(self, pid: int, name: str, cpu_percent: float = 0.0,
                 memory_mb: float = 0.0, status: str = "",
                 exe: str = "", cmdline: str = ""):
        self.pid = pid
        self.name = name
        self.cpu_percent = cpu_percent
        self.memory_mb = memory_mb
        self.status = status
        self.exe = exe
        self.cmdline = cmdline

    def __repr__(self):
        return f"<Process {self.name} (PID:{self.pid}) CPU:{self.cpu_percent:.1f}% MEM:{self.memory_mb:.1f}MB>"


class SystemInfo:
    """System resource snapshot."""

    def __init__(self):
        self.cpu_percent = psutil.cpu_percent(interval=0.5)
        self.cpu_count = psutil.cpu_count()
        mem = psutil.virtual_memory()
        self.memory_total_gb = round(mem.total / (1024 ** 3), 2)
        self.memory_used_gb = round(mem.used / (1024 ** 3), 2)
        self.memory_percent = mem.percent
        try:
            disk = psutil.disk_usage("C:\\")
            self.disk_total_gb = round(disk.total / (1024 ** 3), 2)
            self.disk_used_gb = round(disk.used / (1024 ** 3), 2)
            self.disk_free_gb = round(disk.free / (1024 ** 3), 2)
            self.disk_percent = disk.percent
        except Exception:
            self.disk_total_gb = self.disk_used_gb = self.disk_free_gb = 0
            self.disk_percent = 0
        self.boot_time = psutil.boot_time()
        self.uptime_hours = round((time.time() - self.boot_time) / 3600, 1)

    def __repr__(self):
        return (
            f"CPU: {self.cpu_percent}% ({self.cpu_count} cores) | "
            f"RAM: {self.memory_used_gb}/{self.memory_total_gb} GB ({self.memory_percent}%) | "
            f"Disk: {self.disk_free_gb} GB free ({self.disk_percent}% used) | "
            f"Uptime: {self.uptime_hours}h"
        )


class ProcessManager:
    """Manage system processes and monitor resources."""

    def list_processes(self, name_filter: Optional[str] = None) -> List[ProcessInfo]:
        """List running processes, optionally filtered by name."""
        results = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
            try:
                info = proc.info
                if name_filter and name_filter.lower() not in info["name"].lower():
                    continue
                mem_mb = info["memory_info"].rss / (1024 ** 2) if info.get("memory_info") else 0
                results.append(ProcessInfo(
                    pid=info["pid"],
                    name=info["name"],
                    cpu_percent=info.get("cpu_percent", 0) or 0,
                    memory_mb=round(mem_mb, 1),
                    status=info.get("status", ""),
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return results

    def find_process(self, name: Optional[str] = None,
                     pid: Optional[int] = None) -> Optional[ProcessInfo]:
        """Find a specific process by name or PID."""
        if pid is not None:
            try:
                proc = psutil.Process(pid)
                mem = proc.memory_info()
                return ProcessInfo(
                    pid=proc.pid,
                    name=proc.name(),
                    cpu_percent=proc.cpu_percent(interval=0.1),
                    memory_mb=round(mem.rss / (1024 ** 2), 1),
                    status=proc.status(),
                    exe=proc.exe() if proc.exe() else "",
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None

        if name:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"].lower() == name.lower():
                        return self.find_process(pid=proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        return None

    def is_running(self, name_or_pid) -> bool:
        """Check if a process is running."""
        if isinstance(name_or_pid, int):
            return psutil.pid_exists(name_or_pid)
        return self.find_process(name=name_or_pid) is not None

    def launch(self, path: str, args: Optional[List[str]] = None,
               wait: bool = False, timeout: float = 10.0) -> Optional[ProcessInfo]:
        """Launch a process and optionally wait for it."""
        import subprocess

        cmd = [path] + (args or [])
        try:
            proc = subprocess.Popen(cmd)
            if wait:
                proc.wait(timeout=timeout)
            else:
                time.sleep(0.5)  # Give process time to start
            return self.find_process(pid=proc.pid)
        except FileNotFoundError:
            # Try common locations
            common_paths = [
                os.path.join(os.environ.get("ProgramFiles", ""), path),
                os.path.join(os.environ.get("ProgramFiles(x86)", ""), path),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), path),
                os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), path),
                os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", path),
            ]
            for full_path in common_paths:
                if os.path.exists(full_path):
                    proc = subprocess.Popen([full_path] + (args or []))
                    time.sleep(0.5)
                    return self.find_process(pid=proc.pid)
            raise FileNotFoundError(f"Could not find executable: {path}")
        except Exception as e:
            raise RuntimeError(f"Failed to launch {path}: {e}")

    def kill(self, name_or_pid, force: bool = False, timeout: float = 5.0) -> bool:
        """Terminate a process by name or PID."""
        targets = []

        if isinstance(name_or_pid, int):
            try:
                targets.append(psutil.Process(name_or_pid))
            except psutil.NoSuchProcess:
                return False
        else:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"].lower() == name_or_pid.lower():
                        targets.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        if not targets:
            return False

        for proc in targets:
            try:
                if force:
                    proc.kill()
                else:
                    proc.terminate()
                proc.wait(timeout=timeout)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                if not force:
                    try:
                        proc.kill()
                        proc.wait(timeout=2)
                    except Exception:
                        continue
        return True

    def get_system_info(self) -> SystemInfo:
        """Get current system resource snapshot."""
        return SystemInfo()

    def get_network_connections(self) -> List[Dict[str, Any]]:
        """List active network connections."""
        connections = []
        for conn in psutil.net_connections(kind="inet"):
            try:
                proc_name = ""
                if conn.pid:
                    try:
                        proc_name = psutil.Process(conn.pid).name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        proc_name = f"PID:{conn.pid}"
                connections.append({
                    "pid": conn.pid,
                    "process": proc_name,
                    "local": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "",
                    "remote": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "",
                    "status": conn.status,
                })
            except Exception:
                continue
        return connections

    def get_network_io(self) -> Dict[str, float]:
        """Get network I/O counters (bytes sent/received)."""
        counters = psutil.net_io_counters()
        return {
            "bytes_sent": counters.bytes_sent,
            "bytes_recv": counters.bytes_recv,
            "packets_sent": counters.packets_sent,
            "packets_recv": counters.packets_recv,
        }

    def get_bandwidth_usage(self, interval: float = 2.0) -> Dict[str, float]:
        """Measure current bandwidth usage over an interval."""
        before = psutil.net_io_counters()
        time.sleep(interval)
        after = psutil.net_io_counters()
        return {
            "download_mbps": round((after.bytes_recv - before.bytes_recv) * 8 / (interval * 1_000_000), 2),
            "upload_mbps": round((after.bytes_sent - before.bytes_sent) * 8 / (interval * 1_000_000), 2),
        }

    def get_top_memory_processes(self, limit: int = 10) -> List[ProcessInfo]:
        """Get processes sorted by memory usage."""
        procs = self.list_processes()
        procs.sort(key=lambda p: p.memory_mb, reverse=True)
        return procs[:limit]

    def get_top_cpu_processes(self, limit: int = 10) -> List[ProcessInfo]:
        """Get processes sorted by CPU usage (requires brief measurement)."""
        # Take a snapshot with CPU measurement
        results = []
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                cpu = proc.cpu_percent(interval=0)
                mem = proc.memory_info()
                results.append(ProcessInfo(
                    pid=proc.pid,
                    name=proc.name(),
                    cpu_percent=cpu,
                    memory_mb=round(mem.rss / (1024 ** 2), 1),
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Second pass for accurate CPU
        time.sleep(0.5)
        final = []
        for info in results:
            try:
                proc = psutil.Process(info.pid)
                info.cpu_percent = proc.cpu_percent(interval=0)
                final.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        final.sort(key=lambda p: p.cpu_percent, reverse=True)
        return final[:limit]
