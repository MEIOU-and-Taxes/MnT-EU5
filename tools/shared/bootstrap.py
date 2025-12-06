import sys
from pathlib import Path

# Base paths relative to this shared utilities module
SHARED_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SHARED_DIR.parent
PROJECT_ROOT = TOOLS_DIR.parent


def ensure_repo_paths(extra_paths=None):
	"""
	Ensure common repo directories (project root, tools, shared) plus any extras
	are on sys.path so scripts run correctly from any working directory.
	"""
	paths = [PROJECT_ROOT, TOOLS_DIR, SHARED_DIR]
	if extra_paths:
		paths.extend(extra_paths)

	for path in paths:
		path_str = str(path)
		if path_str not in sys.path:
			sys.path.insert(0, path_str)
