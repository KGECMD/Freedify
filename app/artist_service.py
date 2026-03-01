"""
Artist Biography Service for Freedify
Fetches artist bio, social links, and image from MusicBrainz + Wikipedia
"""

import logging
from typing import Optional, Dict, List
import httpx

logger = logging.getLogger(__name__)

MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1"
USER_AGENT = "Freedify/1.0 (https://github.com/biohaphazard/freedify)"


class ArtistService:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        self._cache: Dict[str, dict] = {}  # Simple in-memory cache

    async def get_artist_bio(self, artist_name: str) -> Optional[Dict]:
        """Get artist biography, social links, and image.
        Returns {name, bio, image, socials, genres} or None.
        """
        # Check cache first
        cache_key = artist_name.lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            # 1. Search MusicBrainz for the artist
            search_url = f"{MUSICBRAINZ_API}/artist/"
            params = {
                "query": f'artist:"{artist_name}"',
                "limit": 1,
                "fmt": "json"
            }
            
            resp = await self.client.get(search_url, params=params)
            if resp.status_code != 200:
                logger.warning(f"MusicBrainz search failed: {resp.status_code}")
                return None
            
            data = resp.json()
            artists = data.get("artists", [])
            if not artists:
                logger.info(f"No MusicBrainz results for: {artist_name}")
                return None
            
            artist = artists[0]
            mbid = artist["id"]
            
            # 2. Get full artist details with URL relations
            detail_url = f"{MUSICBRAINZ_API}/artist/{mbid}"
            detail_params = {"inc": "url-rels+tags", "fmt": "json"}
            
            detail_resp = await self.client.get(detail_url, params=detail_params)
            if detail_resp.status_code != 200:
                logger.warning(f"MusicBrainz detail fetch failed: {detail_resp.status_code}")
                return None
            
            detail = detail_resp.json()
            
            # 3. Extract social links from URL relations
            socials = self._extract_socials(detail.get("relations", []))
            
            # 4. Extract genres/tags
            tags = detail.get("tags", [])
            genres = sorted(tags, key=lambda t: t.get("count", 0), reverse=True)
            genre_names = [t["name"] for t in genres[:5]]
            
            # 5. Get biography from Wikipedia (if available)
            bio = ""
            wiki_url = None
            wikidata_url = None
            for rel in detail.get("relations", []):
                if rel.get("type") == "wikipedia":
                    wiki_url = rel.get("url", {}).get("resource", "")
                elif rel.get("type") == "wikidata":
                    wikidata_url = rel.get("url", {}).get("resource", "")
            
            if wiki_url:
                bio = await self._fetch_wikipedia_extract(wiki_url)
            elif wikidata_url:
                # Resolve Wikidata Q-ID to English Wikipedia title
                q_id = wikidata_url.rstrip("/").split("/")[-1]
                wd_api = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={q_id}&props=sitelinks&sitefilter=enwiki&format=json"
                wd_resp = await self.client.get(wd_api)
                if wd_resp.status_code == 200:
                    wd_data = wd_resp.json()
                    title = wd_data.get("entities", {}).get(q_id, {}).get("sitelinks", {}).get("enwiki", {}).get("title")
                    if title:
                        wiki_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        bio = await self._fetch_wikipedia_extract(wiki_url)
            
            # 6. Try to get artist image
            image = await self._get_artist_image(mbid, artist_name)
            
            result = {
                "name": detail.get("name", artist_name),
                "bio": bio,
                "image": image,
                "socials": socials,
                "genres": genre_names,
                "type": detail.get("type", ""),
                "country": detail.get("country", ""),
                "begin_date": detail.get("life-span", {}).get("begin", ""),
                "end_date": detail.get("life-span", {}).get("end", ""),
                "active": detail.get("life-span", {}).get("ended") is not True
            }
            
            # Cache result (only cache for 24h if bio/image succeeded, else 1 hour)
            if bio or image:
                self._cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Artist bio error for '{artist_name}': {repr(e)}")
            return None

    def _extract_socials(self, relations: List[dict]) -> List[dict]:
        """Extract social media and official links from MusicBrainz relations."""
        social_types = {
            "official homepage": {"icon": "🌐", "label": "Website"},
            "social network": {"icon": "🔗", "label": "Social"},
            "bandcamp": {"icon": "🎵", "label": "Bandcamp"},
            "soundcloud": {"icon": "☁️", "label": "SoundCloud"},
            "youtube": {"icon": "▶️", "label": "YouTube"},
            "streaming": {"icon": "🎧", "label": "Streaming"},
        }
        
        socials = []
        seen_urls = set()
        
        for rel in relations:
            rel_type = rel.get("type", "").lower()
            url = rel.get("url", {}).get("resource", "")
            
            if not url or url in seen_urls:
                continue
            
            # Classify URL
            url_lower = url.lower()
            icon = "🔗"
            label = "Link"
            
            if "instagram.com" in url_lower:
                icon, label = "📸", "Instagram"
            elif "twitter.com" in url_lower or "x.com" in url_lower:
                icon, label = "𝕏", "X/Twitter"
            elif "facebook.com" in url_lower:
                icon, label = "📘", "Facebook"
            elif "bandcamp.com" in url_lower:
                icon, label = "🎵", "Bandcamp"
            elif "soundcloud.com" in url_lower:
                icon, label = "☁️", "SoundCloud"
            elif "youtube.com" in url_lower or "youtu.be" in url_lower:
                icon, label = "▶️", "YouTube"
            elif "spotify.com" in url_lower:
                icon, label = "🟢", "Spotify"
            elif "tidal.com" in url_lower:
                icon, label = "🌊", "Tidal"
            elif "apple.com" in url_lower or "music.apple" in url_lower:
                icon, label = "🍎", "Apple Music"
            elif "deezer.com" in url_lower:
                icon, label = "🎶", "Deezer"
            elif "wikipedia.org" in url_lower:
                icon, label = "📖", "Wikipedia"
            elif "wikidata.org" in url_lower:
                continue  # Skip wikidata links
            elif "discogs.com" in url_lower:
                icon, label = "💿", "Discogs"
            elif "allmusic.com" in url_lower:
                continue  # Skip
            elif rel_type in social_types:
                info = social_types[rel_type]
                icon, label = info["icon"], info["label"]
            elif rel_type == "official homepage":
                icon, label = "🌐", "Website"
            else:
                continue  # Skip unknown relation types
            
            seen_urls.add(url)
            socials.append({"icon": icon, "label": label, "url": url})
        
        return socials

    async def _fetch_wikipedia_extract(self, wiki_url: str) -> str:
        """Fetch article extract from Wikipedia REST API."""
        try:
            # Extract article title from URL
            # e.g., https://en.wikipedia.org/wiki/Radiohead -> Radiohead
            parts = wiki_url.rstrip("/").split("/wiki/")
            if len(parts) < 2:
                return ""
            
            title = parts[-1]
            lang = "en"
            
            # Support non-English Wikipedia
            if "wikipedia.org" in wiki_url:
                domain_parts = wiki_url.split("//")[-1].split(".")
                if len(domain_parts) >= 3:
                    lang = domain_parts[0]
            
            api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
            resp = await self.client.get(api_url)
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get("extract", "")
            
            return ""
        except Exception as e:
            logger.debug(f"Wikipedia fetch failed: {e}")
            return ""

    async def _get_artist_image(self, mbid: str, artist_name: str) -> Optional[str]:
        """Try to get artist image from various sources."""
        # Try fanart.tv (free for personal use)
        try:
            fanart_url = f"https://webservice.fanart.tv/v3/music/{mbid}?api_key=fa0ba2f3c2ec1b5fb60e40baa5644df8"
            resp = await self.client.get(fanart_url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                thumbs = data.get("artistthumb", [])
                if thumbs:
                    return thumbs[0].get("url")
        except Exception:
            pass
        
        # Fallback: Try Wikipedia thumbnail
        try:
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{artist_name.replace(' ', '_')}"
            resp = await self.client.get(wiki_url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                thumbnail = data.get("thumbnail", {})
                if thumbnail.get("source"):
                    return thumbnail["source"]
        except Exception:
            pass
        
        return None


# Singleton instance
artist_service = ArtistService()
