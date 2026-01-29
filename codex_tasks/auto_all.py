"""
Codex Macro: Complete automation pipeline with recovery mode.
Runs lint, cleanup, build, and deploy in one flow and logs output.
"""

import datetime
import io
import os
import sys

from codex_utils import run_step as run

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

os.makedirs("codex_tasks", exist_ok=True)
stamp = datetime.date.today().isoformat()
logfile = f"codex_tasks/auto_all_{stamp}.md"
os.environ["CODEX_LOG_FILE"] = logfile

with open(logfile, "w", encoding="utf-8") as log:
    log.write(f"# [Codex Operation] Auto Macro Run {stamp}\n\n")

run("Lint & Format Fix", "python codex_tasks/fix_lint.py")
run("Cleanup & Dependencies", "python codex_tasks/auto_cleanup.py")
run("Android Build", "python codex_tasks/auto_build.py")
run("Backend Deploy", "python codex_tasks/auto_deploy.py")

run("Git add auto_all log", f"git add {logfile}")
run("Git commit auto_all log", f'git commit -m "Codex: auto macro run {stamp}"')
run("Git push auto_all log", "git push origin duufy-v1.1-fixes")

print("Codex macro complete. See codex_tasks for logs.")
