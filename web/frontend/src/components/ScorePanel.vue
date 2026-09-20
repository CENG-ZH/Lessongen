<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import * as echarts from "echarts/core";
import { RadarChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import { LegendComponent, TooltipComponent } from "echarts/components";
echarts.use([RadarChart, CanvasRenderer, LegendComponent, TooltipComponent]);

const props = defineProps<{
  scores: Record<string, number>;
  overall?: number | null;
}>();
const chart = ref<HTMLDivElement>();
let instance: echarts.ECharts | undefined;
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
const rows = computed(() =>
  Object.entries(labels).map(([key, label]) => ({
    key,
    label,
    score: props.scores[key] ?? 0,
  })),
);
function render() {
  if (!chart.value) return;
  instance ||= echarts.init(chart.value);
  instance.setOption({
    animationDuration: matchMedia("(prefers-reduced-motion: reduce)").matches
      ? 0
      : 500,
    tooltip: {},
    radar: {
      indicator: rows.value.map((item) => ({ name: item.label, max: 10 })),
      radius: "65%",
      axisName: { color: "#334b59", fontSize: 11 },
      splitArea: { areaStyle: { color: ["#fbfaf6", "#f4f1e8"] } },
      axisLine: { lineStyle: { color: "#cbd7d3" } },
      splitLine: { lineStyle: { color: "#d9dfdc" } },
    },
    series: [
      {
        type: "radar",
        data: [
          { value: rows.value.map((item) => item.score), name: "内部质量" },
        ],
        symbolSize: 5,
        lineStyle: { color: "#147d78", width: 2 },
        itemStyle: { color: "#147d78" },
        areaStyle: { color: "rgba(29,148,141,.2)" },
      },
    ],
  });
}
const resize = () => instance?.resize();
onMounted(() => {
  nextTick(render);
  window.addEventListener("resize", resize);
});
watch(
  () => props.scores,
  () => nextTick(render),
  { deep: true },
);
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  instance?.dispose();
});
</script>
<template>
  <section class="score-panel surface">
    <div class="section-heading">
      <div>
        <span class="eyebrow">Quality signals</span>
        <h2>八维内部质量</h2>
      </div>
      <div v-if="overall != null" class="overall-score">
        <strong>{{ overall.toFixed(1) }}</strong
        ><span>/ 10</span>
      </div>
    </div>
    <p class="score-notice">
      这些分数用于管线内部选优和路由，不代表正式教学成效。
    </p>
    <div class="score-layout">
      <div
        ref="chart"
        class="radar-chart"
        role="img"
        aria-label="八维内部质量雷达图"
      />
      <dl class="score-list">
        <div v-for="row in rows" :key="row.key">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.score.toFixed(1) }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>
