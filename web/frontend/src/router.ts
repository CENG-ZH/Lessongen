import { createRouter, createWebHistory } from "vue-router";
import DashboardView from "./views/DashboardView.vue";

export default createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: "/", name: "dashboard", component: DashboardView },
    {
      path: "/create/generate",
      name: "generate",
      component: () => import("./views/GenerateView.vue"),
    },
    {
      path: "/create/optimize",
      name: "optimize",
      component: () => import("./views/OptimizeView.vue"),
    },
    {
      path: "/jobs/:jobId",
      name: "job",
      component: () => import("./views/JobView.vue"),
      props: true,
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
