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
        """Search for subtitles using various criteria."""
        
        # Check if API key is set
        if not self.api_key:
            print("❌ OpenSubtitles API key is missing!")
            return []
        
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
            print(f"🔍 Searching OpenSubtitles: {params}")
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("data", [])
            print(f"✅ Found {len(results)} subtitles from OpenSubtitles")
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error searching subtitles: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"  Status: {e.response.status_code}")
                print(f"  Response: {e.response.text[:200]}")
            return []
    
    def download_subtitle(self, file_id: int) -> Optional[bytes]:
        """Download subtitle file."""
        
        if not self.api_key:
            print("❌ OpenSubtitles API key is missing!")
            return None
        
        url = f"{self.base_url}/download/{file_id}"
        
        try:
            print(f"⬇️ Downloading subtitle: {file_id}")
            response = self.session.get(url)
            response.raise_for_status()
            print(f"✅ Downloaded {len(response.content)} bytes")
            return response.content
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error downloading subtitle: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"  Status: {e.response.status_code}")
                print(f"  Response: {e.response.text[:200]}")
            return None
    
    def get_subtitle_file(self, subtitle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get subtitle file information."""
        
        files = subtitle_data.get("attributes", {}).get("files", [])
        if not files:
            return None
        
        # Select first file (usually best quality)
        return files[0]
    
    def get_subtitle_details(self, subtitle_id: int) -> Optional[Dict[str, Any]]:
        """Get subtitle details by ID."""
        
        url = f"{self.base_url}/subtitles/{subtitle_id}"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json().get("data", {})
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting subtitle details: {e}")
            return None
    
    def search_subtitles_with_fallback(
        self,
        imdb_id: Optional[str] = None,
        query: Optional[str] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Search for subtitles first from OpenSubtitles, then from alternative sources.
        """
        # 1. Try OpenSubtitles
        result = self.search_subtitles(imdb_id, query, season, episode, language)
        
        if result:
            return result
        
        # 2. Try alternative source (SubDL or others)
        print("⚠️ No results from OpenSubtitles, trying fallback...")
        # Add other API client here
        
        return []