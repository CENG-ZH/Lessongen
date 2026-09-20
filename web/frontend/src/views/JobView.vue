<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { connectJobEvents, getJob } from "../api/client";
import { useConnectionStore } from "../stores/connection";
import { useJobStore } from "../stores/jobs";
import { terminalStatuses, type JobEvent } from "../types/api";
import StatusPill from "../components/StatusPill.vue";
import StageTimeline from "../components/StageTimeline.vue";
import ScorePanel from "../components/ScorePanel.vue";
import LessonPreview from "../components/LessonPreview.vue";
import OptimizationPanel from "../components/OptimizationPanel.vue";

const props = defineProps<{ jobId: string }>();
const router = useRouter();
const store = useJobStore();
const connection = useConnectionStore();
const events = ref<JobEvent[]>([]);
const loadError = ref("");
let stopEvents: (() => void) | undefined;
let polling: number | undefined;
let terminalLoaded = false;
const job = computed(() => store.current);
const terminal = computed(
  () => !!job.value && terminalStatuses.includes(job.value.status),
);
const latestMessage = computed(
  () => events.value.at(-1)?.message || stageMessage(job.value?.currentStage),
);
const primaryArtifact = computed(() =>
  store.artifacts.find((item) => item.type === "BEST_DOCX"),
);
const revisedCandidateArtifact = computed(() =>
  store.artifacts.find((item) => item.type === "REVISED_CANDIDATE_DOCX"),
);
const secondaryArtifacts = computed(() =>
  store.artifacts.filter((item) =>
    [
      "BEST_MARKDOWN",
      "BEST_JSON",
      "RECOVERY_JSON",
      "RECOVERY_MARKDOWN",
    ].includes(item.type),
  ),
);
const optimizationReports = computed(() =>
  store.artifacts.filter((item) =>
    ["OPTIMIZATION_REPORT_MARKDOWN", "OPTIMIZATION_REPORT_JSON"].includes(
      item.type,
    ),
  ),
);
const stopLabel: Record<string, string> = {
  quality_passed: "达到内部质量门槛",
  no_actionable_feedback: "暂无可执行的新意见",
  plateau: "质量提升进入平台期",
  oscillation: "多轮修改出现往返",
  regression_guard: "回归保护已触发",
  rewrite_failed: "改写环节未能可靠完成",
  max_rounds: "达到最大迭代轮次",
  budget_exceeded: "达到本次调用预算",
  validation_error: "结构校验未通过",
  runtime_error: "运行环境异常",
};
async function sync() {
  try {
    const next = await getJob(props.jobId);
    store.current = next;
    connection.touched();
    loadError.value = "";
    if (terminalStatuses.includes(next.status) && !terminalLoaded) {
      terminalLoaded = true;
      await store.loadTerminalData(props.jobId);
      if (polling) window.clearInterval(polling);
    }
    return next;
  } catch (reason) {
    loadError.value = reason instanceof Error ? reason.message : "无法读取任务";
    return null;
  }
}
function received(event: JobEvent) {
  if (!events.value.some((item) => item.sequence === event.sequence))
    events.value.push(event);
  events.value.sort((a, b) => a.sequence - b.sequence);
  sync();
}
function stageMessage(stage?: string | null) {
  const labels: Record<string, string> = {
    queued: "任务正在等待执行",
    dispatching: "正在准备引擎请求",
    docx_security_check: "正在检查并提取原 Word",
    design_architect: "正在比较教学设计路线",
    writer: "Writer 正在形成可试教版本",
    judge: "Judge 正在进行八维内部质量检查",
    critics: "三类 Critic 正在独立审阅",
    validator: "Validator 正在去重与查证",
    rewriter: "Rewriter 正在落实有效意见",
    verifier: "正在核对修改是否真正完成",
    optimization_pairwise_compare: "正在交换顺序对照原稿与修改稿",
    finalize: "正在选择最佳版本并导出文件",
  };
  return labels[stage || ""] || "多智能体流程正在推进";
}
onMounted(async () => {
  store.resetCurrent();
  const initial = await sync();
  // Use the response directly instead of relying on a computed invalidation tick;
  // otherwise a fast terminal response can briefly open an unnecessary EventSource.
  if (!initial || terminalStatuses.includes(initial.status)) return;
  stopEvents = connectJobEvents(props.jobId, received, (value) =>
    connection.setLive(value),
  );
  polling = window.setInterval(() => {
    if (connection.mode !== "live" && !terminal.value) sync();
  }, 2000);
});
onBeforeUnmount(() => {
  stopEvents?.();
  if (polling) window.clearInterval(polling);
  store.resetCurrent();
});
const fmt = (value: number) => new Intl.NumberFormat("zh-CN").format(value);
</script>
<template>
  <div v-if="loadError && !job" class="empty-state error-state">
    <span>!</span>
    <h2>暂时无法打开任务</h2>
    <p>{{ loadError }}</p>
    <button class="secondary-button" @click="sync">重新加载</button>
  </div>
  <template v-else-if="job">
    <header class="job-hero">
      <button
        class="back-button"
        aria-label="返回历史任务"
        @click="router.push('/')"
      >
        ←
      </button>
      <div class="job-title">
        <div>
          <StatusPill :status="job.status" /><span>{{
            job.mode === "GENERATE" ? "从零生成" : "Word 优化"
          }}</span>
        </div>
        <h1>{{ job.topic }}</h1>
        <p>
          {{ job.subject }} · {{ job.grade }} · {{ job.durationMinutes }} 分钟
        </p>
      </div>
      <div
        v-if="!terminal"
        class="connection-indicator"
        :class="connection.mode"
      >
        <i /><span>{{
          connection.mode === "live"
            ? "实时连接"
            : connection.mode === "polling"
              ? "轮询同步"
              : "正在连接"
        }}</span>
      </div>
    </header>

    <template v-if="!terminal">
      <div class="progress-layout">
        <section class="surface progress-main">
          <div class="progress-heading">
            <div>
              <span class="eyebrow">LIVE PIPELINE</span>
              <h2>{{ latestMessage }}</h2>
            </div>
            <strong>{{ job.progressPercent }}%</strong>
          </div>
          <div class="large-progress">
            <i :style="{ width: `${job.progressPercent}%` }" />
          </div>
          <StageTimeline :job="job" :events="events" />
          <div class="leave-note">
            <span aria-hidden="true">↗</span>
            <div>
              <strong>可以离开这个页面</strong>
              <p>任务保存在服务端，稍后从“历史任务”回来即可继续查看。</p>
            </div>
          </div>
        </section>
        <aside class="progress-aside">
          <section class="surface">
            <span class="eyebrow">CURRENT ROUND</span
            ><strong class="round-number">{{ job.currentRound || "—" }}</strong>
            <p>当前迭代轮次</p>
          </section>
          <details class="surface usage-card">
            <summary>本次模型用量 <span>＋</span></summary>
            <dl>
              <div>
                <dt>模型调用</dt>
                <dd>{{ job.usage.modelCallCount }}</dd>
              </div>
              <div>
                <dt>输入 Token</dt>
                <dd>{{ fmt(job.usage.inputTokens) }}</dd>
              </div>
              <div>
                <dt>输出 Token</dt>
                <dd>{{ fmt(job.usage.outputTokens) }}</dd>
              </div>
              <div>
                <dt>估算费用</dt>
                <dd>${{ Number(job.usage.estimatedCost).toFixed(4) }}</dd>
              </div>
            </dl>
          </details>
        </aside>
      </div>
    </template>

    <template v-else>
      <section class="result-banner" :class="job.status.toLowerCase()">
        <div>
          <span class="eyebrow">RUN FINISHED</span>
          <h2>
            {{
              job.status === "COMPLETED"
                ? job.mode === "OPTIMIZE" &&
                  store.result?.optimization?.content_changed === false
                  ? "审查已结束，交付稿未修改"
                  : job.mode === "OPTIMIZE" &&
                      store.result?.optimization?.content_changed === true
                    ? "已形成修改稿，建议教师复核"
                    : job.mode === "OPTIMIZE"
                      ? "优化流程已结束，等待结果核验"
                      : "教案闭环已完成"
                : job.status === "NEEDS_HUMAN"
                  ? job.mode === "OPTIMIZE" &&
                    job.stopReason === "rewrite_failed"
                    ? "改写失败，已保留原稿"
                    : job.mode === "OPTIMIZE" &&
                        store.result?.optimization?.content_changed
                      ? "已形成修改候选稿，待教师复核"
                      : "已形成版本，建议教师复核"
                  : "本次任务未完整完成"
            }}
          </h2>
          <p>
            {{
              (job.mode === "OPTIMIZE" && job.stopReason === "rewrite_failed"
                ? "审查产生了可执行意见，但改写未通过校验；当前只保留原稿，并非没有优化空间。"
                : "") ||
              job.errorMessage ||
              (job.mode === "OPTIMIZE"
                ? store.result?.optimization?.message
                : "") ||
              stopLabel[job.stopReason || ""] ||
              "请查看可用结果与产物。"
            }}
          </p>
        </div>
        <div class="result-actions">
          <a
            v-if="primaryArtifact"
            class="primary-button"
            :href="primaryArtifact.downloadUrl"
            >{{
              job.mode === "OPTIMIZE" &&
              store.result?.optimization?.content_changed === false
                ? "下载未修改稿 Word"
                : job.mode === "OPTIMIZE" &&
                    store.result?.optimization?.content_changed === true
                  ? "下载修改稿 Word（待复核）"
                  : job.mode === "OPTIMIZE"
                    ? "下载 Word（内容变化待核验）"
                    : "下载 Word"
            }}</a
          ><a
            v-if="revisedCandidateArtifact"
            class="secondary-button"
            :href="revisedCandidateArtifact.downloadUrl"
            >下载修改候选稿 Word（待复核）</a
          ><a
            v-for="item in secondaryArtifacts.slice(0, 2)"
            :key="item.artifactId"
            class="secondary-button"
            :href="item.downloadUrl"
            >{{ item.type.includes("MARKDOWN") ? "Markdown" : "JSON" }}</a
          >
          <a
            v-for="item in optimizationReports"
            :key="item.artifactId"
            class="secondary-button"
            :href="item.downloadUrl"
            >优化报告 {{ item.type.endsWith("JSON") ? "JSON" : "Markdown" }}</a
          >
        </div>
      </section>
      <div v-if="store.result" class="result-grid">
        <main>
          <p
            v-if="job.mode === 'OPTIMIZE' && !store.result.optimization"
            class="surface"
          >
            该历史任务未保存优化前后对比。仅有分数变化不能证明教案内容被修改。
          </p>
          <OptimizationPanel
            v-if="job.mode === 'OPTIMIZE' && store.result.optimization"
            :summary="store.result.optimization"
          />
          <LessonPreview :plan="store.result.bestLessonPlan" />
        </main>
        <aside class="result-sidebar">
          <ScorePanel
            :scores="store.result.scores"
            :overall="store.result.overallScore"
          />
          <section
            v-if="job.mode !== 'OPTIMIZE' && store.result.changes.length"
            class="surface issue-card"
          >
            <span class="eyebrow">CHANGES</span>
            <h2>本轮主要修改</h2>
            <ul>
              <li
                v-for="item in store.result.changes.slice(0, 8)"
                :key="`${item.targetPath}-${item.summary}`"
              >
                <strong>{{ item.targetPath }}</strong
                ><span>{{ item.summary }}</span>
              </li>
            </ul>
          </section>
          <section
            v-if="
              store.result.parseWarnings.length ||
              store.result.unresolvedIssues.length
            "
            class="surface issue-card warning"
          >
            <span class="eyebrow">REVIEW</span>
            <h2>教师复核清单</h2>
            <ul>
              <li
                v-for="item in [
                  ...store.result.parseWarnings,
                  ...store.result.unresolvedIssues,
                ].slice(0, 12)"
                :key="item"
              >
                <span>{{ item }}</span>
              </li>
            </ul>
          </section>
        </aside>
      </div>
      <section v-else class="surface failed-panel">
        <h2>
          {{
            job.status === "FAILED" ? "没有可展示的完整版本" : "正在读取结果"
          }}
        </h2>
        <p v-if="job.status === 'FAILED'">
          系统不会用空白或硬编码教案冒充结果。下方标为“上传原件”的文件不是优化结果；
          如有 recovery 产物可下载，或根据错误信息处理后再创建任务。
        </p>
        <div v-if="store.artifacts.length" class="artifact-list">
          <a
            v-for="item in store.artifacts"
            :key="item.artifactId"
            :href="item.downloadUrl"
            >{{
              item.type === "ORIGINAL_DOCX"
                ? `上传原件：${item.displayName}`
                : item.displayName
            }}<small>{{ (item.sizeBytes / 1024).toFixed(1) }} KB</small></a
          >
        </div>
      </section>
    </template>
  </template>
  <div v-else class="loading-page">
    <span class="button-spinner" />
    <p>正在读取任务…</p>
  </div>
</template>
