import importlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from tools.shared.bootstrap import ensure_repo_paths, PROJECT_ROOT

DEFAULT_REQUIREMENTS_FILE = PROJECT_ROOT / "tools" / "shared" / "requirements.txt" # This is used unless there is a local requirements.txt for the local script

# Map package names to import targets for dependency checks
DEFAULT_MODULE_IMPORT_TARGETS: Dict[str, Tuple[str, Optional[str]]] = {
	"pillow": ("PIL", "Image"),
	"pyqt6": ("PyQt6", None),
}


def _read_requirements(file_path: Path) -> List[str]:
	"""Read requirement names, ignoring version specifiers and comments."""
	if not file_path.exists():
		return []
	requirements = []
	for line in file_path.read_text().splitlines():
		line = line.split("#", 1)[0].strip()
		if not line:
			continue
		pkg = re.split(r"[<>=]", line, maxsplit=1)[0].strip()
		if pkg:
			requirements.append(pkg)
	return requirements


def _build_dependency_checks(requirements: Iterable[str], import_targets: Dict[str, Tuple[str, Optional[str]]]) -> List[Tuple[str, Optional[str]]]:
	return [import_targets.get(req.lower(), (req, None)) for req in requirements]


def _missing_dependencies(checks: Iterable[Tuple[str, Optional[str]]]) -> List[str]:
	missing = []
	for module, submodule in checks:
		name = f"{module}.{submodule}" if submodule else module
		try:
			importlib.import_module(name)
		except ImportError:
			missing.append(module)
	return missing


def ensure_requirements_installed(requirements_file: Optional[Path] = None, module_import_targets: Optional[Dict[str, Tuple[str, Optional[str]]]] = None):
	"""
	Install required packages automatically if they are missing.
	Use requirements_file=None to skip installation (e.g., lightweight scripts).
	"""
	ensure_repo_paths()

	if requirements_file is None:
		return

	req_file = Path(requirements_file)
	if not req_file.exists():
		print(f"Requirements file not found at {req_file}, cannot auto-install.")
		return

	import_targets = module_import_targets or DEFAULT_MODULE_IMPORT_TARGETS
	requirements = _read_requirements(req_file)
	dependency_checks = _build_dependency_checks(requirements, import_targets)
	missing = _missing_dependencies(dependency_checks)

	if not missing:
		return

	print(f"Installing missing dependencies ({', '.join(sorted(set(missing)))})...")
	try:
		subprocess.check_call([
			sys.executable,
			"-m",
			"pip",
			"install",
			"-r",
			str(req_file)
		])
	except Exception as install_error:
		print(f"Automatic dependency installation failed: {install_error}")
