# api_clients/opensubtitles.py
import requests
import time
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
        self.last_request_time = 0
        self.min_request_interval = 1.0
    
    def _rate_limit(self):
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def search_subtitles(self, 
                        imdb_id: Optional[str] = None,
                        query: Optional[str] = None,
                        season: Optional[int] = None,
                        episode: Optional[int] = None,
                        language: str = "en") -> List[Dict[str, Any]]:
        if not self.api_key:
            print("❌ OpenSubtitles API key is missing!")
            return []
        
        self._rate_limit()
        
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
            
            # Filter valid subtitles
            valid_results = []
            for result in results:
                files = result.get("attributes", {}).get("files", [])
                if files and files[0].get("file_id"):
                    # Get the file_id and check if it's valid
                    file_id = files[0].get("file_id")
                    valid_results.append(result)
            
            print(f"✅ Found {len(valid_results)} valid subtitles from OpenSubtitles")
            return valid_results
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                print("❌ Too many requests (429). Waiting 10 seconds...")
                time.sleep(10)
                return self.search_subtitles(imdb_id, query, season, episode, language)
            
            print(f"❌ Error searching subtitles: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"  Status: {e.response.status_code}")
                print(f"  Response: {e.response.text[:200]}")
            return []
    
    def download_subtitle(self, file_id: int) -> Optional[bytes]:
        """Download subtitle using the correct endpoint."""
        if not self.api_key:
            print("❌ OpenSubtitles API key is missing!")
            return None
        
        self._rate_limit()
        
        # Try different endpoints
        endpoints = [
            f"{self.base_url}/download/{file_id}",
            f"{self.base_url}/download/{file_id}?format=srt",
            f"{self.base_url}/download?file_id={file_id}",
            f"https://dl.opensubtitles.org/en/download/sub/{file_id}",
            f"https://www.opensubtitles.com/en/download/sub/{file_id}",
        ]
        
        for endpoint in endpoints:
            try:
                print(f"⬇️ Trying: {endpoint}")
                response = self.session.get(endpoint)
                
                if response.status_code == 200:
                    content = response.content
                    if len(content) > 100:
                        print(f"✅ Downloaded {len(content)} bytes")
                        return content
                    else:
                        print(f"⚠️ Small file: {len(content)} bytes")
                        continue
                
                if response.status_code == 404:
                    print(f"  ❌ 404 Not Found")
                    continue
                    
                if response.status_code == 401:
                    print(f"  ❌ Unauthorized (401)")
                    continue
                    
                if response.status_code == 429:
                    print(f"  ❌ Rate limited. Waiting...")
                    time.sleep(10)
                    continue
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")
                continue
        
        print(f"❌ All download attempts failed for file_id: {file_id}")
        return None
    
    def get_subtitle_file(self, subtitle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        files = subtitle_data.get("attributes", {}).get("files", [])
        if not files:
            return None
        return files[0]
    
    def get_subtitle_details(self, subtitle_id: int) -> Optional[Dict[str, Any]]:
        self._rate_limit()
        url = f"{self.base_url}/subtitles/{subtitle_id}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json().get("data", {})
        except requests.exceptions.RequestException as e:
            print(f"Error getting subtitle details: {e}")
            return None