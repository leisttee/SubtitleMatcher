# smart_match.py
import re
import time
import threading
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
        
        # Peruutus- ja virhehallinta
        self.cancelled = False
        self.paused = False
        self.cancel_lock = threading.Lock()
        self.progress_callback = None
        self.status_callback = None
        
        # Virheiden seuranta
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        self.total_failures = 0
        self.max_total_failures = 10
        self.api_failure_count = 0
        self.api_failure_threshold = 3
        
        # Prosessin tila
        self.total_episodes = 0
        self.processed_episodes = 0
        self.failed_episodes = []
        self.current_episode = None
        self.current_provider = 'subdl'  # 'subdl' tai 'opensubtitles'
        
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

    # === PERUUTUS JA VIRHEIDENHALLINTA ===

    def cancel(self, reason: str = ""):
        """Peruuta meneillään oleva operaatio"""
        with self.cancel_lock:
            self.cancelled = True
            print(f"\n⏹️ PERUUTETAAN: {reason if reason else 'Käyttäjän toimesta'}")
            self._log_status()

    def reset_cancel(self):
        """Nollaa peruutustila"""
        with self.cancel_lock:
            self.cancelled = False

    def is_cancelled(self) -> bool:
        """Onko operaatio peruutettu"""
        with self.cancel_lock:
            return self.cancelled

    def set_callbacks(self, progress_callback=None, status_callback=None):
        """Aseta takaisinkutsut UI-päivityksiä varten"""
        self.progress_callback = progress_callback
        self.status_callback = status_callback

    def _update_progress(self, progress: float = None, status: str = None):
        """Päivitä edistyminen callbackin kautta"""
        if self.progress_callback:
            if progress is None and self.total_episodes > 0:
                progress = (self.processed_episodes / self.total_episodes) * 100
            if progress is not None:
                self.progress_callback(progress, status or self.current_episode)

    def _update_status(self, message: str):
        """Päivitä status callbackin kautta"""
        if self.status_callback:
            self.status_callback(message)

    def _log_status(self):
        """Tulosta nykyinen tila"""
        print(f"📊 Käsitelty: {self.processed_episodes}/{self.total_episodes}")
        if self.failed_episodes:
            print(f"❌ Epäonnistuneet: {len(self.failed_episodes)} jaksoa")
        if self.is_cancelled():
            print("⏹️ TILA: Peruutettu")

    def _check_auto_cancel(self) -> bool:
        """Tarkista automaattinen peruutus"""
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.cancel(f"{self.consecutive_failures} peräkkäistä virhettä")
            return True
        
        if self.total_failures >= self.max_total_failures:
            self.cancel(f"{self.total_failures} virhettä yhteensä")
            return True
            
        return False

    def _switch_provider(self):
        """Vaihda API-palvelua virhetilanteessa"""
        if self.current_provider == 'subdl' and self.opensubtitles:
            self.current_provider = 'opensubtitles'
            print("🔄 Vaihdetaan OpenSubtitles-palveluun...")
            self.api_failure_count = 0
            return True
        elif self.current_provider == 'opensubtitles' and self.subdl:
            self.current_provider = 'subdl'
            print("🔄 Vaihdetaan SubDL-palveluun...")
            self.api_failure_count = 0
            return True
        return False

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
        Select the best subtitle from SubDL results with intelligent scoring.
        """
        if not subtitles:
            return None
        
        scored_subtitles = []
        
        for subtitle in subtitles:
            score = 0
            
            # 1. Priorisoi SDH (kuulovammaisille) - usein parempi
            if subtitle.get("hearing_impaired"):
                score += 10
            
            # 2. Tarkista onko unpack_files tai url
            if subtitle.get("unpack_files") or subtitle.get("url"):
                score += 20
            
            # 3. Vältä "forced" tai "foreign" (vain vieraskieliset osat)
            filename = subtitle.get("filename", "").lower()
            if "forced" in filename or "foreign" in filename:
                score -= 10
            
            # 4. Priorisoi suosituimmat
            downloads = subtitle.get("download_count", 0)
            if downloads:
                score += min(downloads / 1000, 5)
            
            # 5. Tarkista onko nId tai sd_id (legacy)
            if subtitle.get("nId") or subtitle.get("sd_id"):
                score += 5
            
            scored_subtitles.append((score, subtitle))
        
        # Järjestä pistemäärän mukaan
        scored_subtitles.sort(key=lambda x: x[0], reverse=True)
        
        if scored_subtitles:
            best_score, best_subtitle = scored_subtitles[0]
            print(f"  ✓ Subtitle selected with score: {best_score}")
            return best_subtitle
        
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
            if self.is_cancelled():
                break
                
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
        if self.is_cancelled():
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
            if self.is_cancelled():
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
        """
        Get IMDb ID from TMDB.
        """
        if self.is_cancelled():
            return None
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
            if self.is_cancelled():
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
        """
        Parse movie filename - improved version.
        """
        name = Path(filename).stem

        # Poista yleiset laatutunnisteet
        clean_name = re.sub(
            r"\b(480p|720p|1080p|2160p|4K|UHD|WEBRip|WEB-DL|BluRay|HDRip|BRRip|BDRip|YIFY|YTS|RARBG|REPACK|PROPER|x264|x265|HEVC|5\.1|7\.1|2\.0|Stereo|DD5\.1|AC3|DTS|AAC|MP3)\b",
            "",
            name,
            flags=re.IGNORECASE
        )

        # Poista ryhmät [YTS.GG - YTS.BZ] tms
        clean_name = re.sub(r'\[.*?\]', '', clean_name)
        clean_name = re.sub(r'\{.*?\}', '', clean_name)

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
        Clean movie title - improved version for better detection.
        """
        # Poista tiedostopääte
        name = Path(name).stem
        
        # Poista yleiset laatutunnisteet (SÄILYTTÄEN vuosiluvun)
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
        
        # Korvaa pisteet, alaviivat ja yhdysmerkit välilyönneillä
        name = re.sub(r'[._-]', ' ', name)
        
        # Poista ylimääräiset välilyönnit
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Poista hakasulut ja aaltosulut
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\{.*?\}', '', name)
        
        # Käsittele sulut - säilytä vuosiluvut
        year_match = re.search(r'\((\d{4})\)', name)
        if year_match:
            year = year_match.group(1)
            # Poista kaikki sulut paitsi vuosiluku
            name = re.sub(r'\([^)]*\)', '', name)
            # Lisää vuosiluku takaisin
            name = f"{name.strip()} ({year})"
        else:
            # Poista kaikki sulut
            name = re.sub(r'\([^)]*\)', '', name)
        
        # Poista ylimääräiset välilyönnit
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Capitalize first letter of each word (paitsi lyhyet sanat)
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
        """
        Search TMDB movie ID.
        """
        if self.is_cancelled():
            return None
            
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
            if self.is_cancelled():
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
        """
        Get IMDb ID for a movie from TMDB.
        """
        if self.is_cancelled():
            return None
        if not self.tmdb:
            return None
        external_ids = self.tmdb.get_movie_external_ids(movie_id)
        return external_ids.get("imdb_id")

    def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed movie information from TMDB.
        """
        if self.is_cancelled():
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

    def get_show_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed TV show information from TMDB.
        """
        if self.is_cancelled():
            return None
            
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
        if self.is_cancelled():
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
        Download subtitles using SubDL.
        """
        try:
            self.current_provider = 'subdl'
            
            # Search subtitles
            subtitles = self.subdl.search_subtitles(
                imdb_id=imdb_id,
                season=episode_info.season,
                episode=episode_info.episode,
                language=language
            )

            if not subtitles:
                print(f"  SubDL: Ei tekstejä S{episode_info.season:02d}E{episode_info.episode:02d}")
                self.api_failure_count += 1
                return None

            # Select best subtitle
            subtitle_data = self._select_best_subtitle_subdl(subtitles)
            if not subtitle_data:
                print("  SubDL: Ei sopivaa tekstiä")
                self.api_failure_count += 1
                return None

            # Download
            content = self.subdl.download_subtitle(subtitle_data)
            if not content:
                print("  SubDL: Lataus epäonnistui")
                self.api_failure_count += 1
                return None

            # Save as .srt
            output_dir = episode_info.file_path.parent
            output_file = output_dir / f"{episode_info.file_path.stem}.srt"

            with open(output_file, "wb") as f:
                f.write(content)

            print(f"  ✅ SubDL: {output_file.name}")
            self.api_failure_count = 0
            return output_file

        except Exception as e:
            print(f"  ❌ SubDL virhe: {e}")
            self.api_failure_count += 1
            return None

    def _download_with_opensubtitles(
        self,
        imdb_id: str,
        episode_info: EpisodeInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles using OpenSubtitles (fallback).
        """
        if not self.opensubtitles:
            return None
            
        try:
            self.current_provider = 'opensubtitles'
            
            subtitles = self.opensubtitles.search_subtitles(
                imdb_id=imdb_id,
                season=episode_info.season,
                episode=episode_info.episode,
                language=language
            )

            if not subtitles:
                print(f"  OpenSubtitles: Ei tekstejä S{episode_info.season:02d}E{episode_info.episode:02d}")
                self.api_failure_count += 1
                return None

            subtitle_data = self._select_best_subtitle(subtitles)
            if not subtitle_data:
                print("  OpenSubtitles: Ei sopivaa tekstiä")
                self.api_failure_count += 1
                return None

            file_info = self.opensubtitles.get_subtitle_file(subtitle_data)
            if not file_info:
                print("  OpenSubtitles: Ei tiedostotietoja")
                self.api_failure_count += 1
                return None

            file_id = file_info.get("file_id")
            if not file_id:
                print("  OpenSubtitles: Ei file_id")
                self.api_failure_count += 1
                return None

            content = self.opensubtitles.download_subtitle(file_id)
            if not content:
                print("  OpenSubtitles: Lataus epäonnistui")
                self.api_failure_count += 1
                return None

            # Save as .srt
            output_dir = episode_info.file_path.parent
            output_file = output_dir / f"{episode_info.file_path.stem}.srt"

            with open(output_file, "wb") as f:
                f.write(content)

            print(f"  ✅ OpenSubtitles: {output_file.name}")
            self.api_failure_count = 0
            return output_file

        except Exception as e:
            print(f"  ❌ OpenSubtitles virhe: {e}")
            self.api_failure_count += 1
            return None

    def download_subtitles_for_episode(
        self,
        episode_info: EpisodeInfo,
        imdb_id: str,
        language: str = None
    ) -> Optional[Path]:
        """
        Download subtitles for a single episode with intelligent retry and provider switching.
        """
        if self.is_cancelled():
            return None
            
        if language is None:
            language = episode_info.language

        episode_str = f"S{episode_info.season:02d}E{episode_info.episode:02d}"
        self.current_episode = episode_str

        # Try primary provider first, then fallback
        providers = []
        if self.subdl:
            providers.append(('subdl', self._download_with_subdl))
        if self.opensubtitles:
            providers.append(('opensubtitles', self._download_with_opensubtitles))

        for provider_name, download_func in providers:
            if self.is_cancelled():
                return None
                
            print(f"  🔍 {provider_name}: haetaan {episode_str}...")
            result = download_func(imdb_id, episode_info, language)
            
            if result:
                return result
                
            # Provider failed, check if we should switch
            if self.api_failure_count >= self.api_failure_threshold:
                if self._switch_provider():
                    # Reset failure count after switching
                    self.api_failure_count = 0
                    continue

        # All providers failed
        return None

                # All providers failed
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

    def match_all_episodes(
        self,
        library_path: str,
        language: str = "en"
    ) -> Dict[Path, Path]:
        """
        Match all episodes and download subtitles with cancel support and smart error handling.
        """
        # Nollaa tila
        self.reset_cancel()
        self.consecutive_failures = 0
        self.total_failures = 0
        self.failed_episodes = []
        self.processed_episodes = 0
        self.current_provider = 'subdl'
        self.api_failure_count = 0

        # Skannaa kirjasto
        episodes = self.scan_video_library(library_path)

        if not episodes:
            print("No episodes found in library")
            return {}

        if self.is_cancelled():
            print("⏹️ Operaatio peruutettu ennen aloitusta")
            return {}

        # Tunnista sarja
        show_name = episodes[0].show_name
        print(f"\n🎬 Detected show: '{show_name}'")

        show_id = self.find_show_id(show_name)
        if self.is_cancelled():
            print("⏹️ Operaatio peruutettu")
            return {}
            
        if not show_id:
            print(f"❌ Could not find show: '{show_name}'")
            return {}

        imdb_id = self.get_imdb_id(show_id)
        if self.is_cancelled():
            print("⏹️ Operaatio peruutettu")
            return {}
            
        if not imdb_id:
            print(f"❌ Could not get IMDb ID for: '{show_name}'")
            return {}

        # Valmistele lataus
        self.total_episodes = len(episodes)
        print(f"📦 {self.total_episodes} jaksoa")
        print(f"🌐 Kieli: {language}")
        print(f"🎯 IMDB ID: {imdb_id}")
        print("-" * 50)

        results = {}

        for idx, episode in enumerate(episodes):
            # Tarkista peruutus
            if self.is_cancelled():
                print(f"\n⏹️ Peruutettu {self.processed_episodes}/{self.total_episodes} jakson jälkeen")
                break

            # Tarkista automaattinen peruutus
            if self._check_auto_cancel():
                break

            # Päivitä status
            episode_str = f"S{episode.season:02d}E{episode.episode:02d}"
            self.current_episode = episode_str
            
            progress = (self.processed_episodes / self.total_episodes) * 100
            print(f"\n📥 [{progress:.1f}%] {episode_str} ({idx+1}/{self.total_episodes})")
            self._update_progress(progress, f"Processing: {episode_str}")

            # Lataa tekstitys
            subtitle_file = self.download_subtitles_for_episode(
                episode,
                imdb_id,
                language
            )

            if subtitle_file:
                results[episode.file_path] = subtitle_file
                self.consecutive_failures = 0
                print(f"  ✅ {episode_str} ladattu onnistuneesti")
            else:
                self.failed_episodes.append(episode)
                self.consecutive_failures += 1
                self.total_failures += 1
                print(f"  ❌ {episode_str} ei löytynyt")

            self.processed_episodes += 1
            self._update_progress()

        # Näytä yhteenveto
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
        
        if self.is_cancelled():
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
        # Nollaa tila
        self.reset_cancel()
        self.consecutive_failures = 0
        self.total_failures = 0
        self.failed_movies = []
        self.processed_movies = 0

        # Skannaa kirjasto
        movies = self.scan_movie_library(library_path)

        if not movies:
            print("No movies found in library")
            return {}

        if self.is_cancelled():
            print("⏹️ Operaatio peruutettu ennen aloitusta")
            return {}

        self.total_movies = len(movies)
        print(f"\n🎬 Aloitetaan lataus: {self.total_movies} elokuvaa")
        print(f"🌐 Kieli: {language}")
        print("-" * 50)

        results = {}

        for idx, movie in enumerate(movies):
            # Tarkista peruutus
            if self.is_cancelled():
                print(f"\n⏹️ Peruutettu {self.processed_movies}/{self.total_movies} elokuvan jälkeen")
                break

            # Päivitä status
            self.current_movie = movie.title
            progress = (self.processed_movies / self.total_movies) * 100
            print(f"\n📥 [{progress:.1f}%] {movie.title} ({idx+1}/{self.total_movies})")
            self._update_progress(progress, f"Processing: {movie.title}")

            # Lataa tekstitys
            subtitle_file = self.download_subtitles_for_movie(
                movie,
                language
            )

            if subtitle_file:
                results[movie.file_path] = subtitle_file
                self.consecutive_failures = 0
                print(f"  ✅ {movie.title} ladattu onnistuneesti")
            else:
                self.failed_movies.append(movie)
                self.consecutive_failures += 1
                self.total_failures += 1
                print(f"  ❌ {movie.title} ei löytynyt")

            self.processed_movies += 1
            self._update_progress()

        # Näytä yhteenveto
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
        
        if self.is_cancelled():
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

    def download_subtitles_for_movie(
        self,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles for a movie using SubDL (primary) or OpenSubtitles (fallback).
        """
        if self.is_cancelled():
            return None
            
        print(f"Searching for movie: {movie_info.title}")
        
        # First get IMDB ID via TMDB
        movie_id = self.find_movie_id(movie_info.title, movie_info.year)
        if self.is_cancelled():
            return None
            
        if not movie_id:
            print(f"Could not find movie: {movie_info.title}")
            return None
            
        imdb_id = self.get_movie_imdb_id(movie_id)
        if self.is_cancelled():
            return None
            
        if not imdb_id:
            print(f"Could not get IMDb ID for: {movie_info.title}")
            return None
            
        print(f"IMDB ID: {imdb_id}")
        
        # Try SubDL first (PRIMARY)
        if self.subdl:
            print("🔍 Using SubDL (PRIMARY)...")
            subtitle_file = self._download_movie_with_subdl(imdb_id, movie_info, language)
            if subtitle_file:
                return subtitle_file
            print("  SubDL failed, trying OpenSubtitles...")
        
        # Try OpenSubtitles as fallback
        if self.opensubtitles:
            print("🔍 Using OpenSubtitles (FALLBACK)...")
            return self._download_movie_with_opensubtitles(imdb_id, movie_info, language)
        
        print("❌ No subtitle providers available")
        return None

    def _download_movie_with_subdl(
        self,
        imdb_id: str,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles for movie using SubDL.
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

            # Save with .srt extension
            output_dir = movie_info.file_path.parent
            output_file = output_dir / f"{movie_info.file_path.stem}.srt"

            with open(output_file, "wb") as f:
                f.write(content)

            print(f"  ✅ Downloaded from SubDL: {output_file.name}")
            return output_file

        except Exception as e:
            print(f"  ❌ SubDL error: {e}")
            return None

    def _download_movie_with_opensubtitles(
        self,
        imdb_id: str,
        movie_info: MovieInfo,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Download subtitles for movie using OpenSubtitles (fallback).
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

            # Save with .srt extension
            output_dir = movie_info.file_path.parent
            output_file = output_dir / f"{movie_info.file_path.stem}.srt"

            with open(output_file, "wb") as f:
                f.write(content)

            print(f"  ✅ Downloaded from OpenSubtitles: {output_file.name}")
            return output_file

        except Exception as e:
            print(f"  ❌ OpenSubtitles error: {e}")
            return None

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

    def get_progress(self) -> Dict[str, Any]:
        """
        Hae nykyinen edistymistila.
        """
        return {
            'total': self.total_episodes,
            'processed': self.processed_episodes,
            'failed': len(self.failed_episodes),
            'cancelled': self.is_cancelled(),
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
        
        # Nollaa peruutus
        self.reset_cancel()
        
        # Haetaan IMDB ID uudelleen
        show_name = self.failed_episodes[0].show_name
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
            if self.is_cancelled():
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