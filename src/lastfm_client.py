"""
Last.fm API Client for NextTrack

Last.fm provides:
1. Track similarity data (based on user listening patterns)
2. Track tags (genres, moods, etc.)
3. Artist tags and similar artists

This is more reliable than Spotify's deprecated audio-features endpoint
because it uses collaborative filtering from millions of users.
"""

import os
import httpx
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import asyncio
from urllib.parse import quote


@dataclass
class LastFMTrack:
    """A track from Last.fm."""
    name: str
    artist: str
    mbid: Optional[str] = None
    match_score: float = 0.0  # Similarity score (0-1)
    playcount: int = 0
    url: Optional[str] = None


@dataclass
class LastFMTags:
    """Tags for a track or artist."""
    tags: List[str]

    def get_mood_tags(self) -> List[str]:
        """Extract mood-related tags."""
        mood_keywords = ['happy', 'sad', 'energetic', 'chill', 'angry', 'melancholy',
                        'uplifting', 'dark', 'mellow', 'aggressive', 'romantic', 'party']
        return [t for t in self.tags if any(m in t.lower() for m in mood_keywords)]

    def get_genre_tags(self) -> List[str]:
        """Extract genre-related tags."""
        # Common genre tags
        return [t for t in self.tags[:5]]  # Top 5 tags are usually genres


