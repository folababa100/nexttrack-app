"""
MusicBrainz API Client for NextTrack
Provides open music metadata for genre-aware recommendations.

MusicBrainz is a free, open music encyclopedia that makes music metadata
available to the public. This client accesses:
- Artist information and genres/tags
- Recording metadata
- Release (album) information
- Artist relationships

API Documentation: https://musicbrainz.org/doc/MusicBrainz_API
"""

import asyncio
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
import httpx


@dataclass
class MusicBrainzArtist:
    """Artist information from MusicBrainz."""
    mbid: str  # MusicBrainz ID
    name: str
    sort_name: str
    disambiguation: str = ""
    country: str = ""
    type: str = ""  # Person, Group, Orchestra, etc.
    tags: List[str] = field(default_factory=list)  # Genre tags
    score: int = 100  # Search relevance score

    @classmethod
    def from_api_response(cls, data: Dict) -> 'MusicBrainzArtist':
        """Create from MusicBrainz API response."""
        tags = []
        for tag in data.get('tags', []):
            if tag.get('name'):
                tags.append(tag['name'].lower())

        return cls(
            mbid=data.get('id', ''),
            name=data.get('name', ''),
            sort_name=data.get('sort-name', data.get('name', '')),
            disambiguation=data.get('disambiguation', ''),
            country=data.get('country', ''),
            type=data.get('type', ''),
            tags=tags,
            score=data.get('score', 100)
        )


@dataclass
class MusicBrainzRecording:
    """Recording (track) information from MusicBrainz."""
    mbid: str
    title: str
    artist_name: str
    artist_mbid: str
    length_ms: int = 0
    first_release_date: str = ""
    tags: List[str] = field(default_factory=list)
    score: int = 100

    @classmethod
    def from_api_response(cls, data: Dict) -> 'MusicBrainzRecording':
        """Create from MusicBrainz API response."""
        tags = []
        for tag in data.get('tags', []):
            if tag.get('name'):
                tags.append(tag['name'].lower())

        # Get primary artist
        artist_credit = data.get('artist-credit', [])
        artist_name = ""
        artist_mbid = ""
        if artist_credit:
            artist = artist_credit[0].get('artist', {})
            artist_name = artist.get('name', '')
            artist_mbid = artist.get('id', '')

        return cls(
            mbid=data.get('id', ''),
            title=data.get('title', ''),
            artist_name=artist_name,
            artist_mbid=artist_mbid,
            length_ms=data.get('length', 0) or 0,
            first_release_date=data.get('first-release-date', ''),
            tags=tags,
            score=data.get('score', 100)
        )


@dataclass
class MusicBrainzRelease:
    """Release (album) information from MusicBrainz."""
    mbid: str
    title: str
    artist_name: str
    date: str = ""
    country: str = ""
    status: str = ""  # Official, Bootleg, etc.
    primary_type: str = ""  # Album, Single, EP, etc.
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: Dict) -> 'MusicBrainzRelease':
        """Create from MusicBrainz API response."""
        tags = []
        for tag in data.get('tags', []):
            if tag.get('name'):
                tags.append(tag['name'].lower())

        # Get primary artist
        artist_credit = data.get('artist-credit', [])
        artist_name = ""
        if artist_credit:
            artist = artist_credit[0].get('artist', {})
            artist_name = artist.get('name', '')

        # Get release group type
        rg = data.get('release-group', {})
        primary_type = rg.get('primary-type', '')

        return cls(
            mbid=data.get('id', ''),
            title=data.get('title', ''),
            artist_name=artist_name,
            date=data.get('date', ''),
            country=data.get('country', ''),
            status=data.get('status', ''),
            primary_type=primary_type,
            tags=tags
        )


class MusicBrainzClient:
    """
    Async client for MusicBrainz API.

    MusicBrainz requires a User-Agent header and rate limits to 1 request/second
    for unregistered users.

    Docs: https://musicbrainz.org/doc/MusicBrainz_API
    """

    API_BASE = "https://musicbrainz.org/ws/2"
    RATE_LIMIT_DELAY = 1.1  # Slightly over 1 second to be safe

    def __init__(
        self,
        app_name: str = "NextTrack",
        app_version: str = "1.0.0",
        contact: str = "nexttrack@example.com"
    ):
        """
        Initialize MusicBrainz client.

        Args:
            app_name: Application name for User-Agent
            app_version: Application version for User-Agent
            contact: Contact email for User-Agent (required by MusicBrainz)
        """
        self.user_agent = f"{app_name}/{app_version} ({contact})"
        self._http_client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json"
                }
            )
        return self._http_client

    async def close(self):
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _rate_limit(self):
        """Enforce rate limiting."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            await asyncio.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    async def _api_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Dict:
        """Make a rate-limited API request."""
        await self._rate_limit()

        client = await self._get_client()
        params = params or {}
        params['fmt'] = 'json'  # Always request JSON

        url = f"{self.API_BASE}/{endpoint}"
        response = await client.get(url, params=params)

        if response.status_code == 503:
            # Rate limited - wait and retry
            await asyncio.sleep(2)
            response = await client.get(url, params=params)

        if response.status_code != 200:
            raise Exception(
                f"MusicBrainz API error: {response.status_code} - {response.text}"
            )

        return response.json()

    async def search_artists(
        self,
        query: str,
        limit: int = 10
    ) -> List[MusicBrainzArtist]:
        """
        Search for artists by name.

        Args:
            query: Artist name to search for
            limit: Maximum results to return

        Returns:
            List of matching artists with tags/genres
        """
        params = {
            'query': query,
            'limit': min(limit, 100)
        }

        data = await self._api_request('artist', params)

        artists = []
        for item in data.get('artists', []):
            try:
                artists.append(MusicBrainzArtist.from_api_response(item))
            except Exception:
                continue

        return artists

    async def get_artist(
        self,
        mbid: str,
        includes: List[str] = None
    ) -> Optional[MusicBrainzArtist]:
        """
        Get artist by MusicBrainz ID with additional data.

        Args:
            mbid: MusicBrainz artist ID
            includes: Additional data to include (e.g., 'tags', 'genres')
        """
        includes = includes or ['tags']
        params = {'inc': '+'.join(includes)}

        try:
            data = await self._api_request(f'artist/{mbid}', params)
            return MusicBrainzArtist.from_api_response(data)
        except Exception:
            return None

    async def search_recordings(
        self,
        query: str = None,
        artist: str = None,
        recording: str = None,
        limit: int = 10
    ) -> List[MusicBrainzRecording]:
        """
        Search for recordings (tracks).

        Args:
            query: Free-text search query
            artist: Artist name to filter by
            recording: Recording/track title to filter by
            limit: Maximum results

        Returns:
            List of matching recordings
        """
        # Build Lucene query
        query_parts = []
        if query:
            query_parts.append(query)
        if artist:
            query_parts.append(f'artist:"{artist}"')
        if recording:
            query_parts.append(f'recording:"{recording}"')

        params = {
            'query': ' AND '.join(query_parts) if query_parts else '*',
            'limit': min(limit, 100)
        }

        data = await self._api_request('recording', params)

        recordings = []
        for item in data.get('recordings', []):
            try:
                recordings.append(MusicBrainzRecording.from_api_response(item))
            except Exception:
                continue

        return recordings

    async def get_artist_tags(self, artist_name: str) -> List[str]:
        """
        Get genre tags for an artist by name.

        Returns list of genre/style tags sorted by relevance.
        """
        artists = await self.search_artists(artist_name, limit=3)

        all_tags: Set[str] = set()
        for artist in artists:
            # Only include high-confidence matches
            if artist.score >= 90:
                all_tags.update(artist.tags)

        return list(all_tags)

    async def get_genres_for_artists(
        self,
        artist_names: List[str]
    ) -> Dict[str, List[str]]:
        """
        Get genre tags for multiple artists.

        Args:
            artist_names: List of artist names

        Returns:
            Dict mapping artist name to list of genre tags
        """
        result = {}

        for name in artist_names:
            try:
                tags = await self.get_artist_tags(name)
                result[name] = tags
            except Exception:
                result[name] = []

        return result

    async def find_similar_artists_by_tags(
        self,
        tags: List[str],
        exclude_artists: List[str] = None,
        limit: int = 10
    ) -> List[MusicBrainzArtist]:
        """
        Find artists with similar genre tags.

        Args:
            tags: List of genre tags to search for
            exclude_artists: Artist names to exclude from results
            limit: Maximum results

        Returns:
            List of artists matching the tags
        """
        exclude_artists = exclude_artists or []
        exclude_set = {name.lower() for name in exclude_artists}

        # Search for each tag and collect unique artists
        artists_by_mbid: Dict[str, MusicBrainzArtist] = {}

        for tag in tags[:3]:  # Limit to top 3 tags to reduce API calls
            try:
                query = f'tag:"{tag}"'
                params = {
                    'query': query,
                    'limit': 25
                }

                data = await self._api_request('artist', params)

                for item in data.get('artists', []):
                    artist = MusicBrainzArtist.from_api_response(item)
                    if artist.name.lower() not in exclude_set:
                        # Keep highest scoring version
                        if artist.mbid not in artists_by_mbid or \
                           artist.score > artists_by_mbid[artist.mbid].score:
                            artists_by_mbid[artist.mbid] = artist

            except Exception:
                continue

        # Sort by score and return top results
        artists = list(artists_by_mbid.values())
        artists.sort(key=lambda a: a.score, reverse=True)
        return artists[:limit]

    async def get_related_artists(
        self,
        artist_name: str,
        limit: int = 10
    ) -> List[MusicBrainzArtist]:
        """
        Find artists related to the given artist by shared genre tags.

        This is a tag-based alternative to Spotify's deprecated
        related-artists endpoint.
        """
        # First get the artist's tags
        tags = await self.get_artist_tags(artist_name)

        if not tags:
            return []

        # Find artists with similar tags
        return await self.find_similar_artists_by_tags(
            tags,
            exclude_artists=[artist_name],
            limit=limit
        )


# Genre/tag utilities

# Common music genre mappings for normalization
GENRE_SYNONYMS = {
    'hip hop': ['hip-hop', 'hiphop', 'rap'],
    'r&b': ['rnb', 'rhythm and blues', 'r and b'],
    'electronic': ['electronica', 'edm', 'dance'],
    'rock': ['rock and roll', 'rock & roll'],
    'pop': ['pop music'],
    'jazz': ['jazz music'],
    'classical': ['classical music'],
    'country': ['country music'],
    'folk': ['folk music'],
    'metal': ['heavy metal'],
    'soul': ['soul music'],
    'funk': ['funk music'],
    'reggae': ['reggae music'],
    'blues': ['blues music'],
    'afrobeats': ['afrobeat', 'afro-beats'],
    'latin': ['latin music', 'latino'],
}


def normalize_genre(genre: str) -> str:
    """Normalize a genre tag to a canonical form."""
    genre_lower = genre.lower().strip()

    for canonical, synonyms in GENRE_SYNONYMS.items():
        if genre_lower == canonical or genre_lower in synonyms:
            return canonical

    return genre_lower


def calculate_genre_similarity(
    tags1: List[str],
    tags2: List[str]
) -> float:
    """
    Calculate similarity between two sets of genre tags.

    Returns a score from 0.0 (no overlap) to 1.0 (identical).
    """
    if not tags1 or not tags2:
        return 0.0

    # Normalize all tags
    normalized1 = {normalize_genre(t) for t in tags1}
    normalized2 = {normalize_genre(t) for t in tags2}

    # Jaccard similarity
    intersection = normalized1 & normalized2
    union = normalized1 | normalized2

    if not union:
        return 0.0

    return len(intersection) / len(union)
