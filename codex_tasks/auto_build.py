import datetime
import io
import os
import sys

from codex_utils import run_step

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

stamp = datetime.date.today().isoformat()
logfile = f"codex_tasks/build_{stamp}.md"
os.makedirs("codex_tasks", exist_ok=True)
os.environ["CODEX_LOG_FILE"] = logfile

with open(logfile, "w", encoding="utf-8") as log:
    log.write(f"# [Codex Operation] Build {stamp}\n\n")

run_step("Capacitor sync", "npx cap sync android")
run_step("Gradle assembleRelease", r"cd android; .\\gradlew assembleRelease")

run_step("Git add build log", f"git add {logfile}")
run_step("Git commit build", f'git commit -m "Codex: build {stamp}"')
run_step("Git push build", "git push origin duufy-v1.1-fixes")

print("Android build complete and pushed.")
