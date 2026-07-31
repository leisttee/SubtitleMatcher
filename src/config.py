# src/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    # Etsi .env tiedosto (projektin juuresta)
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # Käyttäjän .env polku (asennetulle versiolle)
    USER_ENV_PATH = Path.home() / ".subtitlematcher" / ".env"
    ENV_PATH = BASE_DIR / ".env"
    
    # API-avaimet (oletusarvot)
    OPENSUBTITLES_API_KEY = ""
    OPENSUBTITLES_USERNAME = ""
    OPENSUBTITLES_PASSWORD = ""
    OPENSUBTITLES_API_URL = "https://api.opensubtitles.com/api/v1"
    
    TMDB_API_KEY = ""
    TMDB_API_URL = "https://api.themoviedb.org/3"
    
    # Supported languages
    SUPPORTED_LANGUAGES = ["en", "fi", "sv", "no", "da", "et", "lv", "lt", "de", "fr", "es", "it", "pl", "cs", "nl", "pt", "ru"]
    
    # Download settings
    DOWNLOAD_DIR = Path.home() / ".subtitlematcher" / "downloads"
    
    @classmethod
    def load(cls):
        """Lataa .env tiedosto ja päivitä API-avaimet"""
        env_loaded = False
        
        # Kokeile ensin käyttäjän .env-tiedostoa
        if cls.USER_ENV_PATH.exists():
            load_dotenv(cls.USER_ENV_PATH)
            print(f"✅ Loaded .env from user: {cls.USER_ENV_PATH}")
            env_loaded = True
        
        # Jos ei löydy, kokeile projektin .env-tiedostoa
        if not env_loaded and cls.ENV_PATH.exists():
            load_dotenv(cls.ENV_PATH)
            print(f"✅ Loaded .env from project: {cls.ENV_PATH}")
            env_loaded = True
        
        if not env_loaded:
            print(f"⚠️ .env file not found")
        
        # Päivitä API-avaimet
        cls.OPENSUBTITLES_API_KEY = os.getenv("OPENSUBTITLES_API_KEY", "")
        cls.OPENSUBTITLES_USERNAME = os.getenv("OPENSUBTITLES_USERNAME", "")
        cls.OPENSUBTITLES_PASSWORD = os.getenv("OPENSUBTITLES_PASSWORD", "")
        cls.TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
    
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
        print(f"  .env path (user): {cls.USER_ENV_PATH}")
        print(f"  .env exists (user): {cls.USER_ENV_PATH.exists()}")

# Lataa config importin yhteydessä
Config.load()