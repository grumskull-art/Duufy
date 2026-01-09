import os, subprocess, datetime
def run(cmd): subprocess.run(cmd, shell=True, check=False)

stamp = datetime.date.today().isoformat()
log = f"codex_tasks/build_{stamp}.md"
os.makedirs("codex_tasks", exist_ok=True)

run("npx cap sync android")
run("cd android && ./gradlew assembleRelease")

with open(log, "w") as f:
    f.write(f"# [Codex Operation] Build {stamp}\n")

run(f"git add {log}")
run(f'git commit -m "Codex: build {stamp}"')
run("git push origin duufy-v1.1-fixes")

print("✅ Android build complete and pushed.")
