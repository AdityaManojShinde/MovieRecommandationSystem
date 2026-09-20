import pickle
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import gradio as gr
import httpx

load_dotenv()

access_token = os.getenv("TMDB_ACCESS_TOKEN")
base_url = "https://api.themoviedb.org/3/movie/"
poster_base_url = "https://image.tmdb.org/t/p/w500"
headers = {
    "Authorization": f"Bearer {access_token}",
    "accept": "application/json",
}
PLACEHOLDER_POSTER = "https://via.placeholder.com/500x750?text=No+Poster"

dataset = pickle.load(open("movies.pkl", "rb"))
similarity = pickle.load(open("similarity.pkl", "rb"))
movie_list = dataset["title"].tolist()

# Reuse one client instead of opening a new connection per request
client = httpx.Client(headers=headers, timeout=10.0)


def fetch_movie_details(movie_id, retries=4):
    """Returns {'poster': str, 'link': str} — poster URL and a link to the movie's
    IMDb page (falls back to its TMDB page if no imdb_id is available)."""
    tmdb_fallback_link = f"https://www.themoviedb.org/movie/{movie_id}"

    for attempt in range(retries):
        try:
            res = client.get(base_url + f"{movie_id}")
            res.raise_for_status()
            data = res.json()

            poster_path = data.get("poster_path")
            poster = poster_base_url + poster_path if poster_path else PLACEHOLDER_POSTER

            imdb_id = data.get("imdb_id")
            link = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else tmdb_fallback_link

            return {"poster": poster, "link": link}
        except httpx.HTTPError as e:
            print(f"Attempt {attempt + 1} failed for movie {movie_id}: {e}")
            time.sleep(0.5)  # brief backoff before retry

    print(f"Giving up on movie {movie_id} after {retries} attempts")
    return {"poster": PLACEHOLDER_POSTER, "link": tmdb_fallback_link}


def get_recommendations(movie_title: str):
    matches = dataset[dataset["title"] == movie_title]
    if matches.empty:
        raise HTTPException(status_code=404, detail="Movie not found in dataset")

    movie_index = matches.index[0]
    distances = similarity[movie_index]
    movies_list = sorted(list(enumerate(distances)), reverse=True, key=lambda x: x[1])[1:6]

    recommended = []
    for movie in movies_list:
        idx = movie[0]
        title = dataset.iloc[idx]["title"]
        movie_id = dataset.iloc[idx]["id"]
        details = fetch_movie_details(movie_id)
        recommended.append({"title": title, "poster": details["poster"], "link": details["link"]})
    return recommended


# ---------------------------------------------------------------------------
# Optional Gradio UI — still mounted at /gradio if you want to use it too
# ---------------------------------------------------------------------------

def build_cards_html(movies):
    cards = ""
    for m in movies:
        safe_title = m["title"].replace('"', "&quot;")
        cards += f"""
        <a class="movie-card" href="{m['link']}" target="_blank" rel="noopener noreferrer">
            <img src="{m['poster']}" alt="{safe_title}" class="movie-poster"
                 onerror="this.onerror=null;this.src='{PLACEHOLDER_POSTER}';">
            <div class="movie-title">{m['title']}</div>
        </a>
        """
    return f"""
    <style>
        .movie-grid {{ display: flex; flex-wrap: wrap; gap: 20px; padding: 10px 0; }}
        .movie-card {{ display: block; width: 180px; border-radius: 10px; overflow: hidden; background: #ffffff;
            border: 1px solid #e0e0e0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s ease, box-shadow 0.2s ease; text-decoration: none; }}
        .movie-card:hover {{ transform: translateY(-6px); box-shadow: 0 6px 16px rgba(0,0,0,0.15); }}
        .movie-poster {{ width: 100%; height: 270px; object-fit: cover; display: block; }}
        .movie-title {{ padding: 10px 8px; font-size: 14px; font-weight: 600; color: #1a1a1a;
            text-align: center; line-height: 1.3; }}
    </style>
    <div class="movie-grid">{cards}</div>
    """


def gradio_recommend(movie_title):
    return build_cards_html(get_recommendations(movie_title))


with gr.Blocks() as gradio_ui:
    gr.Markdown("# 🎬 Movie Recommendation System (Gradio UI)")
    movie_dropdown = gr.Dropdown(choices=movie_list, label="Select Movie", value=movie_list[0])
    recommend_button = gr.Button("Recommend")
    gradio_output = gr.HTML()
    recommend_button.click(fn=gradio_recommend, inputs=movie_dropdown, outputs=gradio_output)


# ---------------------------------------------------------------------------
# FastAPI app — serves the custom index.html frontend + JSON API, mounts Gradio
# ---------------------------------------------------------------------------

app = FastAPI(title="TMDB Movie Recommender API")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/movies")
def api_movies():
    """Returns the full list of movie titles for the dropdown/search box."""
    return {"movies": movie_list}


@app.get("/api/recommend")
def api_recommend(movie: str):
    """Returns TMDB-backed poster + title recommendations for a given movie."""
    return {"recommendations": get_recommendations(movie)}


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Gradio UI still reachable at /gradio if you want it
app = gr.mount_gradio_app(app, gradio_ui, path="/gradio")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7860)