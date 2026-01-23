
import shutil
import tempfile
import zipfile
from pathlib import Path
import sys

# Add current dir to path
sys.path.insert(0, ".")

from folder_flattener_core import flatten_folder

def create_test_env(root: Path):
    # included/zip.zip
    included = root / "included"
    included.mkdir()
    zip_path = included / "archive.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("file_in_zip.txt", "content")

    # excluded/ignored.zip
    excluded = root / "excluded"
    excluded.mkdir()
    zip_ignored = excluded / "ignored.zip"
    with zipfile.ZipFile(zip_ignored, 'w') as zf:
        zf.writestr("should_not_exist.txt", "content")

def test_archive_extraction_respects_excludes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "test_root"
        root.mkdir()
        create_test_env(root)

        print("Testing exclude_dirs with archive extraction...")
        stats = flatten_folder(
            root,
            extract_archives=True,
            exclude_dirs=["excluded"],
            archive_originals=False
        )

        # Check file_in_zip.txt exists in root
        if not (root / "file_in_zip.txt").exists():
            raise AssertionError("file_in_zip.txt should exist")

        # Check should_not_exist.txt does NOT exist
        if (root / "should_not_exist.txt").exists():
            raise AssertionError("should_not_exist.txt should NOT exist (it was in excluded dir)")

        # Check that ignored.zip was NOT moved/processed (it remains in excluded)
        if not (root / "excluded" / "ignored.zip").exists():
             # If it's not there, it might have been moved? But exclude_dirs means we skip the dir.
             # Wait, flatten_folder moves files. If excluded, it skips moving.
             # So it should remain there.
             raise AssertionError("ignored.zip should still be in excluded folder")

        print("✅ Archive extraction respects excludes test passed")

def test_archive_extraction_basic():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "test_basic"
        root.mkdir()
        d = root / "sub"
        d.mkdir()
        zip_path = d / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("hello.txt", "world")

        print("Testing basic archive extraction...")
        stats = flatten_folder(
            root,
            extract_archives=True,
            archive_originals=True
        )

        if not (root / "hello.txt").exists():
             raise AssertionError("hello.txt should be extracted")

        if not (root / "_archives" / "test.zip").exists():
             raise AssertionError("test.zip should be moved to _archives")

        print("✅ Basic archive extraction test passed")

if __name__ == "__main__":
    try:
        test_archive_extraction_respects_excludes()
        test_archive_extraction_basic()
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
