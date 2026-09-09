from django.shortcuts import render, get_object_or_404, redirect
from .models import Song, Artist, Comment
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import models
import ast
import time
import json
# Create your views here.

# page: song_list(main page)
def song_list(request):
    song_queryset = Song.objects.all()
    paginator = Paginator(song_queryset, 36)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'blog/song_list.html', {'page_obj': page_obj})

# page: song_detail(with comments)
def song_detail(request, song_id):
    song = get_object_or_404(Song, id=song_id)

    lyrics_list = ast.literal_eval(song.lyrics)
    if lyrics_list == ['']:
        lyrics_list = ['抱歉，本歌曲在网易云中暂无歌词:(']
    
    # view comments
    comments = song.comments.order_by('-created_at')
    
    # post new comment
    if request.method == 'POST':
        content = request.POST.get('content')
        if content:
            Comment.objects.create(song=song, content=content)
            return redirect('song_detail', song_id=song_id)

    return render(request, 'blog/song_detail.html', {
        'song': song,
        'lyrics': lyrics_list,
        'comments': comments,
    })

# function: delete comment (we need an independent function for this)
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    song_id = comment.song.id
    comment.delete()
    return redirect('song_detail', song_id=song_id)

# page: artist_list
def artist_list(request):
    artist_queryset = Artist.objects.all()
    paginator = Paginator(artist_queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'blog/artist_list.html', {'page_obj': page_obj})

# page: artist_detail
def artist_detail(request, artist_id):
    artist = get_object_or_404(Artist, id=artist_id)
    songs = artist.songs.all()
    return render(request, 'blog/artist_detail.html', {
        'artist': artist,
        'songs': songs,
    })

# page: search
def search(request):
    query = request.GET.get('q', '').strip()
    # search_type = request.GET.get('type', 'song')
    search_type = request.GET.get('type')
    results = []
    time_taken = 0

    if query:
        start = time.time()
        if search_type == 'song':
            results = Song.objects.filter(
                models.Q(name__icontains=query) |
                models.Q(pure_name__icontains=query) |
                models.Q(lyrics__icontains=query) |
                models.Q(artists__name__icontains=query)
            ).distinct()
        else:
            results = Artist.objects.filter(
                models.Q(name__icontains=query) |
                models.Q(description__icontains=query)
            )
        time_taken = round(time.time() - start, 3)

    paginator = Paginator(results, 36)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'blog/search_results.html', {
        'query': query,
        'search_type': search_type,
        'page_obj': page_obj,
        'time_taken': time_taken,
        'total_results': paginator.count,
    })