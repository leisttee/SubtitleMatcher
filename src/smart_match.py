import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from config import Config
from api_clients.opensubtitles import OpenSubtitlesClient
from api_clients.tmdb import TMDBClient


@dataclass
class EpisodeInfo:
    show_name: str
    season: int
    episode: int
    file_path: Path
    language: str = "en"


@dataclass
class MovieInfo:
    title: str
    year: Optional[int]
    file_path: Path
    language: str = "en"


class SmartMatcher:
    def __init__(self):
        self.opensubtitles = OpenSubtitlesClient(
            Config.OPENSUBTITLES_API_KEY
        )

        self.tmdb = TMDBClient(
            Config.TMDB_API_KEY
        )

    # === TV SERIES METHODS ===

    def scan_video_library(self, library_path: str) -> List[EpisodeInfo]:
        """
        Scan video library and return list of found episodes.
        """
        episodes = []
        library = Path(library_path)

        print(f"Scanning library: {library}")

        for video_file in library.rglob("*"):
            if not video_file.is_file():
                continue

            if not self._is_video_file(video_file):
                continue

            print(f"VIDEO FOUND: {video_file.name}")

            episode_info = self._parse_tv_filename(video_file.name)

            if episode_info:
                print(
                    f"MATCHED: "
                    f"{episode_info.show_name} "
                    f"S{episode_info.season:02d}"
                    f"E{episode_info.episode:02d}"
                )

                episode_info.file_path = video_file
                episodes.append(episode_info)
            else:
                # Try parsing as movie if TV parse fails
                movie_info = self._parse_movie_filename(video_file.name)
                if movie_info:
                    print(f"  (This looks like a movie: {movie_info.title})")
                else:
                    print(f"NO MATCH: {video_file.name}")

        print(f"TOTAL MATCHED: {len(episodes)}")

        return episodes

    def _parse_tv_filename(self, filename: str) -> Optional[EpisodeInfo]:
        """
        Parse TV episode filename.
        Supports:
        - Jane.The.Virgin.S03E03
        - Jane_the_Virgin_S03E03
        - Jane-the-Virgin-S03E03
        - Jane the Virgin 3x03
        """
        name = Path(filename).stem

        patterns = [
            # Jane the Virgin S03E03
            r"(.+?)[\s._-]+S(\d{1,2})E(\d{1,2})",

            # Jane the Virgin 3x03
            r"(.+?)[\s._-]+(\d{1,2})x(\d{1,2})",

            # Show.Name.S03E03E04
            r"(.+?)[\s._-]+S(\d{1,2})E(\d{1,2})E\d{1,2}",

            # Show.Name.303
            r"(.+?)[\s._-]+(\d)(\d{2})",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                name,
                re.IGNORECASE
            )

            if not match:
                continue

            try:
                show_name = self._clean_show_name(
                    match.group(1)
                )

                season = int(match.group(2))
                episode = int(match.group(3))

                # Make sure season/episode are reasonable
                if season > 30 or episode > 100:
                    continue

                return EpisodeInfo(
                    show_name=show_name,
                    season=season,
                    episode=episode,
                    file_path=Path("")
                )

            except (ValueError, IndexError):
                continue

        return None

    def _clean_show_name(self, name: str) -> str:
        """
        Clean show name - improved version with smart capitalization.
        """
        # Replace dots, underscores, hyphens with spaces
        name = re.sub(r"[._-]+", " ", name)
        
        # Remove extra spaces
        name = re.sub(r"\s+", " ", name).strip()
        
        # Remove year (1900-2099)
        name = re.sub(r"\b(19|20)\d{2}\b", "", name)
        
        # Remove common quality tags and release groups
        name = re.sub(
            r"\b(480p|720p|1080p|2160p|WEBRip|WEB-DL|BluRay|HDRip|BRRip|REPACK|PROPER|x264|x265|HEVC|H\.264|H\.265|AC3|DTS|AAC|MP3|DD5\.1|Dual|Audio|Multi|Sub|Fix|DVD|BDRip|WEB|DL|Rip|HC|HDTV|TV|Season|Complete|AMZN|NF|HMAX|iT|WEB|RARBG|EZTV|YIFY|YTS|TBS|E?ZTV|XVID|DIVX|AVC|REMUX)\b",
            "",
            name,
            flags=re.IGNORECASE
        )
        
        # Remove episode patterns (S01E01, 1x01, etc.)
        name = re.sub(r"\bS\d{1,2}E\d{1,2}\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\b\d{1,2}x\d{1,2}\b", "", name)
        
        # Remove common words in brackets/parentheses
        name = re.sub(r"\s*\[.*?\]\s*", " ", name)
        name = re.sub(r"\s*\(.*?\)\s*", " ", name)
        
        # Remove extra spaces and trim
        name = re.sub(r"\s+", " ", name).strip()
        
        # Smart capitalization - keep common words lowercase in titles
        words = name.split()
        if words:
            # Capitalize first word
            words[0] = words[0].capitalize()
            # For subsequent words, keep short words lowercase
            short_words = {"the", "and", "of", "for", "with", "on", "at", "by", "in", "a", "an", "to", "from", "up", "down", "off", "over", "under", "after", "before", "between", "through", "during", "without", "against", "among", "upon", "toward"}
            for i in range(1, len(words)):
                word = words[i].lower()
                if word not in short_words:
                    words[i] = word.capitalize()
                else:
                    words[i] = word
            name = " ".join(words)
        
        return name

    def _generate_title_variations(self, title: str) -> List[str]:
        """
        Generate intelligent variations of a title for searching.
        """
        variations = []
        title_lower = title.lower()
        
        # Original
        variations.append(title)
        
        # Remove "The" from beginning
        if title_lower.startswith("the "):
            variations.append(title[4:])
            variations.append(title[4:].strip())
        
        # Replace & with and / and with &
        variations.append(title.replace(" & ", " and "))
        variations.append(title.replace(" and ", " & "))
        
        # Remove apostrophes
        variations.append(title.replace("'", ""))
        
        # Remove all special characters
        variations.append(re.sub(r"[^a-zA-Z0-9 ]", "", title))
        
        # All lowercase
        variations.append(title_lower)
        
        # Title case (first letter of each word capitalized)
        variations.append(" ".join(word.capitalize() for word in title_lower.split()))
        
        # All uppercase
        variations.append(title.upper())
        
        # Remove common words from the beginning
        words = title_lower.split()
        if len(words) > 2:
            # Try without first word if it's common
            common_start_words = {"the", "a", "an"}
            if words[0] in common_start_words:
                variations.append(" ".join(words[1:]))
                variations.append(" ".join(words[1:]).capitalize())
        
        # Try removing words that might be part of quality tags
        clean_title = re.sub(
            r"\b(unrated|director's cut|extended|ultimate|final|special edition|remastered|uncut)\b",
            "",
            title,
            flags=re.IGNORECASE
        ).strip()
        if clean_title != title:
            variations.append(clean_title)
        
        # Remove duplicates while preserving order
        seen = set()
        result = []
        for v in variations:
            v_clean = v.strip()
            if v_clean and v_clean not in seen:
                seen.add(v_clean)
                result.append(v_clean)
        
        return result

    def find_show_id(self, show_name: str) -> Optional[int]:
        """
        Search TMDB TV show ID with intelligent variations.
        """
        if not show_name:
            return None
            
        # Clean the name first
        show_name = self._clean_show_name(show_name)
        print(f"Searching for: '{show_name}'")
        
        # Generate all variations
        variations = self._generate_title_variations(show_name)
        
        # Try exact search first with original name
        results = self.tmdb.search_tv_show(show_name)
        if results:
            print(f"✓ Found: {results[0].get('name')}")
            return results[0].get("id")
        
        # Try all variations
        tried = set()
        for variant in variations:
            if variant == show_name or variant in tried:
                continue
            tried.add(variant)
            print(f"  Trying variation: '{variant}'")
            results = self.tmdb.search_tv_show(variant)
            if results:
                found_name = results[0].get('name')
                print(f"  ✓ Found: '{found_name}' (using variation '{variant}')")
                return results[0].get("id")
        
        print(f"✗ Could not find show: '{show_name}'")
        return None

    def get_imdb_id(self, show_id: int) -> Optional[str]:
        """
        Get IMDb ID from TMDB.
        """
        external_ids = self.tmdb.get_external_ids(show_id)
        return external_ids.get("imdb_id")

    def download_subtitles_for_episode(
        self,
        episode_info: EpisodeInfo,
        imdb_id: str,
        language: str = None
    ) -> Optional[Path]:
        """
        Download subtitles for a single episode.
        """
        if language is None:
            language = episode_info.language

        subtitles = self.opensubtitles.search_subtitles(
            imdb_id=imdb_id,
            season=episode_info.season,
            episode=episode_info.episode,
            language=language
        )

        if not subtitles:
            return None

        subtitle_data = subtitles[0]

        file_info = self.opensubtitles.get_subtitle_file(
            subtitle_data
        )

        if not file_info:
            return None

        file_id = file_info.get("file_id")

        if not file_id:
            return None

        content = self.opensubtitles.download_subtitle(
            file_id
        )

        if not content:
            return None

        output_dir = episode_info.file_path.parent

        output_file = (
            output_dir /
            f"{episode_info.file_path.stem}.{language}.srt"
        )

        with open(output_file, "wb") as f:
            f.write(content)

        return output_file

    def match_all_episodes(
        self,
        library_path: str,
        language: str = "en"
    ) -> Dict[Path, Path]:
        """
        Match all episodes and download subtitles.
        """
        episodes = self.scan_video_library(
            library_path
        )

        if not episodes:
            print("No episodes found in library")
            return {}

        show_name = episodes[0].show_name

        print(f"\nDetected show: '{show_name}'")

        show_id = self.find_show_id(show_name)

        if not show_id:
            print(f"Could not find show: '{show_name}'")
            return {}

        imdb_id = self.get_imdb_id(show_id)

        if not imdb_id:
            print(f"Could not get IMDb ID for: '{show_name}'")
            return {}

        print(f"IMDB ID: {imdb_id}")
        print(f"Downloading subtitles for {len(episodes)} episodes...")

        results = {}

        for episode in episodes:
            print(f"  Episode {episode.episode:02d}...")
            subtitle_file = self.download_subtitles_for_episode(
                episode,
                imdb_id,
                language
            )

            if subtitle_file:
                results[episode.file_path] = subtitle_file
                print(f"    ✓ Downloaded")
            else:
                print(f"    ✗ No subtitle found")

        return results

    # === MOVIE METHODS ===

    def scan_movie_library(self, library_path: str) -> List[MovieInfo]:
        """
        Scan video library for movies.
        """
        movies = []
        library = Path(library_path)

        print(f"Scanning movie library: {library}")

        for video_file in library.rglob("*"):
            if not video_file.is_file():
                continue

            if not self._is_video_file(video_file):
                continue

            print(f"VIDEO FOUND: {video_file.name}")

            movie_info = self._parse_movie_filename(video_file.name)

            if movie_info:
                year_str = f" ({movie_info.year})" if movie_info.year else ""
                print(f"MATCHED: {movie_info.title}{year_str}")

                movie_info.file_path = video_file
                movies.append(movie_info)
            else:
                print(f"NO MATCH: {video_file.name}")

        print(f"TOTAL MOVIES: {len(movies)}")

        return movies

    def _parse_movie_filename(self, filename: str) -> Optional[MovieInfo]:
        """
        Parse movie filename.
        Supports:
        - Movie Name 2023.mp4
        - Movie.Name.2023.mkv
        - Movie Name (2023).mp4
        - Movie.Name.2023.1080p.BluRay.mkv
        """
        name = Path(filename).stem

        # Remove common quality tags
        clean_name = re.sub(
            r"\b(480p|720p|1080p|2160p|WEBRip|WEB-DL|BluRay|HDRip|BRRip|YIFY|YTS|RARBG)\b",
            "",
            name,
            flags=re.IGNORECASE
        )

        # Try to find year in parentheses: "Movie Name (2023)"
        year_match = re.search(r"\((\d{4})\)", clean_name)
        if year_match:
            year = int(year_match.group(1))
            title = re.sub(r"\s*\(\d{4}\)\s*", "", clean_name)
            title = self._clean_movie_title(title)
            if title:
                return MovieInfo(title=title, year=year, file_path=Path(""))

        # Try to find year: "Movie Name 2023" or "Movie.Name.2023"
        year_match = re.search(r"[\s._-](\d{4})$", clean_name)
        if year_match:
            year = int(year_match.group(1))
            title = re.sub(r"[\s._-]\d{4}$", "", clean_name)
            title = self._clean_movie_title(title)
            if title:
                return MovieInfo(title=title, year=year, file_path=Path(""))

        # No year found, just use the title
        title = self._clean_movie_title(clean_name)
        
        # Check if it has valid movie patterns (e.g., not "S01E01" pattern)
        if re.search(r"S\d{1,2}E\d{1,2}", title, re.IGNORECASE):
            return None
            
        # Skip if title is too short or looks like a TV show
        if len(title) < 2:
            return None
            
        return MovieInfo(title=title, year=None, file_path=Path(""))

    def _clean_movie_title(self, name: str) -> str:
        """
        Clean movie title.
        """
        # Replace dots and underscores with spaces
        name = re.sub(r"[._]", " ", name)
        
        # Remove extra spaces
        name = re.sub(r"\s+", " ", name).strip()
        
        # Remove common video tags
        name = re.sub(
            r"\b(480p|720p|1080p|2160p|WEBRip|WEB-DL|BluRay|HDRip|BRRip|REPACK|PROPER|x264|x265|HEVC|YIFY|YTS|RARBG|EZTV)\b",
            "",
            name,
            flags=re.IGNORECASE
        )
        
        # Remove group names in brackets or parentheses
        name = re.sub(r"\s*\[.*?\]\s*", "", name)
        name = re.sub(r"\s*\{.*?\}\s*", "", name)
        
        # Remove release year if it's at the end
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name)
        name = re.sub(r"\s*\d{4}\s*$", "", name)
        
        # Remove "Unrated", "Director's Cut", etc.
        name = re.sub(r"\b(Unrated|Director's? Cut|Extended|Ultimate|Final|Special Edition)\b", "", name, flags=re.IGNORECASE)
        
        # Remove extra spaces
        name = re.sub(r"\s+", " ", name).strip()
        
        # Capitalize properly
        name = " ".join(word.capitalize() for word in name.split())
        
        return name

    def find_movie_id(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """
        Search TMDB movie ID with intelligent variations.
        """
        if not title:
            return None
        
        # Clean the title
        title = self._clean_movie_title(title)
        print(f"Searching for movie: '{title}'")
        
        # Generate variations
        variations = self._generate_title_variations(title)
        
        # Try exact search first
        results = self.tmdb.search_movie(title, year=year)
        if results:
            print(f"✓ Found: {results[0].get('title')}")
            return results[0].get("id")
        
        # Try variations
        tried = set()
        for variant in variations:
            if variant == title or variant in tried:
                continue
            tried.add(variant)
            print(f"  Trying variation: '{variant}'")
            results = self.tmdb.search_movie(variant, year=year)
            if results:
                found_title = results[0].get('title')
                print(f"  ✓ Found: '{found_title}'")
                return results[0].get("id")
        
        print(f"✗ Could not find movie: '{title}'")
        return None

    def get_movie_imdb_id(self, movie_id: int) -> Optional[str]:
        """
        Get IMDb ID for a movie from TMDB.
        """
        external_ids = self.tmdb.get_movie_external_ids(movie_id)
        return external_ids.get("imdb_id")

    def download_subtitles_for_movie(
        self,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles for a movie.
        """
        print(f"Searching for movie: {movie_info.title}")
        
        # Search for movie ID
        movie_id = self.find_movie_id(movie_info.title, movie_info.year)
        
        if not movie_id:
            print(f"Could not find movie: {movie_info.title}")
            return None
            
        # Get IMDb ID
        imdb_id = self.get_movie_imdb_id(movie_id)
        
        if not imdb_id:
            print(f"Could not get IMDb ID for: {movie_info.title}")
            return None
            
        print(f"IMDB ID: {imdb_id}")
        
        # Search for subtitles
        subtitles = self.opensubtitles.search_subtitles(
            imdb_id=imdb_id,
            language=language
        )

        if not subtitles:
            print(f"No subtitles found for: {movie_info.title}")
            return None

        # Get best subtitle (prefer hearing impaired if available, else first)
        subtitle_data = self._get_best_subtitle(subtitles)

        file_info = self.opensubtitles.get_subtitle_file(
            subtitle_data
        )

        if not file_info:
            return None

        file_id = file_info.get("file_id")

        if not file_id:
            return None

        content = self.opensubtitles.download_subtitle(
            file_id
        )

        if not content:
            return None

        output_dir = movie_info.file_path.parent

        output_file = (
            output_dir /
            f"{movie_info.file_path.stem}.{language}.srt"
        )

        with open(output_file, "wb") as f:
            f.write(content)

        return output_file

    def _get_best_subtitle(self, subtitles: List[Dict]) -> Dict:
        """
        Select best subtitle from list.
        Prefers hearing impaired subtitles, then standard.
        """
        # First try to find hearing impaired
        for sub in subtitles:
            if sub.get("hearing_impaired"):
                return sub
        
        # Then try to find one with good score
        best = subtitles[0]
        best_score = 0
        
        for sub in subtitles:
            score = sub.get("score", 0)
            if score > best_score:
                best_score = score
                best = sub
                
        return best

    def match_all_movies(
        self,
        library_path: str,
        language: str = "en"
    ) -> Dict[Path, Path]:
        """
        Match all movies and download subtitles.
        """
        movies = self.scan_movie_library(library_path)

        if not movies:
            print("No movies found in library")
            return {}

        results = {}

        for movie in movies:
            print(f"\nProcessing: {movie.title}")
            
            subtitle_file = self.download_subtitles_for_movie(
                movie,
                language
            )

            if subtitle_file:
                results[movie.file_path] = subtitle_file
                print(f"  ✓ Downloaded: {subtitle_file.name}")
            else:
                print(f"  ✗ No subtitle available")

        return results

    # === UTILITY METHODS ===

    def _is_video_file(self, file_path: Path) -> bool:
        """
        Check whether file is a video file.
        """
        video_extensions = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v"
        }

        return file_path.suffix.lower() in video_extensions