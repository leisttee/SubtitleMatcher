import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List


class Config:
    """Configuration manager for API keys and settings."""
    
    # Class variables for API keys
    SUBDL_API_KEY: Optional[str] = None
    # OPENSUBTITLES_API_KEY poistettu - ei enää käytössä
    TMDB_API_KEY: Optional[str] = None
    
    # Track which .env file was loaded
    _loaded_env_path: Optional[Path] = None
    
    @classmethod
    def load(cls, env_path: Optional[Path] = None) -> 'Config':
        """
        Load configuration from .env file.
        
        Args:
            env_path: Optional path to .env file. If None, searches in default locations.
            
        Returns:
            Config class for chaining
        """
        loaded_path = None
        
        # Try to find .env file
        if env_path and env_path.exists():
            load_dotenv(env_path)
            loaded_path = env_path
        else:
            # Try default locations in order of preference
            possible_paths = [
                Path.home() / ".subtitlematcher" / ".env",  # User config (highest priority)
                Path.cwd() / ".env",                         # Project root
                Path(__file__).resolve().parent.parent / ".env",  # Project root (src/..)
                Path(__file__).resolve().parent / ".env",    # Current directory
            ]
            
            for path in possible_paths:
                if path.exists():
                    load_dotenv(path)
                    loaded_path = path
                    break
        
        # Load API keys from environment
        cls.SUBDL_API_KEY = os.getenv("SUBDL_API_KEY", "")
        # OpenSubtitles poistettu
        cls.TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
        
        cls._loaded_env_path = loaded_path
        
        return cls
    
    @classmethod
    def print_status(cls) -> None:
        """Print API key status."""
        print("\n🔑 API Keys Status:")
        print(f"  SUBDL_API_KEY: {'✅ Set' if cls.SUBDL_API_KEY else '❌ Not set'}")
        print(f"  TMDB_API_KEY: {'✅ Set' if cls.TMDB_API_KEY else '❌ Not set'}")
        print(f"  ℹ️ OpenSubtitles on poistettu käytöstä (vain SubDL käytössä)")
        
        # Show which .env file was loaded
        if cls._loaded_env_path:
            print(f"  📄 Loaded from: {cls._loaded_env_path}")
        else:
            print(f"  📄 No .env file found")
        
        # Show default .env location
        env_file = Path.home() / ".subtitlematcher" / ".env"
        if env_file.exists():
            print(f"  💾 Default save location: {env_file}")
            print(f"  💾 File exists: True")
        else:
            print(f"  💾 Default save location: {env_file}")
            print(f"  💾 File exists: False")
    
    @classmethod
    def save(cls, env_path: Optional[Path] = None) -> None:
        """
        Save current configuration to .env file.
        
        Args:
            env_path: Optional path to save .env file. Defaults to user config.
        """
        if env_path is None:
            env_path = Path.home() / ".subtitlematcher" / ".env"
        
        # Ensure directory exists
        env_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write configuration (vain SubDL ja TMDB)
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"SUBDL_API_KEY={cls.SUBDL_API_KEY or ''}\n")
            f.write(f"TMDB_API_KEY={cls.TMDB_API_KEY or ''}\n")
            # OpenSubtitles ei enää tallenneta
        
        cls._loaded_env_path = env_path
        print(f"✅ Configuration saved to: {env_path}")
    
    @classmethod
    def is_valid(cls) -> bool:
        """Check if subtitle provider is configured (vain SubDL)."""
        return bool(cls.SUBDL_API_KEY)
    
    @classmethod
    def has_tmdb(cls) -> bool:
        """Check if TMDB API key is set."""
        return bool(cls.TMDB_API_KEY)
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available subtitle providers (vain SubDL)."""
        providers = []
        if cls.SUBDL_API_KEY:
            providers.append("subdl")
        # OpenSubtitles poistettu
        return providers
    
    @classmethod
    def get_primary_provider(cls) -> Optional[str]:
        """Get the primary subtitle provider (SubDL)."""
        if cls.SUBDL_API_KEY:
            return "subdl"
        return None
    
    @classmethod
    def to_dict(cls) -> dict:
        """Export configuration as dictionary."""
        return {
            "subdl_api_key": cls.SUBDL_API_KEY,
            "tmdb_api_key": cls.TMDB_API_KEY,
            "loaded_from": str(cls._loaded_env_path) if cls._loaded_env_path else None,
            "providers": cls.get_available_providers(),
            "is_valid": cls.is_valid()
        }
    
    @classmethod
    def get_env_path(cls) -> Optional[Path]:
        """Get the path of the loaded .env file."""
        return cls._loaded_env_path
    
    @classmethod
    def reload(cls) -> 'Config':
        """Reload configuration from the same .env file."""
        if cls._loaded_env_path:
            return cls.load(cls._loaded_env_path)
        return cls.load()


# Auto-load configuration when module is imported
Config.load()