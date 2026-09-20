import os
import pickle
from dotenv import load_dotenv

import httpx

load_dotenv()
dataset = pickle.load(open("movies.pkl", "rb"))
api_key = os.getenv("TMDB_API_KEY")
access_token = os.getenv("TMDB_ACCESS_TOKEN")
base_url = "https://api.themoviedb.org/3/movie/"
headers = {
    "Authorization": f"Bearer {access_token}",
}

movie_id = dataset.iloc[29]["id"]
print("movie id: ", movie_id)

try:
    res = httpx.get(base_url + f"{movie_id}", headers=headers)
    res.raise_for_status()
    print(res.json())
except httpx.HTTPStatusError as e:
    print(f"HTTP error {e.response.status_code}: {e.response.text}")
except httpx.HTTPError as e:
    print(e)