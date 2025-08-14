"""
Movies Desktop App – Cinematic Edition
--------------------------------------
Modern dark-themed PyQt6 app for managing your movie library with TMDB integration.
Includes:
 - CRUD operations
 - Smooth poster flip with animation
 - First-time TMDB API key popup
 - Cinematic UI styling
 - Toolbar with SVG icons (offline)
"""

from __future__ import annotations
import os
import sys
import json
import shutil
from pathlib import Path
from typing import List, Optional
from urllib.request import urlopen

import requests
from sqlalchemy import Column, Integer, String, Float, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session as SASession

from PyQt6.QtCore import Qt, QSize, QUrl, QPropertyAnimation
from PyQt6.QtGui import QAction, QIcon, QPixmap, QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QMessageBox, QDialog, QDialogButtonBox, QListWidget,
    QListWidgetItem, QTextEdit, QDoubleSpinBox, QFileDialog, QSplitter, QFormLayout,
    QHeaderView, QGraphicsOpacityEffect, QScrollArea, QStackedLayout, QSizePolicy
)

# ---------------------- #
# Config & constants     #
# ---------------------- #
APP_NAME = "Movies Desktop"
CONFIG_FILE = "movies_config.json"
DEFAULT_DB = "Movies.db"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

# ---------------------- #
# Database setup         #
# ---------------------- #
Base = declarative_base()

class Movie(Base):
    __tablename__ = 'Movies'
    id = Column(Integer, primary_key=True)
    title = Column(String, unique=True)
    year = Column(Integer, nullable=False)
    description = Column(String, nullable=False)
    rating = Column(Float, nullable=False)
    ranking = Column(Integer, nullable=False)
    review = Column(String, nullable=False)
    img_url = Column(String, nullable=False)

