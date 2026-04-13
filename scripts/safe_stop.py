#!/usr/bin/env python3
"""Safe shutdown script - gracefully stops API and Docker services.

This script properly stops the RAG Agent API server using SIGTERM (graceful)
instead of SIGKILL (force), which allows port 8000 to be released immediately
without crashing Docker.

Usage:
    python scripts/safe_stop.py
"""

import subprocess
import time
import signal
import socket
import sys
import os
from pathlib import Path
from typing import Optional


def is_port_in_use(port: int, host: str = "localhost") -> bool:
    """Check if a port is in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            result = sock.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def get_pid_on_port(port: int) -> Optional[int]:
    """Get PID of process using a specific port."""
    try:
        result = subprocess.run(
            f"lsof -ti:{port}", shell=True, capture_output=True, text=True, timeout=5
        )
        pid_str = result.stdout.strip()
        return int(pid_str) if pid_str else None
    except Exception:
        return None


def graceful_stop_process(pid: int, timeout: int = 15) -> bool:
    """Gracefully stop a process using SIGTERM, then SIGKILL if needed.

    Args:
        pid: Process ID
        timeout: Seconds to wait for graceful shutdown

    Returns:
        True if successful, False if timeout
    """
    try:
        # Send SIGTERM (graceful shutdown)
        os.kill(pid, signal.SIGTERM)
        print(f"  SIGTERM sent to process {pid}")

        # Wait for process to exit
        start = time.time()
        while time.time() - start < timeout:
            try:
                # Check if process still exists
                os.kill(pid, 0)  # Send signal 0 to test
                time.sleep(0.5)
            except ProcessLookupError:
                # Process exited
                print(f"  ✓ Process {pid} exited gracefully")
                return True

        # Timeout: force kill
        print(f"  ⚠ Process did not exit in {timeout}s, force killing...")
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
        return True

    except ProcessLookupError:
        # Process already gone
        return True
    except Exception as e:
        print(f"  Error stopping process: {e}")
        return False


def main():
    """Safe shutdown procedure."""
    port = 8000
    timeout = 15

    print("=" * 60)
    print("Safe Shutdown - Stopping RAG Agent API")
    print("=" * 60)

    # Step 1: Stop API server
    print("\nStep 1: Stopping API server on port 8000...")
    pid = get_pid_on_port(port)

    if pid:
        print(f"  Found process {pid} on port {port}")
        if graceful_stop_process(pid, timeout=timeout):
            time.sleep(1)
        else:
            print("  ✗ Failed to stop process")
    else:
        print(f"  ℹ No process running on port {port}")

    # Step 2: Verify port is released
    print("\nStep 2: Verifying port is released...")
    time.sleep(1)
    if is_port_in_use(port):
        print(f"  ✗ Port {port} still in use!")
        pid = get_pid_on_port(port)
        if pid:
            print(f"    Checking process {pid}...")
            try:
                result = subprocess.run(
                    f"lsof -i:{port}", shell=True, capture_output=True, text=True, timeout=5
                )
                print(f"    {result.stdout}")
            except Exception as e:
                print(f"    Error: {e}")
    else:
        print(f"  ✓ Port {port} is free")

    # Step 3: Show Docker status
    print("\nStep 3: Docker containers status:")
    docker_compose_path = Path(__file__).parent.parent / "docker" / "docker-compose.yml"

    try:
        if docker_compose_path.exists():
            result = subprocess.run(
                "docker-compose -f docker/docker-compose.yml ps",
                shell=True,
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
                timeout=5,
            )
            print("  " + result.stdout.replace("\n", "\n  ") if result.stdout else "  (no output)")

            # Ask to stop Docker
            response = input("\n  Stop Docker containers gracefully? (y/n): ").lower()
            if response.startswith("y"):
                print("  Stopping containers...")
                stop_result = subprocess.run(
                    "docker-compose -f docker/docker-compose.yml stop --timeout=15",
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=Path(__file__).parent.parent,
                    timeout=30,
                )
                if stop_result.returncode == 0:
                    print("  ✓ Containers stopped gracefully")
                    time.sleep(2)
                else:
                    print(f"  ⚠ docker-compose stop failed: {stop_result.stderr[:100]}")
        else:
            print(f"  ℹ docker-compose.yml not found at {docker_compose_path}")
    except Exception as e:
        print(f"  ℹ Could not manage Docker: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("✓ Safe shutdown complete")
    print("=" * 60)
    print("\nTo restart:")
    print("  1. open -a Docker (if not running)")
    print("  2. Wait 30 seconds for Docker to start")
    print("  3. docker-compose -f docker/docker-compose.yml up -d")
    print("  4. python api_server.py")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✓ Shutdown cancelled")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
