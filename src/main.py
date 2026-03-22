"""
NextTrack API - Main Application
Privacy-focused music recommendation API with FastAPI.
"""

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from spotify_client import SpotifyClient
from engine import RecommendationEngine
from musicbrainz_client import MusicBrainzClient
from wikidata_client import WikidataClient
from cache import cache
from genius_client import GeniusClient
from lastfm_client import LastFMClient, create_lastfm_client

# Try to import enhanced engine (optional)
try:
    from enhanced_engine import EnhancedRecommendationEngine
    ENHANCED_ENGINE_AVAILABLE = True
except ImportError:
    ENHANCED_ENGINE_AVAILABLE = False

# Load environment variables from .env file
# Try both src/.env (when running from src/) and .env (when running from project root)
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()  # Fallback to default behavior

# Global instances
spotify_client: Optional[SpotifyClient] = None
recommendation_engine: Optional[RecommendationEngine] = None
musicbrainz_client: Optional[MusicBrainzClient] = None
wikidata_client: Optional[WikidataClient] = None
genius_client: Optional[GeniusClient] = None
lastfm_client: Optional[LastFMClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global spotify_client, recommendation_engine, musicbrainz_client, wikidata_client, genius_client, lastfm_client

    # Initialize cache (Redis or fallback to in-memory)
    await cache.connect()

    # Get credentials from environment
    client_id = os.environ.get('SPOTIFY_CLIENT_ID', '')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
    market = os.environ.get('SPOTIFY_MARKET', 'US')
    use_enhanced = os.environ.get('USE_ENHANCED_ENGINE', 'false').lower() == 'true'

    if client_id and client_secret:
        spotify_client = SpotifyClient(client_id, client_secret, market=market)

        # Initialize optional external data sources
        musicbrainz_client = MusicBrainzClient()
        wikidata_client = WikidataClient()
        genius_client = GeniusClient()

        if genius_client.is_configured:
            print("✓ Genius.com client initialized")
        else:
            print("ℹ Genius.com API not configured (set GENIUS_ACCESS_TOKEN for lyrics context)")

        # Initialize Last.fm client for track similarity
        lastfm_client = create_lastfm_client()
        if lastfm_client:
            print("✓ Last.fm client initialized (for track similarity data)")
        else:
            print("ℹ Last.fm API not configured (set LASTFM_API_KEY for enhanced similarity)")

        # Use enhanced engine if available and enabled
        if use_enhanced and ENHANCED_ENGINE_AVAILABLE:
            from enhanced_engine import EnhancedRecommendationEngine
            recommendation_engine = EnhancedRecommendationEngine(
                spotify_client,
                musicbrainz_client,
                wikidata_client,
                lastfm_client
            )
            print("✓ Enhanced recommendation engine initialized (with MusicBrainz + Wikidata + Last.fm)")
        else:
            recommendation_engine = RecommendationEngine(spotify_client)
            print("✓ Spotify client and recommendation engine initialized")
    else:
        print("⚠ Warning: Spotify credentials not set. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET")

    yield

    # Cleanup
    if spotify_client:
        await spotify_client.close()
    if musicbrainz_client:
        await musicbrainz_client.close()
    if wikidata_client:
        await wikidata_client.close()
    if genius_client:
        await genius_client.close()
    if lastfm_client:
        await lastfm_client.close()
    await cache.close()


# Initialize FastAPI
app = FastAPI(
    title="NextTrack API",
    description="Privacy-focused music recommendation API - No user tracking, no profiling",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for web client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for demo UI
static_dir = os.path.join(os.path.dirname(__file__), 'static')
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ============== Request/Response Models ==============

class TrackInput(BaseModel):
    """Input track identifier."""
    track_id: str = Field(..., description="Spotify track ID")


class Preferences(BaseModel):
    """Recommendation preference parameters."""
    energy_range: Optional[List[float]] = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="[min, max] energy range (0-1)"
    )
    tempo_range: Optional[List[float]] = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="[min, max] tempo range in BPM"
    )
    valence_range: Optional[List[float]] = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="[min, max] valence/mood range (0-1)"
    )
    danceability_range: Optional[List[float]] = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="[min, max] danceability range (0-1)"
    )
    preferred_genres: Optional[List[str]] = Field(
        default=None,
        description="Preferred genre tags"
    )
    avoided_genres: Optional[List[str]] = Field(
        default=None,
        description="Genres to avoid"
    )
    diversity: Optional[float] = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Diversity level (0=similar, 1=varied)"
    )


class RecommendRequest(BaseModel):
    """Recommendation request."""
    track_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of Spotify track IDs (1-10)"
    )
    preferences: Optional[Preferences] = Field(
        default=None,
        description="Optional filtering preferences"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of recommendations (1-50)"
    )


