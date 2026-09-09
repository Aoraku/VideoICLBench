import os
import sys
import subprocess
import time
import webbrowser
import threading

def run_backend():
    """启动后端服务"""
    print("正在启动后端服务...")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # 检查是否已安装所需依赖
    try:
        import fastapi
        import uvicorn
    except ImportError:
        print("正在安装所需依赖...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]"])
    
    # 启动后端服务
    backend_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    backend_process = subprocess.Popen(backend_cmd)
    
    # 等待后端服务启动
    print("等待后端服务启动...")
    time.sleep(2)
    
    return backend_process

def run_frontend():
    """启动前端服务"""
    print("正在启动前端服务...")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # 检查是否已安装所需依赖
    try:
        import streamlit
    except ImportError:
        print("正在安装所需依赖...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
    
    # 启动前端服务
    frontend_cmd = [sys.executable, "-m", "streamlit", "run", "app/frontend.py"]
    frontend_process = subprocess.Popen(frontend_cmd)
    
    # 等待前端服务启动
    print("等待前端服务启动...")
    time.sleep(5)
    
    # 打开浏览器
    webbrowser.open("http://localhost:8501")
    
    return frontend_process

def main():
    """主函数"""
    print("=== 在线评测系统启动脚本 ===")
    
    # 启动后端服务
    backend_process = run_backend()
    
    # 启动前端服务
    frontend_process = run_frontend()
    
    print("\n系统已启动!")
    print("- 后端API地址: http://127.0.0.1:8000")
    print("- 前端界面地址: http://localhost:8501")
    print("\n按Ctrl+C停止服务...\n")
    
    try:
        # 等待用户中断
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        backend_process.terminate()
        frontend_process.terminate()
        print("服务已停止!")

if __name__ == "__main__":
    main() 