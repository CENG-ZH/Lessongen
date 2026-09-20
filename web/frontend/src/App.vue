<script setup lang="ts">
import AppHeader from "./components/AppHeader.vue";
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <AppHeader />
  <main id="main-content" class="page-shell" tabindex="-1">
    <RouterView v-slot="{ Component }">
      <Transition name="page" mode="out-in">
        <!-- Route views intentionally use fragments; Transition needs one keyed element to
             complete leave/enter reliably during in-app navigation. -->
        <div :key="$route.fullPath" class="route-frame">
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
