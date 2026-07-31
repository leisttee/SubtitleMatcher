# config.py - LISÄÄ SUBDL_AVAIN
import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # User .env path
    USER_ENV_PATH = Path.home() / ".subtitlematcher" / ".env"
    ENV_PATH = BASE_DIR / ".env"
    
    # API Keys
    OPENSUBTITLES_API_KEY = ""
    OPENSUBTITLES_USERNAME = ""
    OPENSUBTITLES_PASSWORD = ""
    OPENSUBTITLES_API_URL = "https://api.opensubtitles.com/api/v1"
    
    TMDB_API_KEY = ""
    TMDB_API_URL = "https://api.themoviedb.org/3"
    
    SUBDL_API_KEY = ""  # <-- UUSI
    SUBDL_API_URL = "https://api.subdl.com/api/v1"
    
    # Supported languages
    SUPPORTED_LANGUAGES = ["en", "fi", "sv", "no", "da", "et", "lv", "lt", "de", "fr", "es", "it", "pl", "cs", "nl", "pt", "ru"]
    
    # Download settings
    DOWNLOAD_DIR = Path.home() / ".subtitlematcher" / "downloads"
    
    @classmethod
    def load(cls):
        """Load .env file and update API keys."""
        env_loaded = False
        
        if cls.USER_ENV_PATH.exists():
            load_dotenv(cls.USER_ENV_PATH)
            print(f"✅ Loaded .env from user: {cls.USER_ENV_PATH}")
            env_loaded = True
        elif cls.ENV_PATH.exists():
            load_dotenv(cls.ENV_PATH)
            print(f"✅ Loaded .env from project: {cls.ENV_PATH}")
            env_loaded = True
        
        if not env_loaded:
            print(f"⚠️ .env file not found")
        
        # Update API keys
        cls.OPENSUBTITLES_API_KEY = os.getenv("OPENSUBTITLES_API_KEY", "")
        cls.OPENSUBTITLES_USERNAME = os.getenv("OPENSUBTITLES_USERNAME", "")
        cls.OPENSUBTITLES_PASSWORD = os.getenv("OPENSUBTITLES_PASSWORD", "")
        cls.TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
        cls.SUBDL_API_KEY = os.getenv("SUBDL_API_KEY", "")  # <-- UUSI
    
    @classmethod
    def validate(cls):
        """Check that required API keys are set."""
        missing = []
        if not cls.OPENSUBTITLES_API_KEY and not cls.SUBDL_API_KEY:
            missing.append("OPENSUBTITLES_API_KEY or SUBDL_API_KEY")
        if not cls.TMDB_API_KEY:
            missing.append("TMDB_API_KEY")
        return missing
    
    @classmethod
    def print_status(cls):
        """Print API key status."""
        print("\n🔑 API Keys Status:")
        print(f"  OPENSUBTITLES_API_KEY: {'✅ Set' if cls.OPENSUBTITLES_API_KEY else '❌ Missing'}")
        print(f"  SUBDL_API_KEY: {'✅ Set' if cls.SUBDL_API_KEY else '❌ Missing'}")
        print(f"  TMDB_API_KEY: {'✅ Set' if cls.TMDB_API_KEY else '❌ Missing'}")

Config.load()