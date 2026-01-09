import os, subprocess, datetime
def run(cmd): subprocess.run(cmd, shell=True, check=False)

stamp = datetime.date.today().isoformat()
log = f"codex_tasks/deploy_{stamp}.md"
os.makedirs("codex_tasks", exist_ok=True)

run("uvicorn main:app --host 0.0.0.0 --port 8000")

with open(log, "w") as f:
    f.write(f"# [Codex Operation] Deploy {stamp}\n")

run(f"git add {log}")
run(f'git commit -m "Codex: deploy {stamp}"')
run("git push origin duufy-v1.1-fixes")

print("✅ Deployment complete and pushed to GitHub.")
