import json
import os
import tempfile


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        data = json.load(f)
    return default if data is None else data


def save_json(path, data):
    """Atomic replace so a crash cannot leave a half-written ledger."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
