import datetime
import io
import os
import sys

from codex_utils import run_step

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

stamp = datetime.date.today().isoformat()
os.makedirs("codex_tasks", exist_ok=True)
logfile = f"codex_tasks/cleanup_{stamp}.md"
os.environ["CODEX_LOG_FILE"] = logfile

with open(logfile, "w", encoding="utf-8") as log:
    log.write(f"# [Codex Operation] Cleanup {stamp}\n\n")

run_step("Black format", "black . --line-length 88")
run_step("Sort imports", "isort .")

lint_report = "codex_tasks/lint_report.txt"
lint_result = run_step("Flake8 report", "flake8")
if lint_result:
    with open(lint_report, "w", encoding="utf-8") as report:
        report.write(lint_result.stdout or "")
        report.write(lint_result.stderr or "")

run_step("Install requirements", "pip install -r requirements.txt --upgrade")

run_step("Git add logs", f"git add {logfile} {lint_report}")
run_step("Git commit cleanup", f'git commit -m "Codex: cleanup {stamp}"')
run_step("Git push cleanup", "git push origin duufy-v1.1-fixes")

print("Cleanup complete and pushed.")
