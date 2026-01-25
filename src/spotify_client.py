"""
Spotify API Client for NextTrack
Handles all interactions with the Spotify Web API.
"""

import base64
import httpx
from typing import List, Dict, Optional
from dataclasses import dataclass
import asyncio


@dataclass
class AudioFeatures:
    """Audio features for a track from Spotify."""
    acousticness: float
    danceability: float
    energy: float
    instrumentalness: float
    liveness: float
    loudness: float
    speechiness: float
    tempo: float
    valence: float
    key: int
    mode: int
    time_signature: int

    @classmethod
    def from_dict(cls, data: Dict) -> 'AudioFeatures':
        return cls(
            acousticness=data.get('acousticness', 0.0),
            danceability=data.get('danceability', 0.0),
            energy=data.get('energy', 0.0),
            instrumentalness=data.get('instrumentalness', 0.0),
            liveness=data.get('liveness', 0.0),
            loudness=data.get('loudness', -60.0),
            speechiness=data.get('speechiness', 0.0),
            tempo=data.get('tempo', 120.0),
            valence=data.get('valence', 0.0),
            key=data.get('key', 0),
            mode=data.get('mode', 1),
            time_signature=data.get('time_signature', 4)
        )

    def to_dict(self) -> Dict:
        return {
            'acousticness': self.acousticness,
            'danceability': self.danceability,
            'energy': self.energy,
            'instrumentalness': self.instrumentalness,
            'liveness': self.liveness,
            'loudness': self.loudness,
            'speechiness': self.speechiness,
            'tempo': self.tempo,
            'valence': self.valence,
            'key': self.key,
            'mode': self.mode,
            'time_signature': self.time_signature
        }


@dataclass
class Track:
    """Represents a Spotify track with metadata."""
    id: str
    name: str
    artist_name: str
    artist_id: str
    album_name: str
    album_image: Optional[str]
    duration_ms: int
    popularity: int
    preview_url: Optional[str]
    external_url: str
    isrc: Optional[str] = None  # International Standard Recording Code
    audio_features: Optional[AudioFeatures] = None

    @classmethod
    def from_spotify_response(cls, data: Dict) -> 'Track':
        album_images = data.get('album', {}).get('images', [])
        album_image = album_images[0]['url'] if album_images else None

        # Extract ISRC from external_ids
        external_ids = data.get('external_ids', {})
        isrc = external_ids.get('isrc')

        return cls(
            id=data['id'],
            name=data['name'],
            artist_name=data['artists'][0]['name'] if data.get('artists') else 'Unknown',
            artist_id=data['artists'][0]['id'] if data.get('artists') else '',
            album_name=data.get('album', {}).get('name', 'Unknown'),
            album_image=album_image,
            duration_ms=data.get('duration_ms', 0),
            popularity=data.get('popularity', 0),
            preview_url=data.get('preview_url'),
            external_url=data.get('external_urls', {}).get('spotify', ''),
            isrc=isrc
        )

    def to_dict(self) -> Dict:
        result = {
            'id': self.id,
            'name': self.name,
            'artist_name': self.artist_name,
            'artist_id': self.artist_id,
            'album_name': self.album_name,
            'album_image': self.album_image,
            'duration_ms': self.duration_ms,
            'popularity': self.popularity,
            'preview_url': self.preview_url,
            'external_url': self.external_url
        }
        if self.audio_features:
            result['audio_features'] = self.audio_features.to_dict()
        return result


