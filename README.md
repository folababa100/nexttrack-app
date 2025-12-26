# NextTrack - Privacy-Focused Music Recommendation API

A RESTful API that provides intelligent music recommendations without user tracking or profiling.

## 🎯 Project Overview

**CM3035 Advanced Web Design - Final Project**

NextTrack is a stateless music recommendation system that:
- Accepts a sequence of track identifiers with each request
- Computes audio feature similarity using multiple data sources
- Integrates Spotify, MusicBrainz, and Wikidata for recommendations
- Returns relevant recommendations with confidence scores
- **Never stores user data** - completely privacy-preserving

### Key Features

- 🔒 **Privacy-First**: No user tracking, profiling, or data retention
- 🎵 **Multi-Source**: Combines Spotify, MusicBrainz, and Wikidata
- 🎯 **Smart Recommendations**: Audio similarity + genre matching + diversity
- 🌐 **RESTful API**: Well-documented endpoints with OpenAPI specs
- 🖥️ **Web Demo**: Interactive UI for testing recommendations

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.9+
- Spotify Developer Account (free)

### 2. Get Spotify API Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click "Create App"
3. Fill in app details (name, description)
4. Copy the **Client ID** and **Client Secret**

### 3. Setup

```bash
# Navigate to project directory
cd final-project

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SPOTIFY_CLIENT_ID="your_client_id_here"
export SPOTIFY_CLIENT_SECRET="your_client_secret_here"
export SPOTIFY_MARKET="US"  # Optional: country code for catalog

# Optional: Enable enhanced multi-strategy engine
export USE_ENHANCED_ENGINE=true

# Run the server
cd src
python main.py
```

### 4. Access the Application

- **Web Demo**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📖 API Endpoints

### Search Tracks
```http
GET /api/search?q={query}&limit={limit}
```

### Get Track Details
```http
GET /api/track/{track_id}
```

### Get Recommendations
```http
POST /api/recommend
Content-Type: application/json

{
  "track_ids": ["track_id_1", "track_id_2"],
  "preferences": {
    "energy_range": [0.3, 0.8],
    "tempo_range": [100, 140]
  },
  "limit": 5
}
```

### Health Check
```http
GET /api/health
```

## 🎮 Using the Web Demo

1. **Search** for songs using the search box
2. **Click** on tracks to add them to your "listening history"
3. **Adjust** preference sliders (energy, tempo) if desired
4. **Click** "Get Recommendations" to see suggestions
5. **Play** previews using the ▶ buttons
6. **View** the computed audio profile (centroid) showing why tracks were recommended

## 🔧 Technical Details

### Recommendation Algorithm

1. **Audio Feature Extraction**: Retrieves tempo, energy, valence, danceability, etc. from Spotify
2. **Centroid Calculation**: Computes weighted average of input track features (recent tracks weighted more)
3. **Candidate Generation**: Uses Spotify's recommendation API + related artists
4. **Similarity Scoring**: Weighted Euclidean distance between candidates and centroid
5. **Ranking & Filtering**: Apply preference constraints and return top matches

### Audio Features Used

| Feature | Weight | Description |
|---------|--------|-------------|
| Energy | 1.0 | Intensity and activity |
| Valence | 0.9 | Musical positiveness (mood) |
| Danceability | 0.85 | Rhythm suitability for dancing |
| Tempo | 0.7 | Beats per minute |
| Acousticness | 0.6 | Acoustic vs. electronic |
| Instrumentalness | 0.5 | Vocal vs. instrumental |
| Speechiness | 0.4 | Presence of spoken words |
| Liveness | 0.3 | Audience presence |

## 📁 Project Structure

```
final-project/
├── src/
│   ├── main.py                  # FastAPI application & endpoints
│   ├── spotify_client.py        # Spotify API integration
│   ├── musicbrainz_client.py    # MusicBrainz API for genres
│   ├── wikidata_client.py       # Wikidata SPARQL for context
│   ├── engine.py                # Basic recommendation engine
│   ├── enhanced_engine.py       # Multi-strategy engine
│   └── static/
│       └── index.html           # Web demo interface
├── tests/
│   ├── conftest.py              # Test configuration
│   └── test_engine.py           # Unit tests
├── docs/
│   ├── PROGRESS.md              # Development progress tracker
│   ├── preliminary_report.md    # Academic report
│   └── video_script.md          # Demo video script
├── requirements.txt
├── pytest.ini
└── README.md
```

## 🔬 Recommendation Strategies

### 1. Audio Feature Similarity
Uses weighted Euclidean distance between audio features (energy, valence, danceability, etc.)

### 2. Artist-Based Discovery
Finds more tracks by artists in your listening history

### 3. Genre Matching (MusicBrainz)
Retrieves genre tags and finds tracks with similar genres

### 4. Cultural Context (Wikidata)
Uses artist influences and era information for context-aware recommendations

### 5. Diversity Injection
Prevents homogeneous results by penalizing similar tracks

## 🧪 Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage (if coverage installed)
pytest tests/ -v --cov=src
```

## 📝 Documentation

- [Progress Tracker](docs/PROGRESS.md) - Development status and completed features
- [Preliminary Report](docs/preliminary_report.md) - Academic documentation
- [API Docs](http://localhost:8000/docs) - Interactive OpenAPI documentation (when running)

## 🎥 Demo Video Tips

When recording your 3-5 minute video demonstration:

1. **Introduction** (30s): Explain the privacy-focused concept
2. **Search Demo** (45s): Show searching for and selecting tracks
3. **Preference Controls** (30s): Demonstrate adjusting energy/tempo filters
4. **Recommendations** (60s): Show recommendations with scores and reasoning
5. **Audio Preview** (30s): Play previews of recommended tracks
6. **Centroid Display** (45s): Explain the computed audio profile
7. **Conclusion** (30s): Summarize the stateless, privacy-preserving approach

## 📝 License

This project is for educational purposes as part of CM3035 Advanced Web Design.

## 🔗 Resources

- [Spotify Web API Documentation](https://developer.spotify.com/documentation/web-api/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Audio Features Explained](https://developer.spotify.com/documentation/web-api/reference/get-audio-features)

## 🛠️ Troubleshooting

- `403 Forbidden` from Spotify: double-check that your Client ID/Secret are correct, the app has at least one Redirect URI in the dashboard, and that `SPOTIFY_MARKET` is set to a country where your seed tracks are available (e.g., `US`, `GB`, `NG`). Restart the server after updating environment variables.
