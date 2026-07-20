/** P14 — bilingual UI strings (Chinese / English toggle, per the product spec). */

export type Lang = "en" | "zh";

export const STRINGS = {
  en: {
    brand: "3D Medical CLIP",
    tagline: "Chest CT ↔ report retrieval",
    tabSearch: "Search",
    tabViewer: "Viewer",
    tabTasks: "Tasks",
    queryLabel: "Query",
    queryPlaceholder:
      "Describe the findings, e.g. large pleural effusion with an enlarged heart",
    search: "Search",
    searching: "Searching…",
    results: "Results",
    balance: "Recall ↔ findings balance",
    balanceHint: "Higher = trust image similarity more. Lower = weight clinical findings more.",
    topK: "Results to show",
    indexed: "indexed",
    engineOk: "CT-CLIP ready",
    engineDown: "CT-CLIP unavailable",
    noResults: "No results yet — enter a query and search.",
    noExplanation: "Matched on overall imaging similarity.",
    bothShow: "Both show",
    selectHint: "Select a result to view its report.",
    reportTitle: "Report",
    disclaimer:
      "Research and demonstration use only. Not intended for clinical diagnosis or treatment decisions.",
    engineHelp:
      "The CT-CLIP inference service is not running. Start it (see docs/RETRIEVAL_SERVING.md) — search is disabled until then.",
  },
  zh: {
    brand: "3D 医学 CLIP",
    tagline: "胸部 CT ↔ 报告检索",
    tabSearch: "检索",
    tabViewer: "阅片",
    tabTasks: "任务",
    queryLabel: "查询",
    queryPlaceholder: "描述影像所见，例如：大量胸腔积液伴心影增大",
    search: "检索",
    searching: "检索中…",
    results: "检索结果",
    balance: "召回 ↔ 征象 权重",
    balanceHint: "数值越高越依赖影像相似度；越低越侧重临床征象。",
    topK: "显示条数",
    indexed: "已索引",
    engineOk: "CT-CLIP 就绪",
    engineDown: "CT-CLIP 不可用",
    noResults: "暂无结果 —— 请输入查询后检索。",
    noExplanation: "基于整体影像相似度匹配。",
    bothShow: "双方均见",
    selectHint: "选择一条结果以查看其报告。",
    reportTitle: "报告",
    disclaimer: "仅供研究与演示使用，不用于临床诊断或治疗决策。",
    engineHelp:
      "CT-CLIP 推理服务未运行。请先启动（见 docs/RETRIEVAL_SERVING.md），在此之前无法检索。",
  },
} as const;

export type Strings = (typeof STRINGS)["en"];

export function t(lang: Lang): Strings {
  return STRINGS[lang] as Strings;
}
