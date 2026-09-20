<script setup lang="ts">
import { useRoute } from "vue-router";
const route = useRoute();
const links = [
  { to: "/create/generate", label: "生成教案" },
  { to: "/create/optimize", label: "优化教案" },
  { to: "/", label: "历史任务" },
];
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <RouterLink to="/" class="brand" aria-label="灵犀教案首页">
        <span class="brand-mark" aria-hidden="true">灵</span>
        <span
          ><strong>灵犀教案</strong><small>Lesson Design Studio</small></span
        >
      </RouterLink>
      <nav aria-label="主导航">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          :class="{ active: route.path === link.to }"
          >{{ link.label }}</RouterLink
        >
      </nav>
    </div>
  </header>
</template>
