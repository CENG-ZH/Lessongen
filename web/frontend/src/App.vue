<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import AppHeader from "./components/AppHeader.vue";

const route = useRoute();
function updateTitle() {
  const titles: Record<string, string> = {
    dashboard: "工作台",
    generate: "生成教案",
    optimize: "优化教案",
    job: "任务详情",
  };
  document.title = `${titles[String(route.name)] || "工作台"} · 灵犀教案`;
}
function focusPage(element: globalThis.Element) {
  const heading = element.querySelector("h1");
  if (heading instanceof window.HTMLElement) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
}
onMounted(updateTitle);
watch(() => route.path, updateTitle);
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <AppHeader />
  <main id="main-content" class="page-shell" tabindex="-1">
    <RouterView v-slot="{ Component }">
      <Transition name="page" mode="out-in" @after-enter="focusPage">
        <!-- Route views intentionally use fragments; Transition needs one keyed element to
             complete leave/enter reliably during in-app navigation. -->
        <div :key="$route.path" class="route-frame">
          <component :is="Component" />
        </div>
      </Transition>
    </RouterView>
  </main>
  <footer class="app-footer">
    <span>灵犀教案 · Paper#4 多智能体教学设计工作台</span>
    <span>AI 结果请由教师复核后使用</span>
  </footer>
</template>
