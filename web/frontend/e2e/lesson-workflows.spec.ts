import { expect, test, type Page } from "@playwright/test";

const JOB_ID = "01J00000000000000000000000";

function job(status = "COMPLETED") {
  return {
    jobId: JOB_ID,
    mode: "GENERATE",
    status,
    subject: "化学",
    grade: "高二",
    topic: "官能团",
    durationMinutes: 45,
    currentStage: status === "COMPLETED" ? "finalize" : "critics",
    currentRound: 2,
    progressPercent: status === "RUNNING" ? 52 : 100,
    pipelineStatus: status.toLowerCase(),
    stopReason: status === "NEEDS_HUMAN" ? "rewrite_failed" : "quality_passed",
    bestVersionId: "v1",
    lastVersionId: "v1",
    errorCode: null,
    errorMessage: status === "FAILED" ? "模型服务暂时不可用，请稍后重试" : null,
    usage: {
      modelCallCount: 12,
      inputTokens: 42000,
      outputTokens: 8000,
      estimatedCost: 0.08,
    },
    createdAt: "2026-09-11T07:00:00Z",
    startedAt: "2026-09-11T07:00:01Z",
    finishedAt: status === "RUNNING" ? null : "2026-09-11T07:05:00Z",
    updatedAt: "2026-09-11T07:05:00Z",
    links: { self: "", events: "", result: "", artifacts: "" },
  };
}

const result = {
  jobId: JOB_ID,
  status: "COMPLETED",
  stopReason: "quality_passed",
  bestVersionId: "v1",
  lastVersionId: "v1",
  bestLessonPlan: {
    metadata: {
      subject: "化学",
      grade: "高二",
      topic: "官能团",
      duration_minutes: 45,
    },
    design_thesis: "以结构证据解释性质差异。",
    driving_question: "结构如何决定性质？",
    learning_objectives: [
      {
        objective_id: "obj-1",
        description: "能依据结构识别官能团",
        evidence_of_achievement: "完成分类并说明依据",
      },
    ],
    procedure_steps: [
      {
        step_id: "step-1",
        stage: "证据分类",
        duration_minutes: 15,
        teacher_actions: ["提供分子结构卡片"],
        student_actions: ["分类并陈述证据"],
        assessment: "分类理由",
      },
    ],
  },
  scores: {
    curriculumAlignment: 8,
    knowledgeAccuracy: 9,
    teachingLogic: 8,
    classroomFeasibility: 8.2,
    differentiatedInstruction: 7.8,
    studentEngagement: 8.1,
    assessmentDesign: 8.3,
    languageAndFormat: 8.4,
  },
  overallScore: 8.3,
  scoreNotice: "内部质量信号，不代表正式教学效果评价",
  changes: [
    {
      summary: "补充了结构—性质证据链",
      targetPath: "/procedure_steps/0",
      sourceCritiqueIds: ["ped-001"],
    },
  ],
  unresolvedIssues: [],
  parseWarnings: [],
};

test.beforeEach(async ({ page }) => {
  // Keep long-running JobView tests inside the browser contract boundary. The
  // stream closes after one real SSE frame and advertises a long reconnect delay.
  await page.route("**/api/v1/lesson-jobs/*/events", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `retry: 60000\nevent: job.progress\ndata: ${JSON.stringify({
        sequence: 1,
        eventType: "job.progress",
        stage: "critics",
        roundIndex: 2,
        versionId: "v1",
        progressPercent: 52,
        message: "三类 Critic 正在独立审阅",
        occurredAt: "2026-09-11T07:02:00Z",
      })}\n\n`,
    }),
  );
});

async function mockTerminal(page: Page, status = "COMPLETED") {
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job(status) }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({ json: { ...result, status } }),
  );
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/artifacts`, (route) =>
    route.fulfill({
      json: [
        {
          artifactId: "01J00000000000000000000001",
          type: status === "FAILED" ? "RECOVERY_MARKDOWN" : "BEST_DOCX",
          displayName:
            status === "FAILED" ? "recovery.md" : "best_lesson_plan.docx",
          mediaType: "application/octet-stream",
          sizeBytes: 1024,
          sha256: "a".repeat(64),
          downloadUrl: `/download/${status.toLowerCase()}`,
        },
      ],
    }),
  );
}

test("dashboard presents both MVP entry points on a real browser", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs**", (route) =>
    route.fulfill({
      json: { items: [], page: 0, size: 12, totalElements: 0, totalPages: 0 },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /把课程设想变成/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "从零生成" }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "上传 Word 优化" }).first(),
  ).toBeVisible();
});

test("three required fields create a generate job and open real progress", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs/generate", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload).toMatchObject({
      subject: "化学",
      grade: "高二",
      topic: "官能团",
    });
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    await route.fulfill({
      status: 202,
      json: {
        jobId: JOB_ID,
        status: "QUEUED",
        createdAt: "2026-09-11T07:00:00Z",
        links: {},
      },
    });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job("RUNNING") }),
  );
  await page.goto("/create/generate");
  await page.getByPlaceholder("如：高中化学").fill("化学");
  await page.getByPlaceholder("如：高二").fill("高二");
  await page.getByPlaceholder("如：官能团与有机物性质的关系").fill("官能团");
  await page.getByRole("button", { name: "开始生成教案" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${JOB_ID}$`));
  await expect(page.getByText("三类 Critic 正在独立审阅")).toBeVisible();
});

