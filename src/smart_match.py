# smart_match.py
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from difflib import SequenceMatcher

from config import Config
from api_clients.subdl import SubDLClient
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
        # Lataa config
        Config.load()
        
        # Initialize SubDL (PRIMARY)
        if Config.SUBDL_API_KEY:
            self.subdl = SubDLClient(Config.SUBDL_API_KEY)
            print("✅ SubDL client initialized (PRIMARY)")
        else:
            print("⚠️ SubDL API key is empty! Subtitle download will not work.")
            self.subdl = None
        
        # Initialize OpenSubtitles (FALLBACK)
        if Config.OPENSUBTITLES_API_KEY:
            self.opensubtitles = OpenSubtitlesClient(Config.OPENSUBTITLES_API_KEY)
            print("✅ OpenSubtitles client initialized (FALLBACK)")
        else:
            print("⚠️ OpenSubtitles API key is empty!")
            self.opensubtitles = None
        
        # Initialize TMDB
        if Config.TMDB_API_KEY:
            self.tmdb = TMDBClient(Config.TMDB_API_KEY)
            print("✅ TMDB client initialized")
        else:
            print("⚠️ TMDB API key is empty! Movie/show lookup will not work.")
            self.tmdb = None

    # === SIMILARITY AND SELECTION METHODS ===

    def _similarity(self, a: str, b: str) -> float:
        """
        Calculate similarity between two strings.
        Returns a float between 0.0 and 1.0.
        """
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _select_best_tv_result(self, query: str, results: List[Dict]) -> Optional[Dict]:
        """
        Select the best TV show result based on name similarity.
        """
        if not results:
            return None

        best_result = None
        best_score = 0.0

        for result in results:
            result_name = result.get("name", "")
            score = self._similarity(query, result_name)
            
            # Bonus for popularity
            popularity = result.get("popularity", 0)
            score += min(popularity / 1000, 0.1)

            if score > best_score:
                best_score = score
                best_result = result

        if best_result:
            print(f"  ✓ TMDB match: '{query}' -> '{best_result.get('name')}' (score: {best_score:.2f})")

        return best_result

    def _select_best_movie_result(self, title: str, year: Optional[int], results: List[Dict]) -> Optional[Dict]:
        """
        Select the best movie result based on title similarity and year.
        """
        if not results:
            return None

        best_result = None
        best_score = 0.0

        for result in results:
            result_title = result.get("title", "")
            score = self._similarity(title, result_title)

            # Add bonus for matching year
            result_year = result.get("release_date", "")[:4]
            if year and result_year:
                try:
                    if int(year) == int(result_year):
                        score += 0.3
                except ValueError:
                    pass

            # Bonus for popularity
            popularity = result.get("popularity", 0)
            score += min(popularity / 1000, 0.1)

            if score > best_score:
                best_score = score
                best_result = result

        if best_result:
            print(f"  ✓ TMDB match: '{title}' -> '{best_result.get('title')}' (score: {best_score:.2f})")

        return best_result

    def _select_best_subtitle_subdl(self, subtitles: List[Dict]) -> Optional[Dict]:
        """
        Select the best subtitle from SubDL results.
        """
        if not subtitles:
            return None
        
        # SubDL results are already sorted by relevance
        # Just return the first one with a download URL
        for subtitle in subtitles:
            # Check if it has unpack_files or url
            if subtitle.get("unpack_files") or subtitle.get("url") or subtitle.get("nId") or subtitle.get("sd_id"):
                return subtitle
        
        return subtitles[0] if subtitles else None

    # === TV SERIES METHODS ===

    def scan_video_library(self, library_path: str) -> List[EpisodeInfo]:
        """
        Scan video library and return list of found episodes.
        """
        episodes = []
        library = Path(library_path)

        print(f"Scanning video library: {library}")

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

        print(f"TOTAL EPISODES: {len(episodes)}")

        return episodes

    def _parse_tv_filename(self, filename: str) -> Optional[EpisodeInfo]:
        """
        Parse TV episode filename.
        """
        name = Path(filename).stem

        patterns = [
            r"(.+?)[\s._-]+S(\d{1,2})E(\d{1,2})",
            r"(.+?)[\s._-]+S(\d{1,2})E(\d{1,2})E\d{1,2}",
            r"(.+?)[\s._-]+(\d{1,2})x(\d{1,2})",
            r"(.+?)[\s._-]+(\d)(\d{2})(?!\d)",
            r"(.+?)[\s._-]+[Ss]eason[\s._-]*(\d+)[\s._-]+[Ee]pisode[\s._-]*(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if not match:
                continue

            try:
                show_name = self._clean_show_name(match.group(1))
                season = int(match.group(2))
                episode = int(match.group(3))

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
        name = re.sub(r"[._-]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        name = re.sub(r"\b(19|20)\d{2}\b", "", name)
        
        quality_tags = [
            r"\b(480p|720p|1080p|2160p|4K|UHD)\b",
            r"\b(WEBRip|WEB-DL|BluRay|HDRip|BRRip|BDRip)\b",
            r"\b(REPACK|PROPER|REMUX|COMPLETE)\b",
            r"\b(x264|x265|HEVC|H\.264|H\.265|AVC)\b",
            r"\b(AC3|DTS|AAC|MP3|DD5\.1|Dual Audio)\b",
            r"\b(RARBG|EZTV|YIFY|YTS|TBS|XVID|DIVX)\b",
            r"\b(AMZN|NF|HMAX|iT|WEB|DL)\b",
            r"\b(HC|HDTV|TV|Season|Sub|Fix|DVD)\b",
        ]
        for tag in quality_tags:
            name = re.sub(tag, "", name, flags=re.IGNORECASE)
        
        name = re.sub(r"\bS\d{1,2}E\d{1,2}\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\b\d{1,2}x\d{1,2}\b", "", name)
        name = re.sub(r"\b\d{3}\b", "", name)
        name = re.sub(r"\s*\[.*?\]\s*", " ", name)
        name = re.sub(r"\s*\(.*?\)\s*", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        
        # Smart capitalization
        words = name.split()
        if words:
            words[0] = words[0].capitalize()
            short_words = {"the", "and", "of", "for", "with", "on", "at", "by", "in", "a", "an", "to", "from", "up", "down", "off", "over", "under", "after", "before", "between", "through", "during", "without", "against", "among", "upon", "toward"}
            for i in range(1, len(words)):
                word = words[i].lower()
                words[i] = word if word in short_words else word.capitalize()
            name = " ".join(words)
        
        return name

    def _generate_title_variations(self, title: str) -> List[str]:
        """
        Generate intelligent variations of a title for searching.
        """
        variations = []
        title_lower = title.lower()
        
        variations.append(title)
        
        if title_lower.startswith("the "):
            variations.append(title[4:])
            variations.append(title[4:].strip())
        
        variations.append(title.replace(" & ", " and "))
        variations.append(title.replace(" and ", " & "))
        variations.append(title.replace("'", ""))
        variations.append(re.sub(r"[^a-zA-Z0-9 ]", "", title))
        variations.append(title_lower)
        variations.append(" ".join(word.capitalize() for word in title_lower.split()))
        variations.append(title.upper())
        
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
        Search TMDB TV show ID.
        """
        if not self.tmdb:
            print("❌ TMDB API key not available!")
            return None
            
        if not show_name:
            return None
            
        show_name = self._clean_show_name(show_name)
        print(f"Searching for show: '{show_name}'")
        
        variations = self._generate_title_variations(show_name)
        
        results = self.tmdb.search_tv_show(show_name)
        if results:
            best = self._select_best_tv_result(show_name, results)
            if best:
                return best.get("id")
        
        tried = set()
        for variant in variations:
            if variant == show_name or variant in tried:
                continue
            tried.add(variant)
            results = self.tmdb.search_tv_show(variant)
            if results:
                best = self._select_best_tv_result(variant, results)
                if best:
                    return best.get("id")
        
        print(f"✗ Could not find show: '{show_name}'")
        return None

    def get_imdb_id(self, show_id: int) -> Optional[str]:
        """
        Get IMDb ID from TMDB.
        """
        if not self.tmdb:
            return None
        external_ids = self.tmdb.get_external_ids(show_id)
        return external_ids.get("imdb_id")

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
        """
        name = Path(filename).stem

        clean_name = re.sub(
            r"\b(480p|720p|1080p|2160p|4K|UHD|WEBRip|WEB-DL|BluRay|HDRip|BRRip|BDRip|YIFY|YTS|RARBG|REPACK|PROPER|x264|x265|HEVC)\b",
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

        # Try to find year: "Movie.Name.2023.1080p"
        year_match = re.search(r"[\s._-](\d{4})[\s._-]", clean_name)
        if year_match:
            year = int(year_match.group(1))
            title = re.sub(r"[\s._-]\d{4}[\s._-]", " ", clean_name)
            title = self._clean_movie_title(title)
            if title:
                return MovieInfo(title=title, year=year, file_path=Path(""))

        title = self._clean_movie_title(clean_name)
        
        if re.search(r"S\d{1,2}E\d{1,2}", title, re.IGNORECASE):
            return None
            
        if len(title) < 2:
            return None
            
        return MovieInfo(title=title, year=None, file_path=Path(""))

    def _clean_movie_title(self, name: str) -> str:
        """
        Clean movie title.
        """
        name = re.sub(r"[._]", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        
        quality_tags = [
            r"\b(480p|720p|1080p|2160p|4K|UHD)\b",
            r"\b(WEBRip|WEB-DL|BluRay|HDRip|BRRip|BDRip)\b",
            r"\b(REPACK|PROPER|REMUX)\b",
            r"\b(x264|x265|HEVC|H\.264|H\.265|AVC)\b",
            r"\b(AC3|DTS|AAC|MP3|DD5\.1)\b",
            r"\b(YIFY|YTS|RARBG|EZTV)\b",
        ]
        for tag in quality_tags:
            name = re.sub(tag, "", name, flags=re.IGNORECASE)
        
        name = re.sub(r"\s*\[.*?\]\s*", "", name)
        name = re.sub(r"\s*\{.*?\}\s*", "", name)
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name)
        name = re.sub(r"\s*\d{4}\s*$", "", name)
        name = re.sub(r"\b(Unrated|Director's? Cut|Extended|Ultimate|Final|Special Edition|Remastered|Uncut)\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", name).strip()
        
        if name:
            name = " ".join(word.capitalize() for word in name.split())
        
        return name

    def find_movie_id(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """
        Search TMDB movie ID.
        """
        if not self.tmdb:
            print("❌ TMDB API key not available!")
            return None
            
        if not title:
            return None
        
        title = self._clean_movie_title(title)
        print(f"Searching for movie: '{title}'")
        
        variations = self._generate_title_variations(title)
        
        results = self.tmdb.search_movie(title, year=year)
        if results:
            best = self._select_best_movie_result(title, year, results)
            if best:
                return best.get("id")
        
        tried = set()
        for variant in variations:
            if variant == title or variant in tried:
                continue
            tried.add(variant)
            results = self.tmdb.search_movie(variant, year=year)
            if results:
                best = self._select_best_movie_result(variant, year, results)
                if best:
                    return best.get("id")
        
        print(f"✗ Could not find movie: '{title}'")
        return None

    def get_movie_imdb_id(self, movie_id: int) -> Optional[str]:
        """
        Get IMDb ID for a movie from TMDB.
        """
        if not self.tmdb:
            return None
        external_ids = self.tmdb.get_movie_external_ids(movie_id)
        return external_ids.get("imdb_id")

    def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed movie information from TMDB.
        """
        if not self.tmdb:
            return None
        
        try:
            details = self.tmdb.get_movie_details(tmdb_id)
            if details:
                return {
                    "title": details.get("title", "Unknown"),
                    "year": details.get("year"),
                    "rating": details.get("vote_average", 0),
                    "vote_count": details.get("vote_count", 0),
                    "genres": [g.get("name") for g in details.get("genres", [])],
                    "runtime": details.get("runtime", 0),
                    "overview": details.get("overview", ""),
                    "poster_path": details.get("poster_path"),
                    "imdb_id": details.get("imdb_id")
                }
            return None
        except Exception as e:
            print(f"Error getting movie details: {e}")
            return None

    # smart_match.py - Lisää tämä metodi (jos ei jo ole)

    def get_show_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed TV show information from TMDB.
        """
        if not self.tmdb:
            print("❌ TMDB API key not available!")
            return None
        
        try:
            details = self.tmdb.get_show_details(tmdb_id)
            if details:
                return {
                    "title": details.get("name", "Unknown"),
                    "year": details.get("first_air_date", "")[:4] if details.get("first_air_date") else None,
                    "rating": details.get("vote_average", 0),
                    "vote_count": details.get("vote_count", 0),
                    "genres": [g.get("name") for g in details.get("genres", [])],
                    "overview": details.get("overview", ""),
                    "poster_path": details.get("poster_path"),
                    "imdb_id": details.get("external_ids", {}).get("imdb_id")
                }
            return None
        except Exception as e:
            print(f"Error getting show details: {e}")
            return None

    def update_movie_info_ui(self, movie_info: MovieInfo) -> Optional[Dict[str, Any]]:
        """
        Get movie details for UI display.
        """
        tmdb_id = self.find_movie_id(movie_info.title, movie_info.year)
        if not tmdb_id:
            return None
        return self.get_movie_details(tmdb_id)

    # === DOWNLOAD METHODS ===

    def download_subtitles_for_movie(
        self,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles for a movie using SubDL (primary) or OpenSubtitles (fallback).
        """
        print(f"Searching for movie: {movie_info.title}")
        
        # First get IMDB ID via TMDB
        movie_id = self.find_movie_id(movie_info.title, movie_info.year)
        if not movie_id:
            print(f"Could not find movie: {movie_info.title}")
            return None
            
        imdb_id = self.get_movie_imdb_id(movie_id)
        if not imdb_id:
            print(f"Could not get IMDb ID for: {movie_info.title}")
            return None
            
        print(f"IMDB ID: {imdb_id}")
        
        # Try SubDL first (PRIMARY)
        if self.subdl:
            print("🔍 Using SubDL (PRIMARY)...")
            subtitle_file = self._download_with_subdl(imdb_id, movie_info, language)
            if subtitle_file:
                return subtitle_file
            print("  SubDL failed, trying OpenSubtitles...")
        
        # Try OpenSubtitles as fallback
        if self.opensubtitles:
            print("🔍 Using OpenSubtitles (FALLBACK)...")
            return self._download_with_opensubtitles(imdb_id, movie_info, language)
        
        print("❌ No subtitle providers available")
        return None

    # smart_match.py - Korvaa _download_with_subdl metodi

    def _download_with_subdl(
        self,
        imdb_id: str,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles using SubDL.
        """
        try:
            # Search subtitles
            subtitles = self.subdl.search_subtitles(
                imdb_id=imdb_id,
                language=language
            )

            if not subtitles:
                print("  No subtitles found from SubDL")
                return None

            # Select best subtitle
            subtitle_data = self._select_best_subtitle_subdl(subtitles)
            if not subtitle_data:
                print("  No suitable subtitle found from SubDL")
                return None

            # Download
            content = self.subdl.download_subtitle(subtitle_data)
            if not content:
                print("  Download from SubDL failed")
                return None

            # Save with .srt extension (without language code in filename)
            output_dir = movie_info.file_path.parent
            output_file = output_dir / f"{movie_info.file_path.stem}.srt"

            with open(output_file, "wb") as f:
                f.write(content)

            print(f"  ✅ Downloaded from SubDL: {output_file.name}")
            return output_file

        except Exception as e:
            print(f"  ❌ SubDL error: {e}")
            return None

    # smart_match.py - Korvaa _download_with_opensubtitles metodi

    def _download_with_opensubtitles(
        self,
        imdb_id: str,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles using OpenSubtitles (fallback).
        """
        try:
            subtitles = self.opensubtitles.search_subtitles(
                imdb_id=imdb_id,
                language=language
            )

            if not subtitles:
                print("  No subtitles found from OpenSubtitles")
                return None

            subtitle_data = self._select_best_subtitle(subtitles)
            if not subtitle_data:
                print("  No suitable subtitle found from OpenSubtitles")
                return None

            file_info = self.opensubtitles.get_subtitle_file(subtitle_data)
            if not file_info:
                print("  Could not get file info from OpenSubtitles")
                return None

            file_id = file_info.get("file_id")
            if not file_id:
                print("  No file_id found from OpenSubtitles")
                return None

            content = self.opensubtitles.download_subtitle(file_id)
            if not content:
                print("  Download from OpenSubtitles failed")
                return None

            # Save with .srt extension (without language code in filename)
            output_dir = movie_info.file_path.parent
            output_file = output_dir / f"{movie_info.file_path.stem}.srt"

            with open(output_file, "wb") as f:
                f.write(content)

            print(f"  ✅ Downloaded from OpenSubtitles: {output_file.name}")
            return output_file

        except Exception as e:
            print(f"  ❌ OpenSubtitles error: {e}")
            return None

    def _select_best_subtitle(self, subtitles: List[Dict]) -> Optional[Dict]:
        """
        Select the best subtitle from OpenSubtitles results.
        """
        if not subtitles:
            return None

        best = None
        best_score = -1
        
        valid_subtitles = []
        for subtitle in subtitles:
            attributes = subtitle.get("attributes", {})
            files = attributes.get("files", [])
            file_id = attributes.get("file_id") or subtitle.get("file_id")
            
            if files or file_id:
                valid_subtitles.append(subtitle)
        
        if not valid_subtitles:
            print("⚠️ No subtitles with valid file IDs found")
            return None
        
        print(f"  Found {len(valid_subtitles)} subtitles with valid file IDs")

        for subtitle in valid_subtitles:
            score = subtitle.get("score", 0)
            attributes = subtitle.get("attributes", {})
            
            if attributes.get("hearing_impaired") or subtitle.get("hearing_impaired"):
                score += 15

            downloads = attributes.get("download_count", 0) or subtitle.get("download_count", 0)
            score += min(downloads / 1000, 10)

            files = attributes.get("files", [])
            if files:
                for file_info in files:
                    file_format = file_info.get("file_format", "").lower()
                    if file_format == "srt":
                        score += 5
                    elif file_format == "ass" or file_format == "ssa":
                        score += 2

            if score > best_score:
                best_score = score
                best = subtitle

        if best:
            print(f"  ✓ Subtitle selected: score={best_score:.1f}")
            attrs = best.get("attributes", {})
            files = attrs.get("files", [])
            if files:
                print(f"    File ID: {files[0].get('file_id', 'N/A')}")
            else:
                print(f"    File ID: {attrs.get('file_id', 'N/A')}")
        
        return best

    # smart_match.py - Korvaa download_subtitles_for_episode metodi

    def download_subtitles_for_episode(
        self,
        episode_info: EpisodeInfo,
        imdb_id: str,
        language: str = None
    ) -> Optional[Path]:
        """
        Download subtitles for a single episode using SubDL (primary) or OpenSubtitles (fallback).
        """
        if language is None:
            language = episode_info.language

        # Try SubDL first
        if self.subdl:
            try:
                subtitles = self.subdl.search_subtitles(
                    imdb_id=imdb_id,
                    season=episode_info.season,
                    episode=episode_info.episode,
                    language=language
                )

                if subtitles:
                    subtitle_data = self._select_best_subtitle_subdl(subtitles)
                    if subtitle_data:
                        content = self.subdl.download_subtitle(subtitle_data)
                        if content:
                            output_dir = episode_info.file_path.parent
                            # Save as .srt without language code
                            output_file = output_dir / f"{episode_info.file_path.stem}.srt"
                            with open(output_file, "wb") as f:
                                f.write(content)
                            return output_file
            except Exception as e:
                print(f"  SubDL error: {e}")

        # Try OpenSubtitles as fallback
        if self.opensubtitles:
            try:
                subtitles = self.opensubtitles.search_subtitles(
                    imdb_id=imdb_id,
                    season=episode_info.season,
                    episode=episode_info.episode,
                    language=language
                )

                if subtitles:
                    subtitle_data = self._select_best_subtitle(subtitles)
                    if subtitle_data:
                        file_info = self.opensubtitles.get_subtitle_file(subtitle_data)
                        if file_info:
                            file_id = file_info.get("file_id")
                            if file_id:
                                content = self.opensubtitles.download_subtitle(file_id)
                                if content:
                                    output_dir = episode_info.file_path.parent
                                    output_file = output_dir / f"{episode_info.file_path.stem}.srt"
                                    with open(output_file, "wb") as f:
                                        f.write(content)
                                    return output_file
            except Exception as e:
                print(f"  OpenSubtitles error: {e}")

        return None

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

    def match_all_episodes(
        self,
        library_path: str,
        language: str = "en"
    ) -> Dict[Path, Path]:
        """
        Match all episodes and download subtitles.
        """
        episodes = self.scan_video_library(library_path)

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

    # === UTILITY METHODS ===

    def _is_video_file(self, file_path: Path) -> bool:
        """
        Check whether file is a video file.
        """
        video_extensions = {
            ".mp4", ".mkv", ".avi", ".mov", ".wmv",
            ".flv", ".webm", ".m4v", ".mpg", ".mpeg",
            ".ts", ".m2ts", ".iso"
        }
        return file_path.suffix.lower() in video_extensions