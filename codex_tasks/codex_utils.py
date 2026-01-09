import os, subprocess, datetime, importlib.util

def run(cmd):
    print(f"🧩 {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️ Fejl: {cmd}")
        print(result.stderr)
    return result

def is_installed(module_name):
    return importlib.util.find_spec(module_name) is not None

def log_header(name):
    os.makedirs("codex_tasks", exist_ok=True)
    stamp = datetime.date.today().isoformat()
    logfile = f"codex_tasks/{name}_{stamp}.md"
    f = open(logfile, "w", encoding="utf-8")
    f.write(f"# [Codex Operation] {name} {stamp}\n\n")
    return f, logfile
