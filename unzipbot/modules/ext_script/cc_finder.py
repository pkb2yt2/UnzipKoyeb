import os
import re
from datetime import datetime

# Import the database functions from your project structure
from unzipbot.helpers.database import add_cc_to_dump, get_all_cc_dump_lines_as_set
from unzipbot import LOGGER # Import the logger for better debugging

def find_all_credit_card_folders(root_path):
    """
    (REVISED AND GUARANTEED ROBUST)
    Recursively walks the entire directory tree from root_path and finds all
    folders named 'CreditCards', regardless of nesting depth or parent folder names.
    This method is exhaustive and will not miss any folders.
    """
    cc_folders = []
    # os.walk is the standard, reliable way to traverse a directory tree.
    # It visits every single directory and subdirectory.
    for dirpath, dirnames, _ in os.walk(root_path):
        # We check case-insensitively to be even more robust
        for dirname in dirnames:
            if dirname.lower() == 'creditcards':
                found_path = os.path.join(dirpath, dirname)
                cc_folders.append(found_path)
                LOGGER.info(f"Found 'CreditCards' folder at: {found_path}")
    return cc_folders

async def find_and_extract_cc(root_path: str, only_with_cvv: bool):
    """
    Finds all CCs using the robust os.walk() traversal logic,
    and then applies expiration and duplicate checks.
    """
    current_year = datetime.now().year
    current_month = datetime.now().month

    export_dir = os.path.join(root_path, "cc_results")
    os.makedirs(export_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = os.path.join(export_dir, f"CC_Extract_{timestamp}.txt")

    existing_dump = await get_all_cc_dump_lines_as_set()

    valid_entries = []
    new_cards_for_dump = []
    seen_dump_lines = set()

    # --- THIS IS THE NEW, GUARANTEED ROBUST TRAVERSAL METHOD ---
    LOGGER.info(f"Starting robust search for 'CreditCards' folders in: {root_path}")
    cc_folders = find_all_credit_card_folders(root_path)

    if not cc_folders:
        LOGGER.warning(f"No 'CreditCards' folders found anywhere inside {root_path}")
        return None, "⚠️ No 'CreditCards' folders were found in the extracted files."

    # The rest of the extraction logic remains the same
    for cc_folder in cc_folders:
        try:
            # It's possible the folder is empty or unreadable
            parent_dir = os.path.dirname(cc_folder)
            main_name = os.path.basename(parent_dir)
            country_code = main_name[1:main_name.index(']')] if main_name.startswith('[') and ']' in main_name else main_name[:2]
        except Exception:
            # Fallback for unexpected folder names
            country_code = "XX"
            
        for txt_fn in sorted(os.listdir(cc_folder)):
            if not txt_fn.lower().endswith(".txt"):
                continue
            txt_path = os.path.join(cc_folder, txt_fn)
            try:
                with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                LOGGER.error(f"Could not read file {txt_path}: {e}")
                continue

            # Original Extraction (Old Format)
            cn_match     = re.search(r'CN:\s*(\d+)', content)
            date_match   = re.search(r'DATE:\s*(\d{1,2})/(\d{4})', content)
            name_match   = re.search(r'NAME:\s*(.*)', content)
            target_match = re.search(r'TARGET:\s*(.*)', content)
            cvv_match    = re.search(r'CVV:\s*(\d+)', content)

            if cn_match:
                cn     = cn_match.group(1)
                mm     = date_match.group(1).zfill(2) if date_match else ""
                yyyy   = date_match.group(2) if date_match else ""
                name   = name_match.group(1).strip() if name_match else ""
                target = target_match.group(1).strip() if target_match else ""
                cvv    = cvv_match.group(1) if cvv_match else ""

                if yyyy and mm:
                    try:
                        card_year = int(yyyy)
                        card_month = int(mm)
                        if card_year < current_year or (card_year == current_year and card_month < current_month):
                            continue
                    except ValueError:
                        continue
                
                if only_with_cvv and not cvv:
                    continue
                
                dump_line = f"{cn}|{mm}|{yyyy}|{cvv}"
                if dump_line in existing_dump or dump_line in seen_dump_lines:
                    continue

                seen_dump_lines.add(dump_line)
                new_cards_for_dump.append(dump_line)
                entry = f"{cn}|{mm}|{yyyy}|{cvv}|{country_code}|{name}|{target}"
                valid_entries.append(entry)

            else:
                # New Extraction (Screenshot Format)
                holder_match    = re.search(r'Holder:\s*(.*)', content)
                cardtype_match  = re.search(r'CardType:\s*(.*)', content)
                card_match      = re.search(r'Card:\s*(\d+)', content)
                expire_match    = re.search(r'Expire:\s*(\d{1,2})/(\d{4})', content)

                if card_match and expire_match and holder_match:
                    cn = card_match.group(1)
                    mm = expire_match.group(1).zfill(2)
                    yyyy = expire_match.group(2)
                    name = holder_match.group(1).strip()
                    target = cardtype_match.group(1).strip() if cardtype_match else ""
                    cvv = ""

                    if yyyy and mm:
                        try:
                            card_year = int(yyyy)
                            card_month = int(mm)
                            if card_year < current_year or (card_year == current_year and card_month < current_month):
                                continue
                        except ValueError:
                            continue
                    
                    if only_with_cvv:
                        continue
                    
                    dump_line = f"{cn}|{mm}|{yyyy}|{cvv}"
                    if dump_line in existing_dump or dump_line in seen_dump_lines:
                        continue
                    
                    seen_dump_lines.add(dump_line)
                    new_cards_for_dump.append(dump_line)
                    entry = f"{cn}|{mm}|{yyyy}|{cvv}|{country_code}|{name}|{target}"
                    valid_entries.append(entry)

    # Final section to write the output file
    if valid_entries:
        try:
            with open(output_file, "w", encoding="utf-8") as out:
                out.write("\n".join(valid_entries))
            
            for dump_line in new_cards_for_dump:
                await add_cc_to_dump(dump_line)
            
            return output_file, f"✅ Extracted {len(valid_entries)} new, valid entries."
        except Exception as e:
            return None, f"❌ Failed to write output: {e}"
    else:
        return None, "⚠️ No new, valid credit card entries were found."