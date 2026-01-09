"""
🧩 Codex Operation: Python Lint & Format Fixer
Rydder op i alle .py-filer via black, isort og autopep8
og logger resultatet i codex_tasks/
"""

import os, subprocess, datetime

def run(cmd):
    print(f"🧩 {cmd}")
    subprocess.run(cmd, shell=True, check=False)

# Opret logmappe hvis den ikke findes
os.makedirs("codex_tasks", exist_ok=True)

stamp = datetime.date.today().isoformat()
logfile = f"codex_tasks/fix_lint_{stamp}.md"

# 1️⃣  Installer formateringsværktøjer hvis de mangler
tools = ["black", "isort", "autopep8"]
for tool in tools:
    run(f"pip install {tool}")

# 2️⃣  Sorter imports
run("isort .")

# 3️⃣  Black formatering (linjelængde 88)
run("black . --line-length 88")

# 4️⃣  Autopep8 retter spacing, E302 m.m.
run("autopep8 --in-place --aggressive --aggressive -r .")

# 5️⃣  Lint-tjek og log
run("flake8 > codex_tasks/lint_report.txt")

with open(logfile, "w", encoding="utf-8") as f:
    f.write(f"# [Codex Operation] Lint Fix {stamp}\n")
    f.write("Alle Python-filer formateret og lint-tjek udført.\n")

print("✅ Codex Lint Fix complete – check codex_tasks/lint_report.txt")
