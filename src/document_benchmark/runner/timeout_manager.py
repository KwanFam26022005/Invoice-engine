"""Timeout and process tree termination helper."""

import logging

import psutil

logger = logging.getLogger(__name__)


def terminate_process_tree(pid: int, timeout_sec: float = 3.0) -> None:
    """Safely terminate a parent process and all its descendants."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    children = parent.children(recursive=True)
    processes = children + [parent]

    # First attempt SIGTERM / terminate()
    for p in processes:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass

    # Wait for termination
    _gone, alive = psutil.wait_procs(processes, timeout=timeout_sec)

    # Force kill any remaining processes
    for p in alive:
        try:
            logger.warning("Process PID %d did not terminate gracefully; killing.", p.pid)
            p.kill()
        except psutil.NoSuchProcess:
            pass
