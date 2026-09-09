FROM gradle:8.5-jdk17 AS build

WORKDIR /app

COPY build.gradle.kts settings.gradle.kts ./
COPY gradle ./gradle
COPY src ./src

RUN gradle --no-daemon clean installDist

FROM eclipse-temurin:17-jre

WORKDIR /app

COPY --from=build /app/build/install/vic-news ./

ENV PORT=8080
EXPOSE 8080

CMD ["bin/vic-news"]
