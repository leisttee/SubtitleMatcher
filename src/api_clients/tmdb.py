# api_clients/tmdb.py
import requests
from typing import Optional, List, Dict, Any
import time

class TMDBClient:
    def __init__(self, api_key: str, base_url: str = "https://api.themoviedb.org/3"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.last_request_time = 0
        self.min_request_interval = 0.5
    
    def _rate_limit(self):
        """Rate limiting to avoid 429 errors."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def search_tv_show(self, query: str) -> List[Dict[str, Any]]:
        """Search for TV show by name."""
        if not self.api_key:
            print("❌ TMDB API key is missing!")
            return []
        
        self._rate_limit()
        
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
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                print(f"❌ Rate limited. Waiting 5 seconds...")
                time.sleep(5)
                return self.search_tv_show(query)
            print(f"❌ Error searching TV show: {e}")
            return []
    
    def search_movie(self, query: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for movie by name and year."""
        if not self.api_key:
            print("❌ TMDB API key is missing!")
            return []
        
        self._rate_limit()
        
        url = f"{self.base_url}/search/movie"
        params = {
            "api_key": self.api_key,
            "query": query,
            "language": "en-US"
        }
        
        if year:
            params["year"] = year
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                print(f"❌ Rate limited. Waiting 5 seconds...")
                time.sleep(5)
                return self.search_movie(query, year)
            print(f"❌ Error searching movie: {e}")
            return []
    
    def get_show_details(self, show_id: int) -> Optional[Dict[str, Any]]:
        """Get TV show details with images."""
        self._rate_limit()
        
        url = f"{self.base_url}/tv/{show_id}"
        params = {
            "api_key": self.api_key,
            "language": "en-US",
            "append_to_response": "images,credits"
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("poster_path"):
                data["poster_url"] = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
            if data.get("backdrop_path"):
                data["backdrop_url"] = f"https://image.tmdb.org/t/p/original{data['backdrop_path']}"
            
            return data
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error getting show details: {e}")
            return None
    
    def get_movie_details(self, movie_id: int) -> Optional[Dict[str, Any]]:
        """Get movie details with images."""
        self._rate_limit()
        
        url = f"{self.base_url}/movie/{movie_id}"
        params = {
            "api_key": self.api_key,
            "language": "en-US",
            "append_to_response": "images,credits"
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("poster_path"):
                data["poster_url"] = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
            if data.get("backdrop_path"):
                data["backdrop_url"] = f"https://image.tmdb.org/t/p/original{data['backdrop_path']}"
            
            return data
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting movie details: {e}")
            return None
    
    def get_episode_details(self, show_id: int, season: int, episode: int) -> Optional[Dict[str, Any]]:
        """Get episode details."""
        self._rate_limit()
        
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
            print(f"❌ Error getting episode details: {e}")
            return None
    
    def get_external_ids(self, show_id: int) -> Dict[str, str]:
        """Get external IDs for TV show (IMDB, TVDB, etc.)."""
        self._rate_limit()
        
        url = f"{self.base_url}/tv/{show_id}/external_ids"
        params = {
            "api_key": self.api_key
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error getting external IDs: {e}")
            return {}
    
    def get_movie_external_ids(self, movie_id: int) -> Dict[str, str]:
        """Get external IDs for movie (IMDB, etc.)."""
        self._rate_limit()
        
        url = f"{self.base_url}/movie/{movie_id}/external_ids"
        params = {
            "api_key": self.api_key
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error getting movie external IDs: {e}")
            return {}