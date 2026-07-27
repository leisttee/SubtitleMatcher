from pathlib import Path

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov"
}

SUBTITLE_EXTENSIONS = {
    ".srt",
    ".sub",
    ".ass"
}


def scan_videos(folder):

    videos = []

    for file in Path(folder).rglob("*"):
        if file.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(file)

    return videos


def scan_subtitles(folder):

    subtitles = []

    for file in Path(folder).rglob("*"):
        if file.suffix.lower() in SUBTITLE_EXTENSIONS:
            subtitles.append(file)

    return subtitles