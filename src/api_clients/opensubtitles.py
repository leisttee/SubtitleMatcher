# api_clients/opensubtitles.py
import requests
import hashlib
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

class OpenSubtitlesClient:
    def __init__(self, api_key: str, base_url: str = "https://api.opensubtitles.com/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "SubtitleMatcher v1.0"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def search_subtitles(self, 
                        imdb_id: Optional[str] = None,
                        query: Optional[str] = None,
                        season: Optional[int] = None,
                        episode: Optional[int] = None,
                        language: str = "en") -> List[Dict[str, Any]]:
        """Hakee tekstityksiä eri kriteereillä"""
        
        url = f"{self.base_url}/subtitles"
        params = {
            "languages": language
        }
        
        if imdb_id:
            params["imdb_id"] = imdb_id
        if query:
            params["query"] = query
        if season is not None:
            params["season_number"] = season
        if episode is not None:
            params["episode_number"] = episode
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Palauta tekstitykset listana
            return data.get("data", [])
            
        except requests.exceptions.RequestException as e:
            print(f"Error searching subtitles: {e}")
            return []
    
    def download_subtitle(self, file_id: int) -> Optional[bytes]:
        """Lataa tekstitystiedoston"""
        
        url = f"{self.base_url}/download/{file_id}"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.content
            
        except requests.exceptions.RequestException as e:
            print(f"Error downloading subtitle: {e}")
            return None
    
    def get_subtitle_file(self, subtitle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Hakee tekstityksen tiedostotiedot"""
        
        files = subtitle_data.get("attributes", {}).get("files", [])
        if not files:
            return None
        
        # Valitaan ensimmäinen tiedosto (yleensä paras laatu)
        return files[0]
    
    def get_subtitle_details(self, subtitle_id: int) -> Optional[Dict[str, Any]]:
        """Hakee tekstityksen yksityiskohdat ID:llä"""
        
        url = f"{self.base_url}/subtitles/{subtitle_id}"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json().get("data", {})
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting subtitle details: {e}")
            return None