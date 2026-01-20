#!/usr/bin/env python3
"""
Simple test for Folder Flattener core functionality
Tests only the file operations without GUI components
"""

import tempfile
from pathlib import Path

def create_test_structure(base_path: Path) -> None:
    """Create a test folder structure for testing"""
    # Create folder structure
    folders = [
        "subfolder1",
        "subfolder2", 
        "subfolder1/deep1",
        "subfolder1/deep2",
        "subfolder2/deep3",
        "empty_folder"
    ]
    
    for folder in folders:
        (base_path / folder).mkdir(parents=True, exist_ok=True)
    
    # Create test files
    test_files = [
        "root_file.txt",
        "subfolder1/file1.txt",
        "subfolder1/file2.txt", 
        "subfolder1/deep1/deep_file1.txt",
        "subfolder1/deep2/deep_file2.txt",
        "subfolder2/file3.txt",
        "subfolder2/deep3/deep_file3.txt",
        "subfolder2/duplicate.txt"  # This will test duplicate handling
    ]
    
    for file_path in test_files:
        full_path = base_path / file_path
        full_path.write_text(f"Content of {file_path}\nCreated for testing folder flattener.")
    
    # Create a duplicate file in root for testing
    (base_path / "duplicate.txt").write_text("Original duplicate file in root")

def print_folder_structure(path: Path, indent: str = "") -> None:
    """Print the folder structure for visualization"""
    items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
    
    for item in items:
        if item.is_dir():
            print(f"{indent}📁 {item.name}/")
            print_folder_structure(item, indent + "  ")
        else:
            print(f"{indent}📄 {item.name}")

def test_flattening_logic():
    """Test the core flattening functionality"""
    print("=" * 50)
    print("Testing Folder Flattener Core Logic")
    print("=" * 50)
    
    # Create temporary test directory
    with tempfile.TemporaryDirectory() as temp_dir:
        test_path = Path(temp_dir) / "test_folder"
        test_path.mkdir()
        
        print(f"Created test folder: {test_path}")
        
        # Create test structure
        create_test_structure(test_path)
        
        print("\nOriginal structure:")
        print_folder_structure(test_path)
        
        # Count files before
        original_files = list(test_path.rglob("*"))
        original_file_count = len([f for f in original_files if f.is_file()])
        original_folder_count = len([f for f in original_files if f.is_dir()]) - 1  # Exclude root
        
        print(f"\nBefore flattening:")
        print(f"  Total files: {original_file_count}")
        print(f"  Total subfolders: {original_folder_count}")
        
        from folder_flattener_core import flatten_folder

        print("\nFlattening process:")
        stats = flatten_folder(
            test_path,
            duplicate_mode="rename",
            remove_empty=True,
            include_hidden=False,
            dry_run=False,
        )
        
        print("\nAfter flattening:")
        print_folder_structure(test_path)
        
        # Count files after
        final_files = list(test_path.rglob("*"))
        final_file_count = len([f for f in final_files if f.is_file()])
        final_folder_count = len([f for f in final_files if f.is_dir()]) - 1  # Exclude root
        
        print(f"\nResults:")
        print(f"  Files moved: {stats.moved}")
        print(f"  Files skipped: {stats.skipped}")
        print(f"  Folders removed: {stats.empty_folders_removed}")
        print(f"  Errors: {stats.errors}")
        print(f"  Final file count: {final_file_count}")
        print(f"  Final folder count: {final_folder_count}")
        
        # Verify results
        print(f"\nValidation:")
        if final_folder_count == 0:
            print("✅ All empty folders removed successfully")
        else:
            print("❌ Some folders remain")
        
        if final_file_count == original_file_count:
            print("✅ All files preserved during flattening")
        else:
            print(f"❌ File count mismatch: {original_file_count} -> {final_file_count}")
        
        # Check for specific files
        expected_files = [
            "root_file.txt",
            "file1.txt",
            "file2.txt", 
            "file3.txt",
            "deep_file1.txt",
            "deep_file2.txt",
            "deep_file3.txt",
            "duplicate.txt",
            "duplicate_1.txt"  # Renamed duplicate
        ]
        
        missing_files = []
        for expected in expected_files:
            if not (test_path / expected).exists():
                missing_files.append(expected)
        
        if not missing_files:
            print("✅ All expected files found in root directory")
        else:
            print(f"❌ Missing files: {missing_files}")
        
        if stats.errors == 0 and not missing_files and final_folder_count == 0:
            print("\n🎉 All tests passed! Folder flattener is working correctly.")
        else:
            print("\n⚠️ Some tests failed. Check the results above.")
        
        print("\n" + "=" * 50)
        print("Test completed!")
        print("=" * 50)

if __name__ == "__main__":
    test_flattening_logic()
