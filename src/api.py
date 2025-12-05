"""
NextTrack API - FastAPI Application
Feature Prototype Implementation

This module implements the REST API endpoints for the NextTrack
music recommendation service.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import time
import uuid

# Initialize FastAPI app
app = FastAPI(
    title="NextTrack API",
    description="Privacy-focused music recommendation API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for web client access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models

class TrackInput(BaseModel):
    """Input track identifier."""
    track_id: str = Field(..., description="Spotify track ID or URI")
    source: str = Field(default="spotify", description="Data source identifier")


class Preferences(BaseModel):
    """User preference parameters for recommendation tuning."""
    similarity_weight: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="Weight for audio similarity (0-1)"
    )
    diversity_weight: float = Field(
        default=0.3, ge=0.0, le=1.0,
        description="Weight for diversity injection (0-1)"
    )
    energy_range: Optional[List[float]] = Field(
        default=None,
        description="Acceptable energy range [min, max] (0-1)"
    )
    tempo_range: Optional[List[float]] = Field(
        default=None,
        description="Acceptable tempo range [min, max] in BPM"
    )
    valence_range: Optional[List[float]] = Field(
        default=None,
        description="Acceptable valence/mood range [min, max] (0-1)"
    )
    exclude_artists: List[str] = Field(
        default=[],
        description="Artist IDs to exclude from recommendations"
    )
    preferred_genres: List[str] = Field(
        default=[],
        description="Preferred genres to prioritize"
    )


class RecommendRequest(BaseModel):
    """Request body for recommendation endpoint."""
    track_history: List[TrackInput] = Field(
        ..., min_length=1, max_length=50,
        description="List of recently played tracks (most recent last)"
    )
    preferences: Preferences = Field(
        default_factory=Preferences,
        description="Recommendation preference parameters"
    )
    limit: int = Field(
        default=5, ge=1, le=20,
        description="Number of recommendations to return"
    )


class RecommendedTrack(BaseModel):
    """A single recommended track."""
    track_id: str
    track_name: str
    artist_name: str
    album_name: str
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence score for this recommendation"
    )
    reasoning: List[str] = Field(
        ..., description="Factors contributing to this recommendation"
    )
    preview_url: Optional[str] = Field(
        default=None,
        description="URL for 30-second audio preview"
    )


class RecommendResponse(BaseModel):
    """Response from recommendation endpoint."""
    recommendations: List[RecommendedTrack]
    request_id: str = Field(..., description="Unique identifier for this request")
    processing_time_ms: int = Field(
        ..., description="Time taken to process request in milliseconds"
    )
    centroid_features: Optional[Dict[str, float]] = Field(
        default=None,
        description="Computed feature centroid (for debugging)"
    )


class TrackInfo(BaseModel):
    """Detailed track information."""
    track_id: str
    track_name: str
    artist_name: str
    artist_id: str
    album_name: str
    duration_ms: int
    popularity: int
    audio_features: Optional[Dict[str, float]] = None
    genres: List[str] = []


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    services: Dict[str, str]


class StatsResponse(BaseModel):
    """Anonymous usage statistics."""
    total_requests: int
    average_response_time_ms: float
    cache_hit_rate: float
    uptime_seconds: int


# In-memory stats for prototype (use Redis in production)
stats = {
    "total_requests": 0,
    "total_response_time": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "start_time": time.time()
}


# API Endpoints

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect to documentation."""
    return {"message": "NextTrack API", "docs": "/docs"}


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """
    Check API and external service health.

    Returns status of the API and connected services.
    """
    # In production, actually check external service connectivity
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        services={
            "spotify": "connected",
            "musicbrainz": "connected",
            "cache": "connected"
        }
    )


