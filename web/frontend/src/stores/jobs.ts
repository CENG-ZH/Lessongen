import { defineStore } from "pinia";
import { getArtifacts, getJob, getResult, listJobs } from "../api/client";
import type {
  Artifact,
  JobDetail,
  JobSummary,
  LessonResult,
} from "../types/api";

export const useJobStore = defineStore("jobs", {
  state: () => ({
    recent: [] as JobSummary[],
    current: null as JobDetail | null,
    result: null as LessonResult | null,
    artifacts: [] as Artifact[],
    loading: false,
  }),
  actions: {
    async loadRecent() {
      this.loading = true;
      try {
        this.recent = (await listJobs()).items;
      } finally {
        this.loading = false;
      }
    },
    async loadJob(id: string) {
      this.current = await getJob(id);
      return this.current;
    },
    async loadTerminalData(id: string) {
      const [artifacts, result] = await Promise.all([
        getArtifacts(id).catch(() => []),
        getResult(id).catch(() => null),
      ]);
      this.artifacts = artifacts;
      this.result = result;
    },
    resetCurrent() {
      this.current = null;
      this.result = null;
      this.artifacts = [];
    },
  },
});
