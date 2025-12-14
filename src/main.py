"""
NextTrack API - Main Application
Privacy-focused music recommendation API with FastAPI.
"""

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from spotify_client import SpotifyClient
from engine import RecommendationEngine


# Global instances
spotify_client: Optional[SpotifyClient] = None
recommendation_engine: Optional[RecommendationEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global spotify_client, recommendation_engine

    # Get credentials from environment
    client_id = os.environ.get('SPOTIFY_CLIENT_ID', '')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
    market = os.environ.get('SPOTIFY_MARKET', 'US')

    if client_id and client_secret:
        spotify_client = SpotifyClient(client_id, client_secret, market=market)
        recommendation_engine = RecommendationEngine(spotify_client)
        print("✓ Spotify client initialized")
    else:
        print("⚠ Warning: Spotify credentials not set. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET")

    yield

    # Cleanup
    if spotify_client:
        await spotify_client.close()


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
        description="Energy range [min, max] from 0-1"
    )
    tempo_range: Optional[List[float]] = Field(
        default=None,
        description="Tempo range [min, max] in BPM"
    )
    valence_range: Optional[List[float]] = Field(
        default=None,
        description="Mood/valence range [min, max] from 0-1"
    )
    danceability_range: Optional[List[float]] = Field(
        default=None,
        description="Danceability range [min, max] from 0-1"
    )


class RecommendRequest(BaseModel):
    """Request for track recommendations."""
    track_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of Spotify track IDs (recent listening history)"
    )
    preferences: Optional[Preferences] = Field(
        default=None,
        description="Optional preference filters"
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of recommendations"
    )


class TrackResponse(BaseModel):
    """Track information in response."""
    id: str
    name: str
    artist_name: str
    album_name: str
    album_image: Optional[str]
    preview_url: Optional[str]
    external_url: str
    audio_features: Optional[Dict[str, float]]


class RecommendationResponse(BaseModel):
    """A single recommendation."""
    track: TrackResponse
    score: float = Field(..., description="Confidence score 0-1")
    reasoning: List[str] = Field(..., description="Why this was recommended")


class RecommendResponse(BaseModel):
    """Full recommendation response."""
    recommendations: List[RecommendationResponse]
    centroid: Dict[str, float] = Field(..., description="Computed feature profile")
    request_id: str
    processing_time_ms: int


class SearchResponse(BaseModel):
    """Search results."""
    tracks: List[TrackResponse]
    query: str
    total: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    spotify_connected: bool
    version: str


# ============== API Endpoints ==============

@app.get("/")
async def root():
    """Serve the demo UI."""
    index_path = os.path.join(static_dir, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "NextTrack API", "docs": "/docs"}


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check API health status."""
    return HealthResponse(
        status="healthy",
        spotify_connected=spotify_client is not None,
        version="1.0.0"
    )


@app.get("/api/search", response_model=SearchResponse)
async def search_tracks(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Search for tracks on Spotify.
    Use this to find track IDs for the recommendation endpoint.
    """
    if not spotify_client:
        raise HTTPException(503, "Spotify client not configured")

    try:
        tracks = await spotify_client.search_tracks(q, limit)

        return SearchResponse(
            tracks=[
                TrackResponse(
                    id=t.id,
                    name=t.name,
                    artist_name=t.artist_name,
                    album_name=t.album_name,
                    album_image=t.album_image,
                    preview_url=t.preview_url,
                    external_url=t.external_url,
                    audio_features=None
                )
                for t in tracks
            ],
            query=q,
            total=len(tracks)
        )
    except Exception as e:
        raise HTTPException(500, f"Search failed: {str(e)}")


@app.get("/api/track/{track_id}")
async def get_track(track_id: str):
    """Get detailed track information including audio features."""
    if not spotify_client:
        raise HTTPException(503, "Spotify client not configured")

    try:
        tracks = await spotify_client.get_tracks_with_features([track_id])
        if not tracks:
            raise HTTPException(404, "Track not found")

        track = tracks[0]
        return {
            "id": track.id,
            "name": track.name,
            "artist_name": track.artist_name,
            "album_name": track.album_name,
            "album_image": track.album_image,
            "preview_url": track.preview_url,
            "external_url": track.external_url,
            "popularity": track.popularity,
            "duration_ms": track.duration_ms,
            "audio_features": track.audio_features.to_dict() if track.audio_features else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get track: {str(e)}")


@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest):
    """
    Get track recommendations based on listening history.

    This is the core NextTrack endpoint. It analyzes the provided tracks
    and returns similar recommendations WITHOUT storing any user data.

    The system is completely stateless - each request is independent.
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
                    score=round(rec.score, 3),
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
        raise HTTPException(500, f"Recommendation failed: {str(e)}")


@app.post("/api/analyze")
async def analyze_session(track_ids: List[str]):
    """
    Analyze patterns in a listening session.
    Returns trends in energy, mood, tempo, etc.
    """
    if not recommendation_engine:
        raise HTTPException(503, "Recommendation engine not configured")

    try:
        tracks = await spotify_client.get_tracks_with_features(track_ids)
        analysis = recommendation_engine.analyze_session(tracks)

        return {
            "track_count": len(tracks),
            "analysis": analysis
        }
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


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
