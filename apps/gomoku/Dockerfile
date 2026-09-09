FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential cmake git \
    libsdl2-dev libsdl2-ttf-dev \
    xvfb x11vnc novnc websockify x11-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. 把本地所有文件（包括你正确的 entrypoint.sh 和字体）复制到容器中
COPY . .

# 2. 编译项目
RUN mkdir build && cd build && cmake .. && make

# 3. 将刚才复制进来的 entrypoint.sh 移到根目录，并赋予执行权限
RUN cp entrypoint.sh /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 6080
ENTRYPOINT ["/entrypoint.sh"]