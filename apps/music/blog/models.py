from django.db import models

# Create your models here.

class Artist(models.Model):
    name = models.CharField(max_length=100)
    pure_name = models.CharField(max_length=100) # 使用name和pure_name字段来区分原始含括号名和去掉别名后的歌手/歌曲名
    image = models.URLField()
    url = models.URLField()
    description = models.TextField()
    hot_songs = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name
    def image_filename(self):
        return self.url.split('=')[-1] + ".jpg"

class Song(models.Model):
    name = models.CharField(max_length=200)
    pure_name = models.CharField(max_length=200)
    artists = models.ManyToManyField(Artist, related_name='songs')
    image = models.URLField()
    url = models.URLField()
    description = models.TextField(blank=True)
    date = models.CharField(max_length=50, blank=True)
    lyrics = models.TextField(blank=True)

    def __str__(self):
        return self.name
    def image_filename(self):
        return self.url.split('=')[-1] + ".jpg"

class Comment(models.Model):
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)