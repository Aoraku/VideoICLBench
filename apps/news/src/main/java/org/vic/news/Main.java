package org.vic.news;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));
        NewsServer server = new NewsServer(port, new NewsClient(), new SummaryService());
        server.start();
    }
}
