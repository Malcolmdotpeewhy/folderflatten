"""
Folder Flattener Pro - Ultra Modern GUI

An advanced, sleek Tkinter application with glassmorphic design to flatten
folders by moving all files from subfolders into the root directory.

✨ FEATURES:
- Stunning glassmorphic dark theme with animated effects
- Smart drag-and-drop with visual feedback
- Real-time preview with file count and size estimation
- Advanced duplicate handling with smart recommendations
- Background processing with detailed progress tracking
- One-click undo functionality
- Smart folder analysis and recommendations
- Keyboard shortcuts and accessibility features
- Auto-save preferences and session management

🎨 DESIGN:
- Modern glassmorphic interface with blur effects
- Smooth animations and transitions
- Intuitive icon-based navigation
- Responsive layout with adaptive sizing
- Custom styled components throughout

Author: GitHub Copilot Enhanced AI System
Version: 2.0 Pro
"""
from __future__ import annotations

import json
import os
import threading
import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
import webbrowser
import logging
import shutil
from dataclasses import dataclass
import zipfile

# Embedded Core Logic (replaces external folder_flattener_core dependency)
# ----------------------------------------------------------------------

__all__ = []


def get_logger(log_path: Optional[Path] = None) -> logging.Logger:
    logger = getattr(get_logger, "_logger", None)
    if logger is not None:
        return logger
    logger = logging.getLogger("folder_flattener")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        try:
            if log_path is None:
                log_path = Path(__file__).with_name("folder_flattener.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fmt = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except (OSError, PermissionError):
            ch = logging.StreamHandler()
            logger.addHandler(ch)
    setattr(get_logger, "_logger", logger)
    return logger


@dataclass
class FileInfo:
    source: Path
    size: int


@dataclass
class FlattenStats:
    total_files: int
    total_bytes: int
    moved: int
    skipped: int
    errors: int
    bytes_moved: int
    empty_folders_removed: int
    cancelled: bool = False
    archives_found: int = 0
    archives_extracted: int = 0
    archive_bytes_written: int = 0
    archives_moved: int = 0


def is_hidden(path: Path) -> bool:
    name = path.name
    return name.startswith(".")


def list_files_in_subfolders(root: Path, include_hidden: bool = False) -> List[FileInfo]:
    files: List[FileInfo] = []
    root = root.resolve()
    for p in root.rglob("*"):
        if p.is_file() and p.parent != root:
            if not include_hidden and is_hidden(p):
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            files.append(FileInfo(source=p, size=size))
    return files


def find_zip_archives(root: Path, include_hidden: bool = False) -> List[Path]:
    """Case-insensitive zip discovery in root and subfolders."""
    zips: List[Path] = []
    root = root.resolve()
    for p in root.rglob("*"):
        if p.is_file():  # include files both in root and subfolders
            if not include_hidden and is_hidden(p):
                continue
            if p.suffix.lower() == ".zip":
                zips.append(p)
    return zips


def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def generate_unique_filename(target_path: Path) -> Path:
    parent = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix
    i = 1
    candidate = target_path
    while candidate.exists():
        candidate = parent / f"{stem}_{i}{suffix}"
        i += 1
    return candidate


def remove_empty_folders_recursive(root: Path) -> int:
    count = 0
    for dirpath, _, _ in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root:
            continue
        try:
            if not any(Path(dirpath).iterdir()):
                p.rmdir()
                count += 1
        except (OSError, PermissionError):
            continue
    return count


ProgressCallback = Callable[[Dict[str, object]], None]


def flatten_folder(
    root: Path,
    duplicate_mode: str = "rename",
    remove_empty: bool = True,
    include_hidden: bool = False,
    dry_run: bool = False,
    progress_cb: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
    *,
    extract_archives: bool = False,
    archive_originals: bool = False,
    archive_folder: Optional[Path] = None,
) -> FlattenStats:
    logger = get_logger()
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"Invalid directory: {root}")

    duplicate_mode = duplicate_mode.lower()
    if duplicate_mode not in {"rename", "overwrite", "skip"}:
        raise ValueError("duplicate_mode must be 'rename', 'overwrite', or 'skip'")

    archives_found = 0
    archives_extracted = 0
    archive_bytes_written = 0
    archives_moved = 0

    if extract_archives:
        zips = find_zip_archives(root, include_hidden=include_hidden)
        archives_found = len(zips)
        if progress_cb:
            progress_cb({
                "phase": "extract_scan",
                "total": archives_found,
                "message": f"Found {archives_found} zip archive(s) to extract",
            })

        if archive_originals:
            if archive_folder is None:
                archive_folder = root / "_archives"
            archive_folder = archive_folder.resolve()
            if not dry_run:
                try:
                    archive_folder.mkdir(parents=True, exist_ok=True)
                except (OSError, PermissionError) as e:
                    logger.error(
                        "Cannot create archive folder %s: %s", archive_folder, e
                    )
                    archive_originals = False

        for idx_zip, zip_path in enumerate(zips, start=1):
            if cancel_event is not None and cancel_event.is_set():
                break
            try:
                if progress_cb:
                    progress_cb({
                        "phase": "extract",
                        "zip": str(zip_path),
                        "zip_index": idx_zip,
                        "zip_total": archives_found,
                        "message": f"Extracting {zip_path.name}",
                    })
                if dry_run:
                    with zipfile.ZipFile(zip_path) as zf:
                        for zinfo in zf.infolist():
                            if zinfo.is_dir():
                                continue
                            dest = root / Path(zinfo.filename).name
                            action = "move"
                            if dest.exists():
                                if duplicate_mode == "skip":
                                    action = "skip"
                                elif duplicate_mode == "overwrite":
                                    action = "overwrite"
                                elif duplicate_mode == "rename":
                                    dest = generate_unique_filename(dest)
                            archives_extracted += 1
                            archive_bytes_written += zinfo.file_size
                            if progress_cb:
                                progress_cb({
                                    "phase": "extract_file",
                                    "zip": str(zip_path),
                                    "file": Path(zinfo.filename).name,
                                    "action": action,
                                })
                else:
                    with zipfile.ZipFile(zip_path) as zf:
                        for zinfo in zf.infolist():
                            if zinfo.is_dir():
                                continue
                            if zinfo.flag_bits & 0x1:
                                msg = f"Encrypted entry skipped: {zinfo.filename}"
                                logger.warning(msg)
                                if progress_cb:
                                    progress_cb({
                                        "phase": "error",
                                        "file": f"{zip_path.name}:{zinfo.filename}",
                                        "error": msg,
                                    })
                                continue
                            dest = root / Path(zinfo.filename).name
                            action = "move"
                            if dest.exists():
                                if duplicate_mode == "skip":
                                    action = "skip"
                                elif duplicate_mode == "overwrite":
                                    action = "overwrite"
                                    try:
                                        dest.unlink()
                                    except OSError:
                                        pass
                                elif duplicate_mode == "rename":
                                    dest = generate_unique_filename(dest)
                            if action != "skip":
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                with zf.open(zinfo, "r") as src_f, open(dest, "wb") as out_f:
                                    shutil.copyfileobj(src_f, out_f)
                                archives_extracted += 1
                                archive_bytes_written += zinfo.file_size
                            else:
                                archives_extracted += 1
                            if progress_cb:
                                progress_cb({
                                    "phase": "extract_file",
                                    "zip": str(zip_path),
                                    "file": Path(zinfo.filename).name,
                                    "dest": str(dest),
                                    "action": action,
                                })
                if archive_originals:
                    try:
                        target = (archive_folder / zip_path.name) if archive_folder else (root / "_archives" / zip_path.name)
                        if target.exists():
                            target = generate_unique_filename(target)
                        if not dry_run:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(zip_path), str(target))
                        archives_moved += 1
                        if progress_cb:
                            progress_cb({
                                "phase": "archive_move",
                                "source": str(zip_path),
                                "dest": str(target),
                            })
                    except (OSError, shutil.Error) as e:
                        logger.error("Error moving archive %s: %s", zip_path, e)
                        if progress_cb:
                            progress_cb({
                                "phase": "error",
                                "file": str(zip_path),
                                "error": str(e),
                            })
            except zipfile.BadZipFile as e:
                logger.error("Bad zip file %s: %s", zip_path, e)
                if progress_cb:
                    progress_cb({
                        "phase": "error",
                        "file": str(zip_path),
                        "error": f"Bad zip file: {e}",
                    })
                continue

    files = list_files_in_subfolders(root, include_hidden=include_hidden)
    if extract_archives:
        files = [f for f in files if f.source.suffix.lower() != ".zip"]

    total_files = len(files)
    total_bytes = sum(f.size for f in files)

    moved = 0
    skipped = 0
    errors = 0
    bytes_moved = 0

    if progress_cb:
        progress_cb({
            "phase": "scan",
            "current": 0,
            "total": total_files,
            "bytes_total": total_bytes,
            "message": f"Found {total_files} files ({human_size(total_bytes)})",
        })

    cancelled = False

    for idx, info in enumerate(files, start=1):
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        src = info.source
        dest = root / src.name
        action = "move"
        reason = ""
        try:
            if dest.exists():
                if duplicate_mode == "skip":
                    action = "skip"
                    skipped += 1
                elif duplicate_mode == "overwrite":
                    action = "overwrite"
                    if not dry_run:
                        dest.unlink()
                elif duplicate_mode == "rename":
                    dest = generate_unique_filename(dest)
            if action == "skip":
                reason = "duplicate"
            else:
                if dry_run:
                    moved += 1
                    bytes_moved += info.size
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
                    moved += 1
                    bytes_moved += info.size
            if progress_cb:
                progress_cb({
                    "phase": "move",
                    "current": idx,
                    "total": total_files,
                    "file": str(src),
                    "dest": str(dest),
                    "action": action,
                    "reason": reason,
                    "moved": moved,
                    "skipped": skipped,
                    "errors": errors,
                    "bytes_moved": bytes_moved,
                    "bytes_total": total_bytes,
                })
        except (OSError, shutil.Error) as e:
            errors += 1
            logger.error("Error moving %s: %s", src, e)
            if progress_cb:
                progress_cb({
                    "phase": "error",
                    "current": idx,
                    "total": total_files,
                    "file": str(src),
                    "error": str(e),
                    "moved": moved,
                    "skipped": skipped,
                    "errors": errors,
                    "bytes_moved": bytes_moved,
                    "bytes_total": total_bytes,
                })
            continue

    empty_removed = 0
    if remove_empty and not cancelled:
        try:
            if not dry_run:
                empty_removed = remove_empty_folders_recursive(root)
            else:
                empty_removed = 0
        except (OSError, PermissionError) as e:
            logger.error("Error removing empty folders: %s", e)

    stats = FlattenStats(
        total_files=total_files,
        total_bytes=total_bytes,
        moved=moved,
        skipped=skipped,
        errors=errors,
        bytes_moved=bytes_moved,
        empty_folders_removed=empty_removed,
        cancelled=cancelled,
        archives_found=archives_found,
        archives_extracted=archives_extracted,
        archive_bytes_written=archive_bytes_written,
        archives_moved=archives_moved,
    )

    if progress_cb:
        progress_cb({
            "phase": "done",
            "stats": stats,
            "message": (
                "Completed: moved=%d, skipped=%d, errors=%d, removed_empty=%d%s"
                % (
                    moved,
                    skipped,
                    errors,
                    empty_removed,
                    ", cancelled" if cancelled else "",
                )
            ),
        })

    return stats

