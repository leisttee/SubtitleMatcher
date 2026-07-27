# smart_match.py
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
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

class SmartMatcher:
    def __init__(self):
        self.opensubtitles = OpenSubtitlesClient(Config.OPENSUBTITLES_API_KEY)
        self.tmdb = TMDBClient(Config.TMDB_API_KEY)
    
    def scan_video_library(self, library_path: str) -> List[EpisodeInfo]:
        """Skannaa videokansion ja tunnistaa sarjat, kaudet ja jaksot"""
        
        episodes = []
        library = Path(library_path)
        
        for video_file in library.rglob("*"):
            if not self._is_video_file(video_file):
                continue
            
            episode_info = self._parse_filename(video_file.name)
            if episode_info:
                episode_info.file_path = video_file
                episodes.append(episode_info)
        
        return episodes
    
    def _is_video_file(self, file_path: Path) -> bool:
        """Tarkistaa onko tiedosto video"""
        video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}
        return file_path.suffix.lower() in video_extensions
    
    def _parse_filename(self, filename: str) -> Optional[EpisodeInfo]:
        """Parsii videotiedoston nimen"""
        
        # Common patterns: Show.Name.S01E01.mkv, Show Name - 1x01.mp4, etc.
        patterns = [
            # Pattern: Show.Name.S01E01.mkv
            r'(.+?)\.S(\d{2})E(\d{2})',
            # Pattern: Show Name - 1x01.mp4
            r'(.+?)\s*-\s*(\d+)x(\d+)',
            # Pattern: Show.Name.1x01.mkv
            r'(.+?)\.(\d+)x(\d+)',
            # Pattern: Show.Name.S01E01E02.mkv (double episode)
            r'(.+?)\.S(\d{2})E(\d{2})E\d{2}',
            # Pattern: Show.Name.101.mkv (season 1, episode 1)
            r'(.+?)\.(\d)(\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                show_name = self._clean_show_name(match.group(1))
                season = int(match.group(2))
                episode = int(match.group(3))
                
                return EpisodeInfo(
                    show_name=show_name,
                    season=season,
                    episode=episode,
                    file_path=Path("")  # Will be set later
                )
        
        return None
    
    def _clean_show_name(self, name: str) -> str:
        """Siivoaa sarjan nimen"""
        # Poista ylimääräiset pisteet ja välilyönnit
        name = re.sub(r'[.\s]+', ' ', name).strip()
        # Poista vuosiluku (2000-2099)
        name = re.sub(r'\b(19|20)\d{2}\b', '', name)
        # Poista laatumerkinnät (720p, WEBRip, jne.)
        name = re.sub(r'\b(720p|1080p|2160p|WEBRip|WEB-DL|BluRay|HDRip|BRRip)\b', '', name, flags=re.IGNORECASE)
        return name.strip()
    
    def find_show_id(self, show_name: str) -> Optional[int]:
        """Etsii sarjan TMDB ID:n"""
        
        results = self.tmdb.search_tv_show(show_name)
        if not results:
            return None
        
        # Ota ensimmäinen tulos
        return results[0].get("id")
    
    def get_imdb_id(self, show_id: int) -> Optional[str]:
        """Hakee IMDB ID:n TMDB ID:n perusteella"""
        
        external_ids = self.tmdb.get_external_ids(show_id)
        return external_ids.get("imdb_id")
    
    def download_subtitles_for_episode(self, episode_info: EpisodeInfo, imdb_id: str) -> Optional[Path]:
        """Lataa tekstitykset yhdelle jaksolle"""
        
        subtitles = self.opensubtitles.search_subtitles(
            imdb_id=imdb_id,
            season=episode_info.season,
            episode=episode_info.episode,
            language=episode_info.language
        )
        
        if not subtitles:
            return None
        
        # Ota ensimmäinen tekstitys
        subtitle_data = subtitles[0]
        file_info = self.opensubtitles.get_subtitle_file(subtitle_data)
        
        if not file_info:
            return None
        
        file_id = file_info.get("file_id")
        if not file_id:
            return None
        
        # Lataa tekstitys
        content = self.opensubtitles.download_subtitle(file_id)
        if not content:
            return None
        
        # Tallenna tiedosto
        output_dir = episode_info.file_path.parent
        output_file = output_dir / f"{episode_info.file_path.stem}.{episode_info.language}.srt"
        
        with open(output_file, "wb") as f:
            f.write(content)
        
        return output_file
    
    def match_all_episodes(self, library_path: str, language: str = "en") -> Dict[Path, Path]:
        """Suorittaa Smart Match -toiminnon koko kirjastolle"""
        
        # 1. Skannaa videot
        episodes = self.scan_video_library(library_path)
        if not episodes:
            return {}
        
        # 2. Tunnista sarja
        show_name = episodes[0].show_name
        show_id = self.find_show_id(show_name)
        if not show_id:
            print(f"Could not find show: {show_name}")
            return {}
        
        imdb_id = self.get_imdb_id(show_id)
        if not imdb_id:
            print(f"Could not get IMDB ID for: {show_name}")
            return {}
        
        # 3. Lataa tekstitykset
        results = {}
        for episode in episodes:
            subtitle_file = self.download_subtitles_for_episode(episode, imdb_id)
            if subtitle_file:
                results[episode.file_path] = subtitle_file
        
        return results