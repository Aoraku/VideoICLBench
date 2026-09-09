package org.vic.news;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URLDecoder;
import java.util.HashMap;
import java.util.Map;
import java.util.ArrayList;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

final class NewsClient {
    private static final String NEWS_API = "https://api2.newsminer.net/svc/news/queryNewsList";
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    HttpResult query(String rawQuery) throws IOException, InterruptedException {
        String snapshot = System.getenv("VIC_NEWS_SNAPSHOT");
        if (snapshot != null && !snapshot.isBlank()) {
            ObjectMapper mapper = new ObjectMapper();
            var root = mapper.readTree(Files.readString(Path.of(snapshot)));
            Map<String, String> params = new HashMap<>();
            for (String pair : (rawQuery == null ? "" : rawQuery).split("&")) {
                String[] parts = pair.split("=", 2);
                if (parts.length == 2) params.put(URLDecoder.decode(parts[0], StandardCharsets.UTF_8), URLDecoder.decode(parts[1], StandardCharsets.UTF_8));
            }
            String words = params.getOrDefault("words", "").toLowerCase();
            var output = mapper.createArrayNode();
            for (var item : root.path("data")) {
                if ((item.path("title").asText() + " " + item.path("content").asText()).toLowerCase().contains(words)) output.add(item);
            }
            return new HttpResult(200, "application/json; charset=utf-8", mapper.writeValueAsString(Map.of("data", output)));
        }
        String query = withDefaultParams(rawQuery == null ? "" : rawQuery);
        HttpRequest request = HttpRequest.newBuilder(URI.create(NEWS_API + "?" + query))
                .timeout(Duration.ofSeconds(30))
                .GET()
                .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        return new HttpResult(response.statusCode(), "application/json; charset=utf-8", response.body());
    }

    private String withDefaultParams(String query) {
        String result = query;
        result = appendDefault(result, "size", "15");
        result = appendDefault(result, "page", "1");
        result = appendDefault(result, "startDate", "2024-06-20");
        result = appendDefault(result, "endDate", "2024-08-30");
        return result;
    }

    private String appendDefault(String query, String key, String value) {
        if (query.contains(key + "=")) {
            return query;
        }
        String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);
        return query.isBlank() ? key + "=" + encoded : query + "&" + key + "=" + encoded;
    }
}