class TrackResponse(BaseModel):
    """Track data in response."""
    id: str
    name: str
    artist_name: str
    album_name: str
    album_image: Optional[str]
    preview_url: Optional[str]
    external_url: str
    audio_features: Optional[Dict] = None


class RecommendationResponse(BaseModel):
    """Single recommendation."""
    track: TrackResponse
    score: float
    reasoning: List[str]


class RecommendResponse(BaseModel):
    """Full recommendation response."""
    recommendations: List[RecommendationResponse]
    centroid: Dict[str, float]
    request_id: str
    processing_time_ms: int


# ============== API Endpoints ==============

@app.get("/")
async def root():
    """Serve the demo UI."""
    index_path = os.path.join(static_dir, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "NextTrack API is running. See /docs for API documentation."}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": app.version,
        "spotify_configured": spotify_client is not None,
        "engine_ready": recommendation_engine is not None,
        "cache_enabled": cache.is_enabled
    }


@app.get("/api/search")
async def search_tracks(
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    limit: int = Query(default=10, ge=1, le=50, description="Max results")
):
    """
    Search for tracks by name, artist, or album.

    This is a pass-through to Spotify's search API.
    No user data is stored.
    """
    if not spotify_client:
        raise HTTPException(503, "Spotify client not configured")

    try:
        tracks = await spotify_client.search_tracks(q, limit=limit)
        return {
            "query": q,
            "results": [t.to_dict() for t in tracks]
        }
    except Exception as e:
        msg = str(e)
        if "403" in msg or "premium" in msg.lower() or "subscription" in msg.lower():
            raise HTTPException(503, "Spotify API access denied. This usually means the Spotify account linked to this app requires an active Premium subscription.")
        raise HTTPException(500, f"Search failed: {msg}")


@app.get("/api/track/{track_id}")
async def get_track(track_id: str):
    """
    Get track details by Spotify ID.

    Returns metadata only - no audio features due to Spotify API deprecation.
    Use /api/track/{id}/similar for track similarity via Last.fm.
    """
    if not spotify_client:
        raise HTTPException(503, "Spotify client not configured")

    try:
        track = await spotify_client.get_track(track_id)
        return track.to_dict()
    except Exception as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))


@app.post("/api/recommend")
async def get_recommendations(request: RecommendRequest):
    """
    Get personalized track recommendations.

    This is the core NextTrack endpoint. It analyzes the provided tracks
    and returns similar recommendations WITHOUT storing any user data.

    The system is completely stateless - each request is independent.

    Note: Audio features from Spotify are deprecated (late 2024).
    Recommendations use artist/genre similarity, collaborative filtering
    via Last.fm, and Spotify's recommendation algorithm.
    """
    if not recommendation_engine:
        raise HTTPException(503, "Recommendation engine not configured")

    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    try:
        # Convert preferences to dict
        prefs = None
        if request.preferences:
            prefs = {}
            if request.preferences.energy_range:
                prefs['energy_range'] = request.preferences.energy_range
            if request.preferences.tempo_range:
                prefs['tempo_range'] = request.preferences.tempo_range
            if request.preferences.valence_range:
                prefs['valence_range'] = request.preferences.valence_range
            if request.preferences.danceability_range:
                prefs['danceability_range'] = request.preferences.danceability_range

        # Get recommendations
        recommendations, centroid = await recommendation_engine.recommend(
            request.track_ids,
            preferences=prefs,
            limit=request.limit
        )

        processing_time = int((time.time() - start_time) * 1000)

        return RecommendResponse(
            recommendations=[
                RecommendationResponse(
                    track=TrackResponse(
                        id=rec.track.id,
                        name=rec.track.name,
                        artist_name=rec.track.artist_name,
                        album_name=rec.track.album_name,
                        album_image=rec.track.album_image,
                        preview_url=rec.track.preview_url,
                        external_url=rec.track.external_url,
                        audio_features=rec.track.audio_features.to_dict() if rec.track.audio_features else None
                    ),
                    # Handle both Recommendation (score) and EnhancedRecommendation (final_score)
                    score=round(getattr(rec, 'final_score', getattr(rec, 'score', 0.0)), 3),
                    reasoning=rec.reasoning
                )
                for rec in recommendations
            ],
            centroid={k: round(v, 3) for k, v in centroid.items()},
            request_id=request_id,
            processing_time_ms=processing_time
        )

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        msg = str(e)
        if "403" in msg or "premium" in msg.lower() or "subscription" in msg.lower():
            raise HTTPException(503, "Spotify API access denied. This usually means the Spotify account linked to this app requires an active Premium subscription.")
        raise HTTPException(500, f"Recommendation failed: {msg}")


