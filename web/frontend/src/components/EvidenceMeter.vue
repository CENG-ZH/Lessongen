<script setup lang="ts">
import { computed } from "vue";
import type { LessonInput } from "../types/api";
const props = defineProps<{ value: LessonInput }>();
const items = computed(() => [
  {
    name: "课程标准",
    ok: !!props.value.curriculumStandards?.length,
    note: "帮助目标与评价有据可依",
  },
  {
    name: "教材内容",
    ok: !!props.value.textbookContent?.trim(),
    note: "减少学科边界和难度偏差",
  },
  {
    name: "学习目标",
    ok: !!props.value.learningObjectives?.length,
    note: "让活动与达成证据更清晰",
  },
  {
    name: "学生情况",
    ok: !!props.value.studentProfile?.trim(),
    note: "支持支架与差异化设计",
  },
]);
const count = computed(() => items.value.filter((item) => item.ok).length);
const level = computed(() =>
  count.value >= 3 ? "证据较完整" : count.value >= 1 ? "基础证据" : "极简输入",
);
</script>
<template>
  <aside class="evidence-card" aria-label="输入证据完整度">
    <span class="eyebrow">生成前检查</span>
    <h2>{{ level }}</h2>
    <div class="meter" :aria-label="`已提供 ${count} / 4 类推荐证据`">
      <i :style="{ width: `${count * 25}%` }" />
    </div>
    <p>必填信息足以开始。补充依据可让目标、活动和评价更贴近真实课堂。</p>
    <ul>
      <li v-for="item in items" :key="item.name" :class="{ ready: item.ok }">
        <span aria-hidden="true">{{ item.ok ? "✓" : "○" }}</span>
        <div>
          <strong>{{ item.name }}</strong
          ><small>{{ item.note }}</small>
        </div>
      </li>
    </ul>
    <div class="cost-note">
      <strong>真实模型任务</strong
      ><span>提交后会产生 API 调用与费用；页面关闭不影响继续运行。</span>
    </div>
  </aside>
</template>
