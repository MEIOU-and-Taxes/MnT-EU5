import os
import sys
import traceback
import faulthandler
from PyQt6.QtWidgets import QApplication, QMessageBox

from src.constants import APPDATA_DIR
from src.ui.main_window import MainWindow
from src.widgets.loading_dialog import LoadingDialog

# In windowed mode (console=False), standard streams are None on Windows.
# Redirect them to a crash log in APPDATA so errors can be inspected.
if sys.stderr is None or sys.stdout is None:
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        crash_log_path = os.path.join(APPDATA_DIR, "crash.log")
        _log_file = open(crash_log_path, "a", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = _log_file
        if sys.stdout is None:
            sys.stdout = _log_file
    except Exception:
        pass

if sys.stderr is not None:
    try:
        faulthandler.enable(file=sys.stderr)
    except Exception:
        pass


def _excepthook(exc_type, exc, tb):
    if sys.stderr is not None:
        traceback.print_exception(exc_type, exc, tb, file=sys.stderr)
        try:
            sys.stderr.flush()
        except Exception:
            pass


if __name__ == '__main__':
    try:
        sys.excepthook = _excepthook
        app = QApplication(sys.argv)

        main_window = MainWindow()
        main_window.show()

        loading_dialog = LoadingDialog()
        loading_dialog.show()
        app.processEvents()

        main_window.load_initial_data()
        loading_dialog.close()

        sys.exit(app.exec())
    except Exception as e:
        err_msg = "".join(traceback.format_exc())
        if sys.stderr is not None:
            sys.stderr.write(f"Fatal error: {e}\n{err_msg}\n")
            sys.stderr.flush()
        # If GUI is available, display error dialog before quitting
        if QApplication.instance():
            QMessageBox.critical(None, "Fatal Error", f"A fatal error occurred:\n\n{e}\n\nSee crash.log for details.")