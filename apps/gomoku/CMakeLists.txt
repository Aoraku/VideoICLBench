cmake_minimum_required(VERSION 3.10)
project(GomokuBenchmark)

set(CMAKE_CXX_STANDARD 11)

# 查找 SDL2 库
find_package(SDL2 REQUIRED)

# 添加你的源文件
add_executable(gomoku_benchmark main.cpp)

# 链接 SDL2 和 SDL2_ttf
target_link_libraries(gomoku_benchmark SDL2::SDL2 SDL2_ttf)