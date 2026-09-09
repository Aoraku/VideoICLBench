# VIC-News

VIC-News 是一个基于 Java 17 的新闻查询与摘要服务，整理自 2025 Java 小学期新闻 App 大作业材料和 GLM 调用 demo。

原始作业目标是 Android 新闻客户端；本仓库将其改写为可 Docker 化运行的轻量 HTTP 服务，便于后续作为 VIC benchmark 的一个自建平台组件。

## 功能

- `GET /`：简单网页入口
- `GET /health`：健康检查
- `GET /api/categories`：返回新闻分类
- `GET /api/news`：代理 NewsMiner 新闻查询接口
- `POST /api/summarize`：调用 GLM 为新闻生成摘要

新闻查询参数与课程接口保持一致：

- `size`
- `startDate`
- `endDate`
- `words`
- `categories`
- `page`

分类包括：娱乐、军事、教育、文化、健康、财经、体育、汽车、科技、社会。

## 本地运行

```bash
./gradlew run
```

Windows PowerShell：

```powershell
.\gradlew.bat run
```

访问：

- 首页：http://localhost:8080/
- 健康检查：http://localhost:8080/health
- 新闻查询：http://localhost:8080/api/news?words=拜登&categories=科技&page=1&size=10

## Docker 运行

```bash
docker compose up --build
```

访问：http://localhost:8080/

## GLM 摘要

摘要接口需要设置 `GLM_API_KEY`：

```bash
GLM_API_KEY=your_key docker compose up --build
```

Windows PowerShell：

```powershell
$env:GLM_API_KEY="your_key"
docker compose up --build
```

请求示例：

```bash
curl -X POST http://localhost:8080/api/summarize ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"新闻标题\",\"content\":\"新闻正文\"}"
```

未设置 `GLM_API_KEY` 时，摘要接口会返回明确错误，不生成假摘要。
