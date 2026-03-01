"""
Qobuz Service
Retrieves lossless and Hi-Res audio via the Qobuz squid.wtf proxy.
No authentication required.

Quality codes:
  5 = Hi-Res FLAC 24-bit / 192kHz
  6 = Hi-Res FLAC 24-bit / 96kHz
  7 = FLAC 16-bit lossless (CD quality)
  27 = MP3 320kbps
"""
import httpx
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

QOBUZ_API_BASE = "https://qobuz.squid.wtf/api"


class QobuzService:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Freedify/1.2.0"}
        )

    async def search_tracks(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search tracks on Qobuz via squid.wtf proxy."""
        try:
            resp = await self.client.get(
                f"{QOBUZ_API_BASE}/get-music",
                params={"q": query, "offset": 0, "limit": limit}
            )
            if resp.status_code != 200:
                logger.warning(f"Qobuz search returned {resp.status_code}")
                return []

            text = resp.text
            if not text:
                logger.warning("Qobuz search returned empty body")
                return []
                
            try:
                data = resp.json()
            except Exception as je:
                logger.error(f"Qobuz search JSON parse error: {je}. Response starts with: {text[:100]}")
                return []

            if not data.get("success") or not data.get("data"):
                logger.warning("Qobuz search returned unsuccessful response")
                return []

            tracks_data = data["data"].get("tracks", {})
            items = tracks_data.get("items", [])
            return [self._format_track(t) for t in items if isinstance(t, dict)]

        except Exception as e:
            logger.error(f"Qobuz search error: {e}")
            return []

    async def search_albums(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search albums on Qobuz via squid.wtf proxy."""
        try:
            resp = await self.client.get(
                f"{QOBUZ_API_BASE}/get-music",
                params={"q": query, "offset": 0, "limit": limit}
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            if not data.get("success") or not data.get("data"):
                return []

            albums_data = data["data"].get("albums", {})
            items = albums_data.get("items", [])
            return [self._format_album(t) for t in items if isinstance(t, dict)]
        except Exception as e:
            logger.error(f"Qobuz album search error: {e}")
            return []

    def _format_album(self, item: dict) -> dict:
        """Format Qobuz album to Freedify schema."""
        artist_obj = item.get("artist") or {}
        artist_name = artist_obj.get("name") if isinstance(artist_obj, dict) else str(artist_obj)
        
        image = item.get("image", {})
        cover = image.get("large") if isinstance(image, dict) else None

        return {
            "id": f"qobuz_{item.get('id')}",
            "type": "album",
            "name": item.get("title", ""),
            "artists": artist_name,
            "album_art": cover,
            "release_date": item.get("release_date", ""),
            "total_tracks": item.get("tracks_count", 0),
            "source": "qobuz",
            "is_hi_res": item.get("hires", False) or item.get("hires_streamable", False),
            "audio_quality": {
                "isHiRes": item.get("hires", False) or item.get("hires_streamable", False)
            }
        }

    def _format_track(self, item: dict) -> dict:
        """Format Qobuz track to Freedify schema."""
        # Artist: Qobuz uses 'performer' for main artist
        performer = item.get("performer") or item.get("artist") or {}
        if isinstance(performer, dict):
            artist_name = performer.get("name", "Unknown Artist")
        else:
            artist_name = str(performer) if performer else "Unknown Artist"

        # Album info
        album = item.get("album", {})
        album_title = album.get("title", "") if isinstance(album, dict) else ""

        # Cover art
        album_art = None
        if isinstance(album, dict):
            image = album.get("image", {})
            if isinstance(image, dict):
                album_art = image.get("large") or image.get("small") or image.get("thumbnail")

        return {
            "id": f"qobuz_{item.get('id')}",
            "type": "track",
            "name": item.get("title", "Unknown"),
            "artists": artist_name,
            "album": album_title,
            "album_art": album_art,
            "duration_ms": (item.get("duration", 0)) * 1000,
            "isrc": item.get("isrc"),
            "release_date": album.get("released_at", "") if isinstance(album, dict) else "",
            "source": "qobuz",
            "is_hi_res": item.get("hires", False) or item.get("hires_streamable", False),
        }

    async def get_stream_url(self, track_id: str, quality: str = "5") -> Optional[str]:
        """
        Get stream URL for a track.
        
        Quality codes:
            5 = Hi-Res 192kHz/24-bit
            6 = Hi-Res 96kHz/24-bit
            7 = FLAC 16-bit lossless
            27 = MP3 320kbps
        """
        try:
            clean_id = str(track_id).replace("qobuz_", "")
            resp = await self.client.get(
                f"{QOBUZ_API_BASE}/download-music",
                params={"track_id": clean_id, "quality": quality}
            )
            if resp.status_code != 200:
                logger.warning(f"Qobuz stream fetch failed: {resp.status_code}")
                return None

            data = resp.json()
            if data.get("success") and data.get("data", {}).get("url"):
                url = data["data"]["url"]
                logger.info(f"Qobuz stream URL obtained: {url[:50]}...")
                return url

            logger.warning("Qobuz stream response missing URL")
            return None

        except Exception as e:
            logger.error(f"Qobuz stream error: {e}")
            return None

    async def close(self):
        await self.client.aclose()


# Singleton
qobuz_service = QobuzService()