test("completed and needs-human outcomes remain semantically distinct", async ({
  page,
}) => {
  await mockTerminal(page, "COMPLETED");
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "教案闭环已完成" }),
  ).toBeVisible();
  await expect(page.locator(".connection-indicator")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "下载 Word" })).toHaveAttribute(
    "href",
    "/download/completed",
  );
  await expect(page.getByText("这些分数用于管线内部选优和路由")).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  await mockTerminal(page, "NEEDS_HUMAN");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "已形成版本，建议教师复核" }),
  ).toBeVisible();
  await expect(page.getByText("改写环节未能可靠完成")).toBeVisible();
});

test("failed run never renders a fabricated lesson and exposes recovery", async ({
  page,
}) => {
  await mockTerminal(page, "FAILED");
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/result`, (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/problem+json",
      json: { code: "RESULT_NOT_READY", detail: "任务尚未形成可展示版本" },
    }),
  );
  await page.goto(`/jobs/${JOB_ID}`);
  await expect(
    page.getByRole("heading", { name: "本次任务未完整完成" }),
  ).toBeVisible();
  await expect(page.getByText("没有可展示的完整版本")).toBeVisible();
  await expect(page.getByText("不会用空白或硬编码教案冒充结果")).toBeVisible();
  await expect(page.getByRole("link", { name: /recovery.md/ })).toHaveAttribute(
    "href",
    "/download/failed",
  );
});

test("optimize validates a DOCX and submits metadata with the original file", async ({
  page,
}) => {
  await page.route("**/api/v1/lesson-jobs/optimize", async (route) => {
    expect(route.request().headers()["content-type"]).toContain(
      "multipart/form-data",
    );
    expect(
      route.request().postDataBuffer()?.includes(Buffer.from("lesson.docx")),
    ).toBeTruthy();
    await route.fulfill({
      status: 202,
      json: {
        jobId: JOB_ID,
        status: "QUEUED",
        createdAt: "2026-09-11T07:00:00Z",
        links: {},
      },
    });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) =>
    route.fulfill({ json: job("RUNNING") }),
  );
  await page.goto("/create/optimize");
  await page.locator("input[type=file]").setInputFiles({
    name: "lesson.docx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from([0x50, 0x4b, 0x03, 0x04, 0x01]),
  });
  await page.getByPlaceholder("如：高中化学").fill("化学");
  await page.getByPlaceholder("如：高二").fill("高二");
  await page.getByPlaceholder("如：官能团与有机物性质的关系").fill("官能团");
  await page.getByRole("button", { name: "开始优化教案" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${JOB_ID}$`));
});

test("SSE failure visibly falls back to two-second detail polling", async ({
  page,
}) => {
  let detailCalls = 0;
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}`, (route) => {
    detailCalls += 1;
    return route.fulfill({ json: job("RUNNING") });
  });
  await page.route(`**/api/v1/lesson-jobs/${JOB_ID}/events`, (route) =>
    route.abort("failed"),
  );

  await page.goto(`/jobs/${JOB_ID}`);
  await expect(page.getByText("轮询同步")).toBeVisible();
  await expect
    .poll(() => detailCalls, { timeout: 4_500 })
    .toBeGreaterThanOrEqual(2);
});

test("generate form remains keyboard-usable with reduced motion requested", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/create/generate");
  const subject = page.getByPlaceholder("如：高中化学");
  await subject.focus();
  await subject.fill("化学");
  await page.keyboard.press("Tab");
  await expect(page.getByPlaceholder("如：高二")).toBeFocused();
  await expect
    .poll(() =>
      page.evaluate(
        () => matchMedia("(prefers-reduced-motion: reduce)").matches,
      ),
    )
    .toBe(true);
  const transitionDuration = await page
    .locator(".page-shell")
    .evaluate((element) => getComputedStyle(element).transitionDuration);
  const durationsInMilliseconds = transitionDuration.split(",").map((value) => {
    const duration = value.trim();
    return duration.endsWith("ms")
      ? Number.parseFloat(duration)
      : Number.parseFloat(duration) * 1_000;
  });
  expect(Math.max(...durationsInMilliseconds)).toBeLessThanOrEqual(0.01);
});
