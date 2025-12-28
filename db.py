"""
Database operations with file locking to prevent race conditions
"""
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Any
from filelock import FileLock
import threading

# Thread-safe locks for each file
_locks = {}
_lock_mutex = threading.Lock()
logger = logging.getLogger(__name__)

def get_file_lock(filepath: Path) -> FileLock:
    """Get or create a FileLock for a given file"""
    lock_path = str(filepath) + ".lock"
    
    with _lock_mutex:
        if lock_path not in _locks:
            _locks[lock_path] = FileLock(lock_path, timeout=10)
        return _locks[lock_path]

def safe_read_json(filepath: Path, default: Any = None) -> Any:
    """Thread-safe JSON file reading with file locking"""
    if not filepath.exists():
        return default if default is not None else {}
    
    lock = get_file_lock(filepath)
    with lock:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read JSON file %s: %s", filepath, exc)
            backup_path = Path(str(filepath) + ".bak")
            if backup_path.exists():
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError) as backup_exc:
                    logger.warning("Failed to read JSON backup %s: %s", backup_path, backup_exc)
            return default if default is not None else {}

def safe_write_json(filepath: Path, data: Any) -> None:
    """Thread-safe JSON file writing with file locking"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    lock = get_file_lock(filepath)
    with lock:
        if filepath.exists():
            try:
                if filepath.stat().st_size > 0:
                    backup_path = Path(str(filepath) + ".bak")
                    shutil.copyfile(filepath, backup_path)
            except OSError:
                pass
        # Write to temp file first, then rename (atomic on most systems)
        temp_file = filepath.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(filepath)

def safe_update_json(filepath: Path, update_func, default: Any = None) -> Any:
    """
    Thread-safe JSON update with file locking
    
    Args:
        filepath: Path to JSON file
        update_func: Function that takes current data and returns updated data
        default: Default value if file doesn't exist
        
    Returns:
        Updated data
    """
    lock = get_file_lock(filepath)
    with lock:
        # Read current data
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = default if default is not None else {}
        
        # Update data
        updated_data = update_func(data)
        
        # Write back
        filepath.parent.mkdir(parents=True, exist_ok=True)
        temp_file = filepath.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(updated_data, f, indent=2, ensure_ascii=False)
        temp_file.replace(filepath)
        
        return updated_data
