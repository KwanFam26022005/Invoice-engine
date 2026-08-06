"""Unit tests for ResourceMonitor."""

import os
import time
from document_benchmark.runner.resource_monitor import ResourceMonitor


def test_resource_monitor_sampling():
    monitor = ResourceMonitor(target_pid=os.getpid(), sample_interval_ms=50)
    monitor.start()

    # Do dummy computation to consume CPU & memory
    sum(i * 2 for i in range(100000))
    time.sleep(0.2)

    samples, summary = monitor.stop()

    assert len(samples) > 0
    assert summary.sample_count == len(samples)
    assert summary.rss_peak_mb > 0
    assert summary.peak_thread_count >= 1