def ensure_database(db_path: Path) -> None:
    instance_db = Path("instance/Movies.db")
    if not db_path.exists() and instance_db.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(instance_db, db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

def make_session(db_path: Path) -> SASession:
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Session = sessionmaker(bind=engine)
    return Session()

# ---------------------- #
# Config helpers         #
# ---------------------- #
def load_config() -> dict:
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# ---------------------- #
# TMDB helpers           #
# ---------------------- #
def tmdb_search(api_key: str, query: str) -> List[dict]:
    url = "https://api.themoviedb.org/3/search/movie"
    params = {"api_key": api_key, "query": query, "language": "en-US"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("results", [])

def tmdb_details(api_key: str, tmdb_id: int) -> dict:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
    params = {"api_key": api_key, "language": "en-US"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------------- #
# Dialogs                #
# ---------------------- #
class QInputDialogWithText(QDialog):
    def __init__(self, title: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Paste here…")
        layout.addWidget(QLabel(label))
        layout.addWidget(self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def get_text(parent, title, label):
        dlg = QInputDialogWithText(title, label, parent)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return dlg.edit.text().strip(), ok

class FirstTimeAPIKeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TMDB API Key Setup")
        self.resize(420, 220)
        layout = QVBoxLayout(self)
        info_label = QLabel(
            "This app requires a TMDB (The Movie Database) API key to fetch movie info.\n\n"
            "You can get a free key from the link below:"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        link_label = QLabel('<a href="https://www.themoviedb.org/settings/api">Get your TMDB API key</a>')
        link_label.setOpenExternalLinks(True)
        layout.addWidget(link_label)
        self.key_input = QLineEdit(self)
        self.key_input.setPlaceholderText("Enter TMDB API key here…")
        layout.addWidget(self.key_input)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_key(self):
        return self.key_input.text().strip()

class EditDialog(QDialog):
    def __init__(self, movie: Movie, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit: {movie.title}")
        self.movie = movie
        layout = QFormLayout(self)
        self.rating = QDoubleSpinBox(self)
        self.rating.setDecimals(1)
        self.rating.setRange(0.0, 10.0)
        self.rating.setValue(float(movie.rating))
        self.review = QTextEdit(self)
        self.review.setPlainText(movie.review)
        layout.addRow("Rating (0–10):", self.rating)
        layout.addRow("Review:", self.review)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self, session: SASession):
        self.movie.rating = float(self.rating.value())
        self.movie.review = self.review.toPlainText().strip()
        session.commit()

class SearchDialog(QDialog):
    def __init__(self, api_key: str, session: SASession, parent: QWidget | None = None):
        super().__init__(parent)
        self.api_key = api_key
        self.session = session
        self.setWindowTitle("Add Movie – Search TMDB")
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        self.query_edit = QLineEdit(self)
        self.query_edit.setPlaceholderText("Type a movie title…")
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.on_search)
        row.addWidget(self.query_edit)
        row.addWidget(self.search_btn)
        v.addLayout(row)
        self.results = QListWidget(self)
        self.results.itemDoubleClicked.connect(self.on_pick)
        v.addWidget(self.results)
        self.added_movie: Optional[Movie] = None

    def on_search(self):
        q = self.query_edit.text().strip()
        if not q: return
        try:
            data = tmdb_search(self.api_key, q)
        except Exception as e:
            QMessageBox.critical(self, "TMDB Error", str(e))
            return
        self.results.clear()
        for m in data:
            title = m.get("title")
            year = (m.get("release_date") or "0000")[:4]
            item = QListWidgetItem(f"{title} ({year}) – ID: {m.get('id')}")
            item.setData(Qt.ItemDataRole.UserRole, m)
            self.results.addItem(item)

    def on_pick(self, item: QListWidgetItem):
        m = item.data(Qt.ItemDataRole.UserRole)
        try:
            details = tmdb_details(self.api_key, m.get("id"))
        except Exception as e:
            QMessageBox.critical(self, "TMDB Error", str(e))
            return
        if self.session.query(Movie).filter_by(title=details["title"]).first():
            QMessageBox.information(self, "Exists", "Movie already in list.")
            return
        new_movie = Movie(
            title=details["title"],
            year=int((details.get("release_date") or "0000")[:4]),
            description=details.get("overview") or "",
            img_url=(TMDB_IMAGE_BASE + (details.get("poster_path") or "")),
            rating=0.0, ranking=0, review=""
        )
        self.session.add(new_movie)
        self.session.commit()
        self.added_movie = new_movie
        self.accept()

# ---------------------- #
# Poster Flip Widget     #
# ---------------------- #
class PosterFlipWidget(QWidget):
    def __init__(self, width=300, height=450):
        super().__init__()
        self.setFixedSize(width, height)
        self.front_pixmap = None
        self.rating = ""
        self.summary = ""
        self.review = ""

        # Front side (poster)
        self.front_label = QLabel()
        self.front_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.front_label.setStyleSheet("background-color: black; border-radius: 8px;")
        self.front_label.setFixedSize(width, height)

        # Back side container
        self.back_widget = QWidget()
        self.back_widget.setStyleSheet("""
            background-color: #141414;
            color: white;
            border-radius: 8px;
        """)
        back_layout = QVBoxLayout(self.back_widget)
        back_layout.setContentsMargins(8, 8, 8, 8)

        # --- Sticky top area ---
        self.rating_label = QLabel()
        self.rating_label.setStyleSheet("font-size: 16px; color: #E50914; font-weight: bold;")
        self.rating_label.setWordWrap(True)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 14px; color: #e5e5e5;")
        self.summary_label.setWordWrap(True)

        top_area = QVBoxLayout()
        top_area.addWidget(self.rating_label)
        top_area.addWidget(self.summary_label)

        # --- Scrollable review area ---
        self.review_scroll = QScrollArea()
        self.review_scroll.setWidgetResizable(True)
        self.review_scroll.setStyleSheet("border: none;")
        review_container = QWidget()
        review_layout = QVBoxLayout(review_container)
        self.review_label = QLabel()
        self.review_label.setStyleSheet("font-size: 13px; color: #cccccc;")
        self.review_label.setWordWrap(True)
        review_layout.addWidget(self.review_label)
        self.review_scroll.setWidget(review_container)

        # Add sticky + scrollable sections
        back_layout.addLayout(top_area)
        back_layout.addWidget(self.review_scroll)

        # Stack layout for front/back
        self.stack = QStackedLayout(self)
        self.stack.addWidget(self.front_label)
        self.stack.addWidget(self.back_widget)

        # Animation
        self.anim = QPropertyAnimation(self, b"geometry", self)
        self.anim.setDuration(300)
        self.flipped = False

    def setPoster(self, pixmap: QPixmap):
        self.front_pixmap = pixmap.scaled(
            self.width(), self.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.front_label.setPixmap(self.front_pixmap)

    def setDetails(self, rating, summary, review):
        self.rating_label.setText(f"⭐ {rating} / 10")
        self.summary_label.setText(summary)
        self.review_label.setText(f"Review:\n{review}")

    def enterEvent(self, event):
        self.flip_to_back()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.flip_to_front()
        super().leaveEvent(event)

    def flip_to_back(self):
        if not self.flipped:
            self.stack.setCurrentWidget(self.back_widget)
            self.flipped = True

    def flip_to_front(self):
        if self.flipped:
            self.stack.setCurrentWidget(self.front_label)
            self.flipped = False



# ---------------------- #
# Main Window            #
# ---------------------- #
class MainWindow(QMainWindow):
    def __init__(self, session: SASession, db_path: Path, api_key: Optional[str]):
        super().__init__()
        self.session = session
        self.db_path = db_path
        self.api_key = api_key
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon("icon.ico"))

        # Toolbar
        self.toolbar = self.addToolBar("Main")
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setStyleSheet("""
            QToolBar { background-color: #141414; spacing: 6px; border: none; }
            QToolButton { color: white; }
            QToolButton:hover { background-color: #E50914; color: white; }
        """)

        add_act = QAction(QIcon.fromTheme("list-add"), "Add", self)
        add_act.triggered.connect(self.add_movie)
        edit_act = QAction(QIcon.fromTheme("document-edit"), "Edit", self)
        edit_act.triggered.connect(self.edit_selected)
        del_act = QAction(QIcon.fromTheme("edit-delete"), "Delete", self)
        del_act.triggered.connect(self.delete_selected)
        refresh_act = QAction(QIcon.fromTheme("view-refresh"), "Refresh", self)
        refresh_act.triggered.connect(self.refresh)
        export_act = QAction(QIcon.fromTheme("document-save"), "Export CSV", self)
        export_act.triggered.connect(self.export_csv)

        self.toolbar.addAction(refresh_act)
        self.toolbar.addAction(export_act)

        # Main layout
        splitter = QSplitter(self)

        # Left panel (movie table)
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Title", "Year", "Rating", "Ranking", "Review", "Description", "Poster URL"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        left_layout.addWidget(self.table)

        # --- Button row below table ---
        button_row = QHBoxLayout()
        button_row.setContentsMargins(10, 10, 10, 10)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_movie)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self.edit_selected)

        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self.delete_selected)

        button_row.addWidget(add_btn)
        button_row.addWidget(edit_btn)
        button_row.addWidget(del_btn)

        left_layout.addLayout(button_row)
        splitter.addWidget(left)

        # Right panel (Netflix style)
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right.setStyleSheet("""
            background-color: qlineargradient(
                spread:pad, x1:0, y1:0, x2:0, y2:1,
                stop:0 #141414, stop:1 #1a1a1a
            );
        """)

        # --- Poster + Title Side-by-Side Container ---
        poster_container = QWidget()
        poster_layout = QHBoxLayout(poster_container)
        poster_layout.setContentsMargins(20, 0, 20, 0)
        poster_layout.setSpacing(20)

        # Poster widget
        self.poster = PosterFlipWidget(width=360, height=500)
        self.poster.setMaximumHeight(500)
        poster_layout.addWidget(self.poster, alignment=Qt.AlignmentFlag.AlignLeft)

        # Title label beside poster
        self.title_lbl = QLabel("Select a movie…")
        self.title_lbl.setStyleSheet("""
            font-weight: bold;
            font-size: 24px;
            color: white;
            padding: 12px;
        """)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setMinimumWidth(200)
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        poster_layout.addWidget(self.title_lbl, alignment=Qt.AlignmentFlag.AlignTop)

        # Add to right layout
        right_layout.addWidget(poster_container)

        # Scrollable review area
        self.review_scroll = QScrollArea()
        self.review_scroll.setWidgetResizable(True)
        self.review_scroll.setStyleSheet("border: none;")
        review_container = QWidget()
        review_layout = QVBoxLayout(review_container)
        self.details_lbl = QLabel("")
        self.details_lbl.setStyleSheet("color: #e5e5e5; font-size: 15px; padding: 8px;")
        self.details_lbl.setWordWrap(True)
        review_layout.addWidget(self.details_lbl)
        self.review_scroll.setWidget(review_container)
        right_layout.addWidget(self.review_scroll)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Central widget
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        # Apply Netflix style to table & buttons
        self.setStyleSheet("""
            QMainWindow { background-color: #141414; }
            QTableWidget {
                background-color: #000;
                alternate-background-color: #1a1a1a;
                color: white;
                font-size: 14px;
                gridline-color: #222;
            }
            QHeaderView::section {
                background-color: #181818;
                color: white;
                padding: 6px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #E50914;
                color: white;
            }
            QPushButton {
                background-color: #E50914;
                color: white;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #f6121d;
            }
        """)

        self.refresh()

    def fetch_all_movies(self) -> List[Movie]:
        movies = self.session.query(Movie).order_by(Movie.rating.desc()).all()
        for i, m in enumerate(movies, start=1):
            m.ranking = i
        self.session.commit()
        return movies

    def refresh(self):
        movies = self.fetch_all_movies()
        self.table.setRowCount(len(movies))
        for row, m in enumerate(movies):
            self.table.setItem(row, 0, QTableWidgetItem(m.title))
            self.table.setItem(row, 1, QTableWidgetItem(str(m.year)))
            self.table.setItem(row, 2, QTableWidgetItem(f"{m.rating:.1f}"))
            self.table.setItem(row, 3, QTableWidgetItem(str(m.ranking)))
            self.table.setItem(row, 4, QTableWidgetItem(m.review))
            self.table.setItem(row, 5, QTableWidgetItem(m.description))
            self.table.setItem(row, 6, QTableWidgetItem(m.img_url))
        self.on_row_selected()

    def current_movie(self) -> Optional[Movie]:
        row = self.table.currentRow()
        if row < 0:
            return None
        title_item = self.table.item(row, 0)
        if not title_item:
            return None
        return self.session.query(Movie).filter_by(title=title_item.text()).first()

    def on_row_selected(self):
        m = self.current_movie()
        if not m:
            self.poster.front_label.clear() #changed here the front to front_label
            self.title_lbl.setText("Select a movie…")
            self.details_lbl.setText("")
            return
        self.title_lbl.setText(f"{m.title} ({m.year}) – Rating {m.rating:.1f}")
        snippet = m.review if m.review else "No review available."
        self.details_lbl.setText(snippet)
        pixmap = QPixmap()
        try:
            data = urlopen(m.img_url).read()
            pixmap.loadFromData(data)
        except:
            pass
        self.poster.setPoster(pixmap)
        self.poster.setDetails(m.rating, m.description, m.review)

    def add_movie(self):
        if not self.api_key:
            dlg = FirstTimeAPIKeyDialog()
            if dlg.exec() == QDialog.DialogCode.Accepted:
                key = dlg.get_key()
                if key:
                    cfg = load_config()
                    cfg["API_KEY_TMDB"] = key
                    save_config(cfg)
                    self.api_key = key
                else:
                    return
            else:
                return
        dlg = SearchDialog(self.api_key, self.session, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.added_movie:
            self.edit_movie(dlg.added_movie)
            self.refresh()

    def edit_movie(self, movie: Movie):
        dlg = EditDialog(movie, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply(self.session)
            self.refresh()

    def edit_selected(self):
        m = self.current_movie()
        if m:
            self.edit_movie(m)

    def delete_selected(self):
        m = self.current_movie()
        if m and QMessageBox.question(self, "Delete", f"Delete '{m.title}'?") == QMessageBox.StandardButton.Yes:
            self.session.delete(m)
            self.session.commit()
            self.refresh()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Movies", "movies.csv", "CSV Files (*.csv)")
        if not path:
            return
        movies = self.fetch_all_movies()
        import csv
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Title", "Year", "Rating", "Ranking", "Review", "Description", "Poster URL"])
            for m in movies:
                w.writerow([m.title, m.year, m.rating, m.ranking, m.review, m.description, m.img_url])


# ---------------------- #
# App entry point        #
# ---------------------- #
def main():
    app = QApplication(sys.argv)
    db_path = Path(DEFAULT_DB)
    ensure_database(db_path)
    session = make_session(db_path)
    cfg = load_config()
    api_key = os.environ.get("API_KEY_TMDB") or cfg.get("API_KEY_TMDB")
    if not api_key:
        dlg = FirstTimeAPIKeyDialog()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = dlg.get_key()
            if key:
                cfg["API_KEY_TMDB"] = key
                save_config(cfg)
                api_key = key
            else:
                sys.exit(0)
        else:
            sys.exit(0)
    win = MainWindow(session, db_path, api_key)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
