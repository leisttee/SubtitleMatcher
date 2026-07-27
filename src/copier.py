from pathlib import Path
import shutil


def copy_matches(matches):

    copied_count = 0
    skipped_count = 0

    for video, subtitle in matches:

        destination = (
            video.parent /
            f"{video.stem}{subtitle.suffix}"
        )

        if destination.exists():
            skipped_count += 1
            continue

        shutil.copy2(
            subtitle,
            destination
        )

        copied_count += 1

    return copied_count, skipped_count