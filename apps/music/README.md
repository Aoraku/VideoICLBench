# VIC-Music

VIC-Music 是一个基于 Django 的音乐浏览与搜索网站，包含歌曲列表、歌手列表、歌曲详情、歌手详情、搜索和评论功能。

本仓库整理自课程 Project1，保留原有 Django 项目结构和业务逻辑，仅将页面中的封面图片引用从本地静态图片目录改为数据库中已有的在线图片 URL，以减少仓库体积。

## 技术栈

- Python 3.12
- Django 5.2
- SQLite
- Bootstrap 模板页面

## 目录结构

```text
.
├── blog/                 # 音乐网站应用
│   ├── migrations/       # Django 迁移文件
│   ├── templates/blog/   # 页面模板
│   ├── artist_info.json  # 歌手数据
│   ├── song_info.json    # 歌曲数据
│   ├── import_data.py    # 数据导入脚本
│   ├── models.py
│   ├── urls.py
│   └── views.py
├── Project1/             # Django 项目配置
├── db.sqlite3            # 已初始化的示例数据库
├── manage.py
├── Dockerfile
└── docker-compose.yml
```

## 本地运行

```bash
pip install -r requirements.txt
python manage.py runserver 0.0.0.0:8000
```

访问：

- 网站首页：http://localhost:8000/
- Django Admin：http://localhost:8000/admin/

## Docker 运行

```bash
docker compose up --build
```

访问：http://localhost:8000/

## 数据说明

仓库保留了 `db.sqlite3` 作为可直接运行的示例数据库。`static/song_image/` 和 `static/artist_image/` 不再需要进入仓库，页面会直接使用 `Song.image` 和 `Artist.image` 字段中的在线图片地址。

如果需要重新导入数据，可以先执行迁移，再在 `blog` 目录下运行导入脚本：

```bash
python manage.py migrate
cd blog
python import_data.py
```
