"""
This script monitors the current directory for new Europa Universalis IV autosave files (.eu5).
When a new autosave is detected, it reads the in-game date from the file,
renames the file to include the date,and moves it to a dedicated "saves_watcher" directory.
It also manages the autosaves by retaining only those that are spaced
at least FREQUENCY_MONTHS apart, deleting closer ones to save space.
"""
import configparser
import glob
import os
import re
import sys
from pathlib import Path
from time import sleep
from tools.shared import fetch_logs


# Allow running directly from this folder by ensuring repo root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
	sys.path.insert(0, str(REPO_ROOT))

def months_from_0(date_str):
    """Parse date string format: 'YYYY-MM-DD' and return total months."""
    # Validate format before parsing
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", date_str)
    if not match:
        print(f"Warning: Invalid date format '{date_str}', expected YYYY-MM-DD")
        return 0
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    return year * 12 + month + (day / 30)

def extract_date_from_filename(filename):
    """Safely extract and validate date from save filename."""
    basename = os.path.basename(filename)
    parts = basename.split("_", 1)
    if len(parts) < 2:
        return None
    date_part = parts[0]
    # Validate it looks like a date
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", date_part):
        return date_part
    return None

def get_save_directory_from_config():
    """
    Reads the save directory path from shared/config.ini under the [Paths] section.
    """
    config = configparser.ConfigParser()
    config_path = Path(fetch_logs.__file__).resolve().parent / "config.ini"
    if not config_path.exists():
        print(f"ERROR: Config file not found at {config_path}. Please create it (MT_grapher.py can generate one) and set save_directory.")
        return ""

    try:
        config.read(config_path)
        return config.get("Paths", "save_directory")
    except (configparser.NoSectionError, configparser.NoOptionError):
        print(f"ERROR: 'save_directory' missing in config at {config_path}. Add it under [Paths] and rerun.")
    except Exception as e:
        print(f"ERROR: Could not read save directory from config: {e}")
    return ""


def get_frequency_months_from_config():
    """
    Reads the frequency months from shared/config.ini under the [Settings] section.
    """
    config = configparser.ConfigParser()
    config_path = Path(fetch_logs.__file__).resolve().parent / "config.ini"
    if not config_path.exists():
        print(f"ERROR: Config file not found at {config_path}. Please create it (MT_grapher.py can generate one) and set autosave_month_interval.")

    try:
        config.read(config_path)
        return config.getint("Settings", "autosave_month_interval")
    except (configparser.NoSectionError, configparser.NoOptionError):
        print(f"WARNING: 'autosave_month_interval' missing in config at {config_path}.")
        print("Make sure to add it under [Settings] as 'autosave_month_interval'. Look at example config for guidance.")
    except Exception as e:
        print(f"ERROR: Could not read frequency months from config: {e}")
        print("Make sure to add it under [Settings] in config.ini as 'autosave_month_interval'. Look at example config for guidance.")


if __name__ == "__main__":

    # Get save directory from config
    save_dir_raw = get_save_directory_from_config()
    save_dir = Path(save_dir_raw).expanduser() if save_dir_raw else None
    if not save_dir:
        print("Stopping because save_directory is not set.")
        raise SystemExit(1)
    if not save_dir.is_dir():
        print(f"ERROR: Configured save directory '{save_dir}' does not exist. Update config.ini and rerun.")
        raise SystemExit(1)

    #get frequency months from config
    FREQUENCY_MONTHS = get_frequency_months_from_config()
    print(f"Using autosave frequency of {FREQUENCY_MONTHS} months.")

    # Change to save directory
    os.chdir(save_dir)

    # Initial list of .eu5 files
    files_before = glob.glob("*.eu5")
    os.makedirs("saves_watcher", exist_ok=True)

    #if a file gets created or modified and it's an autosave, move it to saves_watcher
    i = 0
    while True:
        files_after = glob.glob("*.eu5")
        new__files = [f for f in files_after if f not in files_before and "autosave" in f]

        for save in new__files:
            # Read file and get date
            try:
                with open(save, 'r', encoding='utf-8', errors='replace') as file:
                    # Read only the first few lines to check format
                    lines = []
                    for _ in range(5):
                        line = file.readline()
                        if not line:
                            break
                        lines.append(line)

                    if len(lines) < 3:
                        print(f"Unexpected format in {save}, skipping (not a debug save?)")
                        continue

                    if "=" not in lines[2]:
                        print(f"Unexpected format in {save}, skipping (not a debug save?)")
                        continue

                    # Extract date_info from the line ("date=1444.11.11")
                    date_info = lines[2].split("=", 1)[1].strip()
                    date_info = date_info.replace(".", "-").strip('"').strip("'")

                    # Validate date format
                    if not re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", date_info):
                        print(f"Invalid date format '{date_info}' in {save}, skipping")
                        continue

                    print(f"Autosave date info: {date_info}")
                    save_new_name = f"{date_info}_{os.path.splitext(save)[0]}.eu5"

            except (UnicodeDecodeError, OSError) as e:

                print(f"Cannot read {save} (likely not a debug save): {e}")
                print("Make sure to enable debug_mode.")
                continue
            except Exception as e:
                print(f"Error reading {save}: {e}")
                continue

            # Move autosave files to saves_watcher
            os.rename(save, os.path.join("saves_watcher", save_new_name))
            print(f"Moved autosave file {save} to {save_new_name}")
        files_before = files_after

        #Every 60 seconds, check for excess autosaves
        if i % 60 == 0:
            print("Watching for new autosave files...")
            # Remove Excess autosaves
            autosaves = glob.glob("saves_watcher/*.eu5")
            autosaves = [os.path.basename(f) for f in autosaves]

            # Filter and map saves with valid dates
            autosave_dates = {}
            for save in autosaves:
                date_str = extract_date_from_filename(save)
                if date_str:
                    autosave_dates[save] = months_from_0(date_str)
                else:
                    print(f"Skipping '{save}' - could not extract valid date")

            # Keep only valid saves and sort by date
            autosaves = [s for s in autosaves if s in autosave_dates]
            autosaves.sort(key=lambda name: autosave_dates[name])

            print(autosave_dates)
            to_delete = []
            last_kept_date = None

            for save in autosaves:
                date = autosave_dates[save]

                if last_kept_date is None:
                    # always keep the first (oldest)
                    last_kept_date = date
                    continue

                if date - last_kept_date >= FREQUENCY_MONTHS:
                    # enough time passed
                    last_kept_date = date
                else:
                    # too close delete this save
                    to_delete.append(save)
                    print(f"Marking {save} for deletion; too close to previous kept save")

            for save in to_delete:
                path = os.path.join("saves_watcher", save)
                try:
                    os.remove(path)
                    print(f"Deleted {save}")
                except OSError as e:
                    print(f"Error deleting {save}: {e}")


        i+=1
        sleep(1)
