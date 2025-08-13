import os, requests, cohere

from cohere import Client as CohereClient
from flask import Flask, session, redirect, url_for, request, Response, jsonify
from datetime import datetime, timezone
from collections import Counter
from style_guard import enforce_style
from dotenv import load_dotenv

from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify
from spotipy.cache_handler import FlaskSessionCacheHandler

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY")

client_id = os.getenv("SPOTIPY_CLIENT_ID")
client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
redirect_uri= os.getenv("SPOTIPY_REDIRECT_URI")
scope= 'user-top-read'
co = cohere.Client(os.getenv("COHERE_API_KEY"))

cache_handler = FlaskSessionCacheHandler(session)
sp_oauth = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope=scope,
    cache_handler=cache_handler,
    show_dialog=True
)


def loginCheck():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    return Spotify(auth_manager=sp_oauth) 

def build_personality_prompt(traits):
    top_genres_list = traits.get('top_genres', [])
    top_3_genres = ", ".join(
        f"{g.get('genre','?')} ({g.get('count', '?')})" for g in top_genres_list[:3]) if top_genres_list else "unknown"

    return f"""
You are a witty music personality writer for a Spotify top tracks analyzer app.
Your job: turn listening analytics into a short, human personality snapshot (NOT a list of stats).

INPUT TRAITS (read them carefully, but don't quote numbers unless told):
- Average popularity score: {traits.get('avg_popularity', '?')}
- Recent song share (last 3 years): {traits.get('recent_share_pct', '?')}%
- Era span : {traits.get('era_span', ['?', '?'])[0]} to {traits.get('era_span', ['?', '?'])[1]}
- Unique primary artists: {traits.get('unique_artists_primary', '?')}
- Explicit content rate: {traits.get('explicit_rate', '?')}%
- Album diversity ratio: {traits.get('album_diversity', '?')}
- Top genres: {top_3_genres}
- Feature rate: {traits.get('feature_rate', '?')}

STYLE RULES:
- Output 1 sentence, maximum 18 words.
- Use playful, metaphorical language - like a quirky horoscope or personality roast.
- Strongly reflect the top genres' vibe; let 2-3 other traits subtly influence the mood. 
- Avoid stats (percentages, counts, rankings). years and times are okay if they fit the vibe; apply them through imagery.
- Avoid song or artist names, hashtags, emojis, multiple sentences, or trailing ellipses.
- Make it feel oddly specific and unique - not generic.

EXAMPLES (style only, do not copy content):
- "A neon night owl DJing heartbreaks in a thrift-store galaxy."
- "Caffeinated daydreams on a vinyl time machine doing 90 in the carpool lane."
- "Glitter-scarred optimist, moshing with moonlight and spilled espresso."
These are just examples and not templates. Get creative with word and adjective usage and do not get repetitive.

Now, write the single sentence summary:
"""

@app.route('/')
def home():
    sp = loginCheck()
    if isinstance(sp, Response):
        return sp
    return "User is authenticated! NeoAnalysis backend is ready."



@app.route('/callback')
def callback():
    sp_oauth.get_access_token(request.args['code'])
    return redirect(url_for('home'))


@app.route('/neo_data')
def neo_data():
    sp = loginCheck()
    if isinstance(sp, Response):
        return sp
    
    top_tracks = sp.current_user_top_tracks(limit=50, offset=0, time_range='short_term')

    clean_tracks = []

    for tr in top_tracks['items']:
        track_name = tr['name']
        track_id = tr['id']
        popularity = tr.get('popularity', 0)
        explicit = tr.get('explicit', False)
        duration_ms = tr.get('duration_ms')

        album = tr.get('album', {})
        album_name = album.get('name')
        release_date = album.get('release_date')
        cover_url = None
        if album.get('images'):
            cover_url = album['images'][0]['url']
        
        artists = tr.get('artists') or []
        artist_names = [a.get('name') for a in artists if a.get('name')]
        artist_ids = [a.get('id') for a in artists if a.get('id')]

        clean_tracks.append({
            "track_name": track_name,
            "track_id": track_id,
            "popularity": popularity,
            "explicit": explicit,
            "duration_ms": duration_ms,
            "album_name": album_name,
            "album_release_date": release_date,
            "album_cover_url": cover_url,
            "artist_names": artist_names,
            "artist_ids": artist_ids
        })
    
    pops = [t.get("popularity", 0) for t in clean_tracks if t.get("popularity") is not None]
    avg_pops = round(sum(pops) / len(pops), 1) if pops else 0.0 



    years = []
    for t in clean_tracks:
        rd = t.get("album_release_date")
        if rd:
            try: 
                years.append(int(rd.split("-")[0]))
            except ValueError:
                pass
    
    current_year = datetime.now().year
    recent_window = 3

    recent_share_pct = round(
        100 * sum(1 for y in years if y >= current_year - recent_window) / len(years),
        1
    ) if years else 0.0

    avg_release_year = round(sum(years) / len(years)) if years else None
    era_span = (min(years), max(years)) if years else (None, None)



    primary_names = [t["artist_names"][0] for t in clean_tracks if t.get("artist_names")]
    unique_artists_primary = len(set(primary_names))

    explicit_rate = round(
        100 * (sum(1 for t in clean_tracks if t.get("explicit")) / len(clean_tracks)),
        1
    ) if clean_tracks else 0.0



    primary_artist_ids = []
    for t in clean_tracks:
        ids = t.get("artist_ids") or []
        if ids:
            primary_artist_ids.append(ids[0])

    primary_artist_ids = list(dict.fromkeys(primary_artist_ids))

    id2genres = {}
    for i in range(0, len(primary_artist_ids), 50):
        chunk = primary_artist_ids[i:i+50]
        resp = sp.artists(chunk)
        for art in resp.get("artists", []):
            id2genres[art["id"]] = [g.lower() for g in art.get("genres", [])]

    all_genres = []
    for t in clean_tracks:
        ids = t.get("artist_ids") or []
        if not ids:
            continue
        all_genres.extend(id2genres.get(ids[0], []))

    for t in clean_tracks:
        aid = t["artist_ids"][0] if t.get("artist_ids") else None
        t["genres"] = sorted(set(id2genres.get(aid, []))) if aid else []

    genre_counts = Counter(all_genres)
    top_genres = [{"genre": g, "count": c} for g, c in genre_counts.most_common(3)]


    album_names = [t["album_name"] for t in clean_tracks if t.get("album_name")]
    unique_album_count = len(set(album_names))

    album_diversity_ratio = round(unique_album_count / len(clean_tracks), 2)if clean_tracks else 0.0

    feature_rate = round(
        100 * sum(1 for t in clean_tracks if len(t.get("artist_names", [])) > 1) / len(clean_tracks),
                  1
    )

    traits = {
        "avg_popularity": avg_pops,
        "recent_share_pct": recent_share_pct,
        "avg_release_year": avg_release_year,
        "era_span": era_span,
        "unique_artists_primary": unique_artists_primary,
        "explicit_rate": explicit_rate,
        "album_diversity": album_diversity_ratio,
        "top_genres": top_genres,
        "feature_rate": feature_rate
    }
    
    prompt = build_personality_prompt(traits)

    cohere_resp = co.chat(
        model="command-r-plus",
        message=prompt,
        temperature=0.85
    )

    summary_raw = (cohere_resp.text or "").strip()

    summary_cleaned, issues = enforce_style(summary_raw)

    summary_text = summary_cleaned

    return jsonify({
        "traits": traits,
        "summary": summary_text
    })
    

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
