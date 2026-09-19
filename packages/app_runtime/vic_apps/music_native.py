"""Render the upstream Music Django templates against an isolated library."""

from types import SimpleNamespace as Record
from functools import lru_cache
from django.conf import settings
from django.core.paginator import Paginator
from django.http import QueryDict
from django.template import Context, Engine
from django.urls import path, set_script_prefix
from vic.config import ROOT


def unused_view(request, **kwargs):
    raise RuntimeError("Music routes are served by the application worker")


urlpatterns = [
    path("", unused_view, name="song_list"),
    path("songs/<str:id>/", unused_view, name="song_detail"),
    path("artists/", unused_view, name="artist_list"),
    path("artists/<str:id>/", unused_view, name="artist_detail"),
    path("search/", unused_view, name="search"),
    path("library/", unused_view, name="music_library"),
    path("playlists/", unused_view, name="music_playlists"),
    path("comments/<str:id>/delete/", unused_view, name="delete_comment"),
]


@lru_cache
def engine():
    if not settings.configured:
        settings.configure(
            ROOT_URLCONF=__name__, USE_I18N=False, USE_TZ=True,
            STATIC_URL="/native-assets/music/", INSTALLED_APPS=[],
        )
        import django
        django.setup()
    return Engine(
        dirs=[str(ROOT / "apps/music/blog/templates")],
        libraries={"static": "django.templatetags.static"},
    )


def render_music(run_id, state, route, query_string=""):
    renderer = engine()
    set_script_prefix(f"/native/music/{run_id}/")
    query = QueryDict(query_string)
    artists, songs = [], []
    for i, item in enumerate(state["items"]):
        artist = Record(id=f"artist-{i}", name=item["artist"], pure_name=item["artist"],
                        description="独立音乐人，以细腻的旋律记录生活。", image=f"/native-assets/music/cover-{i}.svg", url="#")
        artists.append(artist)
        songs.append(Record(**{
            **item, "image": f"/native-assets/music/cover-{i}.svg",
            "artists": Record(all=lambda artist=artist: [artist]),
            "date": f"{item['year']}-01-15T12:00:00", "url": "#",
            "description": "收录于独立音乐精选集。原声与电子乐器交织，呈现轻松、安静的听觉氛围。",
            "label": state["domain"]["objects"][item["id"]]["label"],
        }))
    if state["task_id"] == 17:
        songs[0].id = "target"
        songs[0].name = state["outputs"].get("target", state["source"]["text"])
    context = dict(benchmark=True, benchmark_run=run_id, benchmark_state=state,
                   songs=songs, artists=artists, comments=[], lyrics=[],
                   request=Record(path=route, GET=query, resolver_match=Record(url_name="song_list")))
    template = "blog/song_list.html"
    rows = songs
    if route.startswith("songs/"):
        context["song"] = next((s for s in songs if s.id == route.split("/")[1]), None)
        if context["song"] is None:
            raise ValueError("Song not found")
        template = "blog/song_detail.html"
    elif route == "artists/":
        template = "blog/artist_list.html"
        rows = artists
    elif route.startswith("artists/"):
        context["artist"] = next((a for a in artists if a.id == route.split("/")[1]), None)
        if context["artist"] is None:
            raise ValueError("Artist not found")
        context["songs"] = [s for s in songs if s.artists.all()[0].id == context["artist"].id]
        template = "blog/artist_detail.html"
    elif route == "search/":
        template = "blog/search_results.html"
        term = query.get("q", "")
        kind = query.get("type", "song")
        rows = [s for s in (artists if kind == "artist" else songs) if term.lower() in s.name.lower()]
        context.update(query=term, search_type=kind, total_results=len(rows), time_taken="0.01")
    elif route in ("library/", "playlists/"):
        template = "blog/benchmark_library.html"
        context["playlist_page"] = route == "playlists/"
        ordered = state["domain"]["orders"]["main"]
        if route == "playlists/" and state["task_id"] != 18:
            songs = [s for s in songs if s.id in state["domain"]["collections"]["list-a"]]
        context["songs"] = sorted(songs, key=lambda s: ordered.index(s.id) if s.id in ordered else -1)
    elif route:
        raise ValueError("Page not found")
    context["request"].resolver_match.url_name = template.split("/")[-1].removesuffix(".html")
    context["page_obj"] = Paginator(rows, 12).get_page(query.get("page", 1))
    return renderer.get_template(template).render(Context(context))
