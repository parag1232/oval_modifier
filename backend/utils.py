# backend/utils.py

import hashlib
import os
import json

def safe_rule_filename(rule_id):
    return hashlib.sha256(rule_id.encode("utf-8")).hexdigest() + ".xml"

def load_filename_map(dir_path, map_filename):
    path = os.path.join(dir_path, map_filename)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_filename_map(dir_path, map_filename, mapping):
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, map_filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)

def get_hashed_path(rule_id, dir_path, map_filename):
    mapping = load_filename_map(dir_path, map_filename)
    safe_filename = mapping.get(rule_id)
    if safe_filename:
        return os.path.join(dir_path, safe_filename)
    return None
