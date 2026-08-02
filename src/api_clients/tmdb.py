# api_clients/tmdb.py
import requests
from typing import Optional, List, Dict, Any
from urllib.parse import quote
import time


class TMDBClient:
    """TMDB API client for movie and TV show information."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.themoviedb.org/3"):
        """
        Initialize TMDB client.
        
        Args:
            api_key: TMDB API key
            base_url: Base URL for API (defaults to v3)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "SubtitleMatcher v1.0"
        })
        self.last_request_time = 0
        self.min_request_interval = 0.2  # 5 requests per second max
        
        # Peruutustila
        self._cancelled = False
        self._cancel_lock = False

    def cancel(self):
        """Peruuta meneillään olevat operaatiot"""
        self._cancelled = True
        print("⏹️ TMDB: Peruutetaan...")

    def reset_cancel(self):
        """Nollaa peruutustila"""
        self._cancelled = False

    def is_cancelled(self) -> bool:
        """Onko operaatio peruutettu"""
        return self._cancelled
    
    def _rate_limit(self):
        """Rate limit requests to avoid hitting API limits."""
        if self.is_cancelled():
            return
            
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make authenticated GET request to TMDB API.
        
        Args:
            endpoint: API endpoint (e.g., "/search/tv")
            params: Query parameters
            
        Returns:
            JSON response or None if error
        """
        if self.is_cancelled():
            return None
            
        self._rate_limit()
        
        if self.is_cancelled():
            return None
        
        url = f"{self.base_url}{endpoint}"
        request_params = params or {}
        request_params["api_key"] = self.api_key
        
        try:
            response = self.session.get(url, params=request_params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ TMDB API error: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"  Status: {e.response.status_code}")
                print(f"  Response: {e.response.text[:200]}")
            return None
    
    def search_tv_show(self, query: str, language: str = "en-US") -> List[Dict[str, Any]]:
        """
        Search for TV shows by name.
        
        Args:
            query: Show name to search for
            language: Language for results
            
        Returns:
            List of show results
        """
        if self.is_cancelled():
            return []
            
        if not query:
            return []
        
        params = {
            "query": query,
            "language": language,
            "include_adult": False
        }
        
        data = self._get("/search/tv", params)
        if data:
            return data.get("results", [])
        return []
    
    def search_movie(self, query: str, year: Optional[int] = None, language: str = "en-US") -> List[Dict[str, Any]]:
        """
        Search for movies by name and optionally year.
        
        Args:
            query: Movie title to search for
            year: Optional release year
            language: Language for results
            
        Returns:
            List of movie results
        """
        if self.is_cancelled():
            return []
            
        if not query:
            return []
        
        params = {
            "query": query,
            "language": language,
            "include_adult": False
        }
        
        if year:
            params["year"] = year
        
        data = self._get("/search/movie", params)
        if data:
            return data.get("results", [])
        return []
    
    def get_show_details(self, show_id: int, language: str = "en-US") -> Optional[Dict[str, Any]]:
        """
        Get detailed TV show information.
        
        Args:
            show_id: TMDB show ID
            language: Language for results
            
        Returns:
            Show details or None if error
        """
        if self.is_cancelled():
            return None
            
        if not show_id:
            return None
        
        params = {
            "language": language,
            "append_to_response": "external_ids,credits"
        }
        
        return self._get(f"/tv/{show_id}", params)
    
    def get_episode_details(self, show_id: int, season: int, episode: int, language: str = "en-US") -> Optional[Dict[str, Any]]:
        """
        Get detailed episode information.
        
        Args:
            show_id: TMDB show ID
            season: Season number
            episode: Episode number
            language: Language for results
            
        Returns:
            Episode details or None if error
        """
        if self.is_cancelled():
            return None
            
        if not show_id or not season or not episode:
            return None
        
        params = {
            "language": language,
            "append_to_response": "external_ids"
        }
        
        return self._get(f"/tv/{show_id}/season/{season}/episode/{episode}", params)
    
    def get_external_ids(self, show_id: int) -> Dict[str, str]:
        """
        Get external IDs for a TV show (IMDB, TVDB, etc.).
        
        Args:
            show_id: TMDB show ID
            
        Returns:
            Dictionary of external IDs
        """
        if self.is_cancelled():
            return {}
            
        if not show_id:
            return {}
        
        data = self._get(f"/tv/{show_id}/external_ids")
        if data:
            # Return only non-empty IDs
            return {k: v for k, v in data.items() if v}
        return {}
    
    def get_movie_external_ids(self, movie_id: int) -> Dict[str, str]:
        """
        Get external IDs for a movie (IMDB, etc.).
        
        Args:
            movie_id: TMDB movie ID
            
        Returns:
            Dictionary of external IDs
        """
        if self.is_cancelled():
            return {}
            
        if not movie_id:
            return {}
        
        data = self._get(f"/movie/{movie_id}/external_ids")
        if data:
            # Return only non-empty IDs
            return {k: v for k, v in data.items() if v}
        return {}
    
    def get_imdb_id(self, tmdb_id: int, is_tv: bool = True) -> Optional[str]:
        """
        Get IMDB ID from TMDB ID.
        
        Args:
            tmdb_id: TMDB ID
            is_tv: True for TV show, False for movie
            
        Returns:
            IMDB ID (e.g., "tt1234567") or None
        """
        if self.is_cancelled():
            return None
            
        if is_tv:
            ids = self.get_external_ids(tmdb_id)
        else:
            ids = self.get_movie_external_ids(tmdb_id)
        
        return ids.get("imdb_id")
    
    def get_movie_details(self, movie_id: int, language: str = "en-US") -> Optional[Dict[str, Any]]:
        """
        Get detailed movie information including external IDs.
        
        Args:
            movie_id: TMDB movie ID
            language: Language for results
            
        Returns:
            Movie details or None if error
        """
        if self.is_cancelled():
            return None
            
        if not movie_id:
            return None
        
        params = {
            "language": language,
            "append_to_response": "external_ids,credits"
        }
        
        data = self._get(f"/movie/{movie_id}", params)
        if data:
            # Add formatted fields
            if data.get("release_date"):
                data["year"] = data["release_date"][:4]
            
            # Get IMDB ID from external_ids
            if data.get("external_ids"):
                data["imdb_id"] = data["external_ids"].get("imdb_id")
            
            return data
        return None
    
    def search_by_imdb_id(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        """
        Find TMDB ID from IMDB ID.
        
        Args:
            imdb_id: IMDB ID (e.g., "tt1234567")
            
        Returns:
            TMDB ID or None
        """
        if self.is_cancelled():
            return None
            
        if not imdb_id:
            return None
        
        # Remove "tt" prefix if present
        imdb_id = imdb_id.replace("tt", "")
        
        params = {
            "external_source": "imdb_id"
        }
        
        # Search for TV show
        data = self._get(f"/find/tt{imdb_id}", params)
        if data:
            # Check if it's a TV show
            tv_results = data.get("tv_results", [])
            if tv_results:
                return tv_results[0].get("id")
            
            # Check if it's a movie
            movie_results = data.get("movie_results", [])
            if movie_results:
                return movie_results[0].get("id")
        
        return None
    
    def find_best_match(self, title: str, year: Optional[int] = None, is_tv: bool = False) -> Optional[Dict[str, Any]]:
        """
        Find the best matching TV show or movie.
        
        Args:
            title: Title to search for
            year: Optional year
            is_tv: True for TV show, False for movie
            
        Returns:
            Best matching result or None
        """
        if self.is_cancelled():
            return None
            
        if not title:
            return None
        
        # Search
        if is_tv:
            results = self.search_tv_show(title)
        else:
            results = self.search_movie(title, year)
        
        if not results:
            return None
        
        # If we have a year, try to find exact year match
        if year:
            for result in results:
                result_year = result.get("first_air_date" if is_tv else "release_date", "")
                result_year = result_year[:4] if result_year else None
                if result_year and int(result_year) == year:
                    return result
        
        # Return first result
        return results[0] if results else None
    
    def get_poster_url(self, poster_path: str, size: str = "w500") -> Optional[str]:
        """
        Get full poster URL from poster path.
        
        Args:
            poster_path: Poster path from TMDB
            size: Image size (w92, w154, w185, w342, w500, w780, original)
            
        Returns:
            Full poster URL or None
        """
        if self.is_cancelled():
            return None
            
        if not poster_path:
            return None
        
        return f"https://image.tmdb.org/t/p/{size}{poster_path}"


# Convenience function
def get_tmdb_client(api_key: str) -> TMDBClient:
    """Get TMDB client instance."""
    return TMDBClient(api_key)