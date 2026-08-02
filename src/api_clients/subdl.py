# api_clients/subdl.py
import requests
import time
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
import zipfile
import io


class SubDLClient:
    def __init__(self, api_key: str, base_url: str = "https://api.subdl.com/api/v1"):
        """
        Initialize SubDL API client.
        
        Args:
            api_key: SubDL API key (required for all operations)
            base_url: Base URL for API (defaults to v1)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "SubtitleMatcher v1.0",
            "Accept": "application/json"
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5
        
        # Peruutustila
        self._cancelled = False
        self._cancel_lock = False

    def cancel(self):
        """Peruuta meneillään olevat operaatiot"""
        self._cancelled = True
        print("⏹️ SubDL: Peruutetaan...")

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
    
    def search_subtitles(self, 
                        imdb_id: Optional[str] = None,
                        tmdb_id: Optional[int] = None,
                        season: Optional[int] = None,
                        episode: Optional[int] = None,
                        language: str = "en") -> List[Dict[str, Any]]:
        """
        Search for subtitles using IMDB ID or TMDB ID.
        
        Args:
            imdb_id: IMDB ID (e.g., "tt1234567")
            tmdb_id: TMDB ID (e.g., 12345)
            season: Season number for TV shows
            episode: Episode number for TV shows
            language: Language code (default: "en")
            
        Returns:
            List of subtitle objects with download URLs
        """
        if self.is_cancelled():
            return []
            
        if not self.api_key:
            print("❌ SubDL API key is missing!")
            return []
        
        if not imdb_id and not tmdb_id:
            print("❌ Either IMDB ID or TMDB ID must be provided")
            return []
        
        self._rate_limit()
        
        # Prepare parameters according to SubDL v1 documentation
        params = {
            "api_key": self.api_key,
            "languages": language.upper(),  # API expects uppercase
            "unpack": 1,  # Get individual file URLs instead of zip
        }
        
        # Add identifier
        if imdb_id:
            if not imdb_id.startswith("tt"):
                imdb_id = f"tt{imdb_id}"
            params["imdb_id"] = imdb_id
        elif tmdb_id:
            params["tmdb_id"] = tmdb_id
        
        # Add TV show parameters if provided
        if season is not None:
            params["season_number"] = season
        if episode is not None:
            params["episode_number"] = episode
        
        # Use v1 API endpoint
        url = f"{self.base_url}/subtitles"
        
        try:
            print(f"🔍 Searching SubDL: {params}")
            response = self.session.get(url, params=params, timeout=15)
            
            if self.is_cancelled():
                return []
            
            if response.status_code == 200:
                data = response.json()
                
                # Check status
                if data.get("status") == False:
                    print(f"❌ SubDL API error: {data.get('error', 'Unknown error')}")
                    return []
                
                # v1 returns subtitles in 'subtitles' key
                subtitles = data.get("subtitles", [])
                
                if subtitles:
                    print(f"✅ Found {len(subtitles)} subtitles from SubDL")
                    
                    # Debug: print first result
                    if subtitles and len(subtitles) > 0:
                        first = subtitles[0]
                        print(f"  First subtitle: {first.get('language', '')} - {first.get('title', '')}")
                        
                        # Check for unpack_files
                        unpack_files = first.get("unpack_files", [])
                        if unpack_files:
                            print(f"  Found {len(unpack_files)} unpacked files")
                            first_file = unpack_files[0]
                            print(f"  First file URL: {first_file.get('url', 'N/A')}")
                        elif first.get("url"):
                            print(f"  Download URL: {first.get('url')[:50]}...")
                        else:
                            print("  ⚠️ No URL found - check if unpack=1 is working")
                    
                    return subtitles
                else:
                    print("❌ No subtitles found")
                    return []
            
            elif response.status_code == 401:
                print("❌ API key invalid or unauthorized")
                print(f"  Response: {response.text[:200]}")
                return []
            
            elif response.status_code == 404:
                print("❌ No subtitles found for the given IDs")
                return []
            
            elif response.status_code == 429:
                print("❌ Rate limit exceeded. Please wait a moment.")
                return []
            
            else:
                print(f"❌ API error: {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error searching SubDL: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"  Status: {e.response.status_code}")
                print(f"  Response: {e.response.text[:200]}")
            return []
        
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing API response: {e}")
            if 'response' in locals() and response:
                print(f"  Response: {response.text[:200]}")
            return []
    
    def download_subtitle(self, subtitle: Dict[str, Any]) -> Optional[bytes]:
        """
        Download a subtitle using the URL from search results.
        
        Args:
            subtitle: Subtitle object from search_subtitles()
            
        Returns:
            Subtitle file content as bytes, or None if download failed
        """
        if self.is_cancelled():
            return None
            
        if not subtitle:
            print("❌ No subtitle data provided")
            return None
        
        # Check for unpack_files first (when unpack=1 is used)
        unpack_files = subtitle.get("unpack_files", [])
        if unpack_files:
            # Use the first file from unpack_files
            first_file = unpack_files[0]
            file_url = first_file.get("url")
            if file_url:
                # Construct full URL
                if file_url.startswith("/"):
                    full_url = f"https://dl.subdl.com{file_url}"
                else:
                    full_url = f"https://dl.subdl.com/{file_url}"
                return self._download_from_url(full_url, f"file: {first_file.get('name', 'unknown')}")
            else:
                print("⚠️ No URL in unpack_files")
        
        # Fallback: use url field
        download_url = subtitle.get("url")
        if download_url:
            return self._download_from_url(download_url, "subtitle URL")
        
        # Legacy: try nId/sd_id
        n_id = subtitle.get("nId") or subtitle.get("sd_id")
        if n_id:
            print(f"⚠️ No URL found, trying download by nId: {n_id}")
            return self._download_by_id(n_id)
        
        print("❌ No download URL or ID found")
        print(f"  Available keys: {list(subtitle.keys())}")
        return None
    
    def _download_from_url(self, download_url: str, label: str = "") -> Optional[bytes]:
        """
        Download subtitle from a URL with authentication.
        """
        if self.is_cancelled():
            return None
            
        # Ensure URL has proper format
        if not download_url.startswith("http"):
            if download_url.startswith("/"):
                download_url = f"https://dl.subdl.com{download_url}"
            else:
                download_url = f"https://dl.subdl.com/{download_url}"
        
        # Add api_key for authenticated downloads
        if "?" in download_url:
            url_with_key = f"{download_url}&api_key={self.api_key}"
        else:
            url_with_key = f"{download_url}?api_key={self.api_key}"
        
        try:
            self._rate_limit()
            
            if self.is_cancelled():
                return None
                
            print(f"⬇️ Downloading {label}...")
            
            response = self.session.get(url_with_key, timeout=30, stream=True)
            
            if self.is_cancelled():
                response.close()
                return None
            
            if response.status_code == 200:
                content = response.content
                
                # Validate content
                if len(content) < 50:
                    print(f"⚠️ Suspiciously small file: {len(content)} bytes")
                    return None
                
                # Check if it's a zip file and extract if needed
                if content.startswith(b'PK'):  # ZIP file magic number
                    try:
                        zip_file = zipfile.ZipFile(io.BytesIO(content))
                        srt_files = [f for f in zip_file.namelist() if f.endswith('.srt')]
                        if srt_files:
                            # Use the first .srt file
                            with zip_file.open(srt_files[0]) as f:
                                content = f.read()
                            print(f"✅ Extracted {len(content)} bytes from zip")
                        else:
                            # Try .ass files
                            ass_files = [f for f in zip_file.namelist() if f.endswith('.ass')]
                            if ass_files:
                                with zip_file.open(ass_files[0]) as f:
                                    content = f.read()
                                print(f"✅ Extracted {len(content)} bytes from zip (ASS)")
                            else:
                                print("⚠️ No .srt or .ass file found in zip, returning raw content")
                    except zipfile.BadZipFile:
                        print("⚠️ File is not a valid zip, returning as is")
                    except Exception as e:
                        print(f"⚠️ Error extracting zip: {e}")
                        # Return raw content if extraction fails
                else:
                    print(f"✅ Downloaded {len(content)} bytes")
                
                return content
            
            elif response.status_code == 402:
                print("  💰 SubDL Pro required for downloads")
                return None
            
            elif response.status_code == 404:
                print("  ❌ Download URL not found (404)")
                return None
            
            elif response.status_code == 403:
                print("  ❌ Access forbidden (403) - check API key or permissions")
                return None
            
            elif response.status_code == 429:
                print("  ❌ Rate limit exceeded. Please wait.")
                return None
            
            else:
                print(f"  ❌ Download failed: {response.status_code}")
                if len(response.content) < 500:
                    print(f"  Response: {response.text[:200]}")
                return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error downloading: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"  Status: {e.response.status_code}")
            return None
    
    def _download_by_id(self, n_id: str) -> Optional[bytes]:
        """
        Legacy method: download subtitle by nId/sd_id.
        Uses the documented download format.
        """
        if self.is_cancelled():
            return None
            
        if not n_id:
            return None
        
        n_id = str(n_id)
        
        # According to SubDL documentation:
        # https://dl.subdl.com/subtitle/{n_id}.zip
        download_url = f"https://dl.subdl.com/subtitle/{n_id}.zip"
        
        try:
            self._rate_limit()
            
            if self.is_cancelled():
                return None
                
            print(f"⬇️ Trying download by ID: {n_id}...")
            
            # Add api_key
            url_with_key = f"{download_url}?api_key={self.api_key}"
            response = self.session.get(url_with_key, timeout=30)
            
            if self.is_cancelled():
                return None
            
            if response.status_code == 200:
                content = response.content
                if len(content) > 100:
                    # Try to extract if zip
                    if content.startswith(b'PK'):
                        try:
                            zip_file = zipfile.ZipFile(io.BytesIO(content))
                            srt_files = [f for f in zip_file.namelist() if f.endswith('.srt')]
                            if srt_files:
                                with zip_file.open(srt_files[0]) as f:
                                    subtitle_content = f.read()
                                print(f"✅ Extracted {len(subtitle_content)} bytes from zip")
                                return subtitle_content
                        except zipfile.BadZipFile:
                            pass
                    print(f"✅ Downloaded {len(content)} bytes")
                    return content
                else:
                    print(f"⚠️ Small file: {len(content)} bytes")
                    return None
            else:
                print(f"  Download by ID failed: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error downloading by ID: {e}")
            return None
    
    def download_and_extract_subtitle(self, subtitle: Dict[str, Any], 
                                     output_path: Optional[str] = None) -> Optional[str]:
        """
        Download subtitle and save to file.
        """
        if self.is_cancelled():
            return None
            
        content = self.download_subtitle(subtitle)
        if not content:
            return None
        
        # Determine output filename
        if output_path:
            output_file = Path(output_path)
        else:
            lang = subtitle.get("language", "en")
            title = subtitle.get("title", "subtitle")
            title = "".join(c for c in title if c.isalnum() or c in " ._-")
            title = title.replace(" ", "_")
            output_file = Path(f"{title}.{lang}.srt")
        
        try:
            output_file.write_bytes(content)
            print(f"✅ Saved subtitle to: {output_file}")
            return str(output_file)
        except Exception as e:
            print(f"❌ Error saving subtitle: {e}")
            return None
    
    def format_subtitle_for_display(self, subtitle: Dict[str, Any]) -> str:
        """Format a subtitle object for human-readable display."""
        lang = subtitle.get("language", "Unknown")
        title = subtitle.get("title", "Unknown title")
        year = subtitle.get("year", "")
        name = subtitle.get("name", "")
        download_count = subtitle.get("download_count", 0)
        rating = subtitle.get("rating", "")
        
        if year:
            title = f"{title} ({year})"
        if name:
            title = f"{title} - {name}"
        rating_str = f" ⭐{rating}" if rating else ""
        
        return f"{title} [{lang}]{rating_str} ({download_count} downloads)"