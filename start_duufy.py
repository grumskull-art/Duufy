"""
Duufy Server Starter
Do you often forget? Duufy don't
"""

import os
import subprocess
import sys
import time
from pathlib import Path


# Colors for Windows terminal
class Colors:
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_banner():
    print(f"{Colors.CYAN}{Colors.BOLD}")
    print("╔═══════════════════════════════════════╗")
    print("║     🧠 DUUFY SERVER STARTER          ║")
    print("║  Do you often forget? Duufy don't    ║")
    print("╚═══════════════════════════════════════╝")
    print(f"{Colors.END}\n")


def start_server():
    """Start FastAPI server"""
    venv_python = (
        r"C:\Users\Grums\Documents\App_projekt_python\.venv\Scripts\python.exe"
    )

    print(f"{Colors.YELLOW}🚀 Starting FastAPI server...{Colors.END}")

    server_process = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "main:app", "--reload"],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to start
    time.sleep(3)

    if server_process.poll() is None:
        print(
            f"{Colors.GREEN}✓ FastAPI server running on http://127.0.0.1:8000{Colors.END}"
        )
        return server_process
    else:
        print(f"{Colors.RED}✗ Server failed to start{Colors.END}")
        return None


def start_ngrok():
    """Start ngrok tunnel"""
    print(f"\n{Colors.YELLOW}🌐 Starting ngrok tunnel...{Colors.END}")

    ngrok_process = subprocess.Popen(
        ["ngrok", "http", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for ngrok to start
    time.sleep(2)

    if ngrok_process.poll() is None:
        print(f"{Colors.GREEN}✓ Ngrok tunnel started{Colors.END}")
        print(f"{Colors.CYAN}  View details: http://127.0.0.1:4040{Colors.END}")
        return ngrok_process
    else:
        print(f"{Colors.RED}✗ Ngrok failed to start{Colors.END}")
        return None


def main():
    print_banner()

    # Start services
    server = start_server()
    if not server:
        print(f"\n{Colors.RED}Failed to start server. Exiting...{Colors.END}")
        sys.exit(1)

    ngrok = start_ngrok()

    # Show status
    print(
        f"\n{
            Colors.GREEN}{
            Colors.BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{
                Colors.END}"
    )
    print(f"{Colors.GREEN}✓ Duufy is running!{Colors.END}\n")
    print(f"{Colors.CYAN}Local:{Colors.END}     http://127.0.0.1:8000")
    print(f"{Colors.CYAN}Docs:{Colors.END}      http://127.0.0.1:8000/docs")
    if ngrok:
        print(
            f"{Colors.CYAN}Ngrok:{Colors.END}     http://127.0.0.1:4040 (for public URL)"
        )
    print(f"\n{Colors.YELLOW}Press Ctrl+C to stop all services{Colors.END}")
    print(f"{Colors.GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}\n")

    try:
        # Keep running
        while True:
            time.sleep(1)
            # Check if server is still running
            if server.poll() is not None:
                print(
                    f"\n{
                        Colors.RED}Server stopped unexpectedly!{
                        Colors.END}"
                )
                break
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⏹️  Stopping Duufy...{Colors.END}")

        # Stop services
        if server and server.poll() is None:
            server.terminate()
            print(f"{Colors.GREEN}✓ Server stopped{Colors.END}")

        if ngrok and ngrok.poll() is None:
            ngrok.terminate()
            print(f"{Colors.GREEN}✓ Ngrok stopped{Colors.END}")

        print(
            f"\n{
                Colors.CYAN}👋 Duufy is offline. See you later!{
                Colors.END}\n"
        )


if __name__ == "__main__":
    main()
