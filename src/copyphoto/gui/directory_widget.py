"""Просмотр и безопасная очистка каталогов изображений в интерфейсе CopyPhoto."""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, TypeVar

from PIL import Image, ImageOps
from PyQt6 import uic
from PyQt6.QtCore import QFile, QObject, QSize, Qt
from PyQt6.QtGui import QImage, QPixmap, QResizeEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QWidget,
)

from copyphoto.album_processor.image_io import iter_source_images


DIRECTORY_FORM_NAME = "directory_widget.ui"
DIRECTORY_FORM = files("copyphoto.gui").joinpath(DIRECTORY_FORM_NAME)
_ObjectT = TypeVar("_ObjectT", bound=QObject)


class ImagePreview(QLabel):
    """Масштабируемая область предварительного просмотра изображения."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Создать область и подготовить хранение исходного изображения."""
        super().__init__(parent)
        self._source_pixmap: QPixmap | None = None

    def show_pixmap(self, pixmap: QPixmap) -> None:
        """Показать изображение, масштабировав его под текущий размер области."""
        self._source_pixmap = pixmap
        self._scale_pixmap()

    def show_message(self, message: str) -> None:
        """Очистить изображение и показать текстовое сообщение."""
        self._source_pixmap = None
        self.clear()
        self.setText(message)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        """Перемасштабировать изображение после изменения размера виджета."""
        super().resizeEvent(event)
        self._scale_pixmap()

    def _scale_pixmap(self) -> None:
        """Вписать исходное изображение в доступную область с сохранением пропорций."""
        if self._source_pixmap is None:
            return
        available = self.size() - QSize(20, 20)
        self.setPixmap(
            self._source_pixmap.scaled(
                available,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class DirectoryWidget(QWidget):
    """Список поддерживаемых изображений каталога и их предпросмотр."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        empty_text: str = "В каталоге нет изображений",
        allow_cleanup: bool = True,
    ) -> None:
        """Загрузить форму просмотра каталога и настроить её поведение."""
        super().__init__(parent)
        self._directory = Path()
        self._empty_text = empty_text
        self._cleanup_allowed = allow_cleanup
        self._allow_cleanup = allow_cleanup
        self._load_form()
        self.refresh_button.clicked.connect(self.refresh)
        self.clear_button.clicked.connect(self._confirm_cleanup)
        self.clear_button.setVisible(allow_cleanup)

        self.file_list.currentItemChanged.connect(self._show_selected)
        self.splitter.setStretchFactor(1, 1)

    def _load_form(self) -> None:
        """Загрузить directory_widget.ui и связать обязательные элементы."""
        with as_file(DIRECTORY_FORM) as form_path:
            loaded = uic.loadUi(str(form_path), self)
        if loaded is not self:
            raise RuntimeError(f"не удалось загрузить форму {DIRECTORY_FORM_NAME}")
        self.header = self._find(QHBoxLayout, "headerLayout")
        self.path_label = self._find(QLabel, "pathLabel")
        self.refresh_button = self._find(QPushButton, "refreshButton")
        self.clear_button = self._find(QPushButton, "clearButton")
        self.file_list = self._find(QListWidget, "fileList")
        self.preview = self._find(ImagePreview, "preview")
        self.details = self._find(QLabel, "details")
        self.splitter = self._find(QSplitter, "splitter")

    def _find(self, object_type: type[_ObjectT], name: str) -> _ObjectT:
        """Найти обязательный объект загруженной формы по имени."""
        found = self.findChild(object_type, name)
        if found is None:
            raise RuntimeError(
                f"в форме {DIRECTORY_FORM_NAME} отсутствует {name}"
            )
        return found

    def configure(self, empty_text: str, *, allow_cleanup: bool = True) -> None:
        """Задать сообщение пустого каталога и доступность его очистки."""
        self._empty_text = empty_text
        self._allow_cleanup = allow_cleanup
        self.clear_button.setVisible(allow_cleanup)
        self.set_cleanup_enabled(self._cleanup_allowed)

    def add_header_action(self, text: str, callback: Any) -> QPushButton:
        """Добавить действие над файлами перед кнопкой очистки."""
        button = QPushButton(text)
        button.clicked.connect(lambda: callback())
        self.header.insertWidget(self.header.count() - 1, button)
        return button

    def add_select_all_action(self) -> QPushButton:
        """Добавить кнопку выделения всех показанных изображений."""
        return self.add_header_action("Выделить все", self.file_list.selectAll)

    def selected_paths(self) -> list[Path]:
        """Вернуть выбранные в списке изображения."""
        return [
            Path(item.data(Qt.ItemDataRole.UserRole))
            for item in self.file_list.selectedItems()
        ]

    def set_directory(self, directory: Path) -> None:
        """Установить отображаемый каталог и обновить список при его изменении."""
        if directory == self._directory:
            return
        self._directory = directory
        self.refresh()

    def refresh(self) -> None:
        """Повторно прочитать каталог, сохранив текущий выбор при возможности."""
        selected_path = None
        current = self.file_list.currentItem()
        if current is not None:
            selected_path = current.data(Qt.ItemDataRole.UserRole)

        self.path_label.setText(str(self._directory))
        self.path_label.setToolTip(str(self._directory))
        self.file_list.clear()
        try:
            paths = iter_source_images(self._directory)
        except OSError as error:
            self.preview.show_message("Не удалось прочитать каталог")
            self.details.setText(str(error))
            return
        for path in paths:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.file_list.addItem(item)
            if str(path) == selected_path:
                self.file_list.setCurrentItem(item)

        if self.file_list.count() == 0:
            self.preview.show_message(self._empty_text)
            self.details.setText("Поддерживаются JPG, PNG, HEIC и HEIF")
        elif self.file_list.currentItem() is None:
            self.file_list.setCurrentRow(0)
        self.clear_button.setEnabled(
            self._allow_cleanup
            and self._cleanup_allowed
            and self.file_list.count() > 0
        )

    def set_cleanup_enabled(self, enabled: bool) -> None:
        """Разрешить очистку, если обработка не выполняется и есть файлы."""
        self._cleanup_allowed = enabled
        self.clear_button.setEnabled(
            self._allow_cleanup and enabled and self.file_list.count() > 0
        )

    def _confirm_cleanup(self) -> None:
        """Запросить подтверждение и переместить изображения в Корзину."""
        try:
            paths = iter_source_images(self._directory)
        except OSError as error:
            self._show_cleanup_message(
                QMessageBox.Icon.Critical,
                "Не удалось прочитать каталог",
                str(error),
            )
            return
        if not paths:
            self._show_cleanup_message(
                QMessageBox.Icon.Information,
                "Каталог уже пуст",
                "Поддерживаемых изображений для удаления нет.",
            )
            return
        if not self._confirm_cleanup_dialog(paths):
            return

        moved, failures = self._trash_images(paths)
        self.refresh()
        self._show_cleanup_result(moved, failures)

    def _confirm_cleanup_dialog(self, paths: list[Path]) -> bool:
        """Показать состав очистки и вернуть подтверждение пользователя."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Очистить каталог")
        dialog.setText(f"Переместить в Корзину изображений: {len(paths)}?")
        dialog.setInformativeText(
            f"Каталог: {self._directory}\n\n"
            "Сам каталог, вложенные папки и остальные типы файлов "
            "будут сохранены."
        )
        clean_button = dialog.addButton(
            "Переместить в Корзину",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            "Отмена",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is clean_button

    def _show_cleanup_result(self, moved: int, failures: list[Path]) -> None:
        """Показать итог полного или частичного перемещения файлов в Корзину."""
        if failures:
            failed_names = ", ".join(path.name for path in failures[:5])
            if len(failures) > 5:
                failed_names += f" и ещё {len(failures) - 5}"
            self._show_cleanup_message(
                QMessageBox.Icon.Warning,
                "Каталог очищен не полностью",
                f"Перемещено в Корзину: {moved}.\n"
                f"Не удалось переместить: {failed_names}",
            )
        else:
            self._show_cleanup_message(
                QMessageBox.Icon.Information,
                "Каталог очищен",
                f"Перемещено в Корзину изображений: {moved}.",
            )

    def _trash_images(self, paths: list[Path]) -> tuple[int, list[Path]]:
        """Переместить только непосредственные файлы текущего каталога."""
        directory = self._directory.resolve()
        moved = 0
        failures: list[Path] = []
        for path in paths:
            try:
                if path.parent.resolve() != directory or not self._move_to_trash(path):
                    failures.append(path)
                else:
                    moved += 1
            except OSError:
                failures.append(path)
        return moved, failures

    @staticmethod
    def _move_to_trash(path: Path) -> bool:
        """Переместить один файл в системную Корзину средствами Qt."""
        success, _new_path = QFile.moveToTrash(str(path))
        return success

    def _show_cleanup_message(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
    ) -> None:
        """Показать результат очистки с русской кнопкой закрытия."""
        dialog = QMessageBox(self)
        dialog.setIcon(icon)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        close_button = dialog.addButton(
            "Закрыть",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.setDefaultButton(close_button)
        dialog.exec()

    def _show_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        """Открыть выбранное изображение и показать его параметры и предпросмотр."""
        if current is None:
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                original_size = image.size
                image.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
                data = image.tobytes("raw", "RGB")
                qt_image = QImage(
                    data,
                    image.width,
                    image.height,
                    image.width * 3,
                    QImage.Format.Format_RGB888,
                ).copy()
            self.preview.show_pixmap(QPixmap.fromImage(qt_image))
            size_megabytes = path.stat().st_size / (1024 * 1024)
            self.details.setText(
                f"{path.name}  •  {original_size[0]} × {original_size[1]}  •  "
                f"{size_megabytes:.2f} МБ"
            )
        except Exception as error:
            self.preview.show_message("Не удалось открыть изображение")
            self.details.setText(f"{path.name}: {error}")
