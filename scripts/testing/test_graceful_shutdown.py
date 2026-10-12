#!/usr/bin/env python3
"""Test graceful shutdown of API server.

Demonstrates that the port is properly released and can be reused
immediately after shutdown.
"""

import subprocess
import time
import socket
import sys
import signal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def is_port_open(port: int, host: str = "localhost") -> bool:
    """Check if a port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    finally:
        sock.close()


def wait_for_port(port: int, timeout: int = 10) -> bool:
    """Wait for port to be open (server started)."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(port):
            return True
        time.sleep(0.1)
    return False


def wait_for_port_closed(port: int, timeout: int = 10) -> bool:
    """Wait for port to be closed (server stopped)."""
    start = time.time()
    while time.time() - start < timeout:
        if not is_port_open(port):
            return True
        time.sleep(0.1)
    return False


def test_graceful_shutdown():
    """Test graceful shutdown and port reuse."""
    port = 8000

    print("=" * 70)
    print("TESTING GRACEFUL SHUTDOWN")
    print("=" * 70)

    # Test 1: Start server
    print("\n[Test 1] Starting API server...")
    proc = subprocess.Popen(
        [sys.executable, "api_server.py"],
        cwd=Path(__file__).parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    print("Waiting for server to start...")
    if not wait_for_port(port):
        print(f"✗ FAILED: Server did not start on port {port}")
        proc.kill()
        return False
    print(f"✓ Server started on port {port}")

    # Test 2: Graceful shutdown
    print("\n[Test 2] Sending SIGTERM signal for graceful shutdown...")
    proc.send_signal(signal.SIGTERM)

    print("Waiting for server to stop...")
    try:
        proc.wait(timeout=20)
        print("✓ Server stopped gracefully")
    except subprocess.TimeoutExpired:
        print("✗ FAILED: Server did not stop within timeout")
        proc.kill()
        return False

    # Test 3: Verify port is released
    print("\n[Test 3] Verifying port is released...")
    time.sleep(0.5)  # Small delay

    if not wait_for_port_closed(port, timeout=5):
        print(f"✗ FAILED: Port {port} still in use")
        return False
    print(f"✓ Port {port} successfully released")

    # Test 4: Restart server (verify port can be reused)
    print("\n[Test 4] Restarting server to verify port reuse...")
    proc2 = subprocess.Popen(
        [sys.executable, "api_server.py"],
        cwd=Path(__file__).parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    print("Waiting for restarted server to start...")
    if not wait_for_port(port):
        print(f"✗ FAILED: Server could not restart on port {port}")
        proc2.kill()
        return False
    print(f"✓ Server successfully restarted on port {port}")

    # Cleanup
    print("\n[Cleanup] Stopping restarted server...")
    proc2.send_signal(signal.SIGTERM)
    try:
        proc2.wait(timeout=20)
        print("✓ Restarted server stopped gracefully")
    except subprocess.TimeoutExpired:
        print("⚠  Server did not stop within timeout, killing...")
        proc2.kill()

    return True


if __name__ == "__main__":
    try:
        success = test_graceful_shutdown()

        print("\n" + "=" * 70)
        if success:
            print("✓ ALL TESTS PASSED")
            print("✓ Graceful shutdown is working correctly")
            print("✓ Port is properly released and can be reused")
        else:
            print("✗ TESTS FAILED")
            sys.exit(1)
        print("=" * 70 + "\n")

    except KeyboardInterrupt:
        print("\n\n✗ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        sys.exit(1)
