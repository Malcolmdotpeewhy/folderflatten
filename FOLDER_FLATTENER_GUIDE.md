# Folder Flattener GUI

A powerful GUI application that flattens folder structures by moving all files from subfolders to the main directory. Perfect for organizing downloads, media collections, or any nested folder structure.

## Features

### 🎯 Core Functionality
- **Drag & Drop Support**: Simply drag a folder onto the application
- **Browse Interface**: Traditional folder browser for selection
- **File Movement**: Moves all files from subfolders to the main directory
- **Empty folder Cleanup**: Option to automatically remove empty folders
- **Safe Operations**: Comprehensive error handling and logging

### 🔧 Duplicate File Handling
- **Rename**: Automatically rename duplicates (file_1.txt, file_2.txt, etc.)
- **Overwrite**: Replace existing files with newer versions
- **Skip**: Skip duplicate files and keep originals

### 📊 Progress Tracking
- **Real-time Progress**: Visual progress bar and status updates
- **Detailed Statistics**: Track files moved, folders removed, duplicates handled
- **Comprehensive Logging**: Full operation log with timestamps
- **Preview Mode**: See what changes will be made before executing
- **Undo Support**: One-click undo for safe operations (when no overwrites/extractions occur)
- **Archive Extraction**: Optionally extract `.zip` archives found in subfolders

## Installation

### Requirements
- Python 3.7 or higher
- tkinter (usually included with Python)
- Optional: tkinterdnd2 for drag & drop functionality

### Quick Start
1. **Run the launcher** (easiest method):
   ```bash
   run_folder_flattener.bat
   ```

2. **Or install manually**:
   ```bash
   # Optional: Install drag & drop support
   pip install tkinterdnd2
   
   # Run the application
   python folder_flattener_gui.py
   ```

## Usage Guide

### Basic Operation
1. **Select a Folder**:
   - Drag & drop a folder onto the gray area, OR
   - Click "Browse Folder" to select manually

2. **Configure Options**:
   - Choose duplicate handling method (Rename/Overwrite/Skip)
   - Enable/disable empty folder removal

3. **Preview Changes** (recommended):
   - Click "Preview Changes" to see what will happen
   - Review the list of files that will be moved

4. **Execute Flattening**:
   - Click "Flatten Folder" to start the process
   - Monitor progress in real-time
   - Review the completion summary
   - Use "Undo Last" to revert safe operations if needed

### Example Scenarios

#### Scenario 1: Download Folder Organization
```
Downloads/
├── Project_A/
│   ├── doc1.pdf
│   └── SubFolder/
│       └── image1.jpg
├── Project_B/
│   └── spreadsheet.xlsx
└── existing_file.txt

After flattening:
Downloads/
├── doc1.pdf
├── image1.jpg
├── spreadsheet.xlsx
└── existing_file.txt
```

#### Scenario 2: Media Collection Flattening
```
Photos/
├── 2023/
│   ├── January/
│   │   └── vacation1.jpg
│   └── February/
│       └── birthday.jpg
└── 2024/
    └── March/
        └── concert.jpg

After flattening:
Photos/
├── vacation1.jpg
├── birthday.jpg
└── concert.jpg
```

## Duplicate Handling Options

### Rename Mode (Recommended)
- Original: `document.pdf`
- Duplicate: `document_1.pdf`
- Another: `document_2.pdf`

### Overwrite Mode
- Replaces existing files with files from subfolders
- **Warning**: This will permanently delete the original files

### Skip Mode
- Keeps original files unchanged
- Skips any files with the same name from subfolders

## Archive Handling Options

### Extract Archives
- Pulls files out of `.zip` archives found in subfolders
- Extracted files are flattened into the root directory

### Archive Originals
- Moves original `.zip` files to an archive folder (defaults to `_archives`)
- Keeps the root tidy after extraction

## Safety Features

### Error Handling
- **File Lock Protection**: Handles files in use by other applications
- **Permission Checks**: Validates write permissions before operations
- **Atomic Operations**: Each file move is independent
- **Rollback Information**: Detailed logging for troubleshooting

