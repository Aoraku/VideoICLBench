package org.vic.news;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;

final class NewsServer {
    private static final String[] CATEGORIES = {
            "娱乐", "军事", "教育", "文化", "健康", "财经", "体育", "汽车", "科技", "社会"
    };

    private final int port;
    private final NewsClient newsClient;
    private final SummaryService summaryService;
    private final ObjectMapper mapper = new ObjectMapper();

    NewsServer(int port, NewsClient newsClient, SummaryService summaryService) {
        this.port = port;
        this.newsClient = newsClient;
        this.summaryService = summaryService;
    }

    void start() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        server.createContext("/", this::handleIndex);
        server.createContext("/health", this::handleHealth);
        server.createContext("/api/categories", this::handleCategories);
        server.createContext("/api/news", this::handleNews);
        server.createContext("/api/summarize", this::handleSummary);
        server.setExecutor(null);
        server.start();
        System.out.printf("VIC-News started on http://0.0.0.0:%d/%n", port);
    }

    private void handleIndex(HttpExchange exchange) throws IOException {
        if (isOptions(exchange)) {
            send(exchange, new HttpResult(204, "text/plain", ""));
            return;
        }
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, Map.of("error", "method not allowed"));
            return;
        }
        send(exchange, new HttpResult(200, "text/html; charset=utf-8", indexHtml()));
    }

    private void handleHealth(HttpExchange exchange) throws IOException {
        if (isOptions(exchange)) {
            send(exchange, new HttpResult(204, "text/plain", ""));
            return;
        }
        sendJson(exchange, 200, Map.of("status", "ok", "service", "VIC-News"));
    }

    private void handleCategories(HttpExchange exchange) throws IOException {
        if (isOptions(exchange)) {
            send(exchange, new HttpResult(204, "text/plain", ""));
            return;
        }
        sendJson(exchange, 200, Map.of("categories", CATEGORIES));
    }

    private void handleNews(HttpExchange exchange) throws IOException {
        if (isOptions(exchange)) {
            send(exchange, new HttpResult(204, "text/plain", ""));
            return;
        }
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, Map.of("error", "method not allowed"));
            return;
        }
        try {
            send(exchange, newsClient.query(exchange.getRequestURI().getRawQuery()));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            sendJson(exchange, 500, Map.of("error", "news request interrupted"));
        } catch (Exception e) {
            sendJson(exchange, 502, Map.of("error", "news upstream request failed", "message", e.getMessage()));
        }
    }

    private void handleSummary(HttpExchange exchange) throws IOException {
        if (isOptions(exchange)) {
            send(exchange, new HttpResult(204, "text/plain", ""));
            return;
        }
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, Map.of("error", "method not allowed"));
            return;
        }
        try {
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            JsonNode node = mapper.readTree(body);
            String title = node.path("title").asText("");
            String content = node.path("content").asText("");
            if (title.isBlank() || content.isBlank()) {
                sendJson(exchange, 400, Map.of("error", "title and content are required"));
                return;
            }
            send(exchange, summaryService.summarize(title, content));
        } catch (Exception e) {
            sendJson(exchange, 500, Map.of("error", "summary request failed", "message", e.getMessage()));
        }
    }

    private boolean isOptions(HttpExchange exchange) {
        return "OPTIONS".equalsIgnoreCase(exchange.getRequestMethod());
    }

    private void sendJson(HttpExchange exchange, int statusCode, Object value) throws IOException {
        send(exchange, new HttpResult(statusCode, "application/json; charset=utf-8", mapper.writeValueAsString(value)));
    }

    private void send(HttpExchange exchange, HttpResult result) throws IOException {
        byte[] bytes = result.body().getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", result.contentType());
        exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
        exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
        exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
        exchange.sendResponseHeaders(result.statusCode(), bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private String indexHtml() {
        return """
                <!doctype html>
                <html lang=\"zh-CN\">
                <head>
                  <meta charset=\"utf-8\">
                  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
                  <title>VIC-News</title>
                  <style>
                    body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f6f7f9;color:#18212f}
                    header{background:#18212f;color:white;padding:24px 32px}
                    main{max-width:1040px;margin:24px auto;padding:0 20px}
                    form{display:grid;grid-template-columns:1fr 160px 120px;gap:12px;margin-bottom:20px}
                    input,select,button{font:inherit;padding:10px 12px;border:1px solid #c9ced6;border-radius:6px;background:white}
                    button{background:#2454d6;color:white;border-color:#2454d6;cursor:pointer}
                    article{background:white;border:1px solid #dde2ea;border-radius:8px;padding:18px;margin:14px 0}
                    .meta{color:#667085;font-size:14px;margin:6px 0 12px}
                    .content{line-height:1.7;white-space:pre-wrap}
                  </style>
                </head>
                <body>
                  <header><h1>VIC-News</h1></header>
                  <main>
                    <form id=\"searchForm\">
                      <input name=\"words\" placeholder=\"关键词\">
                      <select name=\"categories\">
                        <option value=\"\">全部分类</option>
                        <option>娱乐</option><option>军事</option><option>教育</option><option>文化</option><option>健康</option>
                        <option>财经</option><option>体育</option><option>汽车</option><option>科技</option><option>社会</option>
                      </select>
                      <button>搜索</button>
                    </form>
                    <section id=\"results\"></section>
                  </main>
                  <script>
                    const form = document.querySelector('#searchForm');
                    const results = document.querySelector('#results');
                    form.addEventListener('submit', async (event) => {
                      event.preventDefault();
                      const params = new URLSearchParams(new FormData(form));
                      params.set('size', '10');
                      const response = await fetch('/api/news?' + params.toString());
                      const data = await response.json();
                      const items = data.data || [];
                      results.innerHTML = items.map(item => `
                        <article>
                          <h2>${escapeHtml(item.title || '')}</h2>
                          <div class=\"meta\">${escapeHtml(item.publisher || '')} · ${escapeHtml(item.publishTime || '')}</div>
                          <div class=\"content\">${escapeHtml((item.content || '').slice(0, 480))}</div>
                        </article>
                      `).join('');
                    });
                    function escapeHtml(value) {
                      return value.replace(/[&<>\"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[ch]));
                    }
                    form.dispatchEvent(new Event('submit'));
                  </script>
                </body>
                </html>
                """;
    }
}
