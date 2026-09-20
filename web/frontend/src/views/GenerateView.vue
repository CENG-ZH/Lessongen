<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { createGenerate, makeIdempotencyKey, ApiProblem } from "../api/client";
import { useDraftStore } from "../stores/draft";
import LessonFields from "../components/LessonFields.vue";
import EvidenceMeter from "../components/EvidenceMeter.vue";

const router = useRouter();
const drafts = useDraftStore();
const submitting = ref(false);
const error = ref("");
const key = ref("");
const complete = computed(
  () =>
    drafts.generate.subject.trim() &&
    drafts.generate.grade.trim() &&
    drafts.generate.topic.trim(),
);
watch(
  () => drafts.generate,
  () => {
    drafts.persistGenerate();
    key.value = "";
  },
  { deep: true },
);
async function submit() {
  error.value = "";
  if (!complete.value) {
    error.value = "请先填写科目、年级和课题。";
    return;
  }
  submitting.value = true;
  key.value ||= makeIdempotencyKey();
  try {
    const accepted = await createGenerate(drafts.generate, key.value);
    drafts.clearGenerate();
    await router.push(`/jobs/${accepted.jobId}`);
  } catch (reason) {
    error.value =
      reason instanceof ApiProblem ? reason.message : "提交失败，请稍后重试。";
  } finally {
    submitting.value = false;
  }
}
</script>
<template>
  <div class="page-intro compact">
    <span class="eyebrow">CREATE · GENERATE</span>
    <h1>从课程设想开始</h1>
    <p>三项必填即可启动；越具体的真实依据，越能得到有内容、可试教的教案。</p>
  </div>
  <div class="form-layout">
    <form class="lesson-form surface" @submit.prevent="submit">
      <LessonFields v-model="drafts.generate" compact />
      <div v-if="error" class="form-error" role="alert">{{ error }}</div>
      <div class="submit-row">
        <p>
          <strong>准备好后开始闭环</strong
          ><span>Writer → 三类 Critic → Validator → Rewriter → Judge</span>
        </p>
        <button
          class="primary-button"
          type="submit"
          :disabled="submitting || !complete"
        >
          <span v-if="submitting" class="button-spinner" />{{
            submitting ? "正在创建任务…" : "开始生成教案"
          }}
        </button>
      </div>
    </form>
    <EvidenceMeter :value="drafts.generate" />
  </div>
</template>
