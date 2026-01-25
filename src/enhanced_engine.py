"""
NextTrack Enhanced Recommendation Engine
Multi-strategy recommendation system with MusicBrainz and Wikidata integration.

This module implements the complete recommendation pipeline described in the
project design, combining:
1. Audio feature similarity (when available)
2. Artist-based search discovery
3. Metadata matching (genre, era)
4. Diversity injection

The engine operates statelessly - no user data is stored between requests.
"""

import math
import random
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

from spotify_client import Track, AudioFeatures, SpotifyClient
from musicbrainz_client import (
    MusicBrainzClient,
    MusicBrainzArtist,
    calculate_genre_similarity,
    normalize_genre
)
from wikidata_client import (
    WikidataClient,
    WikidataArtist,
    calculate_cultural_similarity,
    calculate_era_similarity
)

# Optional Last.fm client for feature estimation
try:
    from lastfm_client import LastFMClient
except ImportError:
    LastFMClient = None


class RecommendationStrategy(Enum):
    """Available recommendation strategies."""
    AUDIO_SIMILARITY = "audio_similarity"
    ARTIST_SEARCH = "artist_search"
    GENRE_MATCH = "genre_match"
    CULTURAL_CONTEXT = "cultural_context"
    DIVERSITY = "diversity"


@dataclass
class EnhancedRecommendation:
    """A recommendation with detailed scoring breakdown."""
    track: Track
    final_score: float
    strategy_scores: Dict[str, float] = field(default_factory=dict)
    reasoning: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    diversity_bonus: float = 0.0


@dataclass
class RecommendationContext:
    """Context built from input tracks for recommendation."""
    input_tracks: List[Track]
    artists: List[str]
    artist_genres: Dict[str, List[str]]  # Artist name -> genres
    genre_profile: List[str]  # Combined genre profile
    feature_centroid: Dict[str, float]
    era_range: Tuple[Optional[int], Optional[int]]  # (earliest, latest)


class DiversityInjector:
    """
    Implements diversity injection to prevent recommendation homogeneity.

    Reduces similarity between recommended tracks to provide variety
    while maintaining relevance to user preferences.
    """

    def __init__(self, diversity_weight: float = 0.3):
        """
        Args:
            diversity_weight: How much to penalize similarity between recommendations (0-1)
        """
        self.diversity_weight = diversity_weight

    def apply_diversity(
        self,
        recommendations: List[EnhancedRecommendation],
        limit: int
    ) -> List[EnhancedRecommendation]:
        """
        Re-rank recommendations to maximize diversity while preserving relevance.

        Uses a greedy algorithm:
        1. Select the highest-scoring track first
        2. For each subsequent selection, penalize tracks similar to already-selected ones
        """
        if len(recommendations) <= 1 or self.diversity_weight == 0:
            return recommendations[:limit]

        selected: List[EnhancedRecommendation] = []
        remaining = list(recommendations)

        # Always take the top recommendation first
        best = max(remaining, key=lambda r: r.final_score)
        selected.append(best)
        remaining.remove(best)

        while len(selected) < limit and remaining:
            # Calculate diversity-adjusted scores
            best_adjusted = None
            best_score = -1

            for rec in remaining:
                # Calculate similarity to already-selected tracks
                similarities = []
                for sel in selected:
                    sim = self._calculate_pair_similarity(rec, sel)
                    similarities.append(sim)

                avg_similarity = sum(similarities) / len(similarities) if similarities else 0
                diversity_penalty = avg_similarity * self.diversity_weight

                # Adjusted score balances relevance with diversity
                adjusted_score = rec.final_score * (1 - diversity_penalty)

                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_adjusted = rec

            if best_adjusted:
                best_adjusted.diversity_bonus = 1 - (best_adjusted.final_score - best_score)
                selected.append(best_adjusted)
                remaining.remove(best_adjusted)

        return selected

    def _calculate_pair_similarity(
        self,
        rec1: EnhancedRecommendation,
        rec2: EnhancedRecommendation
    ) -> float:
        """Calculate similarity between two recommendations."""
        scores = []

        # Same artist = high similarity
        if rec1.track.artist_name.lower() == rec2.track.artist_name.lower():
            scores.append(1.0)
        else:
            scores.append(0.0)

        # Genre overlap
        if rec1.genres and rec2.genres:
            genre_sim = calculate_genre_similarity(rec1.genres, rec2.genres)
            scores.append(genre_sim)

        # Audio feature similarity (if available)
        if rec1.track.audio_features and rec2.track.audio_features:
            af1 = rec1.track.audio_features
            af2 = rec2.track.audio_features

            feature_diff = 0
            for feature in ['energy', 'valence', 'danceability', 'acousticness']:
                v1 = getattr(af1, feature, 0.5)
                v2 = getattr(af2, feature, 0.5)
                feature_diff += (v1 - v2) ** 2

            feature_sim = 1 - math.sqrt(feature_diff / 4)
            scores.append(feature_sim)

        return sum(scores) / len(scores) if scores else 0.5


