import os, subprocess, datetime

def run(cmd):
    print(f"🧩 {cmd}")
    subprocess.run(cmd, shell=True, check=False)

stamp = datetime.date.today().isoformat()
os.makedirs("codex_tasks", exist_ok=True)
log = f"codex_tasks/cleanup_{stamp}.md"

commands = [
    "black . --line-length 88",
    "isort .",
    "flake8 > codex_tasks/lint_report.txt",
    "pip install -r requirements.txt --upgrade",
]

for c in commands:
    run(c)

with open(log, "w") as f:
    f.write(f"# [Codex Operation] Cleanup {stamp}\n")

# Commit og push til GitHub
run(f'git add {log} codex_tasks/lint_report.txt')
run(f'git commit -m "Codex: cleanup {stamp}"')
run("git push origin duufy-v1.1-fixes")

print("✅ Cleanup done and pushed to GitHub.")
