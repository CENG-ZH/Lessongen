import { defineStore } from "pinia";
import type { LessonInput, OptimizeInput } from "../types/api";

const base = (): LessonInput => ({
  subject: "",
  grade: "",
  topic: "",
  durationMinutes: 45,
  courseInformation: "",
  textbookVersion: "",
  textbookContent: "",
  curriculumStandards: [],
  learningObjectives: [],
  studentProfile: "",
  classSize: null,
  availableResources: [],
  additionalRequirements: "",
  lessonStyle: "choose_the_best_fit_for_this_topic",
  detailLevel: "showcase",
});
const load = <T>(key: string, fallback: T): T => {
  try {
    return JSON.parse(sessionStorage.getItem(key) || "") as T;
  } catch {
    return fallback;
  }
};

export const useDraftStore = defineStore("draft", {
  state: () => ({
    generate: load<LessonInput>("lesoongen.generate-draft", base()),
    optimize: load<OptimizeInput>("lesoongen.optimize-draft", {
      ...base(),
      optimizationFocus: [],
      mustPreserveContent: [],
    }),
  }),
  actions: {
    persistGenerate() {
      sessionStorage.setItem(
        "lesoongen.generate-draft",
        JSON.stringify(this.generate),
      );
    },
    persistOptimize() {
      sessionStorage.setItem(
        "lesoongen.optimize-draft",
        JSON.stringify(this.optimize),
      );
    },
    clearGenerate() {
      this.generate = base();
      sessionStorage.removeItem("lesoongen.generate-draft");
    },
    clearOptimize() {
      this.optimize = {
        ...base(),
        optimizationFocus: [],
        mustPreserveContent: [],
      };
      sessionStorage.removeItem("lesoongen.optimize-draft");
    },
  },
});
