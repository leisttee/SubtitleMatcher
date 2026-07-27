import re


def extract_episode_code(filename):

    filename = filename.lower()

    patterns = [
        r"s(\d+)e(\d+)",
        r"(\d+)x(\d+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)

        if match:
            season = int(match.group(1))
            episode = int(match.group(2))

            return f"S{season:02d}E{episode:02d}"

    return None


def find_matches(videos, subtitles):

    subtitle_index = {}

    for subtitle in subtitles:
        code = extract_episode_code(subtitle.name)

        if code:
            subtitle_index[code] = subtitle

    matches = []

    for video in videos:
        code = extract_episode_code(video.name)

        if code and code in subtitle_index:
            matches.append(
                (video, subtitle_index[code])
            )

    return matches