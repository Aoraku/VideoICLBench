# 仅本地/旧脚本从 backend/ 目录构建时使用。
# 正式部署请用仓库根目录的 Dockerfile（docker-compose.yml 已指向根目录）。
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
