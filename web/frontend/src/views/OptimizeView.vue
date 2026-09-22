<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ApiProblem, createOptimize, makeIdempotencyKey } from "../api/client";
import { useDraftStore } from "../stores/draft";
import LessonFields from "../components/LessonFields.vue";
import ChipInput from "../components/ChipInput.vue";

const router = useRouter();
const drafts = useDraftStore();
const file = ref<File | null>(null);
const fileError = ref("");
const digest = ref("");
const dragging = ref(false);
const submitting = ref(false);
const error = ref("");
const key = ref("");
const complete = computed(
  () =>
    file.value &&
    drafts.optimize.subject.trim() &&
    drafts.optimize.grade.trim() &&
    drafts.optimize.topic.trim(),
);
watch(
  () => drafts.optimize,
  () => {
    drafts.persistOptimize();
    key.value = "";
  },
  { deep: true },
);
const size = computed(() =>
  file.value ? `${(file.value.size / 1024 / 1024).toFixed(2)} MiB` : "",
);
async function choose(candidate?: File) {
  fileError.value = "";
  digest.value = "";
  file.value = null;
  key.value = "";
  if (!candidate) return;
  if (!candidate.name.toLowerCase().endsWith(".docx")) {
    fileError.value = "只支持 .docx 格式。";
    return;
  }
  if (candidate.size > 20 * 1024 * 1024) {
    fileError.value = "文件不能超过 20 MiB。";
    return;
  }
  const magic = new Uint8Array(await candidate.slice(0, 4).arrayBuffer());
  if (
    magic.length !== 4 ||
    magic[0] !== 0x50 ||
    magic[1] !== 0x4b ||
    magic[2] !== 0x03 ||
    magic[3] !== 0x04
  ) {
    fileError.value = "文件不是有效的 OOXML Word 文档。";
    return;
  }
  file.value = candidate;
  const hash = await crypto.subtle.digest(
    "SHA-256",
    await candidate.arrayBuffer(),
  );
  digest.value = Array.from(new Uint8Array(hash))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}
function drop(event: DragEvent) {
  dragging.value = false;
  choose(event.dataTransfer?.files?.[0]);
}
async function submit() {
  error.value = "";
  if (!complete.value || !file.value) {
    error.value = "请先选择 Word，并填写科目、年级和课题。";
    return;
  }
  submitting.value = true;
  key.value ||= makeIdempotencyKey();
  try {
    const accepted = await createOptimize(
      drafts.optimize,
      file.value,
      key.value,
    );
    drafts.clearOptimize();
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
    <span class="eyebrow">CREATE · OPTIMIZE</span>
    <h1>让原教案变得更可教</h1>
    <p>
      可上传其他来源的 .docx
      教案，不要求使用本系统模板。原稿只读保存；导入后审查、改写，
      最终展示实际修改前后对比。若没有可交付的内容变化，页面会如实标明。
    </p>
  </div>
  <form class="lesson-form surface optimize-form" @submit.prevent="submit">
    <section class="upload-section">
      <div class="form-section-title">
        <span>00</span>
        <div>
          <h2>选择原教案</h2>
          <p>
            仅支持含可读取文字的 .docx，最大 20 MiB；扫描图片中的文字暂不识别。
          </p>
        </div>
      </div>
      <label
        class="drop-zone"
        :class="{ dragging, selected: file }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="drop"
      >
        <input
          type="file"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          @change="choose(($event.target as HTMLInputElement).files?.[0])"
        />
        <span class="upload-icon" aria-hidden="true">↥</span>
        <template v-if="file"
          ><strong>{{ file.name }}</strong>
          <p>{{ size }} · SHA-256 已计算</p>
          <code
            >{{ digest.slice(0, 18) }}…{{ digest.slice(-8) }}</code
          ></template
        >
        <template v-else
          ><strong>拖放 Word 教案到这里</strong>
          <p>或点击选择本机文件</p></template
        >
      </label>
      <p v-if="fileError" class="field-error" role="alert">{{ fileError }}</p>
      <div class="format-notice">
        <strong>关于排版</strong
        ><span
          >系统按段落与表格顺序提取原稿，再分段识别教学内容；请核对导入警告和改写对比。输出采用统一教案模板，不复刻原排版。</span
        >
      </div>
    </section>
    <LessonFields v-model="drafts.optimize" compact />
    <section class="form-section">
      <div class="form-section-title">
        <span>05</span>
        <div>
          <h2>优化边界</h2>
          <p>明确最想改好的部分，以及不能被改写掉的内容。</p>
        </div>
      </div>
      <div class="field-grid two">
        <label
          ><span>优化重点</span
          ><ChipInput
            v-model="drafts.optimize.optimizationFocus!"
            placeholder="如：增强课堂提问层次"
        /></label>
        <label
          ><span>必须保留</span
          ><ChipInput
            v-model="drafts.optimize.mustPreserveContent!"
            placeholder="如：保留原实验步骤与数据"
        /></label>
      </div>
    </section>
    <div v-if="error" class="form-error" role="alert">{{ error }}</div>
    <div class="submit-row">
      <p>
        <strong>原文件将只读保存</strong
        ><span>用户填写的科目、年级、课题和课时优先于模型推断。</span>
      </p>
      <button
        class="primary-button"
        type="submit"
        :disabled="submitting || !complete"
      >
        <span v-if="submitting" class="button-spinner" />{{
          submitting ? "正在上传并创建…" : "开始优化教案"
        }}
      </button>
    </div>
  </form>
</template>
