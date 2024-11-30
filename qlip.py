import sys
import os
import json
import qtawesome as qta
import argparse

from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QListWidgetItem, QVBoxLayout, QHBoxLayout,
    QSystemTrayIcon, QMenu, QAbstractItemView, QMessageBox,
    QPushButton
)
from PySide6.QtGui import QIcon, QAction, QClipboard, QPixmap, QColor, QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, QUrl, QDateTime, QSize


class ClipboardItem:
    _counter = 0  # Class variable to keep track of insertion order

    def __init__(self, data_type, data, favorite=False):
        self.data_type = data_type  # 'text', 'url', 'image', 'file'
        self.data = data  # The actual data
        self.favorite = favorite  # Favorite status
        self.index = ClipboardItem._counter  # Insertion order
        ClipboardItem._counter += 1

    def to_dict(self):
        return {
            'data_type': self.data_type,
            'data': self.data,
            'favorite': self.favorite,
            'index': self.index
        }

    @classmethod
    def from_dict(cls, data):
        item = cls(data['data_type'], data['data'], data['favorite'])
        item.index = data['index']
        return item


class ClipboardManager(QWidget):
    def __init__(self, use_tray=True):
        super().__init__()
        self.setWindowTitle("Qlip")
        # Get the path to the icon
        if hasattr(sys, "_MEIPASS"):
            icon_path = os.path.join(sys._MEIPASS, "qlip.png")
        else:  
            icon_path = "qlip.png"
        self.setWindowIcon(QIcon(icon_path))    
        self.resize(400, 600)
        self.setAcceptDrops(True)  # Enable drag-and-drop

        # Initialize clipboard and items list
        self.clipboard = QApplication.clipboard()
        self.items = []
        self.is_paused = False

        # Set up the list widget (Initialize before loading items)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_item_context_menu)
        self.list_widget.setStyleSheet("""
            QListWidget::item {
                border-bottom: 1px solid #E0E0E0;
                padding: 10px;
            }
            QListWidget::item:selected {
                background-color: #E8EAF6;
                color: #000000;
            }
        """)

        # Set up the layout
        main_layout = QVBoxLayout()

        # Top button layout
        top_button_layout = QHBoxLayout()

        # Delete All button at the top
        self.delete_all_button = QPushButton()
        delete_icon = qta.icon('mdi.delete-empty', color='white')
        self.delete_all_button.setIcon(delete_icon)
        self.delete_all_button.setIconSize(QSize(32, 32)) 
        self.delete_all_button.setText(" Delete All")
        self.delete_all_button.clicked.connect(self.delete_all_items)
        self.delete_all_button.setStyleSheet("""
            QPushButton {
                background-color: #D32F2F;
                color: white;
                border: none;
                padding: 10px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #B71C1C;
            }
        """)
        top_button_layout.addWidget(self.delete_all_button)

        # Add the top button layout to the main layout
        main_layout.addLayout(top_button_layout)

        # Add the list widget to the main layout
        main_layout.addWidget(self.list_widget)

        # Pause/Unpause button at the bottom
        self.pause_button = QPushButton()
        self.update_pause_button()
        self.pause_button.clicked.connect(self.toggle_pause)
        main_layout.addWidget(self.pause_button)

        self.setLayout(main_layout)

        # Load items from file (After initializing list_widget)
        self.load_items_from_file()

        # Check if system tray is available
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable() and use_tray

        if self.tray_available:
            # Set up the system tray icon
            icon = qta.icon('mdi.content-copy', color='white')
            self.tray_icon = QSystemTrayIcon(icon, self)
            self.tray_icon.setToolTip("Qlip")
            self.tray_icon.activated.connect(self.on_tray_icon_activated)

            # Set up the tray icon menu with icons
            tray_menu = QMenu()
            open_icon = qta.icon('mdi.open-in-app')
            open_action = QAction(open_icon, "Open", self)
            open_action.triggered.connect(self.show_window)

            pause_icon = qta.icon('mdi.pause' if not self.is_paused else 'mdi.play')
            pause_action = QAction(pause_icon, "Pause" if not self.is_paused else "Resume", self)
            pause_action.triggered.connect(self.toggle_pause)

            quit_icon = qta.icon('mdi.exit-to-app')
            quit_action = QAction(quit_icon, "Quit", self)
            quit_action.triggered.connect(QApplication.quit)

            tray_menu.addAction(open_action)
            tray_menu.addAction(pause_action)
            tray_menu.addSeparator()
            tray_menu.addAction(quit_action)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()

            self.pause_action = pause_action  # Reference to update text and icon
        else:
            self.tray_icon = None
            self.pause_action = None

        # Connect clipboard changes
        self.clipboard.dataChanged.connect(self.on_clipboard_change)

    def update_pause_button(self):
        if self.is_paused:
            icon = qta.icon('mdi.play', color='white')
            self.pause_button.setIcon(icon)
            self.pause_button.setIconSize(QSize(32, 32))
            self.pause_button.setText(" Resume")
        else:
            icon = qta.icon('mdi.pause', color='white')
            self.pause_button.setIcon(icon)
            self.pause_button.setIconSize(QSize(32, 32))
            self.pause_button.setText(" Pause")
        # Apply Material Design style
        self.pause_button.setStyleSheet("""
            QPushButton {
                background-color: #6200EE;
                color: white;
                border: none;
                padding: 10px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #3700B3;
            }
        """)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.update_pause_button()
        if self.tray_available and self.pause_action:
            # Update the pause action text and icon
            pause_icon = qta.icon('mdi.pause' if not self.is_paused else 'mdi.play')
            self.pause_action.setIcon(pause_icon)
            self.pause_action.setText("Pause" if not self.is_paused else "Resume")

    def delete_all_items(self):
        reply = QMessageBox.question(
            self, "Confirm Delete All",
            "Are you sure you want to delete all items?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.items.clear()
            self.list_widget.clear()
            # Reset the counter
            ClipboardItem._counter = 0

    def on_clipboard_change(self):
        if self.is_paused:
            return

        mime_data = self.clipboard.mimeData()
        self.process_mime_data(mime_data)

    def process_mime_data(self, mime_data):
        # Handle text
        if mime_data.hasText():
            text = mime_data.text()
            if text:
                # Check if it's a URL
                if text.startswith(('http://', 'https://')):
                    data_type = 'url'
                    data = text
                elif text.startswith('file://'):
                    data_type = 'file'
                    # Convert file URL to local path
                    url = QUrl(text)
                    data = url.toLocalFile()
                elif text.startswith('/'):
                    data_type = 'file'
                    data = text
                else:
                    data_type = 'text'
                    data = text

                # Avoid duplicates
                if not any(item.data == data for item in self.items):
                    item = ClipboardItem(data_type, data)
                    self.add_item_to_list(item)
        # Handle images
        elif mime_data.hasImage():
            image = mime_data.imageData()
            pixmap = QPixmap.fromImage(image)
            if not any(isinstance(item.data, QPixmap) and item.data.toImage() == pixmap.toImage() for item in self.items):
                item = ClipboardItem('image', pixmap)
                self.add_item_to_list(item)
        # Handle URLs (files)
        elif mime_data.hasUrls():
            urls = mime_data.urls()
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path:
                        # Avoid duplicates
                        if not any(item.data == file_path for item in self.items):
                            item = ClipboardItem('file', file_path)
                            self.add_item_to_list(item)

    def add_item_to_list(self, clipboard_item):
        # Append the new item to the list
        self.items.append(clipboard_item)
        # Reorder items to keep favorites at the top
        self.reorder_items()

    def on_item_clicked(self, list_item):
        clipboard_item = list_item.data(Qt.UserRole)
        if clipboard_item.data_type == 'text':
            self.clipboard.setText(clipboard_item.data)
            if clipboard_item.data.startswith('/'):
                # Treat as file path
                path = clipboard_item.data
                if os.path.exists(path):
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                else:
                    QMessageBox.warning(self, "Qlip", f"File does not exist: {path}")
            else:
                QMessageBox.information(self, "Qlip", "Text copied to clipboard.")
        elif clipboard_item.data_type == 'url':
            self.clipboard.setText(clipboard_item.data)
            QDesktopServices.openUrl(QUrl(clipboard_item.data))
        elif clipboard_item.data_type == 'file':
            # Copy to clipboard
            self.clipboard.setText(clipboard_item.data)
            path = clipboard_item.data
            if os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            else:
                QMessageBox.warning(self, "Qlip", f"File does not exist: {path}")
        elif clipboard_item.data_type == 'image':
            self.clipboard.setPixmap(clipboard_item.data)
            QMessageBox.information(self, "Qlip", "Image copied to clipboard.")

    def show_item_context_menu(self, position):
        menu = QMenu()
        index = self.list_widget.indexAt(position)
        if not index.isValid():
            return
        list_item = self.list_widget.item(index.row())
        clipboard_item = list_item.data(Qt.UserRole)

        # Delete action
        delete_action = QAction(qta.icon('mdi.delete'), "Delete", self)
        delete_action.triggered.connect(lambda: self.delete_item(list_item))

        # Favorite/Unfavorite action
        if clipboard_item.favorite:
            favorite_action = QAction(qta.icon('mdi.star-off'), "Unfavorite", self)
        else:
            favorite_action = QAction(qta.icon('mdi.star'), "Favorite", self)
        favorite_action.triggered.connect(lambda: self.toggle_favorite_item(list_item))

        menu.addAction(favorite_action)
        menu.addAction(delete_action)

        # For long text items, add 'Save to File'
        if clipboard_item.data_type in ['text', 'url', 'file'] and len(clipboard_item.data) > 180:
            save_action = QAction(qta.icon('mdi.content-save'), "Save to File", self)
            save_action.triggered.connect(lambda: self.save_item_to_file(clipboard_item))
            menu.addAction(save_action)

        menu.exec_(self.list_widget.viewport().mapToGlobal(position))

    def delete_item(self, list_item):
        index = self.list_widget.row(list_item)
        clipboard_item = list_item.data(Qt.UserRole)
        self.items.remove(clipboard_item)
        self.list_widget.takeItem(index)

    def toggle_favorite_item(self, list_item):
        clipboard_item = list_item.data(Qt.UserRole)
        clipboard_item.favorite = not clipboard_item.favorite

        # Update font
        font = list_item.font()
        font.setBold(clipboard_item.favorite)
        list_item.setFont(font)

        # Reorder items
        self.reorder_items()

    def reorder_items(self):
        # Clear the list_widget
        self.list_widget.clear()

        # Sort items: favorites first, then by insertion order
        self.items.sort(key=lambda x: (not x.favorite, x.index))

        # Re-add items to list_widget
        for clipboard_item in self.items:
            if clipboard_item.data_type == 'text':
                display_text = clipboard_item.data[:180] + ('...' if len(clipboard_item.data) > 180 else '')
                list_item = QListWidgetItem(display_text)
            elif clipboard_item.data_type == 'url':
                display_text = clipboard_item.data[:180] + ('...' if len(clipboard_item.data) > 180 else '')
                list_item = QListWidgetItem(display_text)
                list_item.setForeground(QColor('blue'))
            elif clipboard_item.data_type == 'file':
                display_text = clipboard_item.data[:180] + ('...' if len(clipboard_item.data) > 180 else '')
                list_item = QListWidgetItem(display_text)
                list_item.setForeground(QColor('green'))
            elif clipboard_item.data_type == 'image':
                icon = QIcon(clipboard_item.data)
                list_item = QListWidgetItem(icon, "Image")

            # Set bold font if favorite
            font = list_item.font()
            font.setBold(clipboard_item.favorite)
            list_item.setFont(font)

            # Store reference to clipboard_item in QListWidgetItem
            list_item.setData(Qt.UserRole, clipboard_item)

            # Add item to list_widget
            self.list_widget.addItem(list_item)

    def save_item_to_file(self, clipboard_item):
        # Generate filename with short datetime
        datetime_str = QDateTime.currentDateTime().toString('yyyyMMdd_HHmmss')
        filename = f'qlip_save_{datetime_str}.txt'

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(clipboard_item.data)

        # Open the saved file
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(filename)))

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_window()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.tray_available:
            event.ignore()
            self.hide()
            if self.tray_icon:
                self.tray_icon.showMessage(
                    "Qlip",
                    "Application minimized to tray. Click the tray icon to restore.",
                    QSystemTrayIcon.Information,
                    2000
                )
        else:
            # Allow the window to close if system tray is not available
            self.save_items_to_file()
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()  # Close the application
        else:
            super().keyPressEvent(event)

    # Drag-and-Drop Event Handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        mime_data = event.mimeData()
        self.process_mime_data(mime_data)
        event.acceptProposedAction()

    def save_items_to_file(self):
        # Exclude image items from saving
        data = [item.to_dict() for item in self.items if item.data_type != 'image']
        self.item_file = os.path.expanduser("~/.qlip.json")
        with open(self.item_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load_items_from_file(self):
        self.item_file = os.path.expanduser("~/.qlip.json")
        if os.path.exists(self.item_file):
            with open(self.item_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.items = []
                for item_data in data:
                    item = ClipboardItem.from_dict(item_data)
                    self.items.append(item)
                # Update _counter to avoid duplicate indices
                if self.items:
                    ClipboardItem._counter = max(item.index for item in self.items) + 1
                else:
                    ClipboardItem._counter = 0
                # Reorder items in the list widget
                self.reorder_items()

    def cleanup(self):
        self.save_items_to_file()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Apply Material Design style
    app.setStyleSheet("""
        QWidget {
            font-family: Roboto, Arial, sans-serif;
            font-size: 14px;
        }
        QListWidget {
            background-color: #FFFFFF;
            color: #000000;
            border: none;
        }
        QListWidget::item:selected {
            background-color: #E8EAF6;
            color: #000000;
        }
    """)

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Qlip App - Clipboard Manager')
    parser.add_argument('-s', '--standalone', action='store_true', help='Run in standalone mode (no system tray icon)')
    args = parser.parse_args()

    window = ClipboardManager(use_tray=not args.standalone)
    if window.tray_available:
        window.hide()  # Start minimized to tray
    else:
        window.show()

    # Connect the aboutToQuit signal to save items before exiting
    app.aboutToQuit.connect(window.cleanup)

    sys.exit(app.exec())
