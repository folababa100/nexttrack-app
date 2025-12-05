"""
NextTrack - Audio Feature Similarity Recommendation Engine
Feature Prototype Implementation

This module implements the core audio feature similarity algorithm
for the NextTrack privacy-focused music recommendation API.
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio


@dataclass
class AudioFeatures:
    """Audio features for a track."""
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

    def to_vector(self, features: List[str]) -> np.ndarray:
        """Convert to numpy array for specified features."""
        return np.array([getattr(self, f) for f in features])

    @classmethod
    def from_spotify_response(cls, data: Dict) -> 'AudioFeatures':
        """Create AudioFeatures from Spotify API response."""
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


@dataclass
class Track:
    """Represents a music track with metadata and audio features."""
    track_id: str
    name: str
    artist_name: str
    artist_id: str
    album_name: str
    duration_ms: int
    popularity: int
    audio_features: Optional[AudioFeatures] = None
    genres: Optional[List[str]] = None

    @classmethod
    def from_spotify_response(cls, track_data: Dict,
                               audio_features: Optional[Dict] = None) -> 'Track':
        """Create Track from Spotify API response."""
        features = None
        if audio_features:
            features = AudioFeatures.from_spotify_response(audio_features)

        return cls(
            track_id=track_data['id'],
            name=track_data['name'],
            artist_name=track_data['artists'][0]['name'],
            artist_id=track_data['artists'][0]['id'],
            album_name=track_data['album']['name'],
            duration_ms=track_data['duration_ms'],
            popularity=track_data.get('popularity', 0),
            audio_features=features
        )


@dataclass
class Recommendation:
    """A recommended track with confidence score and reasoning."""
    track: Track
    confidence: float
    reasoning: List[str]
    feature_distances: Dict[str, float]


class AudioFeatureSimilarity:
    """
    Computes audio feature-based similarity between tracks.

    This class implements the core recommendation algorithm using
    weighted Euclidean distance across normalized audio features.
    """

    # Feature weights determined through empirical testing
    # Higher weights indicate more important features for similarity
    FEATURE_WEIGHTS = {
        'energy': 1.0,
        'valence': 0.9,
        'danceability': 0.85,
        'tempo': 0.7,
        'acousticness': 0.6,
        'instrumentalness': 0.5,
        'speechiness': 0.4,
        'liveness': 0.3
    }

    # Normalization parameters for non-0-1 features
    NORMALIZATION = {
        'tempo': (50, 200),  # Typical tempo range
        'loudness': (-60, 0),  # dB range
    }

    def __init__(self, feature_weights: Optional[Dict[str, float]] = None):
        """
        Initialize the similarity calculator.

        Args:
            feature_weights: Optional custom feature weights
        """
        self.feature_weights = feature_weights or self.FEATURE_WEIGHTS
        self.features = list(self.feature_weights.keys())

    def normalize_feature(self, feature: str, value: float) -> float:
        """
        Normalize a feature value to [0, 1] range.

        Args:
            feature: Feature name
            value: Raw feature value

        Returns:
            Normalized value in [0, 1]
        """
        if feature in self.NORMALIZATION:
            min_val, max_val = self.NORMALIZATION[feature]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value  # Already in [0, 1]

    def compute_centroid(self, tracks: List[Track],
                         recency_decay: float = 0.5) -> Dict[str, float]:
        """
        Compute weighted centroid of track audio features.

        More recent tracks (later in list) receive higher weights,
        simulating a listener's current mood/preference.

        Args:
            tracks: List of tracks (most recent last)
            recency_decay: Exponential decay factor for older tracks

        Returns:
            Dictionary mapping feature names to centroid values
        """
        if not tracks:
            raise ValueError("Cannot compute centroid of empty track list")

        # Filter tracks with audio features
        tracks_with_features = [t for t in tracks if t.audio_features]
        if not tracks_with_features:
            raise ValueError("No tracks with audio features available")

        # Compute recency weights (newer = higher weight)
        n = len(tracks_with_features)
        weights = np.array([recency_decay ** (n - 1 - i) for i in range(n)])
        weights = weights / weights.sum()

        centroid = {}
        for feature in self.features:
            values = []
            for track in tracks_with_features:
                raw_value = getattr(track.audio_features, feature)
                normalized = self.normalize_feature(feature, raw_value)
                values.append(normalized)

            centroid[feature] = np.average(values, weights=weights)

        return centroid

    def compute_similarity(self, candidate: Track,
                          centroid: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        """
        Compute similarity score between a candidate track and centroid.

        Args:
            candidate: Candidate track to evaluate
            centroid: Feature centroid to compare against

        Returns:
            Tuple of (similarity_score, feature_distances)
        """
        if not candidate.audio_features:
            return 0.0, {}

        weighted_diff_sq = 0.0
        total_weight = 0.0
        feature_distances = {}

        for feature, weight in self.feature_weights.items():
            raw_value = getattr(candidate.audio_features, feature)
            normalized = self.normalize_feature(feature, raw_value)

            diff = normalized - centroid[feature]
            feature_distances[feature] = abs(diff)

            weighted_diff_sq += weight * (diff ** 2)
            total_weight += weight

        # Compute weighted Euclidean distance
        distance = np.sqrt(weighted_diff_sq / total_weight)

        # Convert distance to similarity (1 = identical, 0 = maximally different)
        similarity = 1 - distance

        return max(0, min(1, similarity)), feature_distances

    def score_candidates(self, candidates: List[Track],
                        centroid: Dict[str, float],
                        preferences: Optional[Dict] = None) -> List[Recommendation]:
        """
        Score and rank candidate tracks by similarity to centroid.

        Args:
            candidates: List of candidate tracks
            centroid: Feature centroid to compare against
            preferences: Optional preference constraints

        Returns:
            List of Recommendations sorted by confidence (descending)
        """
        recommendations = []

        for candidate in candidates:
            similarity, distances = self.compute_similarity(candidate, centroid)

            # Apply preference filtering
            if preferences and not self._passes_preferences(candidate, preferences):
                continue

            # Generate reasoning based on closest features
            reasoning = self._generate_reasoning(distances)

            recommendations.append(Recommendation(
                track=candidate,
                confidence=similarity,
                reasoning=reasoning,
                feature_distances=distances
            ))

        # Sort by confidence descending
        recommendations.sort(key=lambda r: r.confidence, reverse=True)

        return recommendations

    def _passes_preferences(self, track: Track, preferences: Dict) -> bool:
        """Check if track passes preference constraints."""
        if not track.audio_features:
            return False

        af = track.audio_features

        # Energy range filter
        if 'energy_range' in preferences:
            min_e, max_e = preferences['energy_range']
            if not (min_e <= af.energy <= max_e):
                return False

        # Tempo range filter
        if 'tempo_range' in preferences:
            min_t, max_t = preferences['tempo_range']
            if not (min_t <= af.tempo <= max_t):
                return False

        # Valence (mood) range filter
        if 'valence_range' in preferences:
            min_v, max_v = preferences['valence_range']
            if not (min_v <= af.valence <= max_v):
                return False

        return True

    def _generate_reasoning(self, distances: Dict[str, float]) -> List[str]:
        """Generate human-readable reasoning for recommendation."""
        reasoning = []

        # Sort features by distance (closest first)
        sorted_features = sorted(distances.items(), key=lambda x: x[1])

        # Take top 3 closest features as primary reasons
        for feature, distance in sorted_features[:3]:
            if distance < 0.15:
                reasoning.append(f"{feature}_match")
            elif distance < 0.25:
                reasoning.append(f"{feature}_similar")

        if not reasoning:
            reasoning.append("general_similarity")

        return reasoning


class RecommendationEngine:
    """
    Main recommendation engine combining multiple strategies.

    For the prototype, only audio feature similarity is implemented.
    Future versions will add metadata matching and diversity strategies.
    """

    def __init__(self, spotify_client=None, cache=None):
        """
        Initialize the recommendation engine.

        Args:
            spotify_client: Spotify API client
            cache: Redis cache client
        """
        self.spotify = spotify_client
        self.cache = cache
        self.audio_similarity = AudioFeatureSimilarity()

    async def recommend(self,
                       input_tracks: List[Track],
                       candidates: List[Track],
                       preferences: Optional[Dict] = None,
                       limit: int = 5) -> List[Recommendation]:
        """
        Generate recommendations based on input track sequence.

        Args:
            input_tracks: List of recently played tracks
            candidates: Pool of candidate tracks to consider
            preferences: User preference parameters
            limit: Maximum number of recommendations

        Returns:
            List of Recommendation objects
        """
        # Compute feature centroid from input tracks
        centroid = self.audio_similarity.compute_centroid(input_tracks)

        # Score all candidates
        scored = self.audio_similarity.score_candidates(
            candidates, centroid, preferences
        )

        # Return top results
        return scored[:limit]

    def analyze_sequence(self, tracks: List[Track]) -> Dict:
        """
        Analyze patterns in track sequence for context detection.

        Args:
            tracks: Sequence of tracks to analyze

        Returns:
            Dictionary of detected patterns
        """
        if len(tracks) < 2:
            return {'pattern': 'insufficient_data'}

        features_over_time = {
            'energy': [],
            'tempo': [],
            'valence': []
        }

        for track in tracks:
            if track.audio_features:
                features_over_time['energy'].append(track.audio_features.energy)
                features_over_time['tempo'].append(track.audio_features.tempo)
                features_over_time['valence'].append(track.audio_features.valence)

        patterns = {}

        for feature, values in features_over_time.items():
            if len(values) >= 2:
                # Compute trend
                trend = np.polyfit(range(len(values)), values, 1)[0]

                if trend > 0.05:
                    patterns[f'{feature}_trend'] = 'increasing'
                elif trend < -0.05:
                    patterns[f'{feature}_trend'] = 'decreasing'
                else:
                    patterns[f'{feature}_trend'] = 'stable'

                # Compute variance
                variance = np.var(values)
                patterns[f'{feature}_variance'] = 'high' if variance > 0.1 else 'low'

        return patterns


# Example usage and testing
if __name__ == "__main__":
    # Create sample tracks for testing
    sample_features_1 = AudioFeatures(
        acousticness=0.2, danceability=0.7, energy=0.8,
        instrumentalness=0.0, liveness=0.1, loudness=-5.0,
        speechiness=0.05, tempo=128.0, valence=0.6,
        key=5, mode=1, time_signature=4
    )

    sample_features_2 = AudioFeatures(
        acousticness=0.15, danceability=0.75, energy=0.85,
        instrumentalness=0.0, liveness=0.15, loudness=-4.5,
        speechiness=0.03, tempo=130.0, valence=0.65,
        key=7, mode=1, time_signature=4
    )

    candidate_features = AudioFeatures(
        acousticness=0.18, danceability=0.72, energy=0.82,
        instrumentalness=0.0, liveness=0.12, loudness=-4.8,
        speechiness=0.04, tempo=126.0, valence=0.62,
        key=5, mode=1, time_signature=4
    )

    input_track_1 = Track(
        track_id="track1", name="Upbeat Song 1",
        artist_name="Artist A", artist_id="artist1",
        album_name="Album 1", duration_ms=210000,
        popularity=75, audio_features=sample_features_1
    )

    input_track_2 = Track(
        track_id="track2", name="Upbeat Song 2",
        artist_name="Artist B", artist_id="artist2",
        album_name="Album 2", duration_ms=195000,
        popularity=82, audio_features=sample_features_2
    )

    candidate_track = Track(
        track_id="candidate1", name="Similar Vibes",
        artist_name="Artist C", artist_id="artist3",
        album_name="Album 3", duration_ms=200000,
        popularity=68, audio_features=candidate_features
    )

    # Test similarity calculation
    similarity_engine = AudioFeatureSimilarity()

    # Compute centroid
    input_tracks = [input_track_1, input_track_2]
    centroid = similarity_engine.compute_centroid(input_tracks)
    print("Centroid features:")
    for feature, value in centroid.items():
        print(f"  {feature}: {value:.3f}")

    # Score candidate
    recommendations = similarity_engine.score_candidates(
        [candidate_track], centroid
    )

    if recommendations:
        rec = recommendations[0]
        print(f"\nRecommendation: {rec.track.name} by {rec.track.artist_name}")
        print(f"Confidence: {rec.confidence:.2%}")
        print(f"Reasoning: {', '.join(rec.reasoning)}")
