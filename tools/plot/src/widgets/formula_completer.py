"""Token-aware autocomplete widget for math expressions and alert conditions."""
import re
from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtWidgets import QLineEdit, QCompleter, QStyledItemDelegate

from src.parsing.computed_series import BUILTIN_FUNCS, get_available_variables_for_dataset


class FormulaLineEdit(QLineEdit):
    """QLineEdit providing multi-word token autocompletion for formulas and metrics."""

    def __init__(self, dataset_type="country", parent=None):
        super().__init__(parent)
        self.dataset_type = dataset_type
        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setWidget(self)
        self.completer.activated.connect(self._insert_completion)
        self.update_available_words()

    def set_dataset_type(self, dataset_type: str):
        self.dataset_type = dataset_type
        self.update_available_words()

    def update_available_words(self, prior_names=None):
        words = set()
        for fn in sorted(BUILTIN_FUNCS):
            words.add(f"{fn}(")

        vars_set = get_available_variables_for_dataset(self.dataset_type, prior_names or [])
        for v in vars_set:
            if ' ' in v or '-' in v:
                words.add(f"[{v}]")
            else:
                words.add(v)

        model = QStringListModel(sorted(words, key=lambda s: s.lower()), self.completer)
        self.completer.setModel(model)

    def _get_current_token(self):
        cursor_pos = self.cursorPosition()
        text = self.text()[:cursor_pos]
        # Match word tokens or partially typed bracket tokens like `[Credit `
        match = re.search(r'(\[?[a-zA-Z0-9_ -]*)$', text)
        return match.group(1) if match else ""

    def _insert_completion(self, completion: str):
        cursor_pos = self.cursorPosition()
        prefix = self._get_current_token()
        start = cursor_pos - len(prefix)
        end = cursor_pos

        full_text = self.text()
        new_text = full_text[:start] + completion + full_text[end:]
        self.setText(new_text)
        new_cursor = start + len(completion)
        self.setCursorPosition(new_cursor)

    def keyPressEvent(self, event):
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
                current_index = self.completer.popup().currentIndex()
                if current_index.isValid():
                    self.completer.activated.emit(current_index.data())
                    self.completer.popup().hide()
                    event.accept()
                    return

        super().keyPressEvent(event)

        token = self._get_current_token()
        if len(token) >= 2 or (token.startswith('[') and len(token) >= 2):
            self.completer.setCompletionPrefix(token)
            popup = self.completer.popup()
            popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
            cr = self.cursorRect()
            cr.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width() + 20)
            self.completer.complete(cr)
        else:
            self.completer.popup().hide()


class FormulaItemDelegate(QStyledItemDelegate):
    """Table delegate that embeds FormulaLineEdit inside QTableWidget formula cells."""

    def __init__(self, get_dataset_type_fn, parent=None):
        super().__init__(parent)
        self.get_dataset_type_fn = get_dataset_type_fn

    def createEditor(self, parent, option, index):
        d_type = self.get_dataset_type_fn(index.row())
        editor = FormulaLineEdit(dataset_type=d_type, parent=parent)
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.model().data(index, Qt.ItemDataRole.EditRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)