"""Token-aware autocomplete widget for math expressions and alert conditions."""
import re
from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtWidgets import QLineEdit, QCompleter, QStyledItemDelegate

from src.parsing.computed_series import BUILTIN_FUNCS, get_available_variables_for_dataset


class FormulaLineEdit(QLineEdit):
    """QLineEdit providing substring token autocompletion for formulas, functions, and metrics."""

    def __init__(self, dataset_type="country", parent=None):
        super().__init__(parent)
        self.dataset_type = dataset_type
        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # Enable substring matching across words
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setWidget(self)
        self.completer.activated[str].connect(self._insert_completion)
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

        # If inside an unclosed bracket, match from the bracket
        last_open = text.rfind('[')
        last_close = text.rfind(']')
        if last_open > last_close:
            return text[last_open:]

        # Otherwise match the trailing alphanumeric / underscore word
        match = re.search(r'([a-zA-Z0-9_]+)$', text)
        return match.group(1) if match else ""

    def _insert_completion(self, completion: str):
        cursor_pos = self.cursorPosition()
        token = self._get_current_token()

        start = cursor_pos - len(token)
        end = cursor_pos

        is_function = completion.endswith('(')
        insert_text = f"{completion})" if is_function else completion

        full_text = self.text()
        new_text = full_text[:start] + insert_text + full_text[end:]
        self.setText(new_text)

        # Place cursor inside parentheses if function, otherwise after the insertion
        new_cursor = (start + len(completion)) if is_function else (start + len(insert_text))
        self.setCursorPosition(new_cursor)

    def keyPressEvent(self, event):
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
                current_index = self.completer.popup().currentIndex()
                if current_index.isValid():
                    self._insert_completion(current_index.data())
                    self.completer.popup().hide()
                    event.accept()
                    return

        super().keyPressEvent(event)

        token = self._get_current_token()
        # Trigger when at least 1 letter is typed or opening bracket is entered
        if len(token) >= 1:
            search_prefix = token[1:] if token.startswith('[') else token
            self.completer.setCompletionPrefix(search_prefix)
            popup = self.completer.popup()
            if popup.model().rowCount() > 0:
                popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
                cr = self.cursorRect()
                cr.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 40)
                self.completer.complete(cr)
            else:
                popup.hide()
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