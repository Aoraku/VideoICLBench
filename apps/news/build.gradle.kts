import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("java")
    id("application")
}

group = "org.vic.news"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.0"))
    testImplementation("org.junit.jupiter:junit-jupiter")

    implementation("cn.bigmodel.openapi:oapi-java-sdk:release-V4-2.0.2")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}

tasks.test {
    useJUnitPlatform()
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

application {
    mainClass.set("org.vic.news.Main")
    applicationName = "vic-news"
}