# src/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    # Etsi .env tiedosto (projektin juuresta)
    BASE_DIR = Path(__file__).resolve().parent.parent
    ENV_PATH = BASE_DIR / ".env"
    
    # Lataa .env tiedosto
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
        print(f"✅ Loaded .env from: {ENV_PATH}")
    else:
        print(f"⚠️ .env file not found at: {ENV_PATH}")
    
    # OpenSubtitles API
    OPENSUBTITLES_API_KEY = os.getenv("OPENSUBTITLES_API_KEY", "")
    OPENSUBTITLES_USERNAME = os.getenv("OPENSUBTITLES_USERNAME", "")
    OPENSUBTITLES_PASSWORD = os.getenv("OPENSUBTITLES_PASSWORD", "")
    OPENSUBTITLES_API_URL = "https://api.opensubtitles.com/api/v1"
    
    # TMDB API
    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
    TMDB_API_URL = "https://api.themoviedb.org/3"
    
    # Supported languages
    SUPPORTED_LANGUAGES = ["en", "fi", "sv", "no", "da"]
    
    # Download settings
    DOWNLOAD_DIR = Path.home() / ".subtitlematcher" / "downloads"
    
    @classmethod
    def validate(cls):
        """Tarkistaa että tarvittavat API-avaimet on asetettu"""
        missing = []
        if not cls.OPENSUBTITLES_API_KEY:
            missing.append("OPENSUBTITLES_API_KEY")
        if not cls.TMDB_API_KEY:
            missing.append("TMDB_API_KEY")
        return missing
    
    @classmethod
    def print_status(cls):
        """Tulosta API-avainten tila"""
        print("\n🔑 API Keys Status:")
        print(f"  OPENSUBTITLES_API_KEY: {'✅ Set' if cls.OPENSUBTITLES_API_KEY else '❌ Missing'}")
        print(f"  TMDB_API_KEY: {'✅ Set' if cls.TMDB_API_KEY else '❌ Missing'}")
        print(f"  .env path: {cls.ENV_PATH}")
        print(f"  .env exists: {cls.ENV_PATH.exists()}")