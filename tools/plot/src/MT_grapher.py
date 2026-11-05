import sys
import traceback
from PyQt6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.widgets.loading_dialog import LoadingDialog

import sys, traceback, faulthandler

faulthandler.enable()  # dumps a Python stack on hard crashes

def _excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    sys.stdout.flush()
    sys.stderr.flush()


if __name__ == '__main__':
    try:
        # sys.excepthook = _excepthook
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
        print(f"Fatal error: {e}")
        traceback.print_exc()
        input("\nPress Enter to close...")