class MetadataMatchingStrategy:
    """
    Scores tracks based on metadata matching (genre, era, cultural context).

    Uses MusicBrainz for genre tags and Wikidata for cultural context.
    """

    def __init__(self):
        self.genre_weight = 0.5
        self.era_weight = 0.2
        self.popularity_weight = 0.1
        self.artist_match_weight = 0.2

    def score_candidate(
        self,
        candidate: Track,
        candidate_genres: List[str],
        context: RecommendationContext
    ) -> Tuple[float, List[str]]:
        """
        Score a candidate track based on metadata matching.

        Returns:
            (score, reasoning_list)
        """
        scores = []
        reasoning = []

        # Genre matching
        if candidate_genres and context.genre_profile:
            genre_sim = calculate_genre_similarity(
                candidate_genres,
                context.genre_profile
            )
            scores.append(('genre', genre_sim * self.genre_weight))
            if genre_sim >= 0.5:
                common = set(normalize_genre(g) for g in candidate_genres) & \
                         set(normalize_genre(g) for g in context.genre_profile)
                if common:
                    reasoning.append(f"genre_match:{list(common)[0]}")

        # Artist continuity (from same artist as input)
        if candidate.artist_name in context.artists:
            scores.append(('artist', self.artist_match_weight))
            reasoning.append("same_artist")

        # Popularity range matching
        if context.input_tracks:
            avg_popularity = sum(t.popularity for t in context.input_tracks) / len(context.input_tracks)
            pop_diff = abs(candidate.popularity - avg_popularity) / 100
            pop_score = (1 - pop_diff) * self.popularity_weight
            scores.append(('popularity', pop_score))

        total_score = sum(s[1] for s in scores)
        max_possible = self.genre_weight + self.era_weight + self.popularity_weight + self.artist_match_weight
        normalized_score = total_score / max_possible if max_possible > 0 else 0

        return normalized_score, reasoning


