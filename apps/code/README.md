# VIC-Code

VIC-Code 是一个简易在线评测系统，包含题目管理、用户登录、提交评测、语言管理、日志查看、数据导入导出和特殊评测等功能。

本仓库整理自课程 Project2，保留原有 FastAPI 后端、Streamlit 前端、测试用例和核心评测逻辑，仅补充仓库说明、忽略规则和 Docker 运行配置。

## 技术栈

- Python 3.12
- FastAPI + Uvicorn
- Streamlit
- SQLModel + SQLite
- Pytest

## 目录结构

```text
.
├── app/
│   ├── routes/           # API 路由
│   ├── database.py       # 数据库初始化
│   ├── frontend.py       # Streamlit 前端
│   ├── judge.py          # 判题逻辑
│   ├── main.py           # FastAPI 入口
│   ├── models.py         # 数据模型
│   └── spj.py            # 特殊评测
├── tests/                # API 测试
├── start.py              # 本地双服务启动脚本
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

分别启动后端和前端：

```bash
uvicorn app.main:app --reload
streamlit run app/frontend.py
```

访问：

- 后端 API：http://localhost:8000/
- API 文档：http://localhost:8000/docs
- 前端页面：http://localhost:8501/

默认初始化管理员：

- 用户名：`admin`
- 密码：`admintestpassword`

## Docker 运行

```bash
docker compose up --build
```

访问：

- 后端 API：http://localhost:8000/
- API 文档：http://localhost:8000/docs
- 前端页面：http://localhost:8501/

## 测试

```bash
python -m pytest tests -v
```

## 数据说明

运行时会在项目根目录生成 `oj.db`。该文件属于本地运行数据，不进入仓库。