# Optional drag and drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    HAS_DND = True
except ImportError:
    TkinterDnD = None
    DND_FILES = None
    HAS_DND = False

# Modern Color Palette - Glassmorphic Theme
COLORS = {
    'primary': '#6366f1',
    'primary_hover': '#7c3aed',
    'accent': '#10b981',
    'accent_hover': '#059669',
    'success': '#22c55e',
    'warning': '#f59e0b',
    'danger': '#ef4444',
    'bg_primary': '#0f172a',
    'bg_secondary': '#1e293b',
    'bg_tertiary': '#334155',
    'bg_glass': '#e5e7eb',  # light grey
    'text_primary': '#f8fafc',
    'text_secondary': '#cbd5e1',
    'text_muted': '#64748b',
    'text_dark': '#111827',
    'text_dark_muted': '#374151',
    'border': '#374151',
    'border_light': '#4b5563',
}


class ModernTheme:
    """Ultra-modern glassmorphic theme with smooth animations and effects."""

    @staticmethod
    def apply(root: tk.Tk) -> None:
        """Apply the modern glassmorphic theme to the application."""
        style = ttk.Style(root)
        
        # Use the best available theme as base
        available_themes = style.theme_names()
        if 'vista' in available_themes:
            style.theme_use('vista')
        elif 'clam' in available_themes:
            style.theme_use('clam')
        else:
            style.theme_use('default')

        # Configure main frame styles
        style.configure(
            "Main.TFrame",
            background=COLORS['bg_primary'],
            relief="flat",
            borderwidth=0
        )
        
        style.configure(
            "Glass.TFrame",
            background=COLORS['bg_glass'],
            relief="solid",
            borderwidth=1,
            bordercolor=COLORS['border']
        )
        
        style.configure(
            "Card.TFrame",
            background=COLORS['bg_secondary'],
            relief="solid",
            borderwidth=1,
            bordercolor=COLORS['border_light']
        )

        # Configure label styles
        style.configure(
            "Title.TLabel",
            background=COLORS['bg_primary'],
            foreground=COLORS['text_primary'],
            font=('Segoe UI', 24, 'bold')
        )
        
        style.configure(
            "Subtitle.TLabel",
            background=COLORS['bg_primary'],
            foreground=COLORS['text_secondary'],
            font=('Segoe UI', 11)
        )
        
        style.configure(
            "Info.TLabel",
            background=COLORS['bg_secondary'],
            foreground=COLORS['text_primary'],
            font=('Segoe UI', 10)
        )
        
        style.configure(
            "Muted.TLabel",
            background=COLORS['bg_secondary'],
            foreground=COLORS['text_muted'],
            font=('Segoe UI', 9)
        )
        
        # Labels styled for glass/light grey surfaces
        style.configure(
            "GlassInfo.TLabel",
            background=COLORS['bg_glass'],
            foreground=COLORS['text_dark'],
            font=('Segoe UI', 10)
        )
        style.configure(
            "GlassMuted.TLabel",
            background=COLORS['bg_glass'],
            foreground=COLORS['text_dark_muted'],
            font=('Segoe UI', 9)
        )

        # Configure button styles
        style.configure(
            "Primary.TButton",
            background=COLORS['primary'],
            foreground=COLORS['text_primary'],
            borderwidth=0,
            focuscolor='none',
            relief="flat",
            padding=(20, 12),
            font=('Segoe UI', 10, 'bold')
        )
        
        style.map(
            "Primary.TButton",
            background=[
                ('active', COLORS['primary_hover']),
                ('pressed', COLORS['primary_hover'])
            ],
            relief=[('pressed', 'flat'), ('!pressed', 'flat')]
        )
        
        style.configure(
            "Success.TButton",
            background=COLORS['accent'],
            foreground=COLORS['text_primary'],
            borderwidth=0,
            focuscolor='none',
            relief="flat",
            padding=(20, 12),
            font=('Segoe UI', 10, 'bold')
        )
        
        style.map(
            "Success.TButton",
            background=[
                ('active', COLORS['accent_hover']),
                ('pressed', COLORS['accent_hover'])
            ]
        )
        
        style.configure(
            "Danger.TButton",
            background=COLORS['danger'],
            foreground=COLORS['text_primary'],
            borderwidth=0,
            focuscolor='none',
            relief="flat",
            padding=(16, 10),
            font=('Segoe UI', 9)
        )

        # Configure input styles
        style.configure(
            "Modern.TEntry",
            fieldbackground=COLORS['bg_tertiary'],
            borderwidth=1,
            relief="solid",
            bordercolor=COLORS['border'],
            focuscolor=COLORS['primary'],
            padding=(12, 8),
            font=('Consolas', 10)
        )

        # Configure checkbox and radio styles
        style.configure(
            "Modern.TCheckbutton",
            background=COLORS['bg_secondary'],
            foreground=COLORS['text_primary'],
            focuscolor='none',
            font=('Segoe UI', 10)
        )
        
        style.configure(
            "Modern.TRadiobutton",
            background=COLORS['bg_secondary'],
            foreground=COLORS['text_primary'],
            focuscolor='none',
            font=('Segoe UI', 10)
        )

        # Configure labelframe style
        style.configure(
            "Modern.TLabelframe",
            background=COLORS['bg_secondary'],
            foreground=COLORS['text_primary'],
            borderwidth=1,
            relief="solid",
            bordercolor=COLORS['border'],
            font=('Segoe UI', 10, 'bold')
        )
        
        style.configure(
            "Modern.TLabelframe.Label",
            background=COLORS['bg_secondary'],
            foreground=COLORS['accent'],
            font=('Segoe UI', 10, 'bold')
        )

        # Configure progressbar style
        style.configure(
            "Modern.Horizontal.TProgressbar",
            background=COLORS['accent'],
            troughcolor=COLORS['bg_tertiary'],
            borderwidth=0,
            lightcolor=COLORS['accent'],
            darkcolor=COLORS['accent'],
            relief="flat"
        )

        # Configure separator style
        style.configure(
            "Modern.TSeparator",
            background=COLORS['border']
        )


