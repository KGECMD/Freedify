"""
Last.fm Scrobbling Service for Freedify
Token-based authentication and scrobbling API
"""

import hashlib
import time
import logging
from typing import Optional, Dict
import httpx

logger = logging.getLogger(__name__)

# Hardcoded Freedify Last.fm app credentials
LASTFM_API_KEY = "ba96abee2841548b666379432119b31e"
LASTFM_API_SECRET = "54322add2729332f1e43dc172a70f41b"
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_AUTH_URL = "https://www.last.fm/api/auth/"


class LastFMService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)
    
    def _generate_signature(self, params: Dict[str, str]) -> str:
        """Generate MD5 API signature per Last.fm spec.
        Sort params alphabetically, concatenate key+value pairs, append secret, MD5 hash.
        """
        # Filter out 'format' and 'callback' params — they're excluded from sig
        sig_params = {k: v for k, v in params.items() if k not in ('format', 'callback')}
        sorted_keys = sorted(sig_params.keys())
        sig_string = ''.join(f"{k}{sig_params[k]}" for k in sorted_keys)
        sig_string += LASTFM_API_SECRET
        return hashlib.md5(sig_string.encode('utf-8')).hexdigest()
    
    def get_auth_url(self, callback_url: str) -> str:
        """Generate Last.fm authorization URL for the user to click."""
        return f"{LASTFM_AUTH_URL}?api_key={LASTFM_API_KEY}&cb={callback_url}"
    
    async def get_session(self, token: str) -> Optional[Dict]:
        """Exchange authorization token for a session key.
        Returns {session_key, username} on success, None on failure.
        """
        params = {
            "method": "auth.getSession",
            "api_key": LASTFM_API_KEY,
            "token": token,
        }
        params["api_sig"] = self._generate_signature(params)
        params["format"] = "json"
        
        try:
            response = await self.client.get(LASTFM_API_URL, params=params)
            data = response.json()
            
            if "session" in data:
                session = data["session"]
                logger.info(f"Last.fm auth successful for user: {session['name']}")
                return {
                    "session_key": session["key"],
                    "username": session["name"]
                }
            else:
                error = data.get("error", "Unknown error")
                message = data.get("message", "")
                logger.error(f"Last.fm auth failed: {error} - {message}")
                return None
        except Exception as e:
            logger.error(f"Last.fm session exchange error: {e}")
            return None
    
    async def scrobble(self, session_key: str, artist: str, track: str, 
                       album: str = "", timestamp: Optional[int] = None) -> bool:
        """Scrobble a track to Last.fm.
        Timestamp should be Unix epoch when the track started playing.
        """
        if not timestamp:
            timestamp = int(time.time())
        
        params = {
            "method": "track.scrobble",
            "api_key": LASTFM_API_KEY,
            "sk": session_key,
            "artist": artist,
            "track": track,
            "timestamp": str(timestamp),
        }
        if album:
            params["album"] = album
        
        params["api_sig"] = self._generate_signature(params)
        params["format"] = "json"
        
        try:
            response = await self.client.post(LASTFM_API_URL, data=params)
            data = response.json()
            
            if "scrobbles" in data:
                accepted = data["scrobbles"]["@attr"]["accepted"]
                logger.info(f"Last.fm scrobble {'accepted' if int(accepted) > 0 else 'ignored'}: {artist} - {track}")
                return int(accepted) > 0
            else:
                error = data.get("error", "Unknown")
                logger.error(f"Last.fm scrobble failed: {error}")
                return False
        except Exception as e:
            logger.error(f"Last.fm scrobble error: {e}")
            return False
    
    async def update_now_playing(self, session_key: str, artist: str, track: str,
                                  album: str = "") -> bool:
        """Update the 'Now Playing' status on Last.fm."""
        params = {
            "method": "track.updateNowPlaying",
            "api_key": LASTFM_API_KEY,
            "sk": session_key,
            "artist": artist,
            "track": track,
        }
        if album:
            params["album"] = album
        
        params["api_sig"] = self._generate_signature(params)
        params["format"] = "json"
        
        try:
            response = await self.client.post(LASTFM_API_URL, data=params)
            data = response.json()
            
            if "nowplaying" in data:
                logger.info(f"Last.fm now playing: {artist} - {track}")
                return True
            else:
                error = data.get("error", "Unknown")
                logger.error(f"Last.fm now playing failed: {error}")
                return False
        except Exception as e:
            logger.error(f"Last.fm now playing error: {e}")
            return False

    async def get_similar_artists(self, artist: str, limit: int = 10) -> Optional[list[Dict]]:
        """Get similar artists from Last.fm."""
        params = {
            "method": "artist.getsimilar",
            "api_key": LASTFM_API_KEY,
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
            "format": "json"
        }
        try:
            response = await self.client.get(LASTFM_API_URL, params=params)
            data = response.json()
            if "similarartists" in data and "artist" in data["similarartists"]:
                artists = data["similarartists"]["artist"]
                if isinstance(artists, dict):
                    artists = [artists]
                return [{"name": a["name"], "match": float(a.get("match", 0))} for a in artists]
            return []
        except Exception as e:
            logger.error(f"Last.fm similar artists error: {e}")
            return None


# Singleton instance
lastfm_service = LastFMService()
