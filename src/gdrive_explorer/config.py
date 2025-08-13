"""Configuration management for Google Drive Explorer."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field


class APIConfig(BaseModel):
    """Google Drive API configuration."""
    request_delay: float = 0.1
    max_retries: int = 3
    timeout: int = 30
    page_size: int = 1000


class AuthConfig(BaseModel):
    """Authentication configuration."""
    credentials_file: str = "config/credentials.json"
    token_file: str = "config/token.pickle"


class CacheConfig(BaseModel):
    """Caching configuration."""
    enabled: bool = True
    ttl_hours: int = 24
    max_size_mb: int = 100
    database_path: str = "data/cache.db"


class DisplayConfig(BaseModel):
    """Display configuration."""
    default_format: str = "table"
    max_items: int = 1000
    show_progress: bool = True
    use_colors: bool = True
    human_readable_sizes: bool = True


class ExportConfig(BaseModel):
    """Export configuration."""
    default_format: str = "csv"
    include_metadata: bool = True
    date_format: str = "%Y-%m-%d %H:%M:%S"


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    file: str = "gdrive-explorer.log"
    max_size_mb: int = 10


class Config(BaseModel):
    """Main configuration class."""
    api: APIConfig = Field(default_factory=APIConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class ConfigManager:
    """Manages application configuration from files and environment variables."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager.
        
        Args:
            config_file: Path to YAML configuration file
        """
        self.config_file = config_file or "config/settings.yaml"
        self._config: Optional[Config] = None
    
    def load_config(self) -> Config:
        """Load configuration from file and environment variables.
        
        Returns:
            Loaded configuration object
        """
        if self._config is not None:
            return self._config
        
        # Start with default configuration
        config_data = {}
        
        # Load from YAML file if it exists
        if Path(self.config_file).exists():
            try:
                with open(self.config_file, 'r') as f:
                    config_data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Warning: Failed to load config file {self.config_file}: {e}")
        
        # Override with environment variables
        config_data = self._apply_env_overrides(config_data)
        
        # Create and validate configuration
        self._config = Config(**config_data)
        return self._config
    
    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration.
        
        Args:
            config_data: Base configuration data
            
        Returns:
            Configuration data with environment overrides applied
        """
        # Map environment variables to configuration paths
        env_mapping = {
            'GDRIVE_EXPLORER_CREDENTIALS_FILE': ['auth', 'credentials_file'],
            'GDRIVE_EXPLORER_TOKEN_FILE': ['auth', 'token_file'],
            'GDRIVE_EXPLORER_LOG_LEVEL': ['logging', 'level'],
            'GDRIVE_EXPLORER_CACHE_ENABLED': ['cache', 'enabled'],
            'GDRIVE_EXPLORER_SHOW_PROGRESS': ['display', 'show_progress'],
            'GDRIVE_EXPLORER_USE_COLORS': ['display', 'use_colors'],
        }
        
        for env_var, config_path in env_mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Navigate to the correct nested dictionary
                current = config_data
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                
                # Set the value, converting boolean strings
                final_key = config_path[-1]
                if value.lower() in ('true', 'false'):
                    current[final_key] = value.lower() == 'true'
                else:
                    current[final_key] = value
        
        return config_data
    
    def get_config(self) -> Config:
        """Get the current configuration, loading if necessary.
        
        Returns:
            Current configuration object
        """
        if self._config is None:
            return self.load_config()
        return self._config
    
    def reload_config(self) -> Config:
        """Reload configuration from file.
        
        Returns:
            Reloaded configuration object
        """
        self._config = None
        return self.load_config()
    
    def get_credentials_path(self) -> Path:
        """Get the full path to the credentials file.
        
        Returns:
            Path to credentials file
        """
        config = self.get_config()
        return Path(config.auth.credentials_file).resolve()
    
    def get_token_path(self) -> Path:
        """Get the full path to the token file.
        
        Returns:
            Path to token file
        """
        config = self.get_config()
        return Path(config.auth.token_file).resolve()
    
    def get_cache_path(self) -> Path:
        """Get the full path to the cache database.
        
        Returns:
            Path to cache database
        """
        config = self.get_config()
        return Path(config.cache.database_path).resolve()


# Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance.
    
    Returns:
        Global configuration manager
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> Config:
    """Get the current configuration.
    
    Returns:
        Current configuration object
    """
    return get_config_manager().get_config()