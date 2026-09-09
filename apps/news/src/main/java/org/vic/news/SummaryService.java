package org.vic.news;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zhipu.oapi.ClientV4;
import com.zhipu.oapi.Constants;
import com.zhipu.oapi.service.v4.model.ChatCompletionRequest;
import com.zhipu.oapi.service.v4.model.ChatMessage;
import com.zhipu.oapi.service.v4.model.ChatMessageRole;
import com.zhipu.oapi.service.v4.model.ModelApiResponse;

import java.util.List;
import java.util.Map;

final class SummaryService {
    private final ObjectMapper mapper = new ObjectMapper();

    HttpResult summarize(String title, String content) throws Exception {
        String apiKey = System.getenv("GLM_API_KEY");
        if (apiKey == null || apiKey.isBlank()) {
            return new HttpResult(503, "application/json; charset=utf-8",
                    mapper.writeValueAsString(Map.of("error", "GLM_API_KEY is not set")));
        }

        String model = System.getenv("GLM_MODEL");
        if (model == null || model.isBlank()) {
            model = Constants.ModelChatGLM4;
        }
        ClientV4 client = new ClientV4.Builder(apiKey).build();
        ChatMessage message = new ChatMessage(ChatMessageRole.USER.value(), prompt(title, content));
        ChatCompletionRequest request = ChatCompletionRequest.builder()
                .model(model)
                .stream(Boolean.FALSE)
                .invokeMethod(Constants.invokeMethod)
                .messages(List.of(message))
                .requestId("vic-news-" + System.currentTimeMillis())
                .build();
        ModelApiResponse response = client.invokeModelApi(request);
        return new HttpResult(200, "application/json; charset=utf-8", mapper.writeValueAsString(response));
    }

    private String prompt(String title, String content) {
        return """
                请为下面这条新闻生成中文摘要。
                要求：
                1. 保留关键事实、人物、地点和时间。
                2. 控制在 120 字以内。
                3. 不要添加原文没有的信息。

                标题：%s

                正文：
                %s
                """.formatted(title, content);
    }
}
