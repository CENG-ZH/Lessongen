import { defineStore } from "pinia";

export const useConnectionStore = defineStore("connection", {
  state: () => ({
    mode: "connecting" as "connecting" | "live" | "polling",
    updatedAt: "",
  }),
  actions: {
    setLive(value: boolean) {
      this.mode = value ? "live" : "polling";
    },
    touched() {
      this.updatedAt = new Date().toISOString();
    },
  },
});
