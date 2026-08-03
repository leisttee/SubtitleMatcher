import re
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from difflib import SequenceMatcher

from config import Config
from api_clients.subdl import SubDLClient
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
        Config.load()
        
        self.cancelled = False
        self.paused = False
        self.cancel_lock = threading.Lock()
        self.progress_callback = None
        self.status_callback = None
        
        self.consecutive_failures = 0
        self.max_consecutive_failures = 10  # Nostettu 3 -> 10
        self.total_failures = 0
        self.max_total_failures = 30  # Nostettu 10 -> 30
        self.api_failure_count = 0
        self.api_failure_threshold = 5
        
        self.total_episodes = 0
        self.processed_episodes = 0
        self.failed_episodes = []
        self.current_episode = None
        self.current_provider = 'subdl'
        
        if Config.SUBDL_API_KEY:
            self.subdl = SubDLClient(Config.SUBDL_API_KEY)
            print("✅ SubDL client initialized (PRIMARY)")
        else:
            print("⚠️ SubDL API key is empty! Subtitle download will not work.")
            self.subdl = None
        
        self.opensubtitles = None
        
        if Config.TMDB_API_KEY:
            self.tmdb = TMDBClient(Config.TMDB_API_KEY)
            print("✅ TMDB client initialized")
        else:
            print("⚠️ TMDB API key is empty! Movie/show lookup will not work.")
            self.tmdb = None

        # === STOP / PERUUTUS ===
    def stop(self, reason: str = ""):
        """Stop the current operation gracefully"""
        with self.cancel_lock:
            self.cancelled = True
            print(f"\n⏹️ STOPPED: {reason if reason else 'User action'}")
            self._log_status()
        # Pakota progress-päivitys
        self._update_progress(status="Stopped")

    def reset_stop(self):
        """Reset stop state"""
        with self.cancel_lock:
            self.cancelled = False

    def is_stopped(self) -> bool:
        """Check if operation has been stopped"""
        with self.cancel_lock:
            return self.cancelled
    # === JULKAISURYHMÄN TUNNISTUS ===
    def _extract_release_group(self, filename: str) -> Optional[str]:
        if not filename:
            return None
        groups = [
            'KILLERS', 'DIMENSION', 'EVO', 'NTb', 'FUM', 'TOKiG', 
            'mSD', 'BATV', 'SYS', 'XVID', 'DIVX', 'YIFY', 'YTS',
            'RARBG', 'EZTV', 'TBS', 'BSG', 'WEB', 'AMZN', 'NF',
            'HMAX', 'iT', 'DL', 'HC', 'HDTV', 'TV', 'Sub', 'Fix',
            'DVD', 'REMUX', 'COMPLETE', 'REPACK', 'PROPER'
        ]
        filename_upper = filename.upper()
        for group in groups:
            if group in filename_upper:
                return group
        return None

    # === SIMILARITY AND SELECTION ===
    def _similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _select_best_tv_result(self, query: str, results: List[Dict]) -> Optional[Dict]:
        if not results:
            return None
        best_result = None
        best_score = 0.0
        for result in results:
            result_name = result.get("name", "")
            score = self._similarity(query, result_name)
            popularity = result.get("popularity", 0)
            score += min(popularity / 1000, 0.1)
            if score > best_score:
                best_score = score
                best_result = result
        if best_result:
            print(f"  ✓ TMDB match: '{query}' -> '{best_result.get('name')}' (score: {best_score:.2f})")
        return best_result

    def _select_best_movie_result(self, title: str, year: Optional[int], results: List[Dict]) -> Optional[Dict]:
        if not results:
            return None
        best_result = None
        best_score = 0.0
        for result in results:
            result_title = result.get("title", "")
            score = self._similarity(title, result_title)
            result_year = result.get("release_date", "")[:4]
            if year and result_year:
                try:
                    if int(year) == int(result_year):
                        score += 0.3
                except ValueError:
                    pass
            popularity = result.get("popularity", 0)
            score += min(popularity / 1000, 0.1)
            if score > best_score:
                best_score = score
                best_result = result
        if best_result:
            print(f"  ✓ TMDB match: '{title}' -> '{best_result.get('title')}' (score: {best_score:.2f})")
        return best_result

    def _select_best_subtitle_subdl(self, subtitles: List[Dict], video_filename: str = None) -> Optional[Dict]:
        if not subtitles:
            return None
        video_group = None
        if video_filename:
            video_group = self._extract_release_group(video_filename)
            if video_group:
                print(f"  🎯 Videon julkaisuryhmä: {video_group}")
        scored_subtitles = []
        for subtitle in subtitles:
            score = 0
            if subtitle.get("hearing_impaired"):
                score += 10
            if subtitle.get("unpack_files") or subtitle.get("url"):
                score += 20
            sub_filename = subtitle.get("filename", "")
            sub_group = self._extract_release_group(sub_filename)
            if video_group and sub_group and video_group.upper() == sub_group.upper():
                score += 50
                print(f"    ✅ Sama ryhmä: {video_group}")
            elif sub_group:
                score += 5
            filename = subtitle.get("filename", "").lower()
            if "forced" in filename or "foreign" in filename:
                score -= 10
            downloads = subtitle.get("download_count", 0)
            if downloads:
                score += min(downloads / 1000, 5)
            if subtitle.get("nId") or subtitle.get("sd_id"):
                score += 5
            scored_subtitles.append((score, subtitle))
        scored_subtitles.sort(key=lambda x: x[0], reverse=True)
        if scored_subtitles:
            best_score, best_subtitle = scored_subtitles[0]
            print(f"  ✓ Subtitle selected with score: {best_score}")
            if video_group:
                sub_group = self._extract_release_group(best_subtitle.get("filename", ""))
                if sub_group:
                    print(f"    Valittu ryhmä: {sub_group}")
            return best_subtitle
        return subtitles[0] if subtitles else None

    # === SCAN METHODS ===
    def scan_video_library(self, library_path: str) -> List[EpisodeInfo]:
        episodes = []
        library = Path(library_path)
        print(f"Scanning video library: {library}")
        for video_file in library.rglob("*"):
            if self.is_stopped():
                break
            if not video_file.is_file():
                continue
            if not self._is_video_file(video_file):
                continue
            print(f"VIDEO FOUND: {video_file.name}")
            episode_info = self._parse_tv_filename(video_file.name)
            if episode_info:
                print(f"MATCHED: {episode_info.show_name} S{episode_info.season:02d}E{episode_info.episode:02d}")
                episode_info.file_path = video_file
                episodes.append(episode_info)
            else:
                movie_info = self._parse_movie_filename(video_file.name)
                if movie_info:
                    print(f"  (This looks like a movie: {movie_info.title})")
                else:
                    print(f"NO MATCH: {video_file.name}")
        print(f"TOTAL EPISODES: {len(episodes)}")
        return episodes

    def _parse_tv_filename(self, filename: str) -> Optional[EpisodeInfo]:
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
                return EpisodeInfo(show_name=show_name, season=season, episode=episode, file_path=Path(""))
            except (ValueError, IndexError):
                continue
        return None

    def _clean_show_name(self, name: str) -> str:
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
        seen = set()
        result = []
        for v in variations:
            v_clean = v.strip()
            if v_clean and v_clean not in seen:
                seen.add(v_clean)
                result.append(v_clean)
        return result

    # === TMDB METHODS ===
    def find_show_id(self, show_name: str) -> Optional[int]:
        if self.is_stopped():
            return None
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
            if self.is_stopped():
                break
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
        if self.is_stopped():
            return None
        if not self.tmdb:
            return None
        external_ids = self.tmdb.get_external_ids(show_id)
        return external_ids.get("imdb_id")

    def get_show_info_safe(self, show_name: str) -> Optional[Dict[str, Any]]:
        if self.is_stopped():
            return None
        if self.tmdb:
            try:
                show_id = self.find_show_id(show_name)
                if show_id:
                    details = self.get_show_details(show_id)
                    if details:
                        return details
            except Exception as e:
                print(f"⚠️ TMDB virhe: {e}")
        print(f"ℹ️ Käytetään perustietoja sarjalle: {show_name}")
        return {
            "title": show_name,
            "year": None,
            "rating": 0,
            "vote_count": 0,
            "genres": [],
            "overview": "Tietoja ei saatavilla (TMDB ei vastannut)",
            "poster_path": None,
            "imdb_id": None
        }

    def get_movie_info_safe(self, movie_title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if self.is_stopped():
            return None
        if self.tmdb:
            try:
                movie_id = self.find_movie_id(movie_title, year)
                if movie_id:
                    details = self.get_movie_details(movie_id)
                    if details:
                        return details
            except Exception as e:
                print(f"⚠️ TMDB virhe: {e}")
        print(f"ℹ️ Käytetään perustietoja elokuvalle: {movie_title}")
        return {
            "title": movie_title,
            "year": year,
            "rating": 0,
            "vote_count": 0,
            "genres": [],
            "overview": "Tietoja ei saatavilla (TMDB ei vastannut)",
            "poster_path": None,
            "imdb_id": None
        }

    def get_show_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        if self.is_stopped():
            return None
        if not self.tmdb:
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

    def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        if self.is_stopped():
            return None
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

    # === MOVIE METHODS ===
    def scan_movie_library(self, library_path: str) -> List[MovieInfo]:
        movies = []
        library = Path(library_path)
        print(f"Scanning movie library: {library}")
        for video_file in library.rglob("*"):
            if self.is_stopped():
                break
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
        name = Path(filename).stem
        clean_name = re.sub(
            r"\b(480p|720p|1080p|2160p|4K|UHD|WEBRip|WEB-DL|BluRay|HDRip|BRRip|BDRip|YIFY|YTS|RARBG|REPACK|PROPER|x264|x265|HEVC|5\.1|7\.1|2\.0|Stereo|DD5\.1|AC3|DTS|AAC|MP3)\b",
            "", name, flags=re.IGNORECASE
        )
        clean_name = re.sub(r'\[.*?\]', '', clean_name)
        clean_name = re.sub(r'\{.*?\}', '', clean_name)
        year_match = re.search(r"\((\d{4})\)", clean_name)
        if year_match:
            year = int(year_match.group(1))
            title = re.sub(r"\s*\(\d{4}\)\s*", "", clean_name)
            title = self._clean_movie_title(title)
            if title:
                return MovieInfo(title=title, year=year, file_path=Path(""))
        year_match = re.search(r"[\s._-](\d{4})$", clean_name)
        if year_match:
            year = int(year_match.group(1))
            title = re.sub(r"[\s._-]\d{4}$", "", clean_name)
            title = self._clean_movie_title(title)
            if title:
                return MovieInfo(title=title, year=year, file_path=Path(""))
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
        name = Path(name).stem
        quality_patterns = [
            r'\b(480p|720p|1080p|2160p|4K|UHD)\b',
            r'\b(WEBRip|WEB-DL|BluRay|HDRip|BRRip|BDRip|DVDRip)\b',
            r'\b(REPACK|PROPER|REMUX|COMPLETE)\b',
            r'\b(x264|x265|HEVC|H\.264|H\.265|AVC)\b',
            r'\b(AC3|DTS|AAC|MP3|DD5\.1|Dual Audio)\b',
            r'\b(YIFY|YTS|RARBG|EZTV|TBS|XVID|DIVX)\b',
            r'\b(AMZN|NF|HMAX|iT|WEB|DL)\b',
            r'\b(HC|HDTV|TV|Season|Sub|Fix|DVD)\b',
            r'\b(5\.1|7\.1|2\.0|Stereo)\b',
            r'\b(Eng|Fin|Swe|Nor|Dan|Ger|Fre|Spa|Ita|Por|Rus)\b',
            r'\b(SDH|HI|CC)\b',
            r'\b(10bit|8bit|HDR|SDR)\b',
        ]
        for pattern in quality_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        name = re.sub(r'[._-]', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\{.*?\}', '', name)
        year_match = re.search(r'\((\d{4})\)', name)
        if year_match:
            year = year_match.group(1)
            name = re.sub(r'\([^)]*\)', '', name)
            name = f"{name.strip()} ({year})"
        else:
            name = re.sub(r'\([^)]*\)', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        if name:
            words = name.split()
            short_words = {'the', 'and', 'of', 'for', 'with', 'on', 'at', 'by', 'in', 'a', 'an', 'to', 'from', 'up', 'down', 'off', 'over', 'under', 'after', 'before', 'between', 'through', 'during', 'without', 'against', 'among', 'upon', 'toward'}
            capitalized = []
            for i, word in enumerate(words):
                if i == 0 or word.lower() not in short_words:
                    capitalized.append(word.capitalize())
                else:
                    capitalized.append(word.lower())
            name = ' '.join(capitalized)
        return name

    def find_movie_id(self, title: str, year: Optional[int] = None) -> Optional[int]:
        if self.is_stopped():
            return None
        if not self.tmdb:
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
            if self.is_stopped():
                break
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
        if self.is_stopped():
            return None
        if not self.tmdb:
            return None
        external_ids = self.tmdb.get_movie_external_ids(movie_id)
        return external_ids.get("imdb_id")

    def update_movie_info_ui(self, movie_info: MovieInfo) -> Optional[Dict[str, Any]]:
        if self.is_stopped():
            return None
        tmdb_id = self.find_movie_id(movie_info.title, movie_info.year)
        if not tmdb_id:
            return None
        return self.get_movie_details(tmdb_id)

   # === DOWNLOAD METHODS ===
    def _download_with_subdl(
        self,
        imdb_id: str,
        episode_info: EpisodeInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles using SubDL with release group prioritization.
        """
        if self.is_stopped():
            print("  ⏹️ Stopped")
            return None
            
        try:
            self.current_provider = 'subdl'
            
            if self.is_stopped():
                print("  ⏹️ Stopped before search")
                return None
                
            subtitles = self.subdl.search_subtitles(
                imdb_id=imdb_id,
                season=episode_info.season,
                episode=episode_info.episode,
                language=language
            )

            if not subtitles:
                print(f"  SubDL: No subtitles for S{episode_info.season:02d}E{episode_info.episode:02d}")
                self.api_failure_count += 1
                return None

            if self.is_stopped():
                print("  ⏹️ Stopped before selection")
                return None

            video_filename = episode_info.file_path.name if episode_info.file_path else None
            subtitle_data = self._select_best_subtitle_subdl(subtitles, video_filename)
            if not subtitle_data:
                print("  SubDL: No suitable subtitle")
                self.api_failure_count += 1
                return None

            if self.is_stopped():
                print("  ⏹️ Stopped before download")
                return None

            print("⬇️ Downloading subtitle URL...")
            content = self.subdl.download_subtitle(subtitle_data)
            
            if self.is_stopped():
                print("  ⏹️ Stopped after download")
                return None
                
            if not content:
                print("  SubDL: Download failed")
                self.api_failure_count += 1
                return None

            output_dir = episode_info.file_path.parent
            output_file = output_dir / f"{episode_info.file_path.stem}.srt"

            with open(output_file, "wb") as f:
                f.write(content)

            print(f"  ✅ SubDL: {output_file.name}")
            self.api_failure_count = 0
            return output_file

        except Exception as e:
            error_msg = str(e).lower()
            
            if self.is_stopped():
                print("  ⏹️ Stopped during error handling")
                return None
                
            if "rate limit" in error_msg or "too many" in error_msg:
                print(f"  ⚠️ Daily 50-download limit reached!")
                print(f"  ⏳ Resets tomorrow at 3:00 AM")
                print(f"  📁 Or use 'Browse subtitle file' button for manual download")
                self.api_failure_count += 1
                return None
                
            if "download" in error_msg or "permission" in error_msg:
                print(f"  ⚠️ Download failed - daily limit may be reached")
                print(f"  ⏳ Resets tomorrow at 3:00 AM")
                self.api_failure_count += 1
                return None
                
            print(f"  ❌ SubDL error: {e}")
            self.api_failure_count += 1
            return None

    def download_subtitles_for_episode(
        self,
        episode_info: EpisodeInfo,
        imdb_id: str,
        language: str = None
    ) -> Optional[Path]:
        if self.is_stopped():
            return None
        if language is None:
            language = episode_info.language
        episode_str = f"S{episode_info.season:02d}E{episode_info.episode:02d}"
        self.current_episode = episode_str
        if self.subdl:
            print(f"  🔍 SubDL: haetaan {episode_str}...")
            result = self._download_with_subdl(imdb_id, episode_info, language)
            if result:
                return result
            print(f"  ❌ SubDL: {episode_str} ei löytynyt")
            return None
        print("❌ SubDL client not available!")
        return None

    def download_subtitles_for_movie(
        self,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        if self.is_stopped():
            return None
        print(f"Searching for movie: {movie_info.title}")
        movie_details = self.get_movie_info_safe(movie_info.title, movie_info.year)
        if self.is_stopped():
            return None
        imdb_id = movie_details.get('imdb_id') if movie_details else None
        if not imdb_id:
            movie_id = self.find_movie_id(movie_info.title, movie_info.year)
            if self.is_stopped():
                return None
            if not movie_id:
                print(f"⚠️ Could not find movie: {movie_info.title}")
                print("ℹ️ Yritetään jatkaa ilman IMDB ID:tä...")
                imdb_id = None
            else:
                imdb_id = self.get_movie_imdb_id(movie_id)
                if self.is_stopped():
                    return None
                if not imdb_id:
                    print(f"⚠️ Could not get IMDb ID for: {movie_info.title}")
                    print("ℹ️ Yritetään jatkaa ilman IMDB ID:tä...")
        if imdb_id:
            print(f"IMDB ID: {imdb_id}")
        else:
            print(f"⚠️ Ei IMDB ID:tä - haetaan nimellä")
        if self.subdl:
            print("🔍 Using SubDL...")
            if imdb_id:
                try:
                    subtitles = self.subdl.search_subtitles(
                        imdb_id=imdb_id,
                        language=language
                    )
                except Exception as e:
                    print(f"  SubDL search error: {e}")
                    subtitles = None
            else:
                try:
                    subtitles = self.subdl.search_subtitles_by_title(
                        title=movie_info.title,
                        year=movie_info.year,
                        language=language
                    )
                except AttributeError:
                    print("  SubDL ei tue hakua nimellä")
                    subtitles = None
                except Exception as e:
                    print(f"  SubDL search error: {e}")
                    subtitles = None
            if subtitles:
                video_filename = movie_info.file_path.name if movie_info.file_path else None
                subtitle_data = self._select_best_subtitle_subdl(subtitles, video_filename)
                if subtitle_data:
                    content = self.subdl.download_subtitle(subtitle_data)
                    if content:
                        output_dir = movie_info.file_path.parent
                        output_file = output_dir / f"{movie_info.file_path.stem}.srt"
                        with open(output_file, "wb") as f:
                            f.write(content)

                        print(f"  ✅ Downloaded from SubDL: {output_file.name}")
                        return output_file
                    else:
                     print("  SubDL: Download failed")
                else:
                    print("  SubDL: No suitable subtitle found")
            else:                         
                print("  SubDL: No subtitles found")
        else:
            print("❌ SubDL client not available!")

        return None

    def match_all_episodes(
        self,
        library_path: str,
        language: str = "en"
    ) -> Dict[Path, Path]:
        """
        Match all episodes and download subtitles with stop support.
        """
        self.reset_stop()
        self.consecutive_failures = 0
        self.total_failures = 0
        self.failed_episodes = []
        self.processed_episodes = 0
        self.current_provider = 'subdl'
        self.api_failure_count = 0

        episodes = self.scan_video_library(library_path)

        if not episodes:
            print("No episodes found in library")
            return {}

        if self.is_stopped():
            print("⏹️ Operation stopped before start")
            return {}

        show_name = episodes[0].show_name
        print(f"\n🎬 Detected show: '{show_name}'")

        show_info = self.get_show_info_safe(show_name)
        if self.is_stopped():
            print("⏹️ Operation stopped")
            return {}
        
        if show_info and show_info.get('imdb_id'):
            imdb_id = show_info.get('imdb_id')
            print(f"✅ IMDB ID: {imdb_id}")
        else:
            show_id = self.find_show_id(show_name)
            if self.is_stopped():
                print("⏹️ Operation stopped")
                return {}
                
            if not show_id:
                print(f"⚠️ Show not found in TMDB: '{show_name}'")
                print("ℹ️ Continuing without IMDB ID...")
                imdb_id = None
            else:
                imdb_id = self.get_imdb_id(show_id)
                if self.is_stopped():
                    print("⏹️ Operation stopped")
                    return {}
                
                if not imdb_id:
                    print(f"⚠️ Could not get IMDb ID for: '{show_name}'")
                    print("ℹ️ Continuing without IMDB ID...")

        self.total_episodes = len(episodes)
        print(f"📦 {self.total_episodes} episodes")
        print(f"🌐 Language: {language}")
        if imdb_id:
            print(f"🎯 IMDB ID: {imdb_id}")
        else:
            print(f"⚠️ No IMDB ID - searching by show name")
        print("-" * 50)

        results = {}

        for idx, episode in enumerate(episodes):
            if self.is_stopped():
                print(f"\n⏹️ Stopped after {self.processed_episodes}/{self.total_episodes} episodes")
                break

            if self._check_auto_cancel():
                break

            episode_str = f"S{episode.season:02d}E{episode.episode:02d}"
            self.current_episode = episode_str
            
            progress = (self.processed_episodes / self.total_episodes) * 100
            print(f"\n📥 [{progress:.1f}%] {episode_str} ({idx+1}/{self.total_episodes})")
            self._update_progress(progress, f"Processing: {episode_str}")

            subtitle_file = None
            
            if imdb_id:
                subtitle_file = self.download_subtitles_for_episode(
                    episode,
                    imdb_id,
                    language
                )
            else:
                print(f"  🔍 Searching by name: {episode.show_name}")
                print(f"  ❌ No IMDB ID - skipping")
                self.failed_episodes.append(episode)
                self.consecutive_failures += 1
                self.total_failures += 1

            if subtitle_file:
                results[episode.file_path] = subtitle_file
                self.consecutive_failures = 0
                print(f"  ✅ {episode_str} downloaded successfully")
                time.sleep(3)
            else:
                if imdb_id:
                    self.failed_episodes.append(episode)
                    self.consecutive_failures += 1
                    self.total_failures += 1
                    print(f"  ❌ {episode_str} not found")

            self.processed_episodes += 1
            self._update_progress()

        self._show_summary()
        return results

    def _show_summary(self):
        """Näytä latauksen yhteenveto"""
        print("\n" + "="*50)
        print("📊 LATAUS YHTEENVETO")
        print("="*50)
        
        successful = self.processed_episodes - len(self.failed_episodes)
        print(f"✅ Onnistuneet: {successful}")
        print(f"❌ Epäonnistuneet: {len(self.failed_episodes)}")
        print(f"📊 Käsitelty: {self.processed_episodes}/{self.total_episodes}")
        
        if self.is_stopped():
            print("⏹️ TILA: Peruutettu käyttäjän toimesta")
        elif self.consecutive_failures >= self.max_consecutive_failures:
            print(f"⏹️ TILA: Peruutettu automaattisesti ({self.consecutive_failures} peräkkäistä virhettä)")
        elif self.total_failures >= self.max_total_failures:
            print(f"⏹️ TILA: Peruutettu automaattisesti ({self.total_failures} virhettä yhteensä)")
        else:
            print("✅ TILA: Valmis")
        
        if self.failed_episodes:
            print("\n❌ Epäonnistuneet jaksot:")
            max_display = 10
            for ep in self.failed_episodes[:max_display]:
                print(f"  - S{ep.season:02d}E{ep.episode:02d}")
            if len(self.failed_episodes) > max_display:
                print(f"  ... ja {len(self.failed_episodes) - max_display} muuta")
        
        print("="*50)

    def match_all_movies(
        self,
        library_path: str,
        language: str = "en"
    ) -> Dict[Path, Path]:
        """
        Match all movies and download subtitles with cancel support.
        """
        self.reset_stop()
        self.consecutive_failures = 0
        self.total_failures = 0
        self.failed_movies = []
        self.processed_movies = 0

        movies = self.scan_movie_library(library_path)

        if not movies:
            print("No movies found in library")
            return {}

        if self.is_stopped():
            print("⏹️ Operaatio peruutettu ennen aloitusta")
            return {}

        self.total_movies = len(movies)
        print(f"\n🎬 Aloitetaan lataus: {self.total_movies} elokuvaa")
        print(f"🌐 Kieli: {language}")
        print("-" * 50)

        results = {}

        for idx, movie in enumerate(movies):
            if self.is_stopped():
                print(f"\n⏹️ Peruutettu {self.processed_movies}/{self.total_movies} elokuvan jälkeen")
                break

            self.current_movie = movie.title
            progress = (self.processed_movies / self.total_movies) * 100
            print(f"\n📥 [{progress:.1f}%] {movie.title} ({idx+1}/{self.total_movies})")
            self._update_progress(progress, f"Processing: {movie.title}")

            subtitle_file = self.download_subtitles_for_movie(
                movie,
                language
            )

            if subtitle_file:
                results[movie.file_path] = subtitle_file
                self.consecutive_failures = 0
                print(f"  ✅ {movie.title} ladattu onnistuneesti")
                # Odota 3 sekuntia onnistuneen latauksen jälkeen
                time.sleep(3)
            else:
                self.failed_movies.append(movie)
                self.consecutive_failures += 1
                self.total_failures += 1
                print(f"  ❌ {movie.title} ei löytynyt")

            self.processed_movies += 1
            self._update_progress()

        self._show_movie_summary()
        return results

    def _show_movie_summary(self):
        """Näytä elokuvalatauksen yhteenveto"""
        print("\n" + "="*50)
        print("📊 LATAUS YHTEENVETO (ELOKUVAT)")
        print("="*50)
        
        successful = self.processed_movies - len(self.failed_movies)
        print(f"✅ Onnistuneet: {successful}")
        print(f"❌ Epäonnistuneet: {len(self.failed_movies)}")
        print(f"📊 Käsitelty: {self.processed_movies}/{self.total_movies}")
        
        if self.is_stopped():
            print("⏹️ TILA: Peruutettu käyttäjän toimesta")
        else:
            print("✅ TILA: Valmis")
        
        if self.failed_movies:
            print("\n❌ Epäonnistuneet elokuvat:")
            for movie in self.failed_movies[:10]:
                year_str = f" ({movie.year})" if movie.year else ""
                print(f"  - {movie.title}{year_str}")
            if len(self.failed_movies) > 10:
                print(f"  ... ja {len(self.failed_movies) - 10} muuta")
        
        print("="*50)

    def get_progress(self) -> Dict[str, Any]:
        """
        Hae nykyinen edistymistila.
        """
        return {
            'total': self.total_episodes,
            'processed': self.processed_episodes,
            'failed': len(self.failed_episodes),
            'cancelled': self.is_stopped(),
            'current_episode': self.current_episode,
            'consecutive_failures': self.consecutive_failures,
            'provider': self.current_provider
        }

    def get_failed_episodes(self) -> List[EpisodeInfo]:
        """
        Hae epäonnistuneet jaksot.
        """
        return self.failed_episodes

    def retry_failed_episodes(self, language: str = "en") -> Dict[Path, Path]:
        """
        Yritä uudelleen epäonnistuneita jaksoja.
        """
        if not self.failed_episodes:
            print("Ei epäonnistuneita jaksoja")
            return {}

        print(f"\n🔄 Yritetään uudelleen {len(self.failed_episodes)} epäonnistunutta jaksoa...")
        
        self.reset_stop()
        
        show_name = self.failed_episodes[0].show_name
        show_info = self.get_show_info_safe(show_name)
        if not show_info:
            print(f"⚠️ Could not find show: {show_name}")
            return {}
            
        imdb_id = show_info.get('imdb_id')
        if not imdb_id:
            show_id = self.find_show_id(show_name)
            if not show_id:
                print(f"❌ Could not find show: {show_name}")
                return {}
            imdb_id = self.get_imdb_id(show_id)
            if not imdb_id:
                print(f"❌ Could not get IMDb ID for: '{show_name}'")
                return {}
            
        results = {}
        self.total_episodes = len(self.failed_episodes)
        self.processed_episodes = 0
        
        for idx, episode in enumerate(self.failed_episodes):
            if self.is_stopped():
                break
                
            episode_str = f"S{episode.season:02d}E{episode.episode:02d}"
            print(f"\n📥 Yritetään uudelleen: {episode_str} ({idx+1}/{self.total_episodes})")
            
            subtitle_file = self.download_subtitles_for_episode(
                episode,
                imdb_id,
                language
            )
            
            if subtitle_file:
                results[episode.file_path] = subtitle_file
                self.failed_episodes.remove(episode)
                print(f"  ✅ {episode_str} ladattu onnistuneesti")
            else:
                print(f"  ❌ {episode_str} edelleen epäonnistui")
                
            self.processed_episodes += 1
            
        print(f"\n✅ Uudelleenyritys valmis: {len(results)} jaksoa ladattu")
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

    def _check_auto_cancel(self) -> bool:
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.stop(f"{self.consecutive_failures} consecutive failures")
            return True
        if self.total_failures >= self.max_total_failures:
            self.stop(f"{self.total_failures} total failures")
            return True
        return False

    def _switch_provider(self):
        print("⚠️ Only SubDL available - cannot switch")
        return False

    def _log_status(self):
        print(f"📊 Processed: {self.processed_episodes}/{self.total_episodes}")
        if self.failed_episodes:
            print(f"❌ Failed: {len(self.failed_episodes)} episodes")
        if self.is_stopped():
            print("⏹️ STATUS: Stopped")

    def _update_progress(self, progress: float = None, status: str = None):
        if self.progress_callback:
            if progress is None and self.total_episodes > 0:
                progress = (self.processed_episodes / self.total_episodes) * 100
            if progress is not None:
                self.progress_callback(progress, status or self.current_episode)

    def _update_status(self, message: str):
        if self.status_callback:
            self.status_callback(message)

    def set_callbacks(self, progress_callback=None, status_callback=None):
        self.progress_callback = progress_callback
        self.status_callback = status_callback

    def get_progress(self) -> Dict[str, Any]:
        """
        Get current progress state.
        """
        return {
            'total': self.total_episodes,
            'processed': self.processed_episodes,
            'failed': len(self.failed_episodes),
            'cancelled': self.is_stopped(),
            'current_episode': self.current_episode,
            'consecutive_failures': self.consecutive_failures,
            'provider': self.current_provider
        }

    def get_failed_episodes(self) -> List[EpisodeInfo]:
        """
        Get failed episodes.
        """
        return self.failed_episodes

    def retry_failed_episodes(self, language: str = "en") -> Dict[Path, Path]:
        """
        Retry failed episodes.
        """
        if not self.failed_episodes:
            print("No failed episodes")
            return {}

        print(f"\n🔄 Retrying {len(self.failed_episodes)} failed episodes...")
        
        self.reset_stop()
        
        show_name = self.failed_episodes[0].show_name
        show_info = self.get_show_info_safe(show_name)
        if not show_info:
            print(f"⚠️ Could not find show: {show_name}")
            return {}
            
        imdb_id = show_info.get('imdb_id')
        if not imdb_id:
            show_id = self.find_show_id(show_name)
            if not show_id:
                print(f"❌ Could not find show: {show_name}")
                return {}
            imdb_id = self.get_imdb_id(show_id)
            if not imdb_id:
                print(f"❌ Could not get IMDb ID for: '{show_name}'")
                return {}
            
        results = {}
        self.total_episodes = len(self.failed_episodes)
        self.processed_episodes = 0
        
        for idx, episode in enumerate(self.failed_episodes):
            if self.is_stopped():
                break
                
            episode_str = f"S{episode.season:02d}E{episode.episode:02d}"
            print(f"\n📥 Retrying: {episode_str} ({idx+1}/{self.total_episodes})")
            
            subtitle_file = self.download_subtitles_for_episode(
                episode,
                imdb_id,
                language
            )
            
            if subtitle_file:
                results[episode.file_path] = subtitle_file
                self.failed_episodes.remove(episode)
                print(f"  ✅ {episode_str} downloaded successfully")
            else:
                print(f"  ❌ {episode_str} still failed")
                
            self.processed_episodes += 1
            
        print(f"\n✅ Retry complete: {len(results)} episodes downloaded")
        return results