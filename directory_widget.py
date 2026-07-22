"""Просмотр и безопасная очистка каталогов изображений."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from PyQt6.QtCore import QFile, QSize, Qt
from PyQt6.QtGui import QImage, QPixmap, QResizeEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from album_processor.image_io import iter_source_images


class ImagePreview(QLabel):
    """Масштабируемая область предварительного просмотра изображения."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(360, 280)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setText("Выберите изображение")

    def show_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._scale_pixmap()

    def show_message(self, message: str) -> None:
        self._source_pixmap = None
        self.clear()
        self.setText(message)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self._scale_pixmap()

    def _scale_pixmap(self) -> None:
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
        empty_text: str,
        parent: QWidget | None = None,
        *,
        allow_cleanup: bool = True,
    ) -> None:
        super().__init__(parent)
        self._directory = Path()
        self._empty_text = empty_text
        self._cleanup_allowed = allow_cleanup
        self._allow_cleanup = allow_cleanup

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        refresh_button = QPushButton("Обновить список")
        refresh_button.setToolTip("Повторно прочитать содержимое каталога")
        refresh_button.clicked.connect(self.refresh)
        self.clear_button = QPushButton("Очистить…")
        self.clear_button.clicked.connect(self._confirm_cleanup)

        self.header = QHBoxLayout()
        self.header.addWidget(self.path_label, 1)
        self.header.addWidget(refresh_button)
        self.header.addWidget(self.clear_button)
        self.clear_button.setVisible(allow_cleanup)

        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(260)
        self.file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.file_list.currentItemChanged.connect(self._show_selected)
        self.preview = ImagePreview()
        self.details = QLabel()
        self.details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        preview_column = QWidget()
        preview_layout = QVBoxLayout(preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(self.details)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.file_list)
        splitter.addWidget(preview_column)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(self.header)
        layout.addWidget(splitter, 1)

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
        if directory == self._directory:
            return
        self._directory = directory
        self.refresh()

    def refresh(self) -> None:
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
        if dialog.clickedButton() is not clean_button:
            return

        moved, failures = self._trash_images(paths)
        self.refresh()
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
        success, _new_path = QFile.moveToTrash(str(path))
        return success

    def _show_cleanup_message(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
    ) -> None:
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
