<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  defineComponent,
  h,
  onBeforeUnmount,
  onMounted,
  ref,
} from "vue";

const props = defineProps<{
  scores: Record<string, number>;
  overall?: number | null;
}>();
const labels: Record<string, string> = {
  curriculumAlignment: "课标对齐",
  knowledgeAccuracy: "知识准确",
  teachingLogic: "教学逻辑",
  classroomFeasibility: "课堂可行",
  differentiatedInstruction: "差异教学",
  studentEngagement: "学生参与",
  assessmentDesign: "评价设计",
  languageAndFormat: "语言格式",
};
type ScoreRow = { key: string; label: string; score: number | null };
type ScoredRow = { key: string; label: string; score: number };
const rows = computed(
  () =>
    Object.entries(labels).map(([key, label]) => {
      const value = props.scores?.[key];
      return {
        key,
        label,
        score:
          typeof value === "number" &&
          Number.isFinite(value) &&
          value >= 0 &&
          value <= 10
            ? value
            : null,
      };
    }) satisfies ScoreRow[],
);
const chartRows = computed(() =>
  rows.value.filter((row): row is ScoredRow => row.score !== null),
);
const hasCompleteScores = computed(
  () => chartRows.value.length === Object.keys(labels).length,
);
const validOverall = computed(() =>
  typeof props.overall === "number" &&
  Number.isFinite(props.overall) &&
  props.overall >= 0 &&
  props.overall <= 10
    ? props.overall
    : null,
);
const chartSlot = ref<HTMLDivElement>();
const showChart = ref(false);
let observer: globalThis.IntersectionObserver | undefined;
const ChartFallback = defineComponent({
  render: () =>
    h("p", { class: "chart-fallback" }, "图表暂不可用，数值表仍可查看。"),
});
const RadarChartCanvas = defineAsyncComponent({
  loader: () => import("./RadarChartCanvas.vue"),
  errorComponent: ChartFallback,
  delay: 150,
  timeout: 15_000,
});
onMounted(() => {
  if (!chartSlot.value || !("IntersectionObserver" in window)) {
    showChart.value = true;
    return;
  }
  observer = new window.IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        showChart.value = true;
        observer?.disconnect();
      }
    },
    { rootMargin: "120px" },
  );
  observer.observe(chartSlot.value);
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <section class="score-panel surface">
    <div class="section-heading">
      <div>
        <span class="eyebrow">Quality signals</span>
        <h2>八维内部质量</h2>
      </div>
      <div class="overall-score" :class="{ unavailable: validOverall == null }">
        <strong>{{
          validOverall == null ? "暂不可用" : validOverall.toFixed(1)
        }}</strong
        ><span v-if="validOverall != null">/ 10</span>
      </div>
    </div>
    <p class="score-notice">
      这些分数用于管线内部选优和路由，不代表正式教学成效。
    </p>
    <div class="score-layout">
      <div
        ref="chartSlot"
        class="radar-slot"
        :class="{ unavailable: !hasCompleteScores }"
      >
        <p v-if="!hasCompleteScores" class="chart-fallback">
          部分维度暂无分数，暂不绘制雷达图；已提供的分数见数值表。
        </p>
        <RadarChartCanvas v-else-if="showChart" :rows="chartRows" />
        <p v-else class="chart-fallback">
          滚动到图表时加载；数值表可直接阅读。
        </p>
      </div>
      <dl class="score-list">
        <div v-for="row in rows" :key="row.key">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.score == null ? "暂不可用" : row.score.toFixed(1) }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>
