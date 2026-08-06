"""Resource monitor for tracking CPU, RAM (RSS/USS/VMS), I/O, threads, and GPU/VRAM."""

import logging
import threading
import time

import psutil

from document_benchmark.core.contracts import ResourceSample, ResourceSummary

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Monitors CPU, RAM, I/O, and GPU metrics of a process and its tree."""

    def __init__(self, target_pid: int, sample_interval_ms: int = 200) -> None:
        self.target_pid = target_pid
        self.interval = max(0.05, sample_interval_ms / 1000.0)
        self._samples: list[ResourceSample] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._samples.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> tuple[list[ResourceSample], ResourceSummary]:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        summary = self._compute_summary(self._samples)
        return self._samples, summary

    def _monitor_loop(self) -> None:
        try:
            parent = psutil.Process(self.target_pid)
        except psutil.NoSuchProcess:
            return

        # Warmup CPU percent counters
        try:
            parent.cpu_percent(interval=None)
        except Exception:
            pass

        while not self._stop_event.is_set():
            try:
                sample = self._sample_process_tree(parent)
                if sample:
                    self._samples.append(sample)
            except Exception as e:
                logger.debug("Resource sampling error: %s", e)

            time.sleep(self.interval)

    def _sample_process_tree(self, parent: psutil.Process) -> ResourceSample | None:
        try:
            procs = [parent] + parent.children(recursive=True)
        except (psutil.NoSuchProcess, Exception):
            return None

        total_cpu = 0.0
        total_rss = 0.0
        total_uss = 0.0
        total_vms = 0.0
        total_read_bytes = 0
        total_write_bytes = 0
        total_threads = 0

        for p in procs:
            try:
                # CPU
                total_cpu += p.cpu_percent(interval=None)

                # Memory
                mem_info = p.memory_info()
                total_rss += mem_info.rss / (1024 * 1024)
                total_vms += mem_info.vms / (1024 * 1024)

                try:
                    full_mem = p.memory_full_info()
                    total_uss += getattr(full_mem, "uss", mem_info.rss) / (1024 * 1024)
                except Exception:
                    total_uss += mem_info.rss / (1024 * 1024)

                # Threads
                total_threads += p.num_threads()

                # I/O
                try:
                    io = p.io_counters()
                    total_read_bytes += io.read_bytes
                    total_write_bytes += io.write_bytes
                except Exception:
                    pass

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        gpu_sample = self._sample_gpu()

        return ResourceSample(
            timestamp=time.time(),
            process_id=self.target_pid,
            cpu_percent=round(total_cpu, 2),
            rss_mb=round(total_rss, 2),
            uss_mb=round(total_uss, 2),
            vms_mb=round(total_vms, 2),
            read_bytes=total_read_bytes,
            write_bytes=total_write_bytes,
            thread_count=total_threads,
            gpu_util_percent=gpu_sample.get("gpu_util"),
            gpu_memory_util_percent=gpu_sample.get("gpu_mem_util"),
            gpu_vram_mb=gpu_sample.get("gpu_vram_mb"),
            gpu_power_watts=gpu_sample.get("gpu_power"),
        )

    def _sample_gpu(self) -> dict:
        gpu_data = {
            "gpu_util": None,
            "gpu_mem_util": None,
            "gpu_vram_mb": None,
            "gpu_power": None,
        }
        try:
            import pynvml

            pynvml.nvmlInit()
            if pynvml.nvmlDeviceGetCount() > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_data["gpu_util"] = float(rates.gpu)
                gpu_data["gpu_mem_util"] = float(rates.memory)
                gpu_data["gpu_vram_mb"] = round(mem.used / (1024 * 1024), 2)
                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(handle)
                    gpu_data["gpu_power"] = round(power / 1000.0, 2)
                except Exception:
                    pass
            pynvml.nvmlShutdown()
        except Exception:
            pass
        return gpu_data

    def _compute_summary(self, samples: list[ResourceSample]) -> ResourceSummary:
        if not samples:
            return ResourceSummary()

        cpus = [s.cpu_percent for s in samples]
        rss = [s.rss_mb for s in samples]
        uss = [s.uss_mb for s in samples]
        vms = [s.vms_mb for s in samples]
        threads = [s.thread_count for s in samples]

        read_diff = max(0, samples[-1].read_bytes - samples[0].read_bytes)
        write_diff = max(0, samples[-1].write_bytes - samples[0].write_bytes)

        gpu_utils = [s.gpu_util_percent for s in samples if s.gpu_util_percent is not None]
        gpu_mems = [
            s.gpu_memory_util_percent for s in samples if s.gpu_memory_util_percent is not None
        ]
        gpu_vrams = [s.gpu_vram_mb for s in samples if s.gpu_vram_mb is not None]

        return ResourceSummary(
            cpu_avg_percent=round(sum(cpus) / len(cpus), 2),
            cpu_peak_percent=round(max(cpus), 2),
            rss_peak_mb=round(max(rss), 2),
            uss_peak_mb=round(max(uss), 2),
            vms_peak_mb=round(max(vms), 2),
            read_bytes_total=read_diff,
            write_bytes_total=write_diff,
            peak_thread_count=max(threads),
            gpu_util_avg_percent=round(sum(gpu_utils) / len(gpu_utils), 2) if gpu_utils else None,
            gpu_memory_util_avg_percent=round(sum(gpu_mems) / len(gpu_mems), 2)
            if gpu_mems
            else None,
            gpu_vram_peak_mb=round(max(gpu_vrams), 2) if gpu_vrams else None,
            sample_count=len(samples),
        )
