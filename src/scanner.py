# scanner.py
from pathlib import Path
import os

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".ts",
    ".m2ts"
}

SUBTITLE_EXTENSIONS = {
    ".srt",
    ".sub",
    ".ass",
    ".ssa"
}


def scan_videos(folder):
    """
    Scan folder for video files recursively.
    
    Args:
        folder: Path to folder to scan
        
    Returns:
        List of video file paths
    """
    videos = []
    folder_path = Path(folder)
    
    if not folder_path.exists():
        print(f"❌ Folder not found: {folder}")
        return videos
    
    for file in folder_path.rglob("*"):
        if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(file)
    
    return videos


def scan_subtitles(folder):
    """
    Scan folder for subtitle files recursively.
    
    Args:
        folder: Path to folder to scan
        
    Returns:
        List of subtitle file paths
    """
    subtitles = []
    folder_path = Path(folder)
    
    if not folder_path.exists():
        print(f"❌ Folder not found: {folder}")
        return subtitles
    
    for file in folder_path.rglob("*"):
        if file.is_file() and file.suffix.lower() in SUBTITLE_EXTENSIONS:
            subtitles.append(file)
    
    return subtitles


def scan_files(folder, extensions):
    """
    Generic file scanner for specific extensions.
    
    Args:
        folder: Path to folder to scan
        extensions: Set of file extensions to match
        
    Returns:
        List of matching file paths
    """
    files = []
    folder_path = Path(folder)
    
    if not folder_path.exists():
        print(f"❌ Folder not found: {folder}")
        return files
    
    for file in folder_path.rglob("*"):
        if file.is_file() and file.suffix.lower() in extensions:
            files.append(file)
    
    return files