import os
import zipfile
import random
import string
from config import Config

def _parse_passwords(lines):
    """
    Parses password files from logs (supports both Redline and other styles).
   
    """
    # This function remains the same as before
    entries = []
    block = {}
    for line in lines:
        line = line.strip()
        low = line.lower()
        if line.startswith("URL:"):
            block = {'url': line[4:].strip()}
        elif line.startswith("Username:"):
            block['user'] = line[9:].strip()
        elif line.startswith("Password:"):
            block['pass'] = line[9:].strip()
            if all(k in block for k in ('url', 'user', 'pass')):
                entries.append(block.copy())
            block = {}
        elif low.startswith('url:'):
            block['url'] = line.split(':', 1)[1].strip()
        elif low.startswith('user:'):
            block['user'] = line.split(':', 1)[1].strip()
        elif low.startswith('pass:'):
            block['pass'] = line.split(':', 1)[1].strip()
            if all(k in block for k in ('url', 'user', 'pass')):
                entries.append(block.copy())
            block = {}
    return entries

# In combo_helper.py

def process_txt_file(file_path, keywords):
    """
    UPDATED: Processes a TXT file and groups unique results by keyword.
    """
    results = {kw: set() for kw in keywords} # Use a set to store unique combos
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for line in lines:
        for kw in keywords:
            if kw.lower() in line.lower():
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    combo = f"{parts[-2]}:{parts[-1]}"
                    results[kw].add(combo) # .add() on a set prevents duplicates
    
    # Convert sets back to lists for the final output
    return {kw: list(combos) for kw, combos in results.items()}

def process_logs_folder(logs_dir, keywords):
    """
    UPDATED: Processes log folders and groups unique results by keyword.
    """
    results = {kw: set() for kw in keywords} # Use a set here as well
    session_unique_combos = set() # Track all combos found in this session

    for root, _, files in os.walk(logs_dir):
        pw_file_path = None
        for fname in ("Passwords.txt", "All Passwords.txt"):
            if fname in files:
                pw_file_path = os.path.join(root, fname)
                break
        
        if not pw_file_path:
            continue
            
        with open(pw_file_path, 'r', encoding='utf-8', errors="ignore") as f:
            lines = f.readlines()
        
        entries = _parse_passwords(lines)
        for entry in entries:
            combo = f"{entry.get('user', '')}:{entry.get('pass', '')}"
            if combo in session_unique_combos:
                continue # Skip if we've already processed this exact combo in this run

            for kw in keywords:
                if kw.lower() in entry.get('url', '').lower():
                    user = entry.get('user', '')
                    pwd = entry.get('pass', '')
                    if user and pwd and ' ' not in user and ' ' not in pwd:
                        results[kw].add(combo)
                        session_unique_combos.add(combo)
                        break # Match found, move to next entry
    
    # Convert sets back to lists
    return {kw: list(combos) for kw, combos in results.items()}

def create_combo_archives(results_by_keyword, user_id):
    """
    NEW: Creates keyword-named .txt files and a randomly named .zip archive.
    """
    # Check if there are any results at all
    if not any(results_by_keyword.values()):
        return None, None

    result_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    os.makedirs(result_dir, exist_ok=True)
    
    txt_file_paths = []
    # Create individual .txt files for each keyword
    for keyword, combos in results_by_keyword.items():
        if combos:
            txt_path = os.path.join(result_dir, f"{keyword}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(combos))
            txt_file_paths.append(txt_path)
    
    # If no text files were created, return None
    if not txt_file_paths:
        return None, None

    # Create the randomly named zip file
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    zip_path = os.path.join(result_dir, f"{user_id}_{random_suffix}.zip")
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in txt_file_paths:
            zipf.write(file, os.path.basename(file))
            
    return zip_path, txt_file_paths