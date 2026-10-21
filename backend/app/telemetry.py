"""Sample host resources without confusing client RSS with remote model memory."""
import os
import threading

import psutil


class ResourceMonitor:
    def __init__(self, interval_seconds=0.25):
        self.interval = max(float(interval_seconds), 0.01)
        self._stop = threading.Event()
        self._thread = None
        self._peaks = {"system_ram_used_peak_bytes": None, "backend_rss_peak_bytes": None, "ollama_rss_peak_bytes": None}
        self._samples = 0
        self._processes = set()
        self._first_sample = threading.Event()

    def _sample(self):
        values = {}
        try:
            values["system_ram_used_peak_bytes"] = psutil.virtual_memory().used
            values["backend_rss_peak_bytes"] = psutil.Process(os.getpid()).memory_info().rss
        except (psutil.Error, OSError):
            pass
        for key, value in values.items():
            previous = self._peaks[key]
            self._peaks[key] = max(previous, value) if previous is not None else value
        self._samples += 1
        self._first_sample.set()
        rss = 0
        found = False
        for process in psutil.process_iter(["pid", "name"]):
            if self._stop.is_set():
                break
            try:
                name = (process.info.get("name") or "").lower()
                if "ollama" in name or name.startswith("llama-server") or name.startswith("llama-runner"):
                    found = True
                    rss += process.memory_info().rss
                    self._processes.add((process.pid, name))
            except (psutil.Error, OSError, TypeError):
                continue
        if found:
            values["ollama_rss_peak_bytes"] = rss
            previous = self._peaks["ollama_rss_peak_bytes"]
            self._peaks["ollama_rss_peak_bytes"] = max(previous, rss) if previous is not None else rss

    def start(self):
        def loop():
            while not self._stop.is_set():
                self._sample()
                self._stop.wait(self.interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        self._first_sample.wait(timeout=0.1)
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=min(self.interval + 0.1, 1))
        return {**self._peaks, "gpu_memory_peak_bytes": None, "shared_gpu_memory_peak_bytes": None, "gpu_unavailable_reason": "GPU/공유 메모리 계측 미구현; CPU/GPU 실행 판단은 Ollama /api/ps size_vram 원본으로 확인", "collection_interval_seconds": self.interval, "sample_count": self._samples, "sampling_stopped": not self._thread or not self._thread.is_alive(), "method": "psutil sampled peak RSS (not allocation peak); system used RAM, backend own RSS, sum of named Ollama/runner RSS; shared pages may overlap and are not added to system RAM", "ollama_processes": [{"pid": pid, "name": name} for pid, name in sorted(self._processes)]}
