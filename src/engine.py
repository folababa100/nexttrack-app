"""
NextTrack Recommendation Engine
Core recommendation algorithms using audio feature similarity.
"""

import math
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from spotify_client import Track, AudioFeatures


@dataclass
class Recommendation:
    """A recommended track with score and reasoning."""
    track: Track
    score: float
    reasoning: List[str] = field(default_factory=list)
    feature_scores: Dict[str, float] = field(default_factory=dict)


class AudioFeatureSimilarity:
    """
    Computes similarity between tracks based on audio features.
    Uses weighted Euclidean distance with configurable feature weights.
    """

    # Default feature weights - higher = more important
    DEFAULT_WEIGHTS = {
        'energy': 1.0,
        'valence': 0.9,
        'danceability': 0.85,
        'tempo': 0.7,
        'acousticness': 0.6,
        'instrumentalness': 0.5,
        'speechiness': 0.4,
        'liveness': 0.3
    }

    # Normalization ranges for features not already in [0,1]
    NORMALIZATION = {
        'tempo': (50.0, 200.0),
        'loudness': (-60.0, 0.0),
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

    def normalize(self, feature: str, value: float) -> float:
        """Normalize a feature value to [0, 1] range."""
        if feature in self.NORMALIZATION:
            min_val, max_val = self.NORMALIZATION[feature]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0.0, min(1.0, normalized))
        return value

    def compute_centroid(
        self,
        tracks: List[Track],
        recency_weight: float = 0.7
    ) -> Dict[str, float]:
        """
        Compute the weighted centroid of audio features.
        More recent tracks (later in list) get higher weights.

        Returns default centroid (0.5 for all features) if no features available.
        """
        tracks_with_features = [t for t in tracks if t.audio_features]
        if not tracks_with_features:
            # Return default centroid when no audio features available
            # (e.g., when using Client Credentials without audio-features access)
            return {feature: 0.5 for feature in self.weights.keys()}

        n = len(tracks_with_features)

        # Compute recency weights - newer tracks get higher weight
        weights = []
        for i in range(n):
            w = recency_weight ** (n - 1 - i)
            weights.append(w)

        # Normalize weights
        total = sum(weights)
        weights = [w / total for w in weights]

        centroid = {}
        for feature in self.weights.keys():
            values = []
            for track in tracks_with_features:
                raw = getattr(track.audio_features, feature, 0.0)
                normalized = self.normalize(feature, raw)
                values.append(normalized)

            # Weighted average
            weighted_sum = sum(v * w for v, w in zip(values, weights))
            centroid[feature] = weighted_sum

        return centroid

    def compute_similarity(
        self,
        track: Track,
        centroid: Dict[str, float]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute similarity between a track and a feature centroid.
        Returns (similarity_score, per_feature_scores).
        """
        if not track.audio_features:
            return 0.0, {}

        feature_scores = {}
        weighted_distance_sq = 0.0
        total_weight = 0.0

        for feature, weight in self.weights.items():
            raw = getattr(track.audio_features, feature, 0.0)
            normalized = self.normalize(feature, raw)

            diff = abs(normalized - centroid.get(feature, 0.5))
            feature_scores[feature] = 1.0 - diff  # Per-feature similarity

            weighted_distance_sq += weight * (diff ** 2)
            total_weight += weight

        # Weighted Euclidean distance
        distance = math.sqrt(weighted_distance_sq / total_weight)
        similarity = 1.0 - distance

        return max(0.0, min(1.0, similarity)), feature_scores

    def rank_candidates(
        self,
        candidates: List[Track],
        centroid: Dict[str, float],
        preferences: Optional[Dict] = None
    ) -> List[Recommendation]:
        """
        Rank candidate tracks by similarity to centroid.

        If candidates lack audio features (Client Credentials mode),
        returns them in Spotify's original recommendation order.
        """
        recommendations = []
        has_any_features = any(t.audio_features for t in candidates)

        for i, track in enumerate(candidates):
            # When no features available, use position-based scoring
            if not track.audio_features:
                if has_any_features:
                    # Skip tracks without features if some have them
                    continue
                # Use decreasing score based on Spotify's order
                score = max(0.5, 1.0 - (i * 0.03))
                recommendations.append(Recommendation(
                    track=track,
                    score=score,
                    reasoning=["spotify_recommendation"],
                    feature_scores={}
                ))
                continue

            # Apply preference filters
            if preferences and not self._passes_filters(track, preferences):
                continue

            score, feature_scores = self.compute_similarity(track, centroid)

            # Generate reasoning
            reasoning = self._generate_reasoning(feature_scores)

            recommendations.append(Recommendation(
                track=track,
                score=score,
                reasoning=reasoning,
                feature_scores=feature_scores
            ))

        # Sort by score descending
        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations

    def _passes_filters(self, track: Track, preferences: Dict) -> bool:
        """Check if track passes preference filters."""
        af = track.audio_features
        if not af:
            return False

        # Energy filter
        if 'energy_range' in preferences:
            min_e, max_e = preferences['energy_range']
            if not (min_e <= af.energy <= max_e):
                return False

        # Tempo filter
        if 'tempo_range' in preferences:
            min_t, max_t = preferences['tempo_range']
            if not (min_t <= af.tempo <= max_t):
                return False

        # Valence filter
        if 'valence_range' in preferences:
            min_v, max_v = preferences['valence_range']
            if not (min_v <= af.valence <= max_v):
                return False

        # Danceability filter
        if 'danceability_range' in preferences:
            min_d, max_d = preferences['danceability_range']
            if not (min_d <= af.danceability <= max_d):
                return False

        return True

    def _generate_reasoning(self, feature_scores: Dict[str, float]) -> List[str]:
        """Generate human-readable reasoning from feature scores."""
        reasoning = []

        # Sort by score (highest first)
        sorted_features = sorted(
            feature_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        for feature, score in sorted_features[:3]:
            if score >= 0.9:
                reasoning.append(f"strong_{feature}_match")
            elif score >= 0.75:
                reasoning.append(f"{feature}_similar")

        if not reasoning:
            reasoning.append("general_similarity")

        return reasoning


class RecommendationEngine:
    """
    Main recommendation engine that combines multiple strategies.
    """

    def __init__(self, spotify_client):
        self.spotify = spotify_client
        self.similarity = AudioFeatureSimilarity()

    async def recommend(
        self,
        input_track_ids: List[str],
        preferences: Optional[Dict] = None,
        limit: int = 10
    ) -> Tuple[List[Recommendation], Dict[str, float]]:
        """
        Generate recommendations based on input tracks.

        Returns:
            Tuple of (recommendations, centroid_features)
        """
        # Get input tracks with audio features
        input_tracks = await self.spotify.get_tracks_with_features(input_track_ids)

        if not input_tracks:
            raise ValueError("No valid input tracks found")

        # Compute feature centroid
        centroid = self.similarity.compute_centroid(input_tracks)

        # Generate candidates using Spotify's recommendation engine
        candidates = await self._generate_candidates(
            input_tracks, centroid, preferences, limit * 3
        )

        # Get audio features for candidates
        candidate_ids = [t.id for t in candidates]
        features = await self.spotify.get_audio_features(candidate_ids)

        for track in candidates:
            track.audio_features = features.get(track.id)

        # Filter out input tracks from candidates
        input_ids = set(t.id for t in input_tracks)
        candidates = [t for t in candidates if t.id not in input_ids]

        # Rank candidates by similarity
        recommendations = self.similarity.rank_candidates(
            candidates, centroid, preferences
        )

        return recommendations[:limit], centroid

    async def _generate_candidates(
        self,
        input_tracks: List[Track],
        centroid: Dict[str, float],
        preferences: Optional[Dict],
        limit: int
    ) -> List[Track]:
        """
        Generate candidate tracks using search-based discovery.

        Since Spotify deprecated /recommendations and /related-artists for
        Client Credentials flow (late 2024), we use artist-based search
        to find similar tracks.
        """
        candidates = []
        seen_ids = set(t.id for t in input_tracks)  # Exclude input tracks

        # Get unique artists from input tracks
        artists = []
        seen_artists = set()
        for track in input_tracks:
            if track.artist_name and track.artist_name not in seen_artists:
                artists.append(track.artist_name)
                seen_artists.add(track.artist_name)

        # Search for more tracks by each artist
        for artist_name in artists[:5]:  # Limit to 5 artists
            try:
                # Search for tracks by this artist
                search_results = await self.spotify.search_tracks(
                    f'artist:"{artist_name}"',
                    limit=20
                )

                for track in search_results:
                    if track.id not in seen_ids:
                        candidates.append(track)
                        seen_ids.add(track.id)

                        if len(candidates) >= limit:
                            break

            except Exception as e:
                print(f"Error searching for artist '{artist_name}': {e}")

            if len(candidates) >= limit:
                break

        # If still need more, search by genre keywords from track/album names
        if len(candidates) < limit:
            # Extract keywords from track names
            keywords = set()
            for track in input_tracks[:3]:
                # Use artist name variations for discovery
                words = track.artist_name.split()
                if len(words) > 1:
                    keywords.add(words[0])  # First name

            for keyword in list(keywords)[:3]:
                try:
                    search_results = await self.spotify.search_tracks(keyword, limit=10)
                    for track in search_results:
                        if track.id not in seen_ids:
                            candidates.append(track)
                            seen_ids.add(track.id)

                            if len(candidates) >= limit:
                                break
                except Exception as e:
                    print(f"Error searching for '{keyword}': {e}")

                if len(candidates) >= limit:
                    break

        return candidates[:limit]

    def analyze_session(self, tracks: List[Track]) -> Dict:
        """
        Analyze patterns in a listening session.
        Useful for understanding the trajectory of the session.
        """
        if len(tracks) < 2:
            return {'status': 'insufficient_data'}

        tracks_with_features = [t for t in tracks if t.audio_features]
        if len(tracks_with_features) < 2:
            return {'status': 'insufficient_features'}

        analysis = {}

        for feature in ['energy', 'valence', 'tempo', 'danceability']:
            values = []
            for t in tracks_with_features:
                val = getattr(t.audio_features, feature, None)
                if val is not None:
                    if feature == 'tempo':
                        val = self.similarity.normalize('tempo', val)
                    values.append(val)

            if len(values) >= 2:
                # Calculate trend (simple linear regression slope)
                n = len(values)
                x_mean = (n - 1) / 2
                y_mean = sum(values) / n

                numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
                denominator = sum((i - x_mean) ** 2 for i in range(n))

                slope = numerator / denominator if denominator != 0 else 0

                if slope > 0.05:
                    analysis[f'{feature}_trend'] = 'increasing'
                elif slope < -0.05:
                    analysis[f'{feature}_trend'] = 'decreasing'
                else:
                    analysis[f'{feature}_trend'] = 'stable'

                # Variance
                variance = sum((v - y_mean) ** 2 for v in values) / n
                analysis[f'{feature}_consistency'] = 'high' if variance < 0.05 else 'low'

        return analysis