class AnalyzeRequest(BaseModel):
    """Request for session analysis."""
    track_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of Spotify track IDs to analyze"
    )


@app.post("/api/analyze")
async def analyze_session(request: AnalyzeRequest):
    """
    Analyze patterns in a listening session.
    Returns trends in energy, mood, tempo, etc.

    Note: Due to Spotify API deprecation, analysis uses
    Last.fm tags and genre inference instead of audio features.
    """
    if not recommendation_engine:
        raise HTTPException(503, "Recommendation engine not configured")

    try:
        tracks = await spotify_client.get_tracks_with_features(request.track_ids)
        analysis = recommendation_engine.analyze_session(tracks)

        return {
            "track_count": len(tracks),
            "analysis": analysis
        }
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@app.get("/api/cache/stats")
async def cache_stats():
    """
    Get cache statistics.
    Shows hit/miss rates and backend status.
    """
    stats = await cache.get_stats()
    return stats


@app.post("/api/cache/clear")
async def clear_cache(pattern: Optional[str] = None):
    """
    Clear cached data.
    Optional pattern parameter to clear specific keys (e.g., 'search:*').
    """
    count = await cache.clear(pattern)
    return {"cleared": count, "pattern": pattern or "*"}


@app.get("/api/track/{track_id}/context")
async def get_track_context(track_id: str):
    """
    Get extended track context from Genius.com.
    Returns song description, tags, and cultural context when available.
    """
    if not spotify_client:
        raise HTTPException(503, "Spotify client not configured")

    if not genius_client or not genius_client.is_configured:
        raise HTTPException(503, "Genius client not configured. Set GENIUS_ACCESS_TOKEN.")

    try:
        # Get track info first
        tracks = await spotify_client.get_tracks_with_features([track_id])
        if not tracks:
            raise HTTPException(404, "Track not found")

        track = tracks[0]

        # Get Genius context
        context = await genius_client.get_song_context(track.name, track.artist_name)

        return {
            "track": {
                "id": track.id,
                "name": track.name,
                "artist_name": track.artist_name
            },
            "genius_context": context
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get track context: {str(e)}")


@app.get("/api/track/{track_id}/similar")
async def get_similar_tracks(
    track_id: str,
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Get similar tracks using Last.fm's collaborative filtering.

    This uses Last.fm's "listeners who liked this also liked" data
    which is often more accurate than audio feature similarity.
    """
    if not spotify_client:
        raise HTTPException(503, "Spotify client not configured")

    if not lastfm_client:
        raise HTTPException(503, "Last.fm not configured - set LASTFM_API_KEY")

    try:
        # Get track info from Spotify
        tracks = await spotify_client.get_tracks([track_id])
        if not tracks:
            raise HTTPException(404, "Track not found")

        track = tracks[0]

        # Get similar tracks from Last.fm
        similar = await lastfm_client.get_similar_tracks(
            track_name=track.name,
            artist_name=track.artist_name,
            limit=limit
        )

        # Also get tags for the track
        tags = await lastfm_client.get_track_tags(track.name, track.artist_name)

        # Estimate audio features from tags
        estimated_features = lastfm_client.estimate_audio_features_from_tags(tags)

        return {
            "track": {
                "id": track.id,
                "name": track.name,
                "artist": track.artist_name
            },
            "tags": tags.tags,
            "estimated_features": estimated_features,
            "similar_tracks": [
                {
                    "name": s.name,
                    "artist": s.artist,
                    "match_score": round(s.match_score, 3),
                    "url": s.url
                }
                for s in similar
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get similar tracks: {str(e)}")


@app.get("/api/external-sources")
async def external_sources_status():
    """
    Check status of all external data sources.
    Useful for debugging and monitoring.
    """
    return {
        "spotify": {
            "configured": spotify_client is not None,
            "description": "Track search, metadata, recommendations"
        },
        "musicbrainz": {
            "configured": musicbrainz_client is not None,
            "description": "Genre tags, open metadata"
        },
        "wikidata": {
            "configured": wikidata_client is not None,
            "description": "Artist relationships, cultural context"
        },
        "genius": {
            "configured": genius_client is not None and genius_client.is_configured,
            "description": "Song descriptions, lyrics context"
        },
        "lastfm": {
            "configured": lastfm_client is not None,
            "description": "Track similarity, collaborative filtering tags"
        },
        "cache": {
            "enabled": cache.is_enabled,
            "backend": "redis" if cache.is_enabled else "in-memory"
        }
    }


# ============== Run Server ==============

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
