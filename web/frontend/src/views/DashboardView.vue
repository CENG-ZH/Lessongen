<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useJobStore } from "../stores/jobs";
import type { JobMode, JobStatus } from "../types/api";
import StatusPill from "../components/StatusPill.vue";

const jobs = useJobStore();
const mode = ref<JobMode | "">("");
const status = ref<JobStatus | "">("");
const filtered = computed(() =>
  jobs.recent.filter(
    (item) =>
      (!mode.value || item.mode === mode.value) &&
      (!status.value || item.status === status.value),
  ),
);
const date = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
onMounted(() => jobs.loadRecent());
</script>
<template>
  <section class="hero">
    <div class="hero-copy">
      <span class="eyebrow">MULTI-AGENT LESSON DESIGN</span>
      <h1>把课程设想变成<br /><em>可试教、可复盘</em>的教案</h1>
      <p>
        不需要编辑 JSON。给出真实教学情境，让具有不同知识侧重的 Agent
        共同起草、质疑、校验和改写。
      </p>
      <div class="hero-actions">
        <RouterLink class="primary-button" to="/create/generate"
          >从零生成</RouterLink
        ><RouterLink class="secondary-button" to="/create/optimize"
          >上传 Word 优化</RouterLink
        >
      </div>
    </div>
    <div class="hero-diagram" aria-label="多智能体闭环示意">
      <div class="orbit center">
        <span>最佳教案</span><small>Word · MD · JSON</small>
      </div>
      <div class="orbit writer"><b>W</b><span>构思</span></div>
      <div class="orbit critic"><b>C</b><span>质疑</span></div>
      <div class="orbit validator"><b>V</b><span>查证</span></div>
      <div class="orbit judge"><b>J</b><span>选优</span></div>
      <svg viewBox="0 0 500 360" aria-hidden="true">
        <path
          d="M112 86 C235 4 405 65 420 174 C434 279 273 343 126 272 C48 234 37 133 112 86Z"
        />
        <path
          d="M148 116 C220 62 338 83 369 160 C395 226 303 292 198 270 C107 250 86 164 148 116Z"
        />
      </svg>
    </div>
  </section>
  <section class="action-grid" aria-label="核心功能">
    <RouterLink to="/create/generate" class="action-card"
      ><span class="card-index">01</span>
      <div>
        <small>GENERATE</small>
        <h2>生成一份新教案</h2>
        <p>从课题、教材与学情出发，先比较设计路线，再完成多轮审阅与改写。</p>
        <b>开始设计 <i>→</i></b>
      </div></RouterLink
    >
    <RouterLink to="/create/optimize" class="action-card warm"
      ><span class="card-index">02</span>
      <div>
        <small>OPTIMIZE</small>
        <h2>优化已有 Word</h2>
        <p>
          安全解析原稿，保留指定内容，找出教学逻辑、对齐和学科层面的真实问题。
        </p>
        <b>选择教案 <i>→</i></b>
      </div></RouterLink
    >
  </section>
  <section class="recent-section">
    <div class="section-heading">
      <div>
        <span class="eyebrow">RECENT WORK</span>
        <h2>近期任务</h2>
      </div>
      <div class="filters">
        <select v-model="mode" aria-label="按模式筛选">
          <option value="">全部模式</option>
          <option value="GENERATE">生成</option>
          <option value="OPTIMIZE">优化</option></select
        ><select v-model="status" aria-label="按状态筛选">
          <option value="">全部状态</option>
          <option value="RUNNING">进行中</option>
          <option value="COMPLETED">已完成</option>
          <option value="NEEDS_HUMAN">待复核</option>
          <option value="FAILED">未完成</option>
        </select>
      </div>
    </div>
    <div v-if="jobs.loading" class="job-grid" aria-label="任务加载中">
      <div v-for="i in 3" :key="i" class="job-card skeleton" />
    </div>
    <div v-else-if="!filtered.length" class="empty-state">
      <span>一</span>
      <h3>还没有符合条件的任务</h3>
      <p>从一个真实课题开始，第一份记录会出现在这里。</p>
      <RouterLink to="/create/generate" class="secondary-button"
        >创建教案</RouterLink
      >
    </div>
    <div v-else class="job-grid">
      <RouterLink
        v-for="job in filtered"
        :key="job.jobId"
        :to="`/jobs/${job.jobId}`"
        class="job-card"
      >
        <div class="job-card-top">
          <span>{{ job.mode === "GENERATE" ? "从零生成" : "Word 优化" }}</span
          ><StatusPill :status="job.status" />
        </div>
        <h3>{{ job.topic }}</h3>
        <p>{{ job.subject }} · {{ job.grade }}</p>
        <div class="job-progress">
          <i :style="{ width: `${job.progressPercent}%` }" />
        </div>
        <footer>
          <span>{{
            job.currentRound ? `第 ${job.currentRound} 轮` : "准备阶段"
          }}</span
          ><time>{{ date(job.createdAt) }}</time>
        </footer>
      </RouterLink>
    </div>
  </section>
</template>