class SpotifyClient:
    """
    Async client for Spotify Web API.
    Uses Client Credentials flow for server-to-server authentication.

    Note: Spotify deprecated the /audio-features endpoint for new apps in late 2024.
    This client focuses on track metadata and recommendations via Spotify's
    recommendation algorithm, while audio similarity is handled via Last.fm.
    """

    AUTH_URL = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"

    def __init__(self, client_id: str, client_secret: str, market: str = 'US'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.market = market.upper() if market else 'US'
        self._access_token: Optional[str] = None
        self._token_expires: float = 0
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _ensure_token(self):
        """Ensure we have a valid access token."""
        import time
        if self._access_token and time.time() < self._token_expires:
            return

        client = await self._get_client()

        # Encode credentials
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()

        response = await client.post(
            self.AUTH_URL,
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            data={"grant_type": "client_credentials"}
        )

        if response.status_code != 200:
            raise Exception(f"Failed to authenticate with Spotify: {response.text}")

        data = response.json()
        self._access_token = data['access_token']
        self._token_expires = time.time() + data['expires_in'] - 60  # 60s buffer

    async def _api_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make an authenticated API request."""
        await self._ensure_token()
        client = await self._get_client()

        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f"Bearer {self._access_token}"

        url = f"{self.API_BASE}{endpoint}"
        response = await client.request(method, url, headers=headers, **kwargs)

        if response.status_code == 429:
            # Rate limited - wait and retry
            retry_after = int(response.headers.get('Retry-After', 1))
            await asyncio.sleep(retry_after)
            return await self._api_request(method, endpoint, **kwargs)

        if response.status_code != 200:
            raise Exception(
                f"Spotify API error ({method} {endpoint}): {response.status_code} - {response.text}"
            )

        return response.json()

    async def get_track(self, track_id: str) -> Track:
        """Get a single track by ID."""
        # Handle full URIs
        if track_id.startswith('spotify:track:'):
            track_id = track_id.split(':')[-1]

        data = await self._api_request(
            'GET',
            f'/tracks/{track_id}',
            params={'market': self.market}
        )
        return Track.from_spotify_response(data)

    async def get_tracks(self, track_ids: List[str]) -> List[Track]:
        """Get multiple tracks by ID (max 50)."""
        # Clean track IDs
        clean_ids = []
        for tid in track_ids:
            if tid.startswith('spotify:track:'):
                tid = tid.split(':')[-1]
            clean_ids.append(tid)

        # Spotify allows max 50 tracks per request
        tracks = []
        for i in range(0, len(clean_ids), 50):
            batch = clean_ids[i:i+50]
            data = await self._api_request(
                'GET',
                '/tracks',
                params={
                    'ids': ','.join(batch),
                    'market': self.market
                }
            )
            for track_data in data.get('tracks', []):
                if track_data:
                    tracks.append(Track.from_spotify_response(track_data))

        return tracks

    async def get_audio_features(self, track_ids: List[str]) -> Dict[str, AudioFeatures]:
        """
        Get audio features for multiple tracks.

        NOTE: As of late 2024, Spotify deprecated the /audio-features endpoint
        for new apps. This method will likely return an empty dict.
        Use Last.fm for track similarity instead.
        """
        # Clean track IDs
        clean_ids = []
        for tid in track_ids:
            if tid.startswith('spotify:track:'):
                tid = tid.split(':')[-1]
            clean_ids.append(tid)

        features = {}

        try:
            for i in range(0, len(clean_ids), 100):
                batch = clean_ids[i:i+100]
                data = await self._api_request('GET', '/audio-features', params={'ids': ','.join(batch)})
                for af in data.get('audio_features', []):
                    if af:
                        features[af['id']] = AudioFeatures.from_dict(af)
        except Exception:
            # Audio features endpoint deprecated for new apps (late 2024)
            # Silently return empty dict - app works without audio features
            pass

        return features

    async def get_tracks_with_features(self, track_ids: List[str]) -> List[Track]:
        """
        Get tracks with their audio features.

        Audio features may be unavailable due to Spotify API deprecation.
        Tracks are still returned, just without audio_features attached.
        """
        tracks = await self.get_tracks(track_ids)

        # Try to get audio features (may fail due to deprecation)
        features = await self.get_audio_features([t.id for t in tracks])

        # Attach features to tracks (may be empty dict)
        for track in tracks:
            track.audio_features = features.get(track.id)

        return tracks

    async def search_tracks(self, query: str, limit: int = 20) -> List[Track]:
        """Search for tracks."""
        data = await self._api_request(
            'GET', '/search',
            params={
                'q': query,
                'type': 'track',
                'limit': min(limit, 50),
                'market': self.market
            }
        )

        tracks = []
        for item in data.get('tracks', {}).get('items', []):
            tracks.append(Track.from_spotify_response(item))

        return tracks

    async def get_recommendations(
        self,
        seed_tracks: List[str] = None,
        seed_artists: List[str] = None,
        seed_genres: List[str] = None,
        limit: int = 20,
        **audio_params
    ) -> List[Track]:
        """
        Get track recommendations from Spotify.

        Audio params can include:
        - target_energy, min_energy, max_energy
        - target_valence, min_valence, max_valence
        - target_tempo, min_tempo, max_tempo
        - etc.
        """
        params = {
            'limit': min(limit, 100),
            'market': self.market
        }

        if seed_tracks:
            clean_ids = [t.split(':')[-1] if ':' in t else t for t in seed_tracks[:5]]
            params['seed_tracks'] = ','.join(clean_ids)

        if seed_artists:
            params['seed_artists'] = ','.join(seed_artists[:5])

        if seed_genres:
            params['seed_genres'] = ','.join(seed_genres[:5])

        # Add audio feature parameters
        params.update(audio_params)

        data = await self._api_request('GET', '/recommendations', params=params)

        tracks = []
        for item in data.get('tracks', []):
            tracks.append(Track.from_spotify_response(item))

        return tracks

    async def get_artist_top_tracks(self, artist_id: str, market: Optional[str] = None) -> List[Track]:
        """Get an artist's top tracks."""
        market = (market or self.market).upper()
        data = await self._api_request(
            'GET', f'/artists/{artist_id}/top-tracks',
            params={'market': market}
        )

        tracks = []
        for item in data.get('tracks', []):
            tracks.append(Track.from_spotify_response(item))

        return tracks

    async def get_related_artists(self, artist_id: str) -> List[Dict]:
        """Get artists related to the given artist."""
        data = await self._api_request('GET', f'/artists/{artist_id}/related-artists')
        return data.get('artists', [])