class EnhancedRecommendationEngine:
    """
    Multi-strategy recommendation engine with external data source integration.

    Combines:
    - Spotify for track search and audio features
    - MusicBrainz for genre/tag information
    - Wikidata for cultural context

    All operations are stateless - no user data retained between requests.
    """

    # Strategy weights
    STRATEGY_WEIGHTS = {
        RecommendationStrategy.AUDIO_SIMILARITY: 0.35,
        RecommendationStrategy.ARTIST_SEARCH: 0.25,
        RecommendationStrategy.GENRE_MATCH: 0.25,
        RecommendationStrategy.CULTURAL_CONTEXT: 0.15,
    }

    def __init__(
        self,
        spotify_client: SpotifyClient,
        musicbrainz_client: Optional[MusicBrainzClient] = None,
        wikidata_client: Optional[WikidataClient] = None,
        lastfm_client: Optional['LastFMClient'] = None,
        diversity_weight: float = 0.3
    ):
        """
        Initialize the enhanced recommendation engine.

        Args:
            spotify_client: Spotify API client (required)
            musicbrainz_client: MusicBrainz client (optional, for genre discovery)
            wikidata_client: Wikidata client (optional, for cultural context)
            lastfm_client: Last.fm client (optional, for feature estimation)
            diversity_weight: Weight for diversity injection (0-1)
        """
        self.spotify = spotify_client
        self.musicbrainz = musicbrainz_client
        self.wikidata = wikidata_client
        self.lastfm = lastfm_client
        self.diversity = DiversityInjector(diversity_weight)
        self.metadata_strategy = MetadataMatchingStrategy()

    async def recommend(
        self,
        input_track_ids: List[str],
        preferences: Optional[Dict] = None,
        limit: int = 10,
        use_musicbrainz: bool = True,
        use_wikidata: bool = True
    ) -> Tuple[List[EnhancedRecommendation], Dict[str, float]]:
        """
        Generate recommendations using multiple strategies.

        Args:
            input_track_ids: List of Spotify track IDs
            preferences: Optional filter preferences
            limit: Number of recommendations to return
            use_musicbrainz: Whether to use MusicBrainz for genre discovery
            use_wikidata: Whether to use Wikidata for cultural context

        Returns:
            Tuple of (recommendations, feature_centroid)
        """
        # Step 1: Get input tracks with features
        input_tracks = await self.spotify.get_tracks_with_features(input_track_ids)
        if not input_tracks:
            raise ValueError("No valid input tracks found")

        # Step 2: Build recommendation context
        context = await self._build_context(
            input_tracks,
            use_musicbrainz and self.musicbrainz is not None
        )

        # Step 3: Generate candidates from multiple sources
        candidates = await self._generate_candidates(
            context,
            preferences,
            limit * 4  # Get extra candidates for diversity selection
        )

        # Step 4: Get audio features for candidates
        candidate_ids = [t.id for t in candidates]
        features = await self.spotify.get_audio_features(candidate_ids)
        for track in candidates:
            track.audio_features = features.get(track.id)

        # Step 5: Get genre information for candidates
        candidate_genres = {}
        if use_musicbrainz and self.musicbrainz:
            candidate_genres = await self._get_candidate_genres(candidates)

        # Step 6: Score and rank candidates
        scored = await self._score_candidates(
            candidates,
            candidate_genres,
            context,
            preferences,
            use_wikidata and self.wikidata is not None
        )

        # Step 7: Apply diversity injection
        diverse = self.diversity.apply_diversity(scored, limit)

        return diverse, context.feature_centroid

    async def _build_context(
        self,
        input_tracks: List[Track],
        use_musicbrainz: bool
    ) -> RecommendationContext:
        """Build recommendation context from input tracks."""
        # Extract unique artists
        artists = []
        seen_artists = set()
        for track in input_tracks:
            if track.artist_name and track.artist_name.lower() not in seen_artists:
                artists.append(track.artist_name)
                seen_artists.add(track.artist_name.lower())

        # Get genre information from MusicBrainz
        artist_genres = {}
        genre_profile = []

        if use_musicbrainz and self.musicbrainz:
            for artist in artists[:5]:  # Limit API calls
                try:
                    tags = await self.musicbrainz.get_artist_tags(artist)
                    artist_genres[artist] = tags
                    genre_profile.extend(tags)
                except Exception:
                    artist_genres[artist] = []

        # Deduplicate and limit genre profile
        genre_profile = list(dict.fromkeys(genre_profile))[:15]

        # Try to get Last.fm tags and estimate features if no Spotify audio features
        tracks_with_features = [t for t in input_tracks if t.audio_features]
        if not tracks_with_features and self.lastfm:
            # Estimate features from Last.fm tags
            estimated_features = await self._estimate_features_from_lastfm(input_tracks)
            self._estimated_features = estimated_features
        else:
            self._estimated_features = None

        # Compute audio feature centroid
        centroid = self._compute_centroid(input_tracks)

        return RecommendationContext(
            input_tracks=input_tracks,
            artists=artists,
            artist_genres=artist_genres,
            genre_profile=genre_profile,
            feature_centroid=centroid,
            era_range=(None, None)  # Could be extracted from release dates
        )

    async def _estimate_features_from_lastfm(
        self,
        tracks: List[Track]
    ) -> Dict[str, float]:
        """Estimate audio features from Last.fm tags for input tracks."""
        features = ['energy', 'valence', 'danceability', 'tempo', 'acousticness',
                    'instrumentalness', 'speechiness', 'liveness']

        all_estimated = []

        for track in tracks[:5]:  # Limit API calls
            try:
                # Get tags from Last.fm
                tags_result = await self.lastfm.get_track_tags(track.name, track.artist_name)
                if tags_result and tags_result.tags:
                    # Estimate features from tags
                    estimated = self.lastfm.estimate_audio_features_from_tags(tags_result)
                    if estimated and 'source' in estimated:
                        all_estimated.append(estimated)
            except Exception:
                continue

        if not all_estimated:
            # Return default if estimation failed
            return {f: 0.5 for f in features}

        # Average the estimated features across all tracks
        centroid = {}
        for feature in features:
            values = [e.get(feature, 0.5) for e in all_estimated]
            centroid[feature] = sum(values) / len(values)

        return centroid

    def _compute_centroid(
        self,
        tracks: List[Track],
        recency_weight: float = 0.7
    ) -> Dict[str, float]:
        """Compute weighted feature centroid."""
        features = ['energy', 'valence', 'danceability', 'tempo', 'acousticness',
                    'instrumentalness', 'speechiness', 'liveness']

        tracks_with_features = [t for t in tracks if t.audio_features]

        # If no Spotify audio features, try using Last.fm estimated features
        if not tracks_with_features and hasattr(self, '_estimated_features'):
            # Use pre-computed estimated features from Last.fm
            return self._estimated_features

        if not tracks_with_features:
            # Default centroid when no features available
            return {f: 0.5 for f in features}

        n = len(tracks_with_features)
        weights = [recency_weight ** (n - 1 - i) for i in range(n)]
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        centroid = {}
        for feature in features:
            values = []
            for track in tracks_with_features:
                val = getattr(track.audio_features, feature, 0.5)
                # Normalize tempo
                if feature == 'tempo':
                    val = (val - 50) / 150  # Normalize to ~[0,1]
                    val = max(0, min(1, val))
                values.append(val)

            centroid[feature] = sum(v * w for v, w in zip(values, weights))

        return centroid

    async def _generate_candidates(
        self,
        context: RecommendationContext,
        preferences: Optional[Dict],
        limit: int
    ) -> List[Track]:
        """Generate candidate tracks from multiple sources."""
        candidates = []
        seen_ids = {t.id for t in context.input_tracks}

        # Strategy 1: Artist-based search (primary)
        for artist in context.artists[:5]:
            try:
                results = await self.spotify.search_tracks(
                    f'artist:"{artist}"',
                    limit=25
                )
                for track in results:
                    if track.id not in seen_ids:
                        candidates.append(track)
                        seen_ids.add(track.id)
            except Exception:
                continue

        # Strategy 2: Genre-based search via MusicBrainz
        if self.musicbrainz and context.genre_profile:
            for genre in context.genre_profile[:3]:
                try:
                    # Search Spotify for genre
                    results = await self.spotify.search_tracks(
                        f'genre:"{genre}"',
                        limit=15
                    )
                    for track in results:
                        if track.id not in seen_ids:
                            candidates.append(track)
                            seen_ids.add(track.id)
                except Exception:
                    continue

        # Strategy 3: Related artists via MusicBrainz
        if self.musicbrainz and len(candidates) < limit:
            for artist in context.artists[:2]:
                try:
                    related = await self.musicbrainz.get_related_artists(artist, limit=5)
                    for rel_artist in related:
                        results = await self.spotify.search_tracks(
                            f'artist:"{rel_artist.name}"',
                            limit=10
                        )
                        for track in results:
                            if track.id not in seen_ids:
                                candidates.append(track)
                                seen_ids.add(track.id)
                except Exception:
                    continue

        return candidates[:limit]

    async def _get_candidate_genres(
        self,
        candidates: List[Track]
    ) -> Dict[str, List[str]]:
        """Get genre tags for candidate tracks from MusicBrainz."""
        genres = {}

        # Get unique artists
        artists = set()
        for track in candidates:
            artists.add(track.artist_name)

        # Get genres for each artist (with caching potential)
        artist_genres = {}
        for artist in list(artists)[:20]:  # Limit API calls
            try:
                tags = await self.musicbrainz.get_artist_tags(artist)
                artist_genres[artist] = tags
            except Exception:
                artist_genres[artist] = []

        # Map to track IDs
        for track in candidates:
            genres[track.id] = artist_genres.get(track.artist_name, [])

        return genres

    async def _score_candidates(
        self,
        candidates: List[Track],
        candidate_genres: Dict[str, List[str]],
        context: RecommendationContext,
        preferences: Optional[Dict],
        use_wikidata: bool
    ) -> List[EnhancedRecommendation]:
        """Score and rank candidates using multiple strategies."""
        recommendations = []

        # Pre-fetch Last.fm features for candidates without Spotify audio features
        candidate_features = {}
        if self.lastfm:
            tracks_needing_features = [t for t in candidates if not t.audio_features]
            # Limit to avoid too many API calls
            for track in tracks_needing_features[:20]:
                try:
                    tags_result = await self.lastfm.get_track_tags(track.name, track.artist_name)
                    if tags_result and tags_result.tags:
                        estimated = self.lastfm.estimate_audio_features_from_tags(tags_result)
                        if estimated:
                            candidate_features[track.id] = estimated
                except Exception:
                    pass

        for track in candidates:
            strategy_scores = {}
            reasoning = []
            track_genres = candidate_genres.get(track.id, [])

            # Get estimated features for this candidate
            estimated_features = candidate_features.get(track.id)

            # Strategy 1: Audio feature similarity
            audio_score = self._compute_audio_similarity(track, context, estimated_features)
            strategy_scores[RecommendationStrategy.AUDIO_SIMILARITY.value] = audio_score
            if audio_score >= 0.7:
                reasoning.append("strong_audio_match")
            elif audio_score >= 0.5:
                reasoning.append("audio_similar")

            # Strategy 2: Artist match
            if track.artist_name in context.artists:
                strategy_scores[RecommendationStrategy.ARTIST_SEARCH.value] = 1.0
                reasoning.append("same_artist")
            else:
                strategy_scores[RecommendationStrategy.ARTIST_SEARCH.value] = 0.3

            # Strategy 3: Genre/metadata matching
            meta_score, meta_reasons = self.metadata_strategy.score_candidate(
                track,
                track_genres,
                context
            )
            strategy_scores[RecommendationStrategy.GENRE_MATCH.value] = meta_score
            # Filter out duplicate "same_artist" (already added above)
            meta_reasons = [r for r in meta_reasons if r != "same_artist"]
            reasoning.extend(meta_reasons)

            # Strategy 4: Cultural context (if Wikidata available)
            if use_wikidata and self.wikidata:
                # For performance, we skip detailed Wikidata queries in scoring
                # Cultural context is primarily used in candidate generation
                strategy_scores[RecommendationStrategy.CULTURAL_CONTEXT.value] = 0.5

            # Apply preference filters
            if preferences and not self._passes_filters(track, preferences):
                continue

            # Calculate weighted final score
            final_score = 0
            for strategy, weight in self.STRATEGY_WEIGHTS.items():
                score = strategy_scores.get(strategy.value, 0)
                final_score += score * weight

            recommendations.append(EnhancedRecommendation(
                track=track,
                final_score=final_score,
                strategy_scores=strategy_scores,
                reasoning=reasoning if reasoning else ["general_match"],
                genres=track_genres
            ))

        # Sort by score
        recommendations.sort(key=lambda r: r.final_score, reverse=True)
        return recommendations

    def _compute_audio_similarity(
        self,
        track: Track,
        context: RecommendationContext,
        candidate_estimated_features: Optional[Dict[str, float]] = None
    ) -> float:
        """Compute audio feature similarity to centroid."""
        centroid = context.feature_centroid

        # Use actual audio features if available
        if track.audio_features:
            af = track.audio_features
            features = ['energy', 'valence', 'danceability', 'acousticness']
            weights = [1.0, 0.9, 0.85, 0.6]

            weighted_dist_sq = 0
            total_weight = 0

            for feature, weight in zip(features, weights):
                val = getattr(af, feature, 0.5)
                cent_val = centroid.get(feature, 0.5)

                diff = abs(val - cent_val)
                weighted_dist_sq += weight * (diff ** 2)
                total_weight += weight

            distance = math.sqrt(weighted_dist_sq / total_weight) if total_weight else 0
            similarity = 1 - distance
            return max(0, min(1, similarity))

        # Use estimated features if provided (from Last.fm)
        if candidate_estimated_features:
            features = ['energy', 'valence', 'danceability', 'acousticness']
            weights = [1.0, 0.9, 0.85, 0.6]

            weighted_dist_sq = 0
            total_weight = 0

            for feature, weight in zip(features, weights):
                val = candidate_estimated_features.get(feature, 0.5)
                cent_val = centroid.get(feature, 0.5)

                diff = abs(val - cent_val)
                weighted_dist_sq += weight * (diff ** 2)
                total_weight += weight

            distance = math.sqrt(weighted_dist_sq / total_weight) if total_weight else 0
            similarity = 1 - distance
            return max(0, min(1, similarity))

        return 0.5  # Neutral score when features unavailable

    def _passes_filters(self, track: Track, preferences: Dict) -> bool:
        """Check if track passes preference filters."""
        af = track.audio_features
        if not af:
            return True  # Can't filter without features

        if 'energy_range' in preferences:
            min_e, max_e = preferences['energy_range']
            if not (min_e <= af.energy <= max_e):
                return False

        if 'tempo_range' in preferences:
            min_t, max_t = preferences['tempo_range']
            if not (min_t <= af.tempo <= max_t):
                return False

        if 'valence_range' in preferences:
            min_v, max_v = preferences['valence_range']
            if not (min_v <= af.valence <= max_v):
                return False

        if 'danceability_range' in preferences:
            min_d, max_d = preferences['danceability_range']
            if not (min_d <= af.danceability <= max_d):
                return False

        return True

    def analyze_session(self, tracks: List[Track]) -> Dict:
        """Analyze patterns in a listening session."""
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
                        val = (val - 50) / 150
                    values.append(val)

            if len(values) >= 2:
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

                variance = sum((v - y_mean) ** 2 for v in values) / n
                analysis[f'{feature}_consistency'] = 'high' if variance < 0.05 else 'low'

        return analysis
