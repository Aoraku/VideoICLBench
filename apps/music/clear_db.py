import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Project1.settings")
django.setup()

from blog.models import Artist, Song  # 若你还有 Comment 模型请加上

# 删除顺序要注意 ForeignKey 或 ManyToMany 依赖
print("Clearing all data...")

Song.objects.all().delete()
Artist.objects.all().delete()

# 如果你有评论模型：
# Comment.objects.all().delete()

print("All data cleared.")
