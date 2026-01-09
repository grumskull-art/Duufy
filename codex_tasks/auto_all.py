"""
🧩 Codex Macro: Complete automation pipeline with Recovery Mode
Kører lint-fix, cleanup, build og deploy i ét flow,
logger alt og fortsætter selv hvis et step fejler.
"""

import subprocess
import datetime
import os
from codex_utils import run

# 1️⃣ Setup
os.makedirs("codex_tasks", exist_ok=True)
stamp = datetime.date.today().isoformat()
logfile = f"codex_tasks/auto_all_{stamp}.md"

steps = [
    ("Lint & Format Fix", "python codex_tasks/fix_lint.py"),
    ("Cleanup & Dependencies", "python codex_tasks/auto_cleanup.py"),
    ("Android Build", "python codex_tasks/auto_build.py"),
    ("Backend Deploy", "python codex_tasks/auto_deploy.py"),
]

with open(logfile, "w", encoding="utf-8") as log:
    log.write(f"# [Codex Operation] Auto Macro Run {stamp}\n\n")

    print("🚀 Starter Codex Macro Flow...\n")
    for title, cmd in steps:
        section = f"## {title}\n"
        print(section)
        log.write(section + "\n")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        log.write("```\n" + result.stdout + "\n" + result.stderr + "\n```\n\n")
        if result.returncode != 0:
            error_msg = f"⚠️  Step '{title}' fejlede, men Codex fortsætter.\n"
            print(error_msg)
            log.write(error_msg + "\n")
        else:
            log.write(f"✅  Step '{title}' udført uden fejl.\n\n")

# 2️⃣ Commit + Push logfil
commit_cmds = [
    f"git add {logfile}",
    f'git commit -m "Codex: auto macro run {stamp}"',
    "git push origin duufy-v1.1-fixes"
]

for cmd in commit_cmds:
    run(cmd)

print("\n✅ Codex Macro complete – se logfil i codex_tasks/")
