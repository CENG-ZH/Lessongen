<script setup lang="ts">
import { computed } from "vue";
import type { JobDetail, JobEvent } from "../types/api";
const props = defineProps<{ job: JobDetail; events: JobEvent[] }>();
const generateStages = [
  ["queued", "任务入队"],
  ["design_architect", "设计路线"],
  ["writer", "形成初稿"],
  ["judge", "内部初评"],
  ["critics", "三类批评"],
  ["validator", "意见校验"],
  ["rewriter", "定向改写"],
  ["verifier", "落实核验"],
  ["finalize", "整理产物"],
];
const optimizeStages = [
  ["queued", "任务入队"],
  ["docx_security_check", "Word 安全解析"],
  ["design_architect", "设计路线"],
  ["writer", "形成版本"],
  ["judge", "内部初评"],
  ["critics", "三类批评"],
  ["validator", "意见校验"],
  ["rewriter", "定向改写"],
  ["verifier", "落实核验"],
  ["finalize", "整理产物"],
];
const order: Record<string, number> = {
  queued: 0,
  dispatching: 0,
  docx_security_check: 1,
  preprocessing: 1,
  run: 1,
  bootstrap: 1,
  design_architect: 2,
  writer: 3,
  judge: 4,
  evaluation_router: 4,
  critics: 5,
  critique_aggregator: 5,
  validator: 6,
  validation_router: 6,
  rewriter: 7,
  verifier: 8,
  finalize: 9,
  exporting: 9,
  completed: 10,
  failed: 10,
};
const stages = computed(() =>
  props.job.mode === "OPTIMIZE" ? optimizeStages : generateStages,
);
const furthest = computed(() =>
  Math.max(
    order[props.job.currentStage] ?? 0,
    ...props.events.map((item) => order[item.stage] ?? 0),
  ),
);
const state = (stage: string, index: number) => {
  if (props.job.status === "FAILED" && index === furthest.value)
    return "failed";
  const target = order[stage] ?? index;
  if (
    target < furthest.value ||
    ["COMPLETED", "NEEDS_HUMAN"].includes(props.job.status)
  )
    return "done";
  return target === furthest.value ? "active" : "waiting";
};
</script>
<template>
  <ol class="stage-timeline" aria-label="教案任务进度">
    <li
      v-for="(stage, index) in stages"
      :key="stage[0]"
      :class="state(stage[0], index)"
    >
      <span class="stage-dot" aria-hidden="true">{{
        state(stage[0], index) === "done" ? "✓" : index + 1
      }}</span>
      <div>
        <strong>{{ stage[1] }}</strong
        ><small v-if="state(stage[0], index) === 'active'">当前阶段</small>
      </div>
    </li>
  </ol>
</template>