@app.get("/api/v1/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get anonymous usage statistics.

    Returns aggregate statistics without any user-identifying information.
    """
    uptime = int(time.time() - stats["start_time"])
    avg_response = 0
    if stats["total_requests"] > 0:
        avg_response = stats["total_response_time"] / stats["total_requests"]

    total_cache = stats["cache_hits"] + stats["cache_misses"]
    cache_rate = stats["cache_hits"] / total_cache if total_cache > 0 else 0

    return StatsResponse(
        total_requests=stats["total_requests"],
        average_response_time_ms=avg_response,
        cache_hit_rate=cache_rate,
        uptime_seconds=uptime
    )


@app.post("/api/v1/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest):
    """
    Generate track recommendations based on listening history.

    This endpoint accepts a sequence of recently played tracks and
    preference parameters, returning intelligent next-track suggestions.

    The system is completely stateless - no user data is stored between
    requests.

    **Parameters:**
    - **track_history**: List of recently played track IDs (1-50 tracks)
    - **preferences**: Optional tuning parameters for recommendations
    - **limit**: Number of recommendations to return (1-20)

    **Returns:**
    - List of recommended tracks with confidence scores and reasoning
    - Processing time and request ID for debugging
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())

    try:
        # Extract track IDs
        track_ids = [t.track_id for t in request.track_history]

        # In production, this would:
        # 1. Fetch track details and audio features from Spotify
        # 2. Compute feature centroid
        # 3. Generate candidates from related artists/genres
        # 4. Score candidates and return top results

        # For prototype, return mock recommendations
        # demonstrating the response format
        recommendations = generate_mock_recommendations(
            track_ids,
            request.preferences,
            request.limit
        )

        processing_time = int((time.time() - start_time) * 1000)

        # Update stats
        stats["total_requests"] += 1
        stats["total_response_time"] += processing_time

        return RecommendResponse(
            recommendations=recommendations,
            request_id=request_id,
            processing_time_ms=processing_time,
            centroid_features={
                "energy": 0.72,
                "valence": 0.65,
                "danceability": 0.78,
                "tempo": 0.58,
                "acousticness": 0.18
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/track/{track_id}", response_model=TrackInfo)
async def get_track(track_id: str):
    """
    Get detailed information about a specific track.

    Returns track metadata and audio features for display and debugging.
    """
    # In production, fetch from Spotify API with caching
    # For prototype, return mock data
    return TrackInfo(
        track_id=track_id,
        track_name="Example Track",
        artist_name="Example Artist",
        artist_id="artist123",
        album_name="Example Album",
        duration_ms=210000,
        popularity=75,
        audio_features={
            "acousticness": 0.15,
            "danceability": 0.72,
            "energy": 0.78,
            "instrumentalness": 0.0,
            "liveness": 0.12,
            "loudness": -5.2,
            "speechiness": 0.04,
            "tempo": 128.0,
            "valence": 0.65
        },
        genres=["pop", "dance"]
    )


@app.get("/api/v1/search")
async def search_tracks(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=10, ge=1, le=50, description="Result limit")
):
    """
    Search for tracks by name, artist, or album.

    This endpoint enables finding track IDs to use with the recommendation
    endpoint.
    """
    # In production, search via Spotify API
    # For prototype, return mock results
    return {
        "results": [
            {
                "track_id": f"track_{i}",
                "track_name": f"Search Result {i}",
                "artist_name": f"Artist {i}",
                "album_name": f"Album {i}"
            }
            for i in range(min(limit, 5))
        ],
        "total": 5,
        "query": q
    }


def generate_mock_recommendations(
    track_ids: List[str],
    preferences: Preferences,
    limit: int
) -> List[RecommendedTrack]:
    """
    Generate mock recommendations for prototype demonstration.

    In production, this would be replaced by actual recommendation logic
    using the RecommendationEngine class.
    """
    mock_tracks = [
        ("0c6xIDDpzE81m2q797ordA", "Blinding Lights", "The Weeknd", "After Hours"),
        ("7qiZfU4dY1lWllzX7mPBI3", "Shape of You", "Ed Sheeran", "÷"),
        ("2Fxmhks0bxGSBdJ92vM42m", "bad guy", "Billie Eilish", "WHEN WE ALL FALL ASLEEP"),
        ("6habFhsOp2NvshLv26DqMb", "Levitating", "Dua Lipa", "Future Nostalgia"),
        ("5QO79kh1waicV47BqGRL3g", "Save Your Tears", "The Weeknd", "After Hours"),
        ("3Ofmpyhv5UAQ70mENzB277", "Peaches", "Justin Bieber", "Justice"),
        ("6Im9k8u9iIzKMrmV7BWtlF", "34+35", "Ariana Grande", "Positions"),
        ("4iJyoBOLtHqaGxP12qzhQI", "Peaches", "Jack Black", "Bowser"),
    ]

    recommendations = []
    for i in range(min(limit, len(mock_tracks))):
        track_id, name, artist, album = mock_tracks[i]

        # Vary confidence based on position
        confidence = 0.95 - (i * 0.08)

        # Generate reasoning
        reasoning = ["audio_similarity"]
        if i % 2 == 0:
            reasoning.append("genre_match")
        if i % 3 == 0:
            reasoning.append("artist_relation")

        recommendations.append(RecommendedTrack(
            track_id=track_id,
            track_name=name,
            artist_name=artist,
            album_name=album,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            preview_url=f"https://p.scdn.co/mp3-preview/{track_id[:22]}"
        ))

    return recommendations


# Run with: uvicorn api:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
