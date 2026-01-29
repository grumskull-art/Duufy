"""
Codex Operation: Python lint and format fixer.
Runs black, isort, autopep8, and flake8, and logs output to codex_tasks/.
"""

import datetime
import io
import os
import sys

from codex_utils import run_step

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

os.makedirs("codex_tasks", exist_ok=True)
stamp = datetime.date.today().isoformat()
logfile = f"codex_tasks/fix_lint_{stamp}.md"
os.environ["CODEX_LOG_FILE"] = logfile

with open(logfile, "w", encoding="utf-8") as log:
    log.write(f"# [Codex Operation] Lint Fix {stamp}\n\n")

tools = ["black", "isort", "autopep8", "flake8"]
for tool in tools:
    run_step(f"Install {tool}", f"pip install {tool}")

run_step("Sort imports", "isort .")
run_step("Black format", "black . --line-length 88")
run_step("Autopep8 format", "autopep8 --in-place --aggressive --aggressive -r .")

lint_report = "codex_tasks/lint_report.txt"
lint_result = run_step("Flake8 report", "flake8")
if lint_result:
    with open(lint_report, "w", encoding="utf-8") as report:
        report.write(lint_result.stdout or "")
        report.write(lint_result.stderr or "")

print(f"Lint fix complete. See {lint_report}.")
