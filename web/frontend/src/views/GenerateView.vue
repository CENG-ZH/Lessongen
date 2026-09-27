<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { createGenerate, makeIdempotencyKey, ApiProblem } from "../api/client";
import { useDraftStore } from "../stores/draft";
import LessonFields from "../components/LessonFields.vue";
import EvidenceMeter from "../components/EvidenceMeter.vue";
import FormWayfinder from "../components/FormWayfinder.vue";

const router = useRouter();
const drafts = useDraftStore();
const submitting = ref(false);
const error = ref("");
const key = ref("");
type FieldName =
  "subject" | "grade" | "topic" | "durationMinutes" | "classSize";
const invalidField = ref<FieldName | null>(null);
const lessonFields = ref<{ commitPending: () => void } | null>(null);
const draftNote = ref(
  "表单信息仅暂存在当前浏览器会话；提交后会调用真实模型并产生费用。",
);
let submitted = false;
const complete = computed(
  () =>
    drafts.generate.subject.trim() &&
    drafts.generate.grade.trim() &&
    drafts.generate.topic.trim(),
);
function fieldIsValid(field: FieldName) {
  if (field === "durationMinutes") {
    const value = drafts.generate.durationMinutes;
    return Number.isInteger(value) && value >= 5 && value <= 240;
  }
  if (field === "classSize") {
    const value: unknown = drafts.generate.classSize;
    return (
      value == null ||
      value === "" ||
      (typeof value === "number" &&
        Number.isInteger(value) &&
        value >= 1 &&
        value <= 200)
    );
  }
  return !!drafts.generate[field].trim();
}
watch(
  () => drafts.generate,
  () => {
    if (submitted) return;
    draftNote.value = drafts.persistGenerate()
      ? "草稿已保存在当前浏览器会话；提交后会调用真实模型并产生费用。"
      : "本机草稿保存失败，请勿关闭页面；提交仍可继续。";
    key.value = "";
    if (invalidField.value && fieldIsValid(invalidField.value)) {
      invalidField.value = null;
      error.value = "";
    }
  },
  { deep: true },
);
const sections = computed(() => [
  {
    id: "generate-basic",
    label: "基本信息",
    state: complete.value ? "必填已齐" : "3 项必填",
    complete: !!complete.value,
  },
  {
    id: "generate-evidence",
    label: "教学依据",
    state:
      drafts.generate.curriculumStandards?.length ||
      drafts.generate.textbookContent?.trim() ||
      drafts.generate.textbookVersion?.trim()
        ? "已补充"
        : "可选",
  },
  {
    id: "generate-learning",
    label: "学习设计",
    state:
      drafts.generate.learningObjectives?.length ||
      drafts.generate.studentProfile?.trim() ||
      drafts.generate.availableResources?.length
        ? "已补充"
        : "可选",
  },
  { id: "generate-advanced", label: "风格要求", state: "可选" },
]);
async function focusRequired() {
  const invalid = (
    ["subject", "grade", "topic", "durationMinutes", "classSize"] as const
  ).find((field) => !fieldIsValid(field));
  if (!invalid) return false;
  invalidField.value = invalid;
  error.value =
    invalid === "durationMinutes"
      ? "课时请输入 5–240 分钟的整数。"
      : invalid === "classSize"
        ? "班级人数请输入 1–200 的整数，或留空。"
        : "请补齐基本信息中的必填项。";
  await nextTick();
  document.getElementById(`generate-${invalid}`)?.focus();
  return true;
}
async function submit() {
  lessonFields.value?.commitPending();
  error.value = "";
  if (await focusRequired()) return;
  invalidField.value = null;
  submitting.value = true;
  key.value ||= makeIdempotencyKey();
  try {
    const accepted = await createGenerate(drafts.generate, key.value);
    submitted = true;
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
  <FormWayfinder
    :items="sections"
    :note="submitting ? '正在提交任务，请勿重复操作。' : draftNote"
  />
  <div class="form-layout">
    <EvidenceMeter class="mobile-evidence" :value="drafts.generate" compact />
    <form class="lesson-form surface" novalidate @submit.prevent="submit">
      <LessonFields
        ref="lessonFields"
        v-model="drafts.generate"
        id-prefix="generate"
        :invalid-field="invalidField"
        compact
      />
      <div
        v-if="error"
        id="generate-form-error"
        class="form-error"
        role="alert"
      >
        {{ error }}
      </div>
      <div class="submit-row">
        <p>
          <strong>准备好后开始生成与审查</strong
          ><span
            >Writer → Judge → 三类 Critic → Validator → 按需改写与复评</span
          >
        </p>
        <button class="primary-button" type="submit" :disabled="submitting">
          <span v-if="submitting" class="button-spinner" />{{
            submitting ? "正在创建任务…" : "开始生成教案"
          }}
        </button>
      </div>
    </form>
    <EvidenceMeter class="desktop-evidence" :value="drafts.generate" />
  </div>
</template>
