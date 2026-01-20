"""
Folder Flattener Core

Reusable core logic for flattening folder structures. Designed to be
imported by GUI and test scripts. No third-party dependencies required.

Features:
- Scan subfolders for files to move
- Duplicate handling (rename, overwrite, skip)
- Optional removal of empty folders
- Hidden file filtering
- Dry-run support
- Progress callbacks
- Robust logging

Author: GitHub Copilot
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional
import zipfile

__all__ = [
    "flatten_folder",
    "get_logger",
    "human_size",
    "FlattenStats",
    "MoveRecord",
    "generate_unique_filename",
    "list_files_in_subfolders",
    "remove_empty_folders_recursive",
    "FileInfo",
    "find_zip_archives",
]

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------


def get_logger(log_path: Optional[Path] = None) -> logging.Logger:
    """Return a configured module-level logger.

    Args:
        log_path: Optional path for the log file. Defaults to a file named
                  "folder_flattener.log" alongside this module.
    """
    logger = getattr(get_logger, "_logger", None)
    if logger is not None:
        return logger

    logger = logging.getLogger("folder_flattener")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if reimported
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
            # Fallback to console if file not writeable
            ch = logging.StreamHandler()
            logger.addHandler(ch)

    setattr(get_logger, "_logger", logger)
    return logger


# ----------------------------------------------------------------------------
# Data structures
# ----------------------------------------------------------------------------


@dataclass
class FileInfo:
    """Information about a file slated for moving."""

    source: Path
    size: int


@dataclass
class FlattenStats:
    """Statistics and results of a flatten operation."""

    total_files: int
    total_bytes: int
    moved: int
    skipped: int
    errors: int
    bytes_moved: int
    empty_folders_removed: int
    cancelled: bool = False
    # New archive-related metrics
    archives_found: int = 0
    archives_extracted: int = 0
    archive_bytes_written: int = 0
    archives_moved: int = 0
    overwrites: int = 0
    undo_supported: bool = False
    moves: List["MoveRecord"] = field(default_factory=list)


@dataclass
class MoveRecord:
    """Record of a file move to enable optional undo."""

    source: Path
    destination: Path
    category: str


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def is_hidden(path: Path) -> bool:
    """Return True if path is considered hidden.

    On Windows, many hidden files do not start with '.', but for safety and
    cross-platform simplicity, we treat dotfiles as hidden. Users can still
    include them by toggling the option.
    """
    name = path.name
    return name.startswith(".")


def list_files_in_subfolders(
    root: Path, include_hidden: bool = False
) -> List[FileInfo]:
    """List all files under root's subfolders (not those already in root).

    Args:
        root: Folder to flatten.
        include_hidden: Whether to include dotfiles.

    Returns:
        List of FileInfo for each file to move.
    """
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


# New helper to find zip archives in subfolders

def find_zip_archives(root: Path, include_hidden: bool = False) -> List[Path]:
    """Return a list of .zip files located in subfolders under root.

    Only returns files whose parent is not the root directory to avoid
    acting on zips already in the destination root.
    Case-insensitive detection to handle .ZIP/.Zip, etc.
    """
    zips: List[Path] = []
    root = root.resolve()
    # Use a case-insensitive approach instead of rglob("*.zip") so that
    # archives like FILE.ZIP or File.Zip are detected on all platforms.
    for p in root.rglob("*"):
        if p.is_file() and p.parent != root:
            if not include_hidden and is_hidden(p):
                continue
            if p.suffix.lower() == ".zip":
                zips.append(p)
    return zips


def human_size(num_bytes: int) -> str:
    """Return human-readable size string."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def generate_unique_filename(target_path: Path) -> Path:
    """Generate a unique filename by appending an incrementing suffix.

    Example: file.txt -> file_1.txt, file_2.txt, ...
    """
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
    """Remove empty subfolders under root. Returns number removed."""
    count = 0
    # Walk bottom-up to safely remove nested dirs
    for dirpath, _, _ in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root:
            continue
        try:
            if not any(Path(dirpath).iterdir()):
                p.rmdir()
                count += 1
        except (OSError, PermissionError):
            # Not empty or not permitted
            continue
    return count


