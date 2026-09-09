from django.urls import path
from . import views

urlpatterns = [
    path('', views.song_list, name='song_list'),
    path('song/<int:song_id>/', views.song_detail, name='song_detail'),
    path('comment/delete/<int:comment_id>/', views.delete_comment, name='delete_comment'),
    path('artists/', views.artist_list, name='artist_list'),
    path('artist/<int:artist_id>/', views.artist_detail, name='artist_detail'),
    path('search/', views.search, name='search'),
]