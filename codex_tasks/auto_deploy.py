import datetime
import io
import os
import sys

from codex_utils import run_step

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

stamp = datetime.date.today().isoformat()
logfile = f"codex_tasks/deploy_{stamp}.md"
os.makedirs("codex_tasks", exist_ok=True)
os.environ["CODEX_LOG_FILE"] = logfile

with open(logfile, "w", encoding="utf-8") as log:
    log.write(f"# [Codex Operation] Deploy {stamp}\n\n")

run_step("Run uvicorn", "uvicorn main:app --host 0.0.0.0 --port 8000")

run_step("Git add deploy log", f"git add {logfile}")
run_step("Git commit deploy", f'git commit -m "Codex: deploy {stamp}"')
run_step("Git push deploy", "git push origin duufy-v1.1-fixes")

print("Deployment complete and pushed.")