### Logging
- **Operation Log**: Every action is logged with timestamps
- **Error Tracking**: All errors are captured and reported
- **Statistics Tracking**: Real-time counters for all operations
- **File History**: Complete record saved to `folder_flattener.log`

## Advanced Features

### Preview Mode
- Shows exactly which files will be moved
- Displays source → destination mappings
- Helps identify potential conflicts before execution
- No changes made to your files

### Progress Tracking
- **Visual Progress Bar**: Shows operation status
- **Real-time Statistics**: Updates counters during processing
- **Status Messages**: Current operation and file counts
- **Completion Summary**: Final results with all statistics

### Batch Processing
- Handles thousands of files efficiently
- Memory-optimized for large folder structures
- Threaded processing to keep UI responsive
- Automatic cleanup of temporary data

## Troubleshooting

### Common Issues

#### Drag & Drop Not Working
- **Cause**: tkinterdnd2 not installed
- **Solution**: Run `pip install tkinterdnd2` or use Browse button
- **Alternative**: Use the "Browse Folder" button instead

#### Permission Errors
- **Cause**: Insufficient file system permissions
- **Solution**: Run as administrator or check folder permissions
- **Prevention**: Ensure you have write access to the target folder

#### Files Not Moving
- **Cause**: Files may be in use by other applications
- **Solution**: Close applications using the files and retry
- **Check**: Look at the error log for specific file details

#### Application Won't Start
- **Cause**: Python not installed or not in PATH
- **Solution**: Install Python 3.7+ and ensure it's in your system PATH
- **Test**: Run `python --version` in command prompt

### Log File Analysis
Check `folder_flattener.log` for detailed information:
- File operations and their results
- Error messages with specific file paths
- Timing information for performance analysis
- Statistics for each operation session

## Best Practices

### Before Flattening
1. **Backup Important Data**: Always backup irreplaceable files
2. **Preview First**: Use Preview mode to understand the changes
3. **Check Permissions**: Ensure you have write access to the folder
4. **Close Applications**: Close any programs using files in the folder

### During Operation
1. **Don't Interrupt**: Let the process complete to avoid partial moves
2. **Monitor Progress**: Watch the log for any error messages
3. **Check Statistics**: Verify the numbers make sense for your folder

### After Flattening
1. **Verify Results**: Check that all expected files are present
2. **Review Log**: Look for any errors or warnings
3. **Test Files**: Ensure moved files open correctly
4. **Clean Up**: The original empty folders are removed automatically

## Technical Details

### File Operation Method
- Uses Python's `shutil.move()` for atomic file operations
- Preserves file metadata (timestamps, permissions)
- Cross-platform compatibility (Windows, macOS, Linux)
- Handles long file paths and Unicode characters

### Performance Optimization
- Recursive directory scanning with `pathlib`
- Threaded processing to maintain UI responsiveness
- Memory-efficient processing of large folder structures
- Optimized duplicate detection algorithms

### Security Considerations
- No network access required
- No data transmitted or stored remotely
- Local file operations only
- User-controlled operation with confirmation dialogs

## Keyboard Shortcuts

- **Ctrl+O**: Browse for folder
- **Ctrl+P**: Preview changes
- **Enter**: Start flattening (when folder selected)
- **Ctrl+L**: Clear log
- **F5**: Refresh/Reset statistics

## Version History

### Version 1.0
- Initial release with core flattening functionality
- Drag & drop support
- Three duplicate handling modes
- Comprehensive logging and error handling
- Preview mode for safe operation
- Progress tracking and statistics
- Empty folder cleanup
- Cross-platform GUI with modern styling

---

## Support

For issues, suggestions, or contributions:
1. Check the log file for detailed error information
2. Verify your Python installation and permissions
3. Test with a small folder first to ensure compatibility
4. Review this documentation for troubleshooting steps

**Safe computing practices**: Always backup important data before running any file organization tools.
