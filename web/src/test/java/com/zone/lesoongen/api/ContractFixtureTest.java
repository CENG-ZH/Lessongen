package com.zone.lesoongen.api;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;

import com.zone.lesoongen.api.dto.LessonRequests;
import com.zone.lesoongen.infrastructure.engine.EngineContracts;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ContractFixtureTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private final Path fixtures = Path.of("specs", "001-lesson-plan-web", "contracts", "fixtures");

    @Test
    void publicCamelCaseFixturesStayReadable() throws Exception {
        LessonRequests.Generate request = mapper.readValue(
                Files.readString(fixtures.resolve("public-generate-request.json")),
                LessonRequests.Generate.class);
        JsonNode accepted = mapper.readTree(
                Files.readString(fixtures.resolve("public-job-accepted.json")));

        assertEquals("官能团与有机物性质", request.topic());
        assertEquals(45, request.durationMinutes());
        assertEquals("QUEUED", accepted.get("status").asText());
        assertTrue(accepted.get("links").get("events").asText().endsWith("/events"));
    }

    @Test
    void internalSnakeCaseFixturesStayReadableByJavaAdapter() throws Exception {
        EngineContracts.CreateRequest request = mapper.readValue(
                Files.readString(fixtures.resolve("engine-generate-request.json")),
                EngineContracts.CreateRequest.class);
        EngineContracts.Accepted accepted = mapper.readValue(
                Files.readString(fixtures.resolve("engine-run-accepted.json")),
                EngineContracts.Accepted.class);

        assertEquals("01J00000000000000000000000", request.externalJobId());
        assertEquals(45, request.task().durationMinutes());
        assertEquals("20260911-070000-化学-高二-官能团-000001", accepted.engineRunId());
    }
}
