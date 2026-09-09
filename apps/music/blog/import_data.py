import os
import json
import django
import re
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Project1.settings")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from blog.models import Artist, Song

# clear existing data
Artist.objects.all().delete()
Song.objects.all().delete()

# define a function to purify artist and song names
def extract_pure_name(name):
    name = re.sub(r"[\s\u3000]*（.*）$", "", name)  # 中文括号
    name = re.sub(r"[\s\u3000]*\(.*\)$", "", name)  # 英文括号
    return name.strip()

# load artist_info.json
with open("artist_info.json", "r", encoding="utf-8") as f:
    artists_data = json.load(f)

# create a mapping from pure_name to Artist objects
pure_artist_map = {}
for artist in artists_data:
    original_name = artist["name"]
    pure_name = extract_pure_name(original_name)
    artist_obj = Artist.objects.create(
        name=original_name,
        pure_name=pure_name,
        image=artist["image"],
        url=artist["url"],
        description=artist["description"],
        hot_songs=artist.get("hot_songs", [])
    )
    pure_artist_map[pure_name] = artist_obj

# load song_info.json
with open("song_info.json", "r", encoding="utf-8") as f:
    songs_data = json.load(f)

for song in songs_data:
    artist_names = song["artist"]  # this is a list of artist names

    song_obj = Song.objects.create(
        name=song["name"],
        pure_name=extract_pure_name(song["name"]),
        image=song["image"],
        url=song["url"],
        description=song.get("description", ""),
        date=song.get("date", ""),
        lyrics=song.get("lyrics", "")
    )

    # establish many-to-many relationship with artists
    for pure_name in artist_names:
        artist_obj = pure_artist_map.get(pure_name)
        if artist_obj:
            song_obj.artists.add(artist_obj)
        else:
            print(f"warning: Artist '{pure_name}' not found in artist_info.json, skipping.")

print("Import completed successfully!")