class LastFMClient:
    """
    Async client for Last.fm API.

    Provides track similarity and tag data as alternatives to
    Spotify's deprecated audio features.
    """

    BASE_URL = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        # Cache for similarity data
        self._similar_cache: Dict[str, List[LastFMTrack]] = {}
        self._tags_cache: Dict[str, LastFMTags] = {}

    @staticmethod
    def clean_track_name(track_name: str) -> str:
        """
        Clean track name for better Last.fm matching.
        Removes common suffixes like "- Remastered 2011", "(Deluxe)", etc.
        """
        import re
        # Remove remaster/reissue suffixes
        patterns = [
            r'\s*-\s*Remaster(ed)?(\s+\d{4})?\s*$',
            r'\s*-\s*\d{4}\s+Remaster(ed)?\s*$',
            r'\s*\(Remaster(ed)?(\s+\d{4})?\)\s*$',
            r'\s*\(Deluxe[^)]*\)\s*$',
            r'\s*\(Special[^)]*\)\s*$',
            r'\s*\(Expanded[^)]*\)\s*$',
            r'\s*\[Remaster(ed)?[^\]]*\]\s*$',
            r'\s*-\s*Single\s*$',
            r'\s*-\s*Radio Edit\s*$',
        ]
        cleaned = track_name
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=10.0,
                headers={'User-Agent': 'NextTrack/1.0 (academic project)'}
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def _api_request(self, method: str, **params) -> Dict:
        """Make a request to the Last.fm API."""
        client = await self._get_client()

        params.update({
            'method': method,
            'api_key': self.api_key,
            'format': 'json'
        })

        try:
            response = await client.get(self.BASE_URL, params=params)

            if response.status_code == 200:
                data = response.json()
                # Check for API errors
                if 'error' in data:
                    print(f"[LastFM] API error: {data.get('message', 'Unknown error')}")
                    return {}
                return data
            else:
                print(f"[LastFM] HTTP error: {response.status_code}")
                return {}

        except Exception as e:
            print(f"[LastFM] Request error: {e}")
            return {}

    async def get_similar_tracks(
        self,
        track_name: str,
        artist_name: str,
        limit: int = 20
    ) -> List[LastFMTrack]:
        """
        Get tracks similar to the given track.

        Uses Last.fm's collaborative filtering which is based on
        what users who listened to this track also listened to.
        """
        # Clean track name for better matching
        clean_name = self.clean_track_name(track_name)

        cache_key = f"{artist_name}:{clean_name}".lower()
        if cache_key in self._similar_cache:
            return self._similar_cache[cache_key][:limit]

        data = await self._api_request(
            'track.getSimilar',
            track=clean_name,
            artist=artist_name,
            limit=min(limit, 100),
            autocorrect=1
        )

        similar = []
        similar_tracks = data.get('similartracks', {}).get('track', [])

        # Handle case where API returns single track as dict instead of list
        if isinstance(similar_tracks, dict):
            similar_tracks = [similar_tracks]

        for track in similar_tracks:
            similar.append(LastFMTrack(
                name=track.get('name', ''),
                artist=track.get('artist', {}).get('name', '') if isinstance(track.get('artist'), dict) else track.get('artist', ''),
                mbid=track.get('mbid'),
                match_score=float(track.get('match', 0)),
                playcount=int(track.get('playcount', 0)),
                url=track.get('url')
            ))

        self._similar_cache[cache_key] = similar
        return similar[:limit]

    async def get_track_tags(self, track_name: str, artist_name: str) -> LastFMTags:
        """Get tags for a track (genres, moods, etc.)."""
        # Clean track name for better matching
        clean_name = self.clean_track_name(track_name)

        cache_key = f"track:{artist_name}:{clean_name}".lower()
        if cache_key in self._tags_cache:
            return self._tags_cache[cache_key]

        data = await self._api_request(
            'track.getTopTags',
            track=clean_name,
            artist=artist_name,
            autocorrect=1
        )

        tags = []
        for tag in data.get('toptags', {}).get('tag', [])[:10]:
            tags.append(tag.get('name', '').lower())

        result = LastFMTags(tags=tags)
        self._tags_cache[cache_key] = result
        return result

    async def get_artist_tags(self, artist_name: str) -> LastFMTags:
        """Get tags for an artist."""
        cache_key = f"artist:{artist_name}".lower()
        if cache_key in self._tags_cache:
            return self._tags_cache[cache_key]

        data = await self._api_request(
            'artist.getTopTags',
            artist=artist_name,
            autocorrect=1
        )

        tags = []
        for tag in data.get('toptags', {}).get('tag', [])[:10]:
            tags.append(tag.get('name', '').lower())

        result = LastFMTags(tags=tags)
        self._tags_cache[cache_key] = result
        return result

    async def get_similar_artists(self, artist_name: str, limit: int = 10) -> List[Tuple[str, float]]:
        """Get similar artists with match scores."""
        data = await self._api_request(
            'artist.getSimilar',
            artist=artist_name,
            limit=limit,
            autocorrect=1
        )

        similar = []
        for artist in data.get('similarartists', {}).get('artist', []):
            similar.append((
                artist.get('name', ''),
                float(artist.get('match', 0))
            ))

        return similar

    async def search_track(self, track_name: str, artist_name: str = None) -> Optional[LastFMTrack]:
        """Search for a track on Last.fm."""
        query = f"{artist_name} {track_name}" if artist_name else track_name

        data = await self._api_request(
            'track.search',
            track=query,
            limit=1
        )

        results = data.get('results', {}).get('trackmatches', {}).get('track', [])
        if results:
            track = results[0] if isinstance(results, list) else results
            return LastFMTrack(
                name=track.get('name', ''),
                artist=track.get('artist', ''),
                mbid=track.get('mbid'),
                url=track.get('url')
            )

        return None

    def estimate_audio_features_from_tags(self, tags: LastFMTags) -> Dict[str, float]:
        """
        Estimate pseudo audio features from Last.fm tags.

        This provides approximate values for energy, valence, etc.
        based on genre and mood tags.
        """
        tag_set = set(t.lower() for t in tags.tags)

        # Energy estimation
        high_energy_tags = {'rock', 'metal', 'punk', 'electronic', 'dance', 'edm',
                          'hardcore', 'energetic', 'upbeat', 'party', 'club'}
        low_energy_tags = {'ambient', 'chill', 'acoustic', 'ballad', 'slow',
                         'relaxing', 'soft', 'quiet', 'meditation'}

        energy = 0.5
        if tag_set & high_energy_tags:
            energy = 0.7 + 0.1 * len(tag_set & high_energy_tags)
        elif tag_set & low_energy_tags:
            energy = 0.3 - 0.05 * len(tag_set & low_energy_tags)
        energy = max(0.0, min(1.0, energy))

        # Valence (happiness) estimation
        happy_tags = {'happy', 'uplifting', 'fun', 'party', 'summer', 'feel good',
                     'positive', 'cheerful', 'joyful'}
        sad_tags = {'sad', 'melancholy', 'dark', 'depressing', 'emotional',
                   'heartbreak', 'lonely', 'tragic'}

        valence = 0.5
        if tag_set & happy_tags:
            valence = 0.7 + 0.1 * len(tag_set & happy_tags)
        elif tag_set & sad_tags:
            valence = 0.3 - 0.05 * len(tag_set & sad_tags)
        valence = max(0.0, min(1.0, valence))

        # Danceability estimation
        dance_tags = {'dance', 'electronic', 'disco', 'house', 'techno', 'edm',
                     'club', 'groovy', 'funk', 'rhythm'}

        danceability = 0.5
        if tag_set & dance_tags:
            danceability = 0.7 + 0.1 * len(tag_set & dance_tags)
        danceability = max(0.0, min(1.0, danceability))

        # Acousticness estimation
        acoustic_tags = {'acoustic', 'unplugged', 'folk', 'singer-songwriter',
                        'classical', 'piano', 'guitar'}
        electronic_tags = {'electronic', 'synth', 'edm', 'techno', 'house'}

        acousticness = 0.5
        if tag_set & acoustic_tags:
            acousticness = 0.7 + 0.1 * len(tag_set & acoustic_tags)
        elif tag_set & electronic_tags:
            acousticness = 0.2 - 0.05 * len(tag_set & electronic_tags)
        acousticness = max(0.0, min(1.0, acousticness))

        # Instrumentalness estimation
        instrumental_tags = {'instrumental', 'post-rock', 'ambient', 'classical',
                           'soundtrack', 'jazz', 'electronic'}
        vocal_tags = {'vocal', 'singer-songwriter', 'pop', 'soul', 'r&b'}

        instrumentalness = 0.3  # Default low (most music has vocals)
        if tag_set & instrumental_tags:
            instrumentalness = 0.6 + 0.1 * len(tag_set & instrumental_tags)
        elif tag_set & vocal_tags:
            instrumentalness = 0.1
        instrumentalness = max(0.0, min(1.0, instrumentalness))

        return {
            'energy': energy,
            'valence': valence,
            'danceability': danceability,
            'acousticness': acousticness,
            'instrumentalness': instrumentalness,
            'speechiness': 0.1,  # Default
            'liveness': 0.2,  # Default
            'source': 'lastfm_tags'
        }


# Singleton
_client: Optional[LastFMClient] = None


def create_lastfm_client() -> Optional[LastFMClient]:
    """Create LastFM client if API key is configured."""
    api_key = os.environ.get('LASTFM_API_KEY')
    if api_key:
        return LastFMClient(api_key)
    return None


def get_lastfm_client() -> Optional[LastFMClient]:
    """Get or create the LastFM client singleton."""
    global _client
    if _client is None:
        _client = create_lastfm_client()
    return _client
