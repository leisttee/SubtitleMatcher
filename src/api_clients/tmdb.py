# api_clients/tmdb.py
import requests
from typing import Optional, List, Dict, Any

class TMDBClient:
    def __init__(self, api_key: str, base_url: str = "https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
    
    def search_tv_show(self, query: str) -> List[Dict[str, Any]]:
        """Etsii TV-sarjaa nimellä"""
        
        url = f"{self.base_url}/search/tv"
        params = {
            "api_key": self.api_key,
            "query": query,
            "language": "en-US"
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
            
        except requests.exceptions.RequestException as e:
            print(f"Error searching TV show: {e}")
            return []
    
    def get_show_details(self, show_id: int) -> Optional[Dict[str, Any]]:
        """Hakee sarjan yksityiskohdat"""
        
        url = f"{self.base_url}/tv/{show_id}"
        params = {
            "api_key": self.api_key,
            "language": "en-US"
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting show details: {e}")
            return None
    
    def get_episode_details(self, show_id: int, season: int, episode: int) -> Optional[Dict[str, Any]]:
        """Hakee jakson yksityiskohdat"""
        
        url = f"{self.base_url}/tv/{show_id}/season/{season}/episode/{episode}"
        params = {
            "api_key": self.api_key,
            "language": "en-US"
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting episode details: {e}")
            return None
    
    def get_external_ids(self, show_id: int) -> Dict[str, str]:
        """Hakee sarjan ulkoiset ID:t (IMDB, TVDB jne.)"""
        
        url = f"{self.base_url}/tv/{show_id}/external_ids"
        params = {
            "api_key": self.api_key
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting external IDs: {e}")
            return {}