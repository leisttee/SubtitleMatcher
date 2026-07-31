# api_clients/subdl.py
import requests
import time
import json
from typing import Optional, List, Dict, Any


class SubDLClient:
    def __init__(self, api_key: str, base_url: str = "https://api.subdl.com/api/v2"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SubtitleMatcher v1.0"
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5
    
    def _rate_limit(self):
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def search_subtitles(self, 
                        imdb_id: Optional[str] = None,
                        sd_id: Optional[str] = None,
                        tmdb_id: Optional[int] = None,
                        season: Optional[int] = None,
                        episode: Optional[int] = None,
                        language: str = "en") -> List[Dict[str, Any]]:
        """Search for subtitles using IMDB ID or TMDB ID."""
        
        if not self.api_key:
            print("❌ SubDL API key is missing!")
            return []
        
        self._rate_limit()
        
        all_results = []
        
        # Use v1 API first (more reliable)
        v1_url = "https://api.subdl.com/api/v1/subtitles"
        v1_params = {
            "api_key": self.api_key,
            "imdb_id": imdb_id,
            "languages": language.upper(),  # IMPORTANT: Uppercase
        }
        if season is not None:
            v1_params["season_number"] = season
        if episode is not None:
            v1_params["episode_number"] = episode
        # Add unpack=1 to get individual files
        v1_params["unpack"] = 1
        
        try:
            print(f"🔍 Searching SubDL v1: {v1_params}")
            response = self.session.get(v1_url, params=v1_params)
            
            if response.status_code == 200:
                data = response.json()
                print(f"📄 v1 Response keys: {list(data.keys())}")
                
                # v1 returns subtitles in 'subtitles' key
                subtitles = data.get("subtitles", [])
                if subtitles:
                    print(f"✅ Found {len(subtitles)} subtitles from SubDL v1")
                    # Debug: print first subtitle keys
                    if subtitles:
                        print(f"  First subtitle keys: {list(subtitles[0].keys())}")
                        if subtitles[0].get("url"):
                            print(f"  url: {subtitles[0].get('url')}")
                    return subtitles
                else:
                    print("❌ No subtitles in v1 response")
                    # Try v2 as fallback
            else:
                print(f"❌ v1 API error: {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                
        except Exception as e:
            print(f"❌ v1 API failed: {e}")
        
        # Fallback to v2
        print("🔍 Trying v2 API as fallback...")
        v2_url = "https://api.subdl.com/api/v2/subtitles/search"
        v2_params = {
            "imdb_id": imdb_id,
            "languages": language,
        }
        if season is not None:
            v2_params["season"] = season
        if episode is not None:
            v2_params["episode"] = episode
        
        try:
            print(f"🔍 Searching SubDL v2: {v2_params}")
            response = self.session.get(v2_url, params=v2_params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            for result in results:
                if result.get("subtitles"):
                    for sub in result["subtitles"]:
                        # v2 uses 'nId'
                        n_id = sub.get("nId") or sub.get("sd_id")
                        if n_id:
                            sub["nId"] = n_id
                            all_results.append(sub)
                elif result.get("sd_id"):
                    # If result itself has sd_id, use it as nId
                    n_id = result.get("sd_id")
                    result["nId"] = n_id
                    all_results.append(result)
            
            if all_results:
                print(f"✅ Found {len(all_results)} subtitles from SubDL v2")
                if all_results:
                    print(f"  First subtitle keys: {list(all_results[0].keys())}")
        except Exception as e:
            print(f"❌ v2 API failed: {e}")
        
        return all_results
    
    def download_subtitle_by_url(self, subtitle_url: str) -> Optional[bytes]:
        """Download subtitle using the url from v1 API response."""
        
        if not self.api_key:
            print("❌ SubDL API key is missing!")
            return None
        
        self._rate_limit()
        
        # If url starts with /, add domain
        if subtitle_url.startswith("/"):
            download_url = f"https://dl.subdl.com{subtitle_url}"
        else:
            download_url = f"https://dl.subdl.com/{subtitle_url}"
        
        # Add api_key for authenticated downloads
        download_url_with_key = f"{download_url}?api_key={self.api_key}"
        
        try:
            print(f"⬇️ Downloading: {download_url_with_key[:80]}...")
            response = self.session.get(download_url_with_key)
            
            if response.status_code == 402:
                print("  💰 SubDL Pro required for downloads")
                return None
            
            if response.status_code == 404:
                print("  ❌ 404 Not Found")
                return None
            
            response.raise_for_status()
            content = response.content
            if len(content) > 100:
                print(f"✅ Downloaded {len(content)} bytes")
                return content
            else:
                print(f"⚠️ Suspiciously small file: {len(content)} bytes")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error downloading: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"  Status: {e.response.status_code}")
            return None
    
    def download_subtitle(self, n_id: str, format_type: str = "file") -> Optional[bytes]:
        """Download a subtitle by its nId or sd_id (legacy method)."""
        
        if not self.api_key:
            print("❌ SubDL API key is missing!")
            return None
        
        self._rate_limit()
        
        n_id = str(n_id)
        
        # Try different download endpoints with different ID formats
        endpoints = [
            # Try with sd_id format (if it's sd_id)
            f"https://dl.subdl.com/subtitle/{n_id}",
            f"https://dl.subdl.com/subtitle/{n_id}.zip",
            # Try with api endpoints
            f"https://api.subdl.com/api/v1/download/{n_id}",
            f"https://api.subdl.com/api/v2/subtitles/{n_id}/download",
            # Try with sd_id prefix
            f"https://dl.subdl.com/subtitle/sd{n_id}",
            f"https://dl.subdl.com/subtitle/sd{n_id}.zip",
        ]
        
        for endpoint in endpoints:
            try:
                # Add api_key to URL for authenticated downloads
                url_with_key = f"{endpoint}?api_key={self.api_key}"
                print(f"⬇️ Downloading subtitle: {n_id} (using {url_with_key[:50]}...)")
                response = self.session.get(url_with_key)
                
                if response.status_code == 402:
                    print("  💰 SubDL Pro required for downloads")
                    continue
                
                if response.status_code == 404:
                    print("  ❌ 404 Not Found")
                    continue
                
                response.raise_for_status()
                content = response.content
                if len(content) > 100:
                    print(f"✅ Downloaded {len(content)} bytes")
                    return content
                else:
                    print(f"⚠️ Suspiciously small file: {len(content)} bytes")
                    continue
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Error downloading subtitle: {e}")
                if hasattr(e, 'response') and e.response:
                    print(f"  Status: {e.response.status_code}")
                continue
        
        print("❌ All download attempts failed")
        return None