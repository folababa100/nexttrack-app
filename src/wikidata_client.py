"""
Wikidata Client for NextTrack
Provides cultural context and knowledge graph data for music recommendations.

Wikidata is a free and open knowledge base that can be read and edited by
both humans and machines. It contains structured data about music artists,
genres, and their relationships.

This client uses SPARQL queries to access Wikidata.
API Documentation: https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service
"""

import asyncio
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
import httpx
import urllib.parse


@dataclass
class WikidataArtist:
    """Artist information from Wikidata."""
    qid: str  # Wikidata Q-ID (e.g., "Q483")
    name: str
    description: str = ""
    genres: List[str] = field(default_factory=list)
    country: str = ""
    birth_year: Optional[int] = None
    spotify_id: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    influenced_by: List[str] = field(default_factory=list)
    influences: List[str] = field(default_factory=list)


@dataclass
class WikidataGenre:
    """Genre information from Wikidata."""
    qid: str
    name: str
    description: str = ""
    parent_genres: List[str] = field(default_factory=list)
    subgenres: List[str] = field(default_factory=list)
    origin_country: str = ""
    origin_decade: str = ""


class WikidataClient:
    """
    Async client for Wikidata SPARQL endpoint.

    Provides cultural context for music recommendation including:
    - Genre hierarchies and relationships
    - Artist influences and connections
    - Historical and geographic context

    Note: Wikidata is rate-limited. This client includes delays between requests.
    """

    SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
    RATE_LIMIT_DELAY = 0.5  # 500ms between requests

    def __init__(self, user_agent: str = "NextTrack/1.0"):
        """Initialize Wikidata client."""
        self.user_agent = user_agent
        self._http_client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/sparql-results+json"
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

    async def _sparql_query(self, query: str) -> List[Dict]:
        """Execute a SPARQL query and return results."""
        await self._rate_limit()

        client = await self._get_client()

        # Encode query for URL
        params = {"query": query, "format": "json"}

        try:
            response = await client.get(
                self.SPARQL_ENDPOINT,
                params=params
            )

            if response.status_code == 429:
                # Rate limited - wait and retry
                await asyncio.sleep(5)
                response = await client.get(
                    self.SPARQL_ENDPOINT,
                    params=params
                )

            if response.status_code != 200:
                return []

            data = response.json()
            return data.get("results", {}).get("bindings", [])

        except Exception as e:
            print(f"Wikidata query error: {e}")
            return []

    def _extract_value(self, binding: Dict, key: str) -> str:
        """Extract a value from a SPARQL result binding."""
        if key in binding:
            return binding[key].get("value", "")
        return ""

    def _extract_qid(self, uri: str) -> str:
        """Extract Q-ID from Wikidata URI."""
        if uri and "/entity/Q" in uri:
            return uri.split("/")[-1]
        return ""

    async def search_artist(self, artist_name: str) -> Optional[WikidataArtist]:
        """
        Search for an artist by name and return their Wikidata info.

        Args:
            artist_name: Name of the artist to search for

        Returns:
            WikidataArtist with genres, country, influences, etc.
        """
        # SPARQL query to find artist by name
        query = f'''
        SELECT ?artist ?artistLabel ?artistDescription ?genreLabel ?countryLabel
               ?birthYear ?spotifyId ?mbid ?influencedByLabel
        WHERE {{
          ?artist rdfs:label "{artist_name}"@en .
          ?artist wdt:P31/wdt:P279* wd:Q5 .  # Instance of human (or subclass)

          OPTIONAL {{ ?artist wdt:P136 ?genre . }}
          OPTIONAL {{ ?artist wdt:P27 ?country . }}
          OPTIONAL {{ ?artist wdt:P569 ?birthDate . BIND(YEAR(?birthDate) AS ?birthYear) }}
          OPTIONAL {{ ?artist wdt:P1902 ?spotifyId . }}
          OPTIONAL {{ ?artist wdt:P434 ?mbid . }}
          OPTIONAL {{ ?artist wdt:P737 ?influencedBy . }}

          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 20
        '''

        results = await self._sparql_query(query)

        if not results:
            # Try broader search (musicians)
            query2 = f'''
            SELECT ?artist ?artistLabel ?artistDescription ?genreLabel ?countryLabel
            WHERE {{
              ?artist ?label "{artist_name}"@en .
              {{ ?artist wdt:P106 wd:Q177220 . }}  # occupation: singer
              UNION
              {{ ?artist wdt:P106 wd:Q639669 . }}  # occupation: musician
              UNION
              {{ ?artist wdt:P31 wd:Q215380 . }}   # instance of: musical group

              OPTIONAL {{ ?artist wdt:P136 ?genre . }}
              OPTIONAL {{ ?artist wdt:P27 ?country . }}

              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
            }}
            LIMIT 10
            '''
            results = await self._sparql_query(query2)

        if not results:
            return None

        # Aggregate results (multiple rows for multiple genres/influences)
        artist_data = {
            "qid": "",
            "name": artist_name,
            "description": "",
            "genres": set(),
            "country": "",
            "birth_year": None,
            "spotify_id": None,
            "musicbrainz_id": None,
            "influenced_by": set()
        }

        for row in results:
            if not artist_data["qid"]:
                artist_data["qid"] = self._extract_qid(
                    self._extract_value(row, "artist")
                )
                artist_data["description"] = self._extract_value(
                    row, "artistDescription"
                )
                artist_data["country"] = self._extract_value(row, "countryLabel")

                birth = self._extract_value(row, "birthYear")
                if birth:
                    try:
                        artist_data["birth_year"] = int(birth)
                    except ValueError:
                        pass

                artist_data["spotify_id"] = self._extract_value(row, "spotifyId") or None
                artist_data["musicbrainz_id"] = self._extract_value(row, "mbid") or None

            genre = self._extract_value(row, "genreLabel")
            if genre:
                artist_data["genres"].add(genre)

            influence = self._extract_value(row, "influencedByLabel")
            if influence:
                artist_data["influenced_by"].add(influence)

        return WikidataArtist(
            qid=artist_data["qid"],
            name=artist_data["name"],
            description=artist_data["description"],
            genres=list(artist_data["genres"]),
            country=artist_data["country"],
            birth_year=artist_data["birth_year"],
            spotify_id=artist_data["spotify_id"],
            musicbrainz_id=artist_data["musicbrainz_id"],
            influenced_by=list(artist_data["influenced_by"])
        )

    async def get_genre_hierarchy(self, genre_name: str) -> Optional[WikidataGenre]:
        """
        Get genre information including parent genres and subgenres.

        Args:
            genre_name: Name of the genre (e.g., "afrobeats", "hip hop")

        Returns:
            WikidataGenre with hierarchical relationships
        """
        query = f'''
        SELECT ?genre ?genreLabel ?genreDescription
               ?parentLabel ?subgenreLabel ?countryLabel ?decade
        WHERE {{
          ?genre rdfs:label "{genre_name}"@en .
          ?genre wdt:P31/wdt:P279* wd:Q188451 .  # Instance of music genre

          OPTIONAL {{ ?genre wdt:P279 ?parent . }}  # Subclass of (parent genre)
          OPTIONAL {{ ?subgenre wdt:P279 ?genre . }}  # Subgenres
          OPTIONAL {{ ?genre wdt:P495 ?country . }}  # Country of origin
          OPTIONAL {{ ?genre wdt:P571 ?inception . BIND(YEAR(?inception) AS ?decade) }}

          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 50
        '''

        results = await self._sparql_query(query)

        if not results:
            return None

        genre_data = {
            "qid": "",
            "name": genre_name,
            "description": "",
            "parent_genres": set(),
            "subgenres": set(),
            "origin_country": "",
            "origin_decade": ""
        }

        for row in results:
            if not genre_data["qid"]:
                genre_data["qid"] = self._extract_qid(
                    self._extract_value(row, "genre")
                )
                genre_data["description"] = self._extract_value(
                    row, "genreDescription"
                )
                genre_data["origin_country"] = self._extract_value(
                    row, "countryLabel"
                )
                decade = self._extract_value(row, "decade")
                if decade:
                    genre_data["origin_decade"] = f"{decade}s"

            parent = self._extract_value(row, "parentLabel")
            if parent and parent != genre_name:
                genre_data["parent_genres"].add(parent)

            subgenre = self._extract_value(row, "subgenreLabel")
            if subgenre and subgenre != genre_name:
                genre_data["subgenres"].add(subgenre)

        return WikidataGenre(
            qid=genre_data["qid"],
            name=genre_data["name"],
            description=genre_data["description"],
            parent_genres=list(genre_data["parent_genres"]),
            subgenres=list(genre_data["subgenres"]),
            origin_country=genre_data["origin_country"],
            origin_decade=genre_data["origin_decade"]
        )

    async def find_artists_by_genre(
        self,
        genre_name: str,
        limit: int = 20
    ) -> List[Tuple[str, str]]:
        """
        Find artists associated with a genre.

        Args:
            genre_name: Name of the genre
            limit: Maximum number of artists to return

        Returns:
            List of (artist_name, spotify_id) tuples
        """
        query = f'''
        SELECT DISTINCT ?artistLabel ?spotifyId
        WHERE {{
          ?genre rdfs:label "{genre_name}"@en .
          ?genre wdt:P31/wdt:P279* wd:Q188451 .

          ?artist wdt:P136 ?genre .
          ?artist wdt:P1902 ?spotifyId .  # Has Spotify ID

          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT {limit}
        '''

        results = await self._sparql_query(query)

        artists = []
        for row in results:
            name = self._extract_value(row, "artistLabel")
            spotify_id = self._extract_value(row, "spotifyId")
            if name and spotify_id:
                artists.append((name, spotify_id))

        return artists

    async def get_artist_influences(
        self,
        artist_name: str
    ) -> Dict[str, List[str]]:
        """
        Get artists who influenced or were influenced by the given artist.

        Returns:
            Dict with "influenced_by" and "influences" lists
        """
        query = f'''
        SELECT ?artistLabel ?influencedByLabel ?influencesLabel
        WHERE {{
          ?artist rdfs:label "{artist_name}"@en .
          {{ ?artist wdt:P106 wd:Q177220 . }} UNION {{ ?artist wdt:P106 wd:Q639669 . }}

          OPTIONAL {{ ?artist wdt:P737 ?influencedBy . }}
          OPTIONAL {{ ?influenced wdt:P737 ?artist . BIND(?influenced AS ?influences) }}

          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 50
        '''

        results = await self._sparql_query(query)

        influenced_by = set()
        influences = set()

        for row in results:
            by = self._extract_value(row, "influencedByLabel")
            if by and by != artist_name:
                influenced_by.add(by)

            inf = self._extract_value(row, "influencesLabel")
            if inf and inf != artist_name:
                influences.add(inf)

        return {
            "influenced_by": list(influenced_by),
            "influences": list(influences)
        }

    async def get_related_genres(
        self,
        genre_names: List[str]
    ) -> Set[str]:
        """
        Get related genres (parent genres, sibling genres) for a list of genres.

        Useful for expanding recommendation candidates beyond exact genre matches.
        """
        all_related = set()

        for genre in genre_names[:5]:  # Limit API calls
            genre_info = await self.get_genre_hierarchy(genre)
            if genre_info:
                all_related.update(genre_info.parent_genres)
                all_related.update(genre_info.subgenres)

        # Remove the input genres
        all_related -= set(genre_names)

        return all_related


# Utility functions for cultural context

def calculate_era_similarity(year1: Optional[int], year2: Optional[int]) -> float:
    """
    Calculate similarity based on release/birth years.

    Artists/tracks from similar eras get higher similarity.
    Returns 0.0 to 1.0.
    """
    if year1 is None or year2 is None:
        return 0.5  # Unknown - neutral score

    diff = abs(year1 - year2)

    if diff <= 5:
        return 1.0
    elif diff <= 10:
        return 0.8
    elif diff <= 20:
        return 0.6
    elif diff <= 30:
        return 0.4
    else:
        return 0.2


def calculate_cultural_similarity(
    artist1: WikidataArtist,
    artist2: WikidataArtist
) -> float:
    """
    Calculate cultural similarity between two artists.

    Considers genres, country, era, and influences.
    Returns 0.0 to 1.0.
    """
    scores = []

    # Genre overlap
    if artist1.genres and artist2.genres:
        genres1 = set(g.lower() for g in artist1.genres)
        genres2 = set(g.lower() for g in artist2.genres)
        intersection = genres1 & genres2
        union = genres1 | genres2
        genre_sim = len(intersection) / len(union) if union else 0
        scores.append(genre_sim * 1.5)  # Weight genres highly

    # Same country
    if artist1.country and artist2.country:
        if artist1.country.lower() == artist2.country.lower():
            scores.append(0.8)
        else:
            scores.append(0.2)

    # Era similarity
    era_sim = calculate_era_similarity(artist1.birth_year, artist2.birth_year)
    scores.append(era_sim * 0.5)  # Lower weight for era

    # Influence relationship
    if artist1.name in artist2.influenced_by or artist2.name in artist1.influenced_by:
        scores.append(1.0)

    if not scores:
        return 0.5

    return min(1.0, sum(scores) / len(scores))
