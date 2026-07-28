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
        Clean show name.
        """
        name = re.sub(
            r"[._]+",
            " ",
            name
        )

        name = re.sub(
            r"\s+",
            " ",
            name
        ).strip()

        name = re.sub(
            r"\b(19|20)\d{2}\b",
            "",
            name
        )

        name = re.sub(
            r"\b(480p|720p|1080p|2160p|WEBRip|WEB-DL|BluRay|HDRip|BRRip)\b",
            "",
            name,
            flags=re.IGNORECASE
        )

        return name.strip()

    def find_show_id(self, show_name: str) -> Optional[str]:
        """
        Search TMDB TV show ID.
        """
        results = self.tmdb.search_tv_show(show_name)

        if not results:
            return None

        return results[0].get("id")

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
            return {}

        show_name = episodes[0].show_name

        print(f"Detected show: {show_name}")

        show_id = self.find_show_id(show_name)

        if not show_id:
            print(f"Could not find show: {show_name}")
            return {}

        imdb_id = self.get_imdb_id(show_id)

        if not imdb_id:
            print(f"Could not get IMDb ID for: {show_name}")
            return {}

        results = {}

        for episode in episodes:
            subtitle_file = self.download_subtitles_for_episode(
                episode,
                imdb_id,
                language
            )

            if subtitle_file:
                results[episode.file_path] = subtitle_file

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
                print(
                    f"MATCHED: "
                    f"{movie_info.title}"
                    f" ({movie_info.year})" if movie_info.year else ""
                )

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
            r"\b(480p|720p|1080p|2160p|WEBRip|WEB-DL|BluRay|HDRip|BRRip)\b",
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
            return MovieInfo(title=title, year=year, file_path=Path(""))

        # Try to find year: "Movie Name 2023" or "Movie.Name.2023"
        year_match = re.search(r"[\s._-](\d{4})$", clean_name)
        if year_match:
            year = int(year_match.group(1))
            title = re.sub(r"[\s._-]\d{4}$", "", clean_name)
            title = self._clean_movie_title(title)
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
            r"\b(480p|720p|1080p|2160p|WEBRip|WEB-DL|BluRay|HDRip|BRRip)\b",
            "",
            name,
            flags=re.IGNORECASE
        )
        
        # Remove group names in brackets or parentheses
        name = re.sub(r"\s*\[.*?\]\s*", "", name)
        name = re.sub(r"\s*\{.*?\}\s*", "", name)
        
        return name.strip()

    def find_movie_id(self, title: str, year: Optional[int] = None) -> Optional[str]:
        """
        Search TMDB movie ID.
        """
        results = self.tmdb.search_movie(title, year=year)

        if not results:
            return None

        return results[0].get("id")

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
        external_ids = self.tmdb.get_external_ids(movie_id)
        imdb_id = external_ids.get("imdb_id")
        
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