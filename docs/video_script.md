# NextTrack Feature Prototype - Video Demonstration Script

**Duration:** 3-5 minutes
**Purpose:** Demonstrate the working prototype and explain the technical implementation

---

## 🎬 VIDEO OUTLINE

| Section | Duration | Content |
|---------|----------|---------|
| 1. Introduction | 0:00 - 0:30 | Project overview and privacy concept |
| 2. The Problem | 0:30 - 1:00 | Why this matters |
| 3. Live Demo | 1:00 - 3:00 | Showing the working prototype |
| 4. Technical Explanation | 3:00 - 4:00 | How the algorithm works |
| 5. Evaluation & Conclusion | 4:00 - 4:30 | Results and next steps |

---

## 📝 FULL SCRIPT

### SECTION 1: Introduction (0:00 - 0:30)

> **[SCREEN: Show the NextTrack web interface or title slide]**

**SAY:**

"Hi, I'm [Your Name], and this is NextTrack — a privacy-focused music recommendation API I've built for my Advanced Web Design project.

The core idea is simple but powerful: What if we could get intelligent music recommendations *without* being tracked? No user accounts, no listening history stored on a server — just smart suggestions based on what you're listening to *right now*.

Let me show you how it works."

---

### SECTION 2: The Problem (0:30 - 1:00)

> **[SCREEN: Can show Spotify's privacy policy or a simple diagram]**

**SAY:**

"Every major music platform — Spotify, Apple Music, YouTube — builds a profile of you. Every song you play, skip, or save is logged forever.

This creates two problems I wanted to solve:

**First**, privacy. Your music taste can reveal a lot about you — your mood, your politics, even your mental health.

**Second**, the 'shared device' problem. If my kids use my account, suddenly I'm getting recommendations for Disney soundtracks mixed with my jazz playlists.

NextTrack solves both by being completely *stateless*. The server literally cannot remember your previous request."

---

### SECTION 3: Live Demo (1:00 - 3:00)

> **[SCREEN: Switch to the running web application at localhost:8000]**

**SAY:**

"Let me demonstrate the working prototype.

> **[Action: Type a search query, e.g., "Daft Punk"]**

I'll start by searching for some tracks. Let's say I've been listening to Daft Punk.

> **[Action: Click on 2-3 tracks to add them to the selection]**

I'll select a few tracks to simulate my recent listening history. Notice these are just being stored temporarily in my browser — nothing is saved on the server.

> **[Action: Optionally adjust the Energy or Tempo sliders]**

I can also set preferences. Let's say I want high-energy tracks, so I'll set the minimum energy to around 60%.

> **[Action: Click "Get Recommendations"]**

Now I click 'Get Recommendations'...

> **[Wait for results to load]**

And here we go! The API has returned five recommendations, each with a *confidence score* showing how similar it is to my input tracks.

> **[Action: Point to a specific recommendation]**

Look at this one — it has an 89% match. If I hover over the reasoning, you can see it matched on 'strong energy match' and 'danceability similar'. These aren't random — they're based on real audio analysis.

> **[Action: Click the play button on a preview if available]**

I can even preview the tracks directly. *[Let it play for 2-3 seconds]*

> **[Action: Scroll down to show the Centroid display]**

Down here, you can see the 'Audio Profile' or centroid that was computed from my input tracks. This shows the average energy, valence, tempo, and other features. The recommendations were chosen because they're mathematically close to this profile."

---

### SECTION 4: Technical Explanation (3:00 - 4:00)

> **[SCREEN: Can show the architecture diagram or code snippet]**

**SAY:**

"Let me briefly explain what's happening behind the scenes.

When you click 'Get Recommendations', the client sends a POST request to my API with the list of track IDs. The server then:

1. **Fetches track metadata** from Spotify — artist names, album info, and track details.

2. **Generates candidates** using artist-based search — I search for more tracks by the same artists you selected, expanding outward to find related music.

3. **Ranks candidates** by relevance — Spotify's search returns results ordered by popularity and relevance to your artists.

4. **Returns scored recommendations** — each track gets a confidence score based on its position in the search results.

Note: Spotify recently deprecated their audio-features and recommendations endpoints for apps using Client Credentials. My solution was to pivot to a search-based discovery approach, which still produces relevant recommendations while maintaining the stateless, privacy-preserving design.

All of this happens in under one second."

---

### SECTION 5: Evaluation & Conclusion (4:00 - 4:30)

> **[SCREEN: Can show the evaluation results table or return to the web interface]**

**SAY:**

"In my testing, NextTrack successfully returns relevant recommendations from the same artists and related genres. The search-based approach ensures cultural coherence — if you're listening to Afrobeats artists, you get more Afrobeats recommendations.

User feedback was positive, with testers noting the recommendations 'felt natural' and appreciated the instant, account-free experience.

There are areas for future improvement. With user-authorized OAuth tokens, I could access Spotify's audio features and recommendations endpoints for even more sophisticated similarity matching. Another enhancement would be integrating MusicBrainz metadata for genre-aware discovery.

But the core prototype proves the concept: you *can* get quality recommendations without sacrificing your privacy.

Thank you for watching."

> **[END SCREEN: Show project title, your name, course code]**

---

## 🎥 RECORDING TIPS

### Before Recording:
- [ ] Start the server: `cd src && uvicorn main:app --reload`
- [ ] Set Spotify credentials: `export SPOTIFY_CLIENT_ID=xxx` and `export SPOTIFY_CLIENT_SECRET=xxx`
- [ ] Open browser to `http://localhost:8000`
- [ ] Clear any previous searches/selections
- [ ] Test that search and recommendations work
- [ ] Close unnecessary browser tabs and notifications

### Screen Recording:
- Use **QuickTime** (Mac) or **OBS** (cross-platform)
- Record at 1080p resolution
- Include your microphone audio
- Consider recording your face in a small corner window

### Presentation Tips:
- Speak slowly and clearly
- Pause briefly when switching screens
- If something fails, explain it — real demos have bugs!
- Keep energy up but professional

### Backup Plan:
If the API fails during recording, you can:
1. Show the Swagger docs at `/docs` to demonstrate the API structure
2. Show pre-recorded successful results as a fallback
3. Explain the architecture using the code files

---

## 📋 QUICK REFERENCE - Key Points to Hit

1. ✅ **Privacy-focused** — no user tracking
2. ✅ **Stateless** — server can't remember you
3. ✅ **Real Spotify integration** — live search and track data
4. ✅ **Artist-based discovery** — finds more tracks from your artists
5. ✅ **Search-based ranking** — leverages Spotify's relevance ordering
6. ✅ **Culturally coherent** — genre consistency in recommendations
7. ✅ **Future work** — OAuth for audio features, MusicBrainz integration

---

**Good luck with your recording! 🎬**
