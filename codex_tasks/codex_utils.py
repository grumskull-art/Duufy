# codex_tasks/codex_utils.py
import io
import os
import subprocess
import sys

POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _append_log(log_file, name, command, stdout, stderr, returncode, error=None):
    if not log_file:
        return
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"## {name}\n")
        log.write(f"`{command}`\n\n")
        log.write("```text\n")
        if stdout:
            log.write(stdout)
        if stderr:
            if stdout and not stdout.endswith("\n"):
                log.write("\n")
            log.write(stderr)
        log.write("\n```\n\n")
        if error:
            log.write(f"Result: error {error}\n\n")
        else:
            log.write(f"Result: exit {returncode}\n\n")


def run_step(name: str, command: str, cwd="."):
    print(f"[STEP] {name}")
    env = os.environ.copy()
    log_file = env.get("CODEX_LOG_FILE")
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            executable=POWERSHELL,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        _append_log(
            log_file,
            name,
            command,
            result.stdout,
            result.stderr,
            result.returncode,
        )
        if result.returncode == 0:
            print(f"[OK] {name}")
        else:
            print(f"[WARN] {name} failed with exit {result.returncode}")
        return result
    except Exception as exc:
        msg = str(exc)
        _append_log(log_file, name, command, "", msg, 1, error=msg)
        print(f"[ERROR] {name} raised an exception: {msg}")
        return None