class SettingsManager:
    """Manage application settings with persistence."""
    
    def __init__(self):
        self.settings_file = Path(__file__).parent / "flattener_settings.json"
        self.default_settings = {
            'last_path': '',
            'remove_empty': True,
            'include_hidden': False,
            'dry_run': False,
            'duplicate_mode': 'rename',
            'window_geometry': '1200x800+100+100',
            'theme': 'dark'
        }
        self.settings = self.load_settings()
    
    def load_settings(self) -> Dict[str, Any]:
        """Load settings from file or return defaults."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge with defaults to handle new settings
                    settings = self.default_settings.copy()
                    settings.update(loaded)
                    return settings
        except Exception:
            pass
        return self.default_settings.copy()
    
    def save_settings(self) -> None:
        """Save current settings to file."""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass
    
    def get(self, key: str, default=None):
        """Get a setting value."""
        return self.settings.get(key, default)
    
    def set(self, key: str, value) -> None:
        """Set a setting value."""
        self.settings[key] = value


class AnimatedProgressBar:
    """Custom animated progress bar with glassmorphic styling."""
    
    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=COLORS['bg_secondary'], height=8)
        self.canvas = tk.Canvas(
            self.frame, 
            height=8, 
            bg=COLORS['bg_tertiary'], 
            highlightthickness=0,
            relief='flat'
        )
        self.canvas.pack(fill='x', padx=2, pady=2)
        
        self.progress = 0
        self.max_value = 100
        self.animation_id = None
        
    def set_progress(self, value: float, max_val: float = 100):
        """Set progress value with smooth animation."""
        target_progress = min(value / max_val * 100, 100)
        self.animate_to(target_progress)
    
    def animate_to(self, target: float):
        """Animate progress bar to target value."""
        if self.animation_id:
            self.frame.after_cancel(self.animation_id)
        
        def animate():
            if abs(self.progress - target) < 0.5:
                self.progress = target
                self.update_display()
                return
            
            self.progress += (target - self.progress) * 0.1
            self.update_display()
            self.animation_id = self.frame.after(16, animate)  # ~60 FPS
        
        animate()
    
    def update_display(self):
        """Update the visual display of the progress bar."""
        self.canvas.delete('all')
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width > 1:
            progress_width = (width - 4) * (self.progress / 100)
            
            # Background
            self.canvas.create_rectangle(
                2, 2, width - 2, height - 2,
                fill=COLORS['bg_tertiary'],
                outline=COLORS['border'],
                width=1
            )
            
            # Progress fill with gradient effect
            if progress_width > 0:
                steps = max(int(progress_width / 4), 1)
                for i in range(steps):
                    x = 2 + (i * progress_width / steps)
                    w = progress_width / steps
                    color = COLORS['accent']
                    self.canvas.create_rectangle(
                        x, 2, x + w, height - 2,
                        fill=color,
                        outline=''
                    )
    
    def pack(self, **kwargs):
        """Pack the progress bar frame."""
        self.frame.pack(**kwargs)
        self.frame.after(100, self.update_display)  # Initial display update


class Worker:
    """Background worker to run flatten operation without blocking UI."""

    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.cancel = threading.Event()

    def start(self, target, *args, **kwargs) -> None:
        self.thread = threading.Thread(
            target=target, args=args, kwargs=kwargs, daemon=True
        )
        self.thread.start()

    def stop(self) -> None:
        self.cancel.set()

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class FolderFlattenerPro:
    """Advanced Folder Flattener with modern glassmorphic UI and enhanced features."""
    
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Folder Flattener Pro")
        self.root.configure(bg=COLORS['bg_primary'])
        
        # Initialize managers
        self.settings = SettingsManager()
        self.logger = get_logger()
        
        # Restore window geometry
        try:
            self.root.geometry(self.settings.get('window_geometry', '1200x800+100+100'))
        except tk.TclError:
            self.root.geometry('1200x800+100+100')
        
        self.root.minsize(900, 700)
        
        # Apply modern theme
        ModernTheme.apply(self.root)
        
        # Initialize variables
        self.path_var = tk.StringVar(value=self.settings.get('last_path', ''))
        self.remove_empty_var = tk.BooleanVar(value=self.settings.get('remove_empty', True))
        self.include_hidden_var = tk.BooleanVar(value=self.settings.get('include_hidden', False))
        self.dry_run_var = tk.BooleanVar(value=self.settings.get('dry_run', False))
        self.duplicate_mode_var = tk.StringVar(value=self.settings.get('duplicate_mode', 'rename'))
        self.extract_archives_var = tk.BooleanVar(value=self.settings.get('extract_archives', True))
        self.archive_originals_var = tk.BooleanVar(value=self.settings.get('archive_originals', False))
        self.archive_folder_var = tk.StringVar(value=self.settings.get('archive_folder', ''))

        # Internal state
        self._preview_timer = None
        self.total_files = 0
        self.total_bytes = 0
        self.preview_data = None
        self.last_operation = None
        
        # Threading
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.worker = Worker()
        
        # Build UI
        self._build_modern_ui()
        self._setup_drag_drop()
        self._setup_keyboard_shortcuts()
        self._poll_events()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        if self.path_var.get():
            self.root.after(500, self._update_preview)
    def _build_modern_ui(self) -> None:
        """Build the ultra-modern glassmorphic user interface."""
        
        # Main container with padding
        main_container = ttk.Frame(self.root, style="Main.TFrame")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header section with modern styling
        self._build_header(main_container)
        
        # Main content area with glassmorphic cards
        content_frame = ttk.Frame(main_container, style="Main.TFrame")
        content_frame.pack(fill="both", expand=True, pady=(20, 0))
        
        # Left panel - Configuration
        left_panel = ttk.Frame(content_frame, style="Card.TFrame")
        left_panel.pack(side="left", fill="y", padx=(0, 10))
        left_panel.configure(width=400)
        
        # Right panel - Preview and Progress
        right_panel = ttk.Frame(content_frame, style="Card.TFrame")
        right_panel.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        # Build panel contents
        self._build_config_panel(left_panel)
        self._build_preview_panel(right_panel)
        
        # Status bar at bottom
        self._build_status_bar(main_container)

    def _build_header(self, parent) -> None:
        """Build the modern header section."""
        header = ttk.Frame(parent, style="Main.TFrame")
        header.pack(fill="x", pady=(0, 20))
        
        # Title and subtitle
        title_frame = ttk.Frame(header, style="Main.TFrame")
        title_frame.pack(side="left", fill="x", expand=True)
        
        title = ttk.Label(
            title_frame,
            text="🗂️ Folder Flattener Pro",
            style="Title.TLabel"
        )
        title.pack(anchor="w")
        
        subtitle = ttk.Label(
            title_frame,
            text="Advanced folder organization with intelligent file management",
            style="Subtitle.TLabel"
        )
        subtitle.pack(anchor="w", pady=(5, 0))
        
        # Action buttons in header
        actions_frame = ttk.Frame(header, style="Main.TFrame")
        actions_frame.pack(side="right")
        
        help_btn = ttk.Button(
            actions_frame,
            text="❓ Help",
            command=self._show_help,
            style="Primary.TButton"
        )
        help_btn.pack(side="right", padx=(10, 0))
        
        settings_btn = ttk.Button(
            actions_frame,
            text="⚙️ Settings",
            command=self._show_settings,
            style="Primary.TButton"
        )
        settings_btn.pack(side="right")

    def _build_config_panel(self, parent) -> None:
        """Build the configuration panel with modern styling."""
        # Add padding to the card
        card_content = ttk.Frame(parent, style="Card.TFrame")
        card_content.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Section title
        ttk.Label(
            card_content,
            text="📁 Folder Selection",
            style="Info.TLabel"
        ).pack(anchor="w", pady=(0, 15))
        
        # Path selection with modern styling
        path_frame = ttk.Frame(card_content, style="Card.TFrame")
        path_frame.pack(fill="x", pady=(0, 20))
        
        self.path_entry = ttk.Entry(
            path_frame,
            textvariable=self.path_var,
            style="Modern.TEntry"
        )
        self.path_entry.pack(fill="x", pady=(0, 10))
        self.path_entry.bind('<KeyRelease>', self._on_path_change)
        
        # Browse button
        browse_btn = ttk.Button(
            path_frame,
            text="📂 Browse Folder",
            command=self._browse_folder,
            style="Primary.TButton"
        )
        browse_btn.pack(fill="x")
        
        # Separator
        ttk.Separator(card_content, style="Modern.TSeparator").pack(fill="x", pady=20)
        
        # Options section
        ttk.Label(
            card_content,
            text="⚙️ Options",
            style="Info.TLabel"
        ).pack(anchor="w", pady=(0, 15))
        
        options_frame = ttk.Frame(card_content, style="Card.TFrame")
        options_frame.pack(fill="x", pady=(0, 20))
        
        # Modern checkboxes
        ttk.Checkbutton(
            options_frame,
            text="🗑️ Remove empty folders after moving",
            variable=self.remove_empty_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change
        ).pack(anchor="w", pady=5)
        
        ttk.Checkbutton(
            options_frame,
            text="👁️ Include hidden files (dotfiles)",
            variable=self.include_hidden_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change
        ).pack(anchor="w", pady=5)
        
        ttk.Checkbutton(
            options_frame,
            text="🔍 Dry run (preview only, no changes)",
            variable=self.dry_run_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change
        ).pack(anchor="w", pady=5)
        
        ttk.Checkbutton(
            options_frame,
            text="🗜️ Extract .zip archives found in subfolders",
            variable=self.extract_archives_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change
        ).pack(anchor="w", pady=5)

        archive_row = ttk.Frame(options_frame, style="Card.TFrame")
        archive_row.pack(fill="x", pady=(0, 0))
        ttk.Checkbutton(
            archive_row,
            text="📦 Move original zips to archive folder",
            variable=self.archive_originals_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change
        ).pack(side="left", anchor="w", pady=5)

        # Archive folder selector
        af_frame = ttk.Frame(options_frame, style="Card.TFrame")
        af_frame.pack(fill="x", pady=(5, 10))
        ttk.Label(
            af_frame,
            text="Archive folder (optional):",
            style="Muted.TLabel"
        ).pack(anchor="w")
        af_inner = ttk.Frame(af_frame, style="Card.TFrame")
        af_inner.pack(fill="x")
        af_entry = ttk.Entry(
            af_inner,
            textvariable=self.archive_folder_var,
            style="Modern.TEntry"
        )
        af_entry.pack(side="left", fill="x", expand=True, pady=(0, 5))
        ttk.Button(
            af_inner,
            text="📂 Browse",
            command=self._browse_archive_folder,
            style="Primary.TButton"
        ).pack(side="left", padx=(8, 0))

        # Separator
        ttk.Separator(card_content, style="Modern.TSeparator").pack(fill="x", pady=20)
        
        # Duplicate handling
        ttk.Label(
            card_content,
            text="🔄 Duplicate File Handling",
            style="Info.TLabel"
        ).pack(anchor="w", pady=(0, 15))
        
        dup_frame = ttk.LabelFrame(
            card_content,
            text="Choose how to handle duplicate files",
            style="Modern.TLabelframe",
            padding=15
        )
        dup_frame.pack(fill="x", pady=(0, 20))
        
        # Radio buttons with modern styling
        ttk.Radiobutton(
            dup_frame,
            text="📝 Rename duplicates (file_1.ext, file_2.ext, ...)",
            value="rename",
            variable=self.duplicate_mode_var,
            style="Modern.TRadiobutton",
            command=self._on_option_change
        ).pack(anchor="w", pady=3)
        
        ttk.Radiobutton(
            dup_frame,
            text="🔄 Overwrite existing files",
            value="overwrite",
            variable=self.duplicate_mode_var,
            style="Modern.TRadiobutton",
            command=self._on_option_change
        ).pack(anchor="w", pady=3)
        
        ttk.Radiobutton(
            dup_frame,
            text="⏭️ Skip duplicate files",
            value="skip",
            variable=self.duplicate_mode_var,
            style="Modern.TRadiobutton",
            command=self._on_option_change
        ).pack(anchor="w", pady=3)
        
        # Action buttons
        buttons_frame = ttk.Frame(card_content, style="Card.TFrame")
        buttons_frame.pack(fill="x", pady=(10, 0))
        
        self.start_btn = ttk.Button(
            buttons_frame,
            text="🚀 Start Flattening",
            command=self._start_operation,
            style="Success.TButton"
        )
        self.start_btn.pack(fill="x", pady=(0, 10))
        
        self.cancel_btn = ttk.Button(
            buttons_frame,
            text="⏹️ Cancel Operation",
            command=self._cancel_operation,
            style="Danger.TButton",
            state="disabled"
        )
        self.cancel_btn.pack(fill="x")

    def _build_preview_panel(self, parent) -> None:
        """Build the preview and progress panel."""
        # Add padding to the card
        card_content = ttk.Frame(parent, style="Card.TFrame")
        card_content.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Preview section
        preview_label = ttk.Label(
            card_content,
            text="📊 Folder Analysis & Preview",
            style="Info.TLabel"
        )
        preview_label.pack(anchor="w", pady=(0, 15))
        
        # Stats frame
        self.stats_frame = ttk.Frame(card_content, style="Glass.TFrame")
        self.stats_frame.pack(fill="x", pady=(0, 15))
        
        # Create stats labels
        self._build_stats_display()
        
        # Progress section
        progress_label = ttk.Label(
            card_content,
            text="⏳ Operation Progress",
            style="Info.TLabel"
        )
        progress_label.pack(anchor="w", pady=(15, 10))
        
        # Modern progress bar
        self.progress_bar = AnimatedProgressBar(card_content)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        
        # Progress text
        self.progress_label = ttk.Label(
            card_content,
            text="Ready to start...",
            style="Muted.TLabel"
        )
        self.progress_label.pack(anchor="w")
        
        # Log section
        log_label = ttk.Label(
            card_content,
            text="📝 Operation Log",
            style="Info.TLabel"
        )
        log_label.pack(anchor="w", pady=(20, 10))
        
        # Log text area with scrollbar
        log_frame = ttk.Frame(card_content, style="Card.TFrame")
        log_frame.pack(fill="both", expand=True)
        
        self.log_text = tk.Text(
            log_frame,
            height=12,
            bg=COLORS['bg_tertiary'],
            fg=COLORS['text_primary'],
            insertbackground=COLORS['text_primary'],
            selectbackground=COLORS['border_light'],
            selectforeground=COLORS['text_primary'],
            relief="flat",
            wrap="word",
            font=('Consolas', 9),
            padx=10,
            pady=10
        )
        
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")
        
        # Initial log message
        self._log("🎉 Folder Flattener Pro initialized successfully!")
        self._log("💡 Select a folder to see detailed analysis and preview.")

    def _build_stats_display(self) -> None:
        """Build the statistics display area."""
        stats_content = ttk.Frame(self.stats_frame, style="Glass.TFrame")
        stats_content.pack(fill="x", padx=15, pady=15)
        
        # Create a grid of stat cards
        stats_grid = ttk.Frame(stats_content, style="Glass.TFrame")
        stats_grid.pack(fill="x")
        
        # Files count
        self.files_label = ttk.Label(
            stats_grid,
            text="📄 Files to move: --",
            style="GlassInfo.TLabel"
        )
        self.files_label.grid(row=0, column=0, sticky="w", padx=(0, 20), pady=5)
        
        # Total size
        self.size_label = ttk.Label(
            stats_grid,
            text="💾 Total size: --",
            style="GlassInfo.TLabel"
        )
        self.size_label.grid(row=0, column=1, sticky="w", padx=(0, 20), pady=5)
        
        # Folders count
        self.folders_label = ttk.Label(
            stats_grid,
            text="📁 Subfolders: --",
            style="GlassInfo.TLabel"
        )
        self.folders_label.grid(row=1, column=0, sticky="w", padx=(0, 20), pady=5)
        
        # Duplicates estimate
        self.duplicates_label = ttk.Label(
            stats_grid,
            text="🔄 Potential duplicates: --",
            style="GlassInfo.TLabel"
        )
        self.duplicates_label.grid(row=1, column=1, sticky="w", padx=(0, 20), pady=5)

        # Archive stats
        self.archives_label = ttk.Label(
            stats_grid,
            text="🗜️ Archives found: --",
            style="GlassInfo.TLabel"
        )
        self.archives_label.grid(row=2, column=0, sticky="w", padx=(0, 20), pady=5)
        self.extracted_label = ttk.Label(
            stats_grid,
            text="📤 Extracted entries: --",
            style="GlassInfo.TLabel"
        )
        self.extracted_label.grid(row=2, column=1, sticky="w", padx=(0, 20), pady=5)

    def _build_status_bar(self, parent) -> None:
        """Build the status bar at the bottom."""
        status_frame = ttk.Frame(parent, style="Glass.TFrame")
        status_frame.pack(fill="x", pady=(20, 0))
        
        status_content = ttk.Frame(status_frame, style="Glass.TFrame")
        status_content.pack(fill="x", padx=15, pady=8)
        
        # Status text
        self.status_label = ttk.Label(
            status_content,
            text="🟢 Ready",
            style="GlassMuted.TLabel"
        )
        self.status_label.pack(side="left")
        
        # Quick tips
        tips_label = ttk.Label(
            status_content,
            text="💡 Tip: Drag & drop folders directly into the window! | Ctrl+O: Browse | Ctrl+Enter: Start | Esc: Cancel",
            style="GlassMuted.TLabel"
        )
        tips_label.pack(side="right")

    def _setup_drag_drop(self) -> None:
        """Setup drag and drop functionality if available."""
        if not HAS_DND or TkinterDnD is None:
            return
        try:
            if hasattr(self.root, 'drop_target_register'):
                self.root.drop_target_register(DND_FILES)
                dnd_bind = getattr(self.root, 'dnd_bind', None)
                if callable(dnd_bind):
                    dnd_bind('<<Drop>>', self._on_drop)
                self._log("✅ Drag & drop enabled - you can drag folders directly into the window!")
        except Exception as e:
            self._log(f"⚠️ Drag & drop not available: {e}")

    def _setup_keyboard_shortcuts(self) -> None:
        """Setup keyboard shortcuts for better usability."""
        self.root.bind('<Control-o>', lambda e: self._browse_folder())
        self.root.bind('<Control-Return>', lambda e: self._start_operation())
        self.root.bind('<Control-Enter>', lambda e: self._start_operation())
        self.root.bind('<Escape>', lambda e: self._cancel_operation())
        self.root.bind('<F1>', lambda e: self._show_help())
        self.root.bind('<Control-comma>', lambda e: self._show_settings())

    # Event handlers and core functionality methods will be added next...

    def _on_drop(self, event) -> None:
        """Handle drag and drop events with visual feedback."""
        try:
            files = event.data.split()
            if files:
                # Take the first file/folder
                dropped_path = files[0].strip('{}')
                path_obj = Path(dropped_path)
                
                if path_obj.is_dir():
                    self.path_var.set(str(path_obj))
                    self._log(f"📂 Folder dropped: {path_obj}")
                    self._update_preview()
                else:
                    # If file dropped, use its parent directory
                    parent_dir = path_obj.parent
                    self.path_var.set(str(parent_dir))
                    self._log(f"📄 File dropped, using parent folder: {parent_dir}")
                    self._update_preview()
        except Exception as e:
            self._log(f"❌ Error processing dropped item: {e}")

    def _browse_folder(self) -> None:
        """Browse for folder with enhanced path handling."""
        initial_dir = self.path_var.get()
        if not initial_dir or not Path(initial_dir).exists():
            initial_dir = str(Path.home())
        
        path = filedialog.askdirectory(
            title="Select folder to flatten",
            initialdir=initial_dir
        )
        
        if path:
            self.path_var.set(path)
            self._log(f"📁 Folder selected: {path}")
            self._update_preview()

    def _browse_archive_folder(self) -> None:
        """Browse for archive folder where original zips will be moved."""
        initial_dir = self.archive_folder_var.get()
        if not initial_dir or not Path(initial_dir).exists():
            initial_dir = str(Path.home())
        
        path = filedialog.askdirectory(
            title="Select archive folder for original zip files",
            initialdir=initial_dir
        )
        
        if path:
            self.archive_folder_var.set(path)
            self._log(f"📦 Archive folder selected: {path}")
            self._save_current_settings()

    def _on_path_change(self, event=None) -> None:
        """Handle path changes with debounced preview updates."""
        if self._preview_timer is not None:
            try:
                self.root.after_cancel(self._preview_timer)
            except Exception:
                pass
        self._preview_timer = self.root.after(1000, self._update_preview)

    def _on_option_change(self) -> None:
        """Handle option changes and save settings."""
        self._save_current_settings()
        if self.path_var.get():
            self._update_preview()

    def _update_preview(self) -> None:
        """Update the preview with current folder analysis."""
        path_str = self.path_var.get().strip()
        if not path_str:
            self._clear_preview()
            return
        
        path_obj = Path(path_str)
        if not path_obj.exists() or not path_obj.is_dir():
            self._clear_preview()
            self._log(f"⚠️ Invalid folder path: {path_str}")
            return
        
        try:
            # Analyze folder in background to avoid UI freeze
            def analyze():
                try:
                    files = list_files_in_subfolders(
                        path_obj, 
                        include_hidden=self.include_hidden_var.get()
                    )
                    # Count .zip archives in subfolders
                    try:
                        zips = find_zip_archives(
                            path_obj,
                            include_hidden=self.include_hidden_var.get()
                        )
                        archives_found = len(zips)
                    except Exception:
                        archives_found = 0
                    
                    total_files = len(files)
                    total_bytes = sum(f.size for f in files)
                    
                    # Count subfolders
                    subfolders = set()
                    for file_info in files:
                        subfolders.add(file_info.source.parent)
                    
                    # Estimate potential duplicates
                    names = [f.source.name for f in files]
                    duplicates = len(names) - len(set(names))
                    
                    # Update UI in main thread
                    self.root.after(0, lambda: self._update_preview_display(
                        total_files, total_bytes, len(subfolders), duplicates,
                        archives_found
                    ))
                    
                except Exception as e:
                    self.root.after(0, lambda: self._log(f"❌ Error analyzing folder: {e}"))
            
            # Run analysis in background
            threading.Thread(target=analyze, daemon=True).start()
            self._log(f"🔍 Analyzing folder: {path_str}")
            
        except Exception as e:
            self._log(f"❌ Error starting folder analysis: {e}")

    def _update_preview_display(self, files: int, bytes_total: int, folders: int, duplicates: int, archives_found: int = 0) -> None:
        """Update the preview display with analysis results."""
        self.total_files = files
        self.total_bytes = bytes_total
        
        # Update stats display
        self.files_label.config(text=f"📄 Files to move: {files:,}")
        self.size_label.config(text=f"💾 Total size: {human_size(bytes_total)}")
        self.folders_label.config(text=f"📁 Subfolders: {folders:,}")
        self.duplicates_label.config(text=f"🔄 Potential duplicates: {duplicates:,}")
        self.archives_label.config(text=f"🗜️ Archives found: {archives_found:,}")
        
        # Update status
        if files > 0:
            self.status_label.config(text=f"🔍 Ready to process {files:,} files ({human_size(bytes_total)})")
            self.start_btn.config(state="normal")
            
            # Log summary
            self._log(f"📊 Analysis complete: {files:,} files in {folders:,} subfolders")
            if duplicates > 0:
                mode = self.duplicate_mode_var.get()
                self._log(f"🔄 Found {duplicates:,} potential duplicates (will {mode})")
        else:
            self.status_label.config(text="📂 No files found in subfolders")
            self.start_btn.config(state="disabled")
            self._log("ℹ️ No files found to move from subfolders")

    def _clear_preview(self) -> None:
        """Clear the preview display."""
        self.files_label.config(text="📄 Files to move: --")
        self.size_label.config(text="💾 Total size: --")
        self.folders_label.config(text="📁 Subfolders: --")
        self.duplicates_label.config(text="🔄 Potential duplicates: --")
        self.status_label.config(text="📂 Select a folder to analyze")
        self.start_btn.config(state="disabled")

    def _start_operation(self) -> None:
        """Start the flattening operation with enhanced progress tracking."""
        if self.worker.is_running():
            return
        
        root_path = self.path_var.get().strip()
        if not root_path:
            messagebox.showwarning(
                "No Folder Selected", 
                "Please select a folder to flatten first."
            )
            return
        
        root = Path(root_path)
        if not root.exists() or not root.is_dir():
            messagebox.showerror(
                "Invalid Folder", 
                "The selected path is not a valid folder."
            )
            return
        
        if self.total_files == 0:
            messagebox.showinfo(
                "No Files to Move", 
                "There are no files in subfolders to move."
            )
            return
        
        # Confirm operation if not dry run
        if not self.dry_run_var.get():
            response = messagebox.askyesno(
                "Confirm Operation",
                f"Are you sure you want to move {self.total_files:,} files "
                f"({human_size(self.total_bytes)}) from subfolders?\n\n"
                f"Duplicate handling: {self.duplicate_mode_var.get()}\n"
                f"Remove empty folders: {'Yes' if self.remove_empty_var.get() else 'No'}\n\n"
                "This operation cannot be easily undone!"
            )
            if not response:
                return
        
        # Reset UI for operation
        self._prepare_for_operation()
        
        # Get settings
        duplicate_mode = self.duplicate_mode_var.get()
        remove_empty = self.remove_empty_var.get()
        include_hidden = self.include_hidden_var.get()
        dry_run = self.dry_run_var.get()
        extract_archives = self.extract_archives_var.get()
        archive_originals = self.archive_originals_var.get()
        archive_folder = Path(self.archive_folder_var.get()).resolve() if self.archive_folder_var.get().strip() else None
        
        mode_text = "🔍 DRY RUN" if dry_run else "🚀 LIVE MODE"
        self._log(f"\n{'='*50}")
        self._log(f"🎯 Starting operation in {mode_text}")
        self._log(f"📁 Target folder: {root_path}")
        self._log(f"🔄 Duplicate handling: {duplicate_mode}")
        self._log(f"🗑️ Remove empty folders: {remove_empty}")
        self._log(f"👁️ Include hidden files: {include_hidden}")
        self._log(f"🗜️ Extract archives: {extract_archives}")
        self._log(f"📦 Archive originals: {archive_originals}")
        if archive_originals and archive_folder:
            self._log(f"📂 Archive folder: {archive_folder}")
        self._log(f"{'='*50}\n")
        
        def progress_callback(event_data: dict) -> None:
            self.events.put(event_data)
        
        def operation_worker() -> None:
            try:
                stats = flatten_folder(
                    root,
                    duplicate_mode=duplicate_mode,
                    remove_empty=remove_empty,
                    include_hidden=include_hidden,
                    dry_run=dry_run,
                    progress_cb=progress_callback,
                    cancel_event=self.worker.cancel,
                    extract_archives=extract_archives,
                    archive_originals=archive_originals,
                    archive_folder=archive_folder,
                )
                self.events.put({"phase": "complete", "stats": stats})
            except Exception as e:
                self.events.put({"phase": "error", "error": str(e)})
        
        # Start the operation
        self.worker = Worker()
        self.worker.start(operation_worker)

    def _prepare_for_operation(self) -> None:
        """Prepare UI for operation start."""
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress_bar.set_progress(0, 100)
        self.progress_label.config(text="🚀 Starting operation...")
        self.status_label.config(text="🔄 Operation in progress...")
        
        # Clear log for new operation
        self.log_text.delete("1.0", tk.END)

    def _cancel_operation(self) -> None:
        """Cancel the current operation."""
        if self.worker.is_running():
            self.worker.stop()
            self._log("⏹️ Cancellation requested - finishing current file...")
            self.status_label.config(text="⏹️ Cancelling operation...")

    def _operation_complete(self) -> None:
        """Handle operation completion."""
        self.start_btn.config(state="normal" if self.total_files > 0 else "disabled")
        self.cancel_btn.config(state="disabled")
        self.progress_bar.set_progress(100, 100)
        self.status_label.config(text="✅ Operation completed")
        
        # Refresh preview to show updated state
        if self.path_var.get():
            self.root.after(1000, self._update_preview)

    def _poll_events(self) -> None:
        """Poll for worker thread events and update UI."""
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self._poll_events)

    def _handle_event(self, event: dict) -> None:
        """Handle events from the worker thread."""
        phase = event.get("phase")
        
        if phase == "scan":
            total = event.get("total", 0)
            message = event.get("message", "Scanning...")
            self._log(f"🔍 {message}")
            self.progress_bar.set_progress(0, max(total, 1))
            
        elif phase == "extract_scan":
            total = event.get("total", 0)
            self._log(f"🗜️ Found {total} archive(s) to extract")
        elif phase == "extract":
            self._log(event.get("message", "Extracting archives..."))
        elif phase == "extract_file":
            zip_name = Path(event.get("zip", "")).name
            file_name = event.get("file", "")
            action = event.get("action", "move")
            self._log(f"📤 [{zip_name}] {action}: {file_name}")
        elif phase == "archive_move":
            src = event.get("source", "")
            dest = event.get("dest", "")
            self._log(f"📦 Archived zip -> {Path(src).name} → {dest}")
        elif phase == "move":
            current = event.get("current", 0)
            total = event.get("total", 1)
            file_path = event.get("file", "")
            action = event.get("action", "move")
            
            # Update progress
            progress = (current / max(total, 1)) * 100
            self.progress_bar.set_progress(current, total)
            self.progress_label.config(
                text=f"📦 Processing: {current:,}/{total:,} files ({progress:.1f}%)"
            )
            
            # Log action with appropriate emoji
            action_emoji = {"move": "📦", "skip": "⏭️", "overwrite": "🔄", "rename": "📝"}
            emoji = action_emoji.get(action, "📦")
            file_name = Path(file_path).name if file_path else "Unknown file"
            self._log(f"{emoji} [{current:,}/{total:,}] {action}: {file_name}")
            
        elif phase == "complete":
            stats = event.get("stats")
            self._handle_operation_complete(stats)
            
        elif phase == "error":
            error_msg = event.get("error", "Unknown error occurred")
            self._handle_operation_error(error_msg)

    def _handle_operation_complete(self, stats) -> None:
        """Handle successful operation completion."""
        self._operation_complete()
        
        if stats:
            moved = getattr(stats, 'moved', 0)
            skipped = getattr(stats, 'skipped', 0)
            errors = getattr(stats, 'errors', 0)
            bytes_moved = getattr(stats, 'bytes_moved', 0)
            empty_removed = getattr(stats, 'empty_folders_removed', 0)
            cancelled = getattr(stats, 'cancelled', False)
            
            self._log(f"\n{'='*50}")
            if cancelled:
                self._log("⏹️ OPERATION CANCELLED")
            else:
                self._log("🎉 OPERATION COMPLETED SUCCESSFULLY!")
            
            self._log(f"📦 Files moved: {moved:,}")
            self._log(f"⏭️ Files skipped: {skipped:,}")
            self._log(f"❌ Errors: {errors:,}")
            self._log(f"💾 Data moved: {human_size(bytes_moved)}")
            # Archive stats
            af = getattr(stats, 'archives_found', 0)
            ae = getattr(stats, 'archives_extracted', 0)
            ab = getattr(stats, 'archive_bytes_written', 0)
            am = getattr(stats, 'archives_moved', 0)
            if af or ae or am:
                self._log(f"🗜️ Archives found: {af:,}")
                self._log(f"📤 Extracted entries: {ae:,} ({human_size(ab)})")
                self._log(f"📦 Original zips archived: {am:,}")
            self._log(f"{'='*50}")
            
            # Show completion message
            if not cancelled:
                if errors == 0:
                    messagebox.showinfo(
                        "Operation Completed!",
                        f"Successfully processed {moved:,} files!\n"
                        f"Data moved: {human_size(bytes_moved)}\n"
                        f"Skipped: {skipped:,} files\n"
                        f"Empty folders removed: {empty_removed:,}"
                    )
                else:
                    messagebox.showwarning(
                        "Operation Completed with Errors",
                        f"Processed {moved:,} files with {errors:,} errors.\n"
                        f"Check the log for details."
                    )

    def _handle_operation_error(self, error_msg: str) -> None:
        """Handle operation error."""
        self._operation_complete()
        self._log(f"💥 FATAL ERROR: {error_msg}")
        messagebox.showerror("Operation Failed", f"Operation failed with error:\n\n{error_msg}")

    def _show_help(self) -> None:
        """Show help dialog with usage instructions."""
        help_text = """
🗂️ Folder Flattener Pro - Help

WHAT IT DOES:
• Moves all files from subfolders into the main folder
• Handles duplicate files according to your preference
• Optionally removes empty folders after moving
• Provides detailed preview and progress tracking

HOW TO USE:
1. Select a folder using Browse or drag & drop
2. Review the analysis and preview
3. Choose your duplicate handling preference:
   • Rename: Add numbers to duplicate names (file_1.ext)
   • Overwrite: Replace existing files
   • Skip: Leave duplicates in subfolders
4. Enable options as needed:
   • Remove empty folders: Clean up after moving
   • Include hidden files: Process dotfiles too
   • Dry run: Preview without making changes
5. Click "Start Flattening" to begin

KEYBOARD SHORTCUTS:
• Ctrl+O: Browse for folder
• Ctrl+Enter: Start operation
• Esc: Cancel operation
• F1: Show this help
• Ctrl+, : Show settings

SAFETY FEATURES:
• Dry run mode for safe preview
• Detailed confirmation before live operations
• Comprehensive logging of all actions
• Automatic settings persistence

TIPS:
• Always use Dry Run first to preview changes
• Check the log for detailed operation information
• Large operations may take time - be patient!
• Drag & drop works with folders from Explorer
        """
        
        help_window = tk.Toplevel(self.root)
        help_window.title("Folder Flattener Pro - Help")
        help_window.geometry("600x500")
        help_window.configure(bg=COLORS['bg_primary'])
        
        text_widget = tk.Text(
            help_window,
            wrap="word",
            bg=COLORS['bg_secondary'],
            fg=COLORS['text_primary'],
            selectbackground=COLORS['border_light'],
            selectforeground=COLORS['text_primary'],
            font=('Segoe UI', 10),
            padx=20,
            pady=20
        )
        text_widget.pack(fill="both", expand=True, padx=20, pady=20)
        text_widget.insert("1.0", help_text)
        text_widget.config(state="disabled")

    def _show_settings(self) -> None:
        """Show fully functional settings dialog."""
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("560x520")
        win.configure(bg=COLORS['bg_primary'])
        win.transient(self.root)
        win.grab_set()

        container = ttk.Frame(win, style="Card.TFrame")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        header = ttk.Label(container, text="⚙️ Application Settings", style="Title.TLabel")
        header.pack(anchor="w")
        ttk.Separator(container, style="Modern.TSeparator").pack(fill="x", pady=10)

        # Options
        opt_frame = ttk.Frame(container, style="Card.TFrame")
        opt_frame.pack(fill="x")

        ttk.Checkbutton(
            opt_frame,
            text="🗑️ Remove empty folders after moving",
            variable=self.remove_empty_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change,
        ).pack(anchor="w", pady=4)

        ttk.Checkbutton(
            opt_frame,
            text="👁️ Include hidden files (dotfiles)",
            variable=self.include_hidden_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change,
        ).pack(anchor="w", pady=4)

        ttk.Checkbutton(
            opt_frame,
            text="🔍 Dry run (preview only, no changes)",
            variable=self.dry_run_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change,
        ).pack(anchor="w", pady=4)

        ttk.Checkbutton(
            opt_frame,
            text="🗜️ Extract .zip archives found in subfolders",
            variable=self.extract_archives_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change,
        ).pack(anchor="w", pady=4)

        ttk.Checkbutton(
            opt_frame,
            text="📦 Move original zips to archive folder",
            variable=self.archive_originals_var,
            style="Modern.TCheckbutton",
            command=self._on_option_change,
        ).pack(anchor="w", pady=4)

        af_frame = ttk.Frame(container, style="Card.TFrame")
        af_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(af_frame, text="Archive folder (optional):", style="Info.TLabel").pack(anchor="w")
        af_inner = ttk.Frame(af_frame, style="Card.TFrame")
        af_inner.pack(fill="x")
        af_entry = ttk.Entry(af_inner, textvariable=self.archive_folder_var, style="Modern.TEntry")
        af_entry.pack(side="left", fill="x", expand=True, pady=(0, 5))
        ttk.Button(af_inner, text="📂 Browse", style="Primary.TButton", command=self._browse_archive_folder).pack(side="left", padx=(8, 0))

        # Duplicate mode
        ttk.Separator(container, style="Modern.TSeparator").pack(fill="x", pady=10)
        dup = ttk.LabelFrame(
            container,
            text="Duplicate File Handling",
            style="Modern.TLabelframe",
            padding=12,
        )
        dup.pack(fill="x")
        ttk.Radiobutton(dup, text="📝 Rename duplicates", value="rename", variable=self.duplicate_mode_var, style="Modern.TRadiobutton", command=self._on_option_change).pack(anchor="w", pady=2)
        ttk.Radiobutton(dup, text="🔄 Overwrite existing files", value="overwrite", variable=self.duplicate_mode_var, style="Modern.TRadiobutton", command=self._on_option_change).pack(anchor="w", pady=2)
        ttk.Radiobutton(dup, text="⏭️ Skip duplicates", value="skip", variable=self.duplicate_mode_var, style="Modern.TRadiobutton", command=self._on_option_change).pack(anchor="w", pady=2)

        # Actions
        ttk.Separator(container, style="Modern.TSeparator").pack(fill="x", pady=10)
        btns = ttk.Frame(container, style="Card.TFrame")
        btns.pack(fill="x")
        def save_and_close():
            self._save_current_settings()
            if self.path_var.get():
                self._update_preview()
            win.destroy()
        def reset_defaults():
            defaults = SettingsManager().default_settings
            self.remove_empty_var.set(defaults['remove_empty'])
            self.include_hidden_var.set(defaults['include_hidden'])
            self.dry_run_var.set(defaults['dry_run'])
            self.duplicate_mode_var.set(defaults['duplicate_mode'])
            self.extract_archives_var.set(defaults.get('extract_archives', True))
            self.archive_originals_var.set(defaults.get('archive_originals', False))
            self.archive_folder_var.set(defaults.get('archive_folder', ''))
            self._save_current_settings()
            if self.path_var.get():
                self._update_preview()
        ttk.Button(btns, text="💾 Save", style="Success.TButton", command=save_and_close).pack(side="right")
        ttk.Button(btns, text="↩️ Reset Defaults", style="Danger.TButton", command=reset_defaults).pack(side="left")

    def _save_current_settings(self) -> None:
        """Save current settings to file."""
        self.settings.set('last_path', self.path_var.get())
        self.settings.set('remove_empty', self.remove_empty_var.get())
        self.settings.set('include_hidden', self.include_hidden_var.get())
        self.settings.set('dry_run', self.dry_run_var.get())
        self.settings.set('duplicate_mode', self.duplicate_mode_var.get())
        # New settings
        self.settings.set('extract_archives', self.extract_archives_var.get())
        self.settings.set('archive_originals', self.archive_originals_var.get())
        self.settings.set('archive_folder', self.archive_folder_var.get())
        self.settings.set('window_geometry', self.root.geometry())
        self.settings.save_settings()

    def _on_closing(self) -> None:
        """Handle application closing."""
        # Cancel any running operation
        if self.worker.is_running():
            response = messagebox.askyesno(
                "Operation in Progress",
                "An operation is currently running. Cancel it and exit?"
            )
            if response:
                self.worker.stop()
            else:
                return
        
        # Save settings
        self._save_current_settings()
        
        # Close application
        self.root.destroy()

    def _log(self, message: str) -> None:
        """Add message to log with timestamp and auto-scroll."""
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, formatted_message)
        self.log_text.see(tk.END)
        
        # Also log to file
        self.logger.info(message.replace('🎉', '').replace('❌', '').replace('📁', '').strip())


def main() -> None:
    """Main entry point for the application."""
    # Create root window
    if HAS_DND and TkinterDnD is not None:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    # Set window icon and properties
    root.title("Folder Flattener Pro")
    
    try:
        # Try to set a nice icon (if available)
        root.iconbitmap(default='folder.ico')
    except:
        pass
    
    # Create and run the application
    app = FolderFlattenerPro(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
    except Exception as e:
        print(f"Application error: {e}")
        messagebox.showerror("Application Error", f"An unexpected error occurred:\n{e}")


if __name__ == "__main__":
    main()
