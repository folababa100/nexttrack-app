"""
Genius.com API client for lyrics and song context.
Provides additional contextual information for recommendations.
"""

import httpx
from typing import Optional, Dict, List
from dataclasses import dataclass
import os
import re


@dataclass
class GeniusSong:
    """Genius song information."""
    id: int
    title: str
    artist_name: str
    url: str
    annotation_count: int
    description: Optional[str] = None
    release_date: Optional[str] = None
    primary_genre: Optional[str] = None
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class GeniusClient:
    """
    Client for Genius.com API.

    Provides lyrics metadata and song context for enhanced recommendations.
    Requires GENIUS_ACCESS_TOKEN environment variable.

    Rate limit: ~5 requests/second (generous for free tier)
    """

    BASE_URL = "https://api.genius.com"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("GENIUS_ACCESS_TOKEN")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """Check if API token is available."""
        return bool(self.access_token)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "User-Agent": "NextTrack/1.0"
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"

            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=10.0
            )
        return self._client

    async def search_song(
        self,
        title: str,
        artist: Optional[str] = None
    ) -> Optional[GeniusSong]:
        """
        Search for a song on Genius.

        Args:
            title: Song title
            artist: Optional artist name for better matching

        Returns:
            GeniusSong if found, None otherwise
        """
        if not self.access_token:
            return None  # Graceful degradation without API key

        # Build search query
        query = title
        if artist:
            query = f"{artist} {title}"

        client = await self._get_client()
        try:
            response = await client.get(
                "/search",
                params={"q": query}
            )
            response.raise_for_status()
            data = response.json()

            hits = data.get("response", {}).get("hits", [])

            # Find best match
            for hit in hits:
                result = hit.get("result", {})

                # If artist specified, verify match
                if artist:
                    result_artist = result.get("primary_artist", {}).get("name", "").lower()
                    if artist.lower() not in result_artist and result_artist not in artist.lower():
                        continue

                return GeniusSong(
                    id=result.get("id"),
                    title=result.get("title", ""),
                    artist_name=result.get("primary_artist", {}).get("name", ""),
                    url=result.get("url", ""),
                    annotation_count=result.get("annotation_count", 0),
                    release_date=result.get("release_date_for_display"),
                )

            return None

        except httpx.HTTPStatusError as e:
            print(f"Genius API HTTP error: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"Genius API error: {e}")
            return None

    async def get_song_details(self, song_id: int) -> Optional[GeniusSong]:
        """
        Get detailed song information including description and tags.

        Args:
            song_id: Genius song ID

        Returns:
            GeniusSong with full details
        """
        if not self.access_token:
            return None

        client = await self._get_client()
        try:
            response = await client.get(
                f"/songs/{song_id}",
                params={"text_format": "plain"}
            )
            response.raise_for_status()

            song_data = response.json().get("response", {}).get("song", {})

            # Extract tags from custom performances and metadata
            tags = []
            for tag in song_data.get("tags", []):
                if isinstance(tag, dict):
                    tags.append(tag.get("name", ""))
                elif isinstance(tag, str):
                    tags.append(tag)

            # Extract description text
            description = None
            desc_obj = song_data.get("description", {})
            if isinstance(desc_obj, dict):
                description = desc_obj.get("plain", "")
            elif isinstance(desc_obj, str):
                description = desc_obj

            # Clean description
            if description:
                description = self._clean_text(description)[:500]  # Limit length

            return GeniusSong(
                id=song_data.get("id"),
                title=song_data.get("title", ""),
                artist_name=song_data.get("primary_artist", {}).get("name", ""),
                url=song_data.get("url", ""),
                annotation_count=song_data.get("annotation_count", 0),
                description=description,
                release_date=song_data.get("release_date_for_display"),
                primary_genre=self._extract_genre(song_data),
                tags=tags
            )

        except httpx.HTTPStatusError as e:
            print(f"Genius API HTTP error: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"Genius API error: {e}")
            return None

    async def get_song_context(
        self,
        title: str,
        artist: str
    ) -> Optional[Dict]:
        """
        Get contextual information about a song for recommendation enhancement.

        Returns dict with:
        - description: Song description/meaning
        - tags: Associated tags
        - genre: Primary genre if available
        - annotation_count: Popularity indicator
        """
        song = await self.search_song(title, artist)
        if not song:
            return None

        # Get full details
        details = await self.get_song_details(song.id)
        if not details:
            return {
                "title": song.title,
                "artist": song.artist_name,
                "url": song.url,
                "annotation_count": song.annotation_count
            }

        return {
            "title": details.title,
            "artist": details.artist_name,
            "url": details.url,
            "description": details.description,
            "genre": details.primary_genre,
            "tags": details.tags,
            "annotation_count": details.annotation_count,
            "release_date": details.release_date
        }

    def _extract_genre(self, song_data: Dict) -> Optional[str]:
        """Extract primary genre from song data."""
        # Try custom performances first
        custom_perfs = song_data.get("custom_performances", [])
        for perf in custom_perfs:
            label = perf.get("label", "").lower()
            if "genre" in label:
                artists = perf.get("artists", [])
                if artists:
                    return artists[0].get("name")

        # Try tags
        tags = song_data.get("tags", [])
        genre_keywords = ["pop", "rock", "hip hop", "rap", "r&b", "country",
                         "electronic", "jazz", "classical", "metal", "indie",
                         "soul", "funk", "reggae", "blues", "folk"]

        for tag in tags:
            tag_name = tag.get("name", "").lower() if isinstance(tag, dict) else str(tag).lower()
            for genre in genre_keywords:
                if genre in tag_name:
                    return tag_name.title()

        return None

    def _clean_text(self, text: str) -> str:
        """Clean text by removing excess whitespace and special chars."""
        if not text:
            return ""
        # Remove multiple spaces/newlines
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Convenience function for one-off lookups
async def get_song_context(title: str, artist: str) -> Optional[Dict]:
    """
    Quick lookup of song context.

    Usage:
        context = await get_song_context("Blinding Lights", "The Weeknd")
    """
    client = GeniusClient()
    try:
        return await client.get_song_context(title, artist)
    finally:
        await client.close()
