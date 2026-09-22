FROM eclipse-temurin:17-jdk AS build

WORKDIR /app
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
COPY src/ src/
RUN chmod +x ./mvnw && ./mvnw -B -ntp -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/Lesoongen-*.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