# ----------------------------------------------------------------------------
# Core operation
# ----------------------------------------------------------------------------

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
    record_moves: bool = False,
) -> FlattenStats:
    """Flatten a folder by moving all files from subfolders into the root.

    Args:
        root: Target root directory.
        duplicate_mode: One of 'rename', 'overwrite', 'skip'.
        remove_empty: If True, remove empty subfolders after move.
        include_hidden: Include dotfiles when scanning.
        dry_run: If True, do not move files; only simulate.
        progress_cb: Optional callback receiving progress dicts.
        cancel_event: Optional event that, when set, cancels the operation.
        record_moves: If True, record move operations for optional undo support.

    Returns:
        FlattenStats describing the operation outcome.

    Added capabilities:
    - If extract_archives is True, extract .zip files found in subfolders
      directly into the root (flattened), applying duplicate_mode.
    - If archive_originals is True, move the original .zip files into the
      archive_folder (defaults to root / "_archives"), using duplicate handling
      to avoid overwrite in the archive as well (rename).
    """
    logger = get_logger()
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"Invalid directory: {root}")

    duplicate_mode = duplicate_mode.lower()
    if duplicate_mode not in {"rename", "overwrite", "skip"}:
        raise ValueError(
            "duplicate_mode must be 'rename', 'overwrite', or 'skip'"
        )

    # Optional archive extraction phase
    archives_found = 0
    archives_extracted = 0
    archive_bytes_written = 0
    archives_moved = 0
    overwrites = 0
    move_records: List[MoveRecord] = []

    if extract_archives:
        zips = find_zip_archives(root, include_hidden=include_hidden)
        archives_found = len(zips)
        if progress_cb:
            progress_cb({
                "phase": "extract_scan",
                "total": archives_found,
                "message": f"Found {archives_found} zip archive(s) to extract",
            })

        # Determine archive destination for originals
        if archive_originals:
            if archive_folder is None:
                archive_folder = root / "_archives"
            archive_folder = archive_folder.resolve()
            if not dry_run:
                try:
                    archive_folder.mkdir(parents=True, exist_ok=True)
                except (OSError, PermissionError) as e:
                    logger.error(
                        "Cannot create archive folder %s: %s",
                        archive_folder,
                        e,
                    )
                    # If we cannot create archive folder, disable moving
                    # originals
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
                    # Estimate extraction by counting files in the archive
                    with zipfile.ZipFile(zip_path) as zf:
                        for zinfo in zf.infolist():
                            if zinfo.is_dir():
                                continue
                            # Simulate duplicate handling
                            dest = root / Path(zinfo.filename).name
                            action = "move"
                            if dest.exists():
                                if duplicate_mode == "skip":
                                    action = "skip"
                                elif duplicate_mode == "overwrite":
                                    action = "overwrite"
                                    overwrites += 1
                                elif duplicate_mode == "rename":
                                    dest = generate_unique_filename(dest)
                            # Count as extracted
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
                            # Skip encrypted entries (no password support)
                            if zinfo.flag_bits & 0x1:
                                errors_msg = (
                                    "Encrypted entry skipped: "
                                    f"{zinfo.filename}"
                                )
                                logger.warning(errors_msg)
                                if progress_cb:
                                    progress_cb({
                                        "phase": "error",
                                        "file": (
                                            f"{zip_path.name}:"
                                            f"{zinfo.filename}"
                                        ),
                                        "error": errors_msg,
                                    })
                                continue

                            dest = root / Path(zinfo.filename).name
                            action = "move"
                            if dest.exists():
                                if duplicate_mode == "skip":
                                    action = "skip"
                                elif duplicate_mode == "overwrite":
                                    action = "overwrite"
                                    overwrites += 1
                                    try:
                                        dest.unlink()
                                    except OSError:
                                        pass
                                elif duplicate_mode == "rename":
                                    dest = generate_unique_filename(dest)

                            if action != "skip":
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                with zf.open(zinfo, "r") as src_f, open(
                                    dest, "wb"
                                ) as out_f:
                                    shutil.copyfileobj(src_f, out_f)
                                archives_extracted += 1
                                archive_bytes_written += zinfo.file_size
                            else:
                                # Count a skipped extracted file as processed
                                archives_extracted += 1

                            if progress_cb:
                                progress_cb({
                                    "phase": "extract_file",
                                    "zip": str(zip_path),
                                    "file": Path(zinfo.filename).name,
                                    "dest": str(dest),
                                    "action": action,
                                })
                # Move original zip to archive folder if requested
                if archive_originals:
                    try:
                        target = (
                            (archive_folder / zip_path.name)
                            if archive_folder
                            else (root / "_archives" / zip_path.name)
                        )
                        if target.exists():
                            target = generate_unique_filename(target)
                        if not dry_run:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(zip_path), str(target))
                        archives_moved += 1
                        if record_moves and not dry_run:
                            move_records.append(
                                MoveRecord(
                                    source=zip_path,
                                    destination=target,
                                    category="archive",
                                )
                            )
                        if progress_cb:
                            progress_cb({
                                "phase": "archive_move",
                                "source": str(zip_path),
                                "dest": str(target),
                            })
                    except (OSError, shutil.Error) as e:
                        logger.error(
                            "Error moving archive %s: %s", zip_path, e
                        )
                        if progress_cb:
                            progress_cb({
                                "phase": "error",
                                "file": str(zip_path),
                                "error": str(e),
                            })
                        # continue with next
            except zipfile.BadZipFile as e:
                # Corrupt archive; log and continue
                logger.error("Bad zip file %s: %s", zip_path, e)
                if progress_cb:
                    progress_cb({
                        "phase": "error",
                        "file": str(zip_path),
                        "error": f"Bad zip file: {e}",
                    })
                continue

    # Now list files to move from subfolders (optionally exclude .zip files)
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
        progress_cb(
            {
                "phase": "scan",
                "current": 0,
                "total": total_files,
                "bytes_total": total_bytes,
                "message": (
                    f"Found {total_files} files ("
                    f"{human_size(total_bytes)})"
                ),
            }
        )

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
                    overwrites += 1
                    if not dry_run:
                        # Remove existing before move
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
                    if record_moves:
                        move_records.append(
                            MoveRecord(
                                source=src,
                                destination=dest,
                                category="file",
                            )
                        )

            if progress_cb:
                progress_cb(
                    {
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
                    }
                )
        except (OSError, shutil.Error) as e:
            errors += 1
            logger.error("Error moving %s: %s", src, e)
            if progress_cb:
                progress_cb(
                    {
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
                    }
                )
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

    undo_supported = (
        not dry_run
        and not extract_archives
        and overwrites == 0
        and not cancelled
    )

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
        overwrites=overwrites,
        undo_supported=undo_supported,
        moves=move_records,
    )

    if progress_cb:
        progress_cb(
            {
                "phase": "done",
                "stats": stats,
                "message": (
                    "Completed: moved=%d, skipped=%d, errors=%d, "
                    "removed_empty=%d%s"
                    % (
                        moved,
                        skipped,
                        errors,
                        empty_removed,
                        ", cancelled" if cancelled else "",
                    )
                ),
            }
        )

    return stats
