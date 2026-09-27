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
import { lessonPathLabel } from "../utils/lessonPresentation";

const props = defineProps<{ jobId: string }>();
const router = useRouter();
const store = useJobStore();
const connection = useConnectionStore();
const events = ref<JobEvent[]>([]);
const loadError = ref("");
let stopEvents: (() => void) | undefined;
let polling: number | undefined;
let terminalLoaded = false;
let terminalDataInFlight: Promise<boolean> | undefined;
let active = true;
let requestSequence = 0;
let appliedSequence = 0;
const job = computed(() => store.current);
const terminal = computed(
  () => !!job.value && terminalStatuses.includes(job.value.status),
);
const stagePercent = computed(() => {
  const value = job.value?.progressPercent;
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(100, Math.max(0, value))
    : null;
});
const latestMessage = computed(
  () =>
    (events.value.at(-1)?.stage === job.value?.currentStage
      ? events.value.at(-1)?.message
      : "") || stageMessage(job.value?.currentStage),
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
const generatedReview = computed(() =>
  job.value?.mode === "GENERATE" ? store.result?.review : null,
);
const generateOutcome = computed(() => {
  const review = generatedReview.value;
  if (!review?.independent_review_complete)
    return "教案已生成，独立审查尚未完成";
  return review.content_changed
    ? "已完成独立审查并形成修改稿"
    : "已完成独立审查，教案未改写";
});
async function sync() {
  const requestId = ++requestSequence;
  try {
    const next = await getJob(props.jobId);
    if (!active || requestId < appliedSequence) return null;
    if (terminal.value && !terminalStatuses.includes(next.status))
      return job.value;
    appliedSequence = requestId;
    store.current = next;
    connection.touched();
    loadError.value = "";
    if (terminalStatuses.includes(next.status)) {
      stopEvents?.();
      stopEvents = undefined;
    }
    if (terminalStatuses.includes(next.status) && !terminalLoaded) {
      terminalDataInFlight ||= store.loadTerminalData(
        props.jobId,
        next.status === "FAILED",
      );
      const loaded = await terminalDataInFlight;
      terminalDataInFlight = undefined;
      if (!active) return null;
      terminalLoaded = loaded;
      if (terminalLoaded && polling) {
        window.clearInterval(polling);
        polling = undefined;
      }
    }
    return next;
  } catch (reason) {
    if (active && requestId === requestSequence)
      loadError.value =
        reason instanceof Error ? reason.message : "无法读取任务";
    return null;
  }
}
function received(event: JobEvent) {
  if (!active || terminal.value) return;
  if (!events.value.some((item) => item.sequence === event.sequence))
    events.value.push(event);
  events.value.sort((a, b) => a.sequence - b.sequence);
  void sync();
}
function stageMessage(stage?: string | null) {
  const labels: Record<string, string> = {
    queued: "任务正在等待执行",
    dispatching: "正在准备引擎请求",
    docx_security_check: "正在检查并提取原 Word",
    docx_normalize: "正在识别 Word 中的教学内容",
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
function ensureUpdates(next: NonNullable<typeof job.value>) {
  if (!terminalStatuses.includes(next.status) && !stopEvents) {
    stopEvents = connectJobEvents(props.jobId, received, (value) =>
      connection.setLive(value),
    );
  }
  if (!terminalLoaded && !polling) {
    polling = window.setInterval(() => {
      if ((terminal.value && !terminalLoaded) || connection.mode !== "live")
        void sync();
    }, 2000);
  }
}
function settleTerminalData() {
  terminalLoaded = store.resultReady && store.artifactsReady;
  if (terminalLoaded && polling) {
    window.clearInterval(polling);
    polling = undefined;
  }
}
async function retryResult() {
  await store.loadResult(props.jobId, job.value?.status === "FAILED");
  if (active) settleTerminalData();
}
async function retryArtifacts() {
  await store.loadArtifacts(props.jobId);
  if (active) settleTerminalData();
}
async function resume() {
  const next = await sync();
  if (next) ensureUpdates(next);
}
onMounted(async () => {
  active = true;
  store.resetCurrent();
  connection.reset();
  const initial = await sync();
  // Use the response directly instead of relying on a computed invalidation tick;
  // otherwise a fast terminal response can briefly open an unnecessary EventSource.
  if (!initial) return;
  ensureUpdates(initial);
});
onBeforeUnmount(() => {
  active = false;
  requestSequence += 1;
  stopEvents?.();
  if (polling) window.clearInterval(polling);
  store.resetCurrent();
});
const fmt = (value?: number | null) =>
  typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("zh-CN").format(value)
    : "暂不可用";
const cost = (value?: number | null) =>
  typeof value === "number" && Number.isFinite(value)
    ? `$${value.toFixed(4)}`
    : "暂不可用";
const durationLabel = (value?: number | null) =>
  typeof value === "number" && Number.isFinite(value) && value > 0
    ? `${value} 分钟`
    : "课时待确认";
const lastUpdated = computed(() =>
  connection.updatedAt
    ? new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(new Date(connection.updatedAt))
    : "暂不可用",
);
</script>
<template>
  <div v-if="loadError && !job" class="empty-state error-state" role="alert">
    <span>!</span>
    <h2>暂时无法打开任务</h2>
    <p>{{ loadError }}</p>
    <button class="secondary-button" @click="resume">重新加载</button>
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
          {{ job.subject }} · {{ job.grade }} ·
          {{ durationLabel(job.durationMinutes) }}
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
    <div v-if="loadError" class="recent-alert" role="alert">
      <span>任务同步暂时中断，页面显示的是上次读取的状态：{{ loadError }}</span>
      <button type="button" @click="resume">重新同步</button>
    </div>

    <template v-if="!terminal">
      <div class="progress-layout">
        <section class="surface progress-main">
          <div class="progress-heading">
            <div>
              <span class="eyebrow">LIVE PIPELINE</span>
              <h2 aria-live="polite" aria-atomic="true">{{ latestMessage }}</h2>
              <p class="progress-caption">
                系统阶段进度，不代表剩余时间；上次同步 {{ lastUpdated }}。
              </p>
            </div>
            <strong>{{
              stagePercent == null ? "暂不可用" : `${stagePercent}%`
            }}</strong>
          </div>
          <div
            v-if="stagePercent != null"
            class="large-progress"
            role="progressbar"
            aria-label="系统阶段进度"
            :aria-valuenow="stagePercent"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <i :style="{ width: `${stagePercent}%` }" />
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
                <dd>{{ fmt(job.usage?.modelCallCount) }}</dd>
              </div>
              <div>
                <dt>输入 Token</dt>
                <dd>{{ fmt(job.usage?.inputTokens) }}</dd>
              </div>
              <div>
                <dt>输出 Token</dt>
                <dd>{{ fmt(job.usage?.outputTokens) }}</dd>
              </div>
              <div>
                <dt>估算费用</dt>
                <dd>{{ cost(job.usage?.estimatedCost) }}</dd>
              </div>
            </dl>
            <p class="usage-note">
              Token
              与费用仅汇总供应商已返回的用量；未返回用量的调用可能未计入，实际账单以供应商为准。
            </p>
          </details>
        </aside>
      </div>
    </template>

    <template v-else>
      <section class="result-banner" :class="job.status.toLowerCase()">
        <div>
          <span class="eyebrow">{{
            job.status === "FAILED"
              ? "任务未完成"
              : job.status === "NEEDS_HUMAN"
                ? "等待教师复核"
                : "处理完成"
          }}</span>
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
                      : generateOutcome
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
              (job.status !== "COMPLETED" && job.stopReason
                ? stopLabel[job.stopReason]
                : "") ||
              (job.mode === "GENERATE" && generatedReview
                ? generatedReview.independent_review_complete
                  ? `已完成 ${generatedReview.reviewed_roles.length} 类角色审查及 Validator 裁决；${generatedReview.content_changed ? "交付稿有内容修改。" : "交付稿内容未改变。"}`
                  : "目前只有内部评分或部分审查记录，不能称为完成三方独立审查。"
                : "") ||
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
          ><RouterLink
            v-if="store.result"
            class="secondary-button result-jump"
            :to="{ hash: '#lesson-content' }"
            >直接阅读教案</RouterLink
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
            >{{ item.type.startsWith("RECOVERY_") ? "恢复记录 " : ""
            }}{{ item.type.includes("MARKDOWN") ? "Markdown" : "JSON" }}</a
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
      <div v-if="store.artifactWarning" class="recent-alert" role="alert">
        <span>{{ store.artifactWarning }}</span>
        <button
          type="button"
          :disabled="store.artifactLoading"
          @click="retryArtifacts"
        >
          {{ store.artifactLoading ? "正在重试…" : "重试读取下载文件" }}
        </button>
      </div>
      <div v-if="store.resultError" class="recent-alert" role="alert">
        <span>{{ store.resultError }}</span>
        <button
          type="button"
          :disabled="store.resultLoading"
          @click="retryResult"
        >
          {{ store.resultLoading ? "正在重试…" : "重试读取教案结果" }}
        </button>
      </div>
      <div v-if="store.result" class="result-grid">
        <div class="result-main">
          <p
            v-if="job.mode === 'OPTIMIZE' && !store.result.optimization"
            class="surface"
          >
            该历史任务未保存优化前后对比。仅有分数变化不能证明教案内容被修改。
          </p>
          <p
            v-if="job.mode === 'GENERATE' && !store.result.review"
            class="surface"
          >
            这条历史任务没有保存独立审查记录；内部评分不代表已完成三方审查。
          </p>
          <OptimizationPanel
            v-if="job.mode === 'OPTIMIZE' && store.result.optimization"
            :summary="store.result.optimization"
          />
          <section
            v-if="job.mode !== 'OPTIMIZE' && store.result.changes.length"
            class="surface issue-card"
          >
            <span class="eyebrow">本轮修改</span>
            <h2>这份教案实际改了什么</h2>
            <ul>
              <li
                v-for="item in store.result.changes.slice(0, 8)"
                :key="`${item.targetPath}-${item.summary}`"
              >
                <strong>{{ lessonPathLabel(item.targetPath) }}</strong>
                <span>{{ item.summary }}</span>
                <details class="technical-path">
                  <summary>技术位置</summary>
                  <code>{{ item.targetPath }}</code>
                </details>
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
            <span class="eyebrow">教师复核</span>
            <h2>使用前仍需确认</h2>
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
          <LessonPreview
            id="lesson-content"
            :plan="store.result.bestLessonPlan"
          />
        </div>
        <aside class="result-sidebar">
          <ScorePanel
            :scores="store.result.scores"
            :overall="store.result.overallScore"
          />
        </aside>
      </div>
      <section v-else class="surface failed-panel">
        <h2>
          {{
            job.status === "FAILED"
              ? "没有可展示的完整版本"
              : store.resultError
                ? "教案结果暂时无法读取"
                : "正在读取结果"
          }}
        </h2>
        <p v-if="store.resultError && job.status !== 'FAILED'">
          下载文件如已列出，仍可先取回；也可以使用上方按钮单独重试读取教案。
        </p>
        <p v-if="job.status === 'FAILED'">
          系统不会用空白教案冒充结果。“上传原件”是您提交的
          Word；“恢复记录”仅保存可取回的运行内容，
          不是已完成的优化稿。请查看上方原因，处理后重新创建任务。
        </p>
        <RouterLink
          v-if="job.status === 'FAILED'"
          class="secondary-button"
          :to="
            job.mode === 'OPTIMIZE' ? '/create/optimize' : '/create/generate'
          "
          >重新创建任务</RouterLink
        >
        <div v-if="store.artifacts.length" class="artifact-list">
          <a
            v-for="item in store.artifacts"
            :key="item.artifactId"
            :href="item.downloadUrl"
            >{{
              item.type === "ORIGINAL_DOCX"
                ? `上传原件：${item.displayName}`
                : item.type.startsWith("RECOVERY_")
                  ? `恢复记录 ${item.type.endsWith("MARKDOWN") ? "Markdown" : "JSON"}`
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
