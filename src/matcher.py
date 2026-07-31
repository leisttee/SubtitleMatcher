import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any


def extract_episode_code(filename: str) -> Optional[str]:
    """
    Extract episode code from filename.
    
    Supports patterns:
    - S01E01, S1E1
    - 1x01, 1x1
    - Season 1 Episode 1
    - 101 (if unambiguous)
    
    Args:
        filename: Video or subtitle filename
        
    Returns:
        Episode code in format "S01E01" or None if not found
    """
    filename = filename.lower()
    
    patterns = [
        # S01E01, S1E1
        r"s(\d+)e(\d+)",
        # 1x01, 1x1
        r"(\d+)x(\d+)",
        # Season 1 Episode 1
        r"season\s*(\d+)\s*episode\s*(\d+)",
        # s01e01 (already covered by first pattern)
        # 1.01, 1.1 (if it's clearly episode)
        r"(\d+)\.(\d{2})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            try:
                season = int(match.group(1))
                episode = int(match.group(2))
                # Validate reasonable numbers
                if 0 < season <= 50 and 0 < episode <= 100:
                    return f"S{season:02d}E{episode:02d}"
            except (ValueError, IndexError):
                continue
    
    return None


def extract_movie_info(filename: str) -> Optional[Dict[str, Any]]:
    """
    Extract movie title and year from filename.
    
    Args:
        filename: Video filename
        
    Returns:
        Dictionary with title and year, or None if not found
    """
    # Remove extension
    name = Path(filename).stem
    
    # Try to find year in parentheses or brackets
    year_patterns = [
        r"\((\d{4})\)",  # (2006)
        r"\[(\d{4})\]",  # [2006]
        r"\.(\d{4})\.",  # .2006.
        r"(\d{4})",      # Just 4 digits (less reliable)
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, name)
        if match:
            year = match.group(1)
            # Remove year from title
            title = re.sub(pattern, "", name)
            # Clean up title
            title = re.sub(r"[._\-]", " ", title).strip()
            title = re.sub(r"\s+", " ", title)
            return {
                "title": title,
                "year": int(year)
            }
    
    # No year found, return cleaned title
    title = re.sub(r"[._\-]", " ", name).strip()
    title = re.sub(r"\s+", " ", title)
    return {"title": title, "year": None}


def find_matches(videos: List[Any], subtitles: List[Any]) -> List[Tuple[Any, Any]]:
    """
    Find matches between videos and subtitles.
    Supports both TV series (episode codes) and movies (title matching).
    
    Args:
        videos: List of video objects with 'name' attribute
        subtitles: List of subtitle objects with 'name' attribute
        
    Returns:
        List of (video, subtitle) tuples
    """
    # First, try episode code matching for TV series
    subtitle_episode_index = {}
    subtitle_movie_index = {}
    
    for subtitle in subtitles:
        code = extract_episode_code(subtitle.name)
        if code:
            subtitle_episode_index[code] = subtitle
        else:
            # Try movie matching
            movie_info = extract_movie_info(subtitle.name)
            if movie_info and movie_info.get("title"):
                # Index by cleaned title
                clean_title = clean_title_for_matching(movie_info["title"])
                year = movie_info.get("year")
                key = f"{clean_title}_{year}" if year else clean_title
                if key not in subtitle_movie_index:
                    subtitle_movie_index[key] = []
                subtitle_movie_index[key].append(subtitle)
    
    matches = []
    
    for video in videos:
        # Try episode code first
        code = extract_episode_code(video.name)
        if code and code in subtitle_episode_index:
            matches.append((video, subtitle_episode_index[code]))
            continue
        
        # Try movie matching
        movie_info = extract_movie_info(video.name)
        if movie_info and movie_info.get("title"):
            clean_title = clean_title_for_matching(movie_info["title"])
            year = movie_info.get("year")
            
            # Try exact year match first
            if year:
                key = f"{clean_title}_{year}"
                if key in subtitle_movie_index:
                    # Take the best match (first one)
                    matches.append((video, subtitle_movie_index[key][0]))
                    continue
            
            # Try without year
            if clean_title in subtitle_movie_index:
                matches.append((video, subtitle_movie_index[clean_title][0]))
                continue
            
            # Try partial match (if no exact match)
            best_match = find_best_movie_match(clean_title, subtitle_movie_index)
            if best_match:
                matches.append((video, best_match))
    
    return matches


def clean_title_for_matching(title: str) -> str:
    """
    Clean title for better matching.
    
    Args:
        title: Movie title
        
    Returns:
        Cleaned title
    """
    # Remove common words
    common_words = ["the", "a", "an", "and", "or", "but", "for", "of"]
    
    # Convert to lowercase and split
    words = title.lower().split()
    
    # Remove common words
    words = [w for w in words if w not in common_words]
    
    # Remove non-alphanumeric characters
    words = [re.sub(r"[^a-z0-9]", "", w) for w in words]
    
    # Join back
    return " ".join(words)


def find_best_movie_match(clean_title: str, movie_index: Dict[str, List[Any]]) -> Optional[Any]:
    """
    Find best matching movie subtitle using fuzzy matching.
    
    Args:
        clean_title: Cleaned movie title
        movie_index: Dictionary of cleaned titles to subtitle objects
        
    Returns:
        Best matching subtitle or None
    """
    if not clean_title or not movie_index:
        return None
    
    # Try partial matches
    title_parts = clean_title.split()
    
    # If title has multiple words, try to find best match
    best_match = None
    best_score = 0
    
    for key, subtitles in movie_index.items():
        # Calculate similarity score
        key_parts = key.split()
        
        # Count matching words
        matching_words = sum(1 for part in title_parts if part in key_parts)
        
        # Score based on matching words / total words
        score = matching_words / max(len(title_parts), 1)
        
        if score > best_score and score >= 0.5:  # At least 50% match
            best_score = score
            best_match = subtitles[0]
    
    return best_match


def find_match_for_movie(video: Any, subtitles: List[Any]) -> Optional[Any]:
    """
    Find best matching subtitle for a single movie.
    
    Args:
        video: Video object
        subtitles: List of subtitle objects
        
    Returns:
        Best matching subtitle or None
    """
    video_info = extract_movie_info(video.name)
    if not video_info or not video_info.get("title"):
        return None
    
    clean_video_title = clean_title_for_matching(video_info["title"])
    video_year = video_info.get("year")
    
    best_match = None
    best_score = 0
    
    for subtitle in subtitles:
        sub_info = extract_movie_info(subtitle.name)
        if not sub_info or not sub_info.get("title"):
            continue
        
        clean_sub_title = clean_title_for_matching(sub_info["title"])
        
        # Prefer exact year match
        if video_year and sub_info.get("year") == video_year:
            year_score = 1.0
        else:
            year_score = 0.0
        
        # Calculate title similarity
        title_parts = clean_video_title.split()
        sub_parts = clean_sub_title.split()
        
        matching_words = sum(1 for part in title_parts if part in sub_parts)
        title_score = matching_words / max(len(title_parts), 1) if title_parts else 0
        
        # Combined score (year match is weighted higher)
        score = title_score + (year_score * 0.5)
        
        if score > best_score and title_score >= 0.3:  # At least 30% title match
            best_score = score
            best_match = subtitle
    
    return best_match