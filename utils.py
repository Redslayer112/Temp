import hashlib
import os
from pathlib import Path
import json
import shutil

CONFIG = json.load(open('config.json'))
HASH_CHUNK_SIZE = CONFIG['HASH_CHUNK_SIZE']
HASH_ALGORITHM = CONFIG['HASH_ALGORITHM']


def calculate_file_hash(filepath):
    """Calculate hash of file using algorithm set in config"""
    try:
        hash_func = hashlib.new(HASH_ALGORITHM)
    except ValueError:
        raise ValueError(f"Unsupported hash algorithm: {HASH_ALGORITHM}")

    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def format_size(size):
    """Convert a file size in bytes to a human-readable string"""
    if size <= 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    for unit in units:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} EB"


def collect_directory_files(dir_path):
    """Collect all files in directory with their info"""
    files_info = []
    total_size = 0
    base_path = Path(dir_path)
    
    for file_path in base_path.rglob('*'):
        if file_path.is_file():
            rel_path = file_path.relative_to(base_path)
            size = file_path.stat().st_size
            files_info.append({
                'path': str(rel_path),
                'full_path': str(file_path),
                'size': size
            })
            total_size += size
    
    return files_info, total_size

def clean_path(path: str) -> str:
    if not path:
        return ""

    path = path.strip()

    # Handle PowerShell drag & drop that prepends "& "
    if path.startswith("& "):
        path = path[2:].lstrip()

    # Remove surrounding quotes if present
    if (path.startswith('"') and path.endswith('"')) or \
       (path.startswith("'") and path.endswith("'")):
        path = path[1:-1]

    # Normalize path format (e.g., slashes/backslashes)
    return os.path.normpath(path)


def get_disk_usage(path):
    """
    Get disk usage for a given path, with fallback handling.
    Returns (total, used, free) in bytes, or None if cannot determine.
    """
    
    # First ensure the directory exists
    try:
        ensure_directory(path)
    except Exception:
        # If we can't create the directory, try parent directories
        parent = path
        while parent and parent != os.path.dirname(parent):
            parent = os.path.dirname(parent)
            if os.path.exists(parent):
                path = parent
                break
        else:
            # Fallback to current directory
            path = '.'
    
    try:
        return shutil.disk_usage(path)
    except Exception:
        return None

def ensure_directory(path):
    """
    Ensure directory exists, create if it doesn't.
    Handles Windows path issues and permission errors.
    """
    if not path:
        return
        
    try:
        # Normalize the path for Windows
        path = os.path.normpath(path)
        
        # Create directory if it doesn't exist
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            
        # Verify directory was created and is accessible
        if not os.path.isdir(path):
            raise OSError(f"Path exists but is not a directory: {path}")
            
        # Test write permissions
        test_file = os.path.join(path, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except (OSError, IOError) as e:
            raise OSError(f"Directory not writable: {path} - {e}")
            
    except FileExistsError:
        # Directory already exists, that's fine
        pass
    except OSError as e:
        if e.errno == 3:  # "The system cannot find the path specified"
            # Try to create parent directories first
            parent = os.path.dirname(path)
            if parent and parent != path:
                ensure_directory(parent)
                os.makedirs(path, exist_ok=True)
            else:
                raise OSError(f"Cannot create directory: {path} - {e}")
        else:
            raise OSError(f"Cannot create directory: {path} - {e}")
    except Exception as e:
        raise Exception(f"Unexpected error creating directory {path}: {e}")