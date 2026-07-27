const state = {
  allArticles: [],
  filteredArticles: [],
  view: "all",
  query: "",
  category: "전체",
  period: "all",
  sort: "latest",
  saved: new Set(readJson("altbrief-saved", [])),
  updatedAt: null
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const els = {
  totalCount: $("#totalCount"),
  updatedAt: $("#updatedAt"),
  savedCount: $("#savedCount"),
  searchInput: $("#searchInput"),
  refreshButton: $("#refreshButton"),
  retryButton: $("#retryButton"),
  categoryChips: $("#categoryChips"),
  periodSelect: $("#periodSelect"),
  sortSelect: $("#sortSelect"),
  sectionEyebrow: $("#sectionEyebrow"),
  sectionTitle: $("#sectionTitle"),
  resultCount: $("#resultCount"),
  newsGrid: $("#newsGrid"),
  loadingState: $("#loadingState"),
  errorState: $("#errorState"),
  errorMessage: $("#errorMessage"),
  emptyState: $("#emptyState"),
  articleTemplate: $("#articleTemplate"),
  toast: $("#toast"),
  themeButton: $("#themeButton")
};

function readJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => els.toast.classList.remove("show"), 2200);
}

async function loadNews({ force = false } = {}) {
  setLoading(true);

  try {
    const cacheBust = `?v=${Date.now()}`;
    const response = await fetch(`./news.json${cacheBust}`, {
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(`news.json 응답 오류 (${response.status})`);
    }

    const payload = await response.json();
    const rawArticles = getArticleArray(payload);

    state.updatedAt = getUpdatedAt(payload, rawArticles);
    state.allArticles = deduplicate(
      rawArticles
        .map(normalizeArticle)
        .filter((article) => article.title && article.url)
    );

    renderMeta();
    renderCategories();
    applyFilters();

    if (force) {
      showToast("최신 news.json을 다시 불러왔습니다.");
    }
  } catch (error) {
    console.error(error);
    showError(error.message || "news.json을 확인해 주세요.");
  } finally {
    setLoading(false);
  }
}

function getArticleArray(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.articles)) return payload.articles;
  if (Array.isArray(payload?.news)) return payload.news;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

function getUpdatedAt(payload, articles) {
  const candidates = [
    payload?.updated_at,
    payload?.updatedAt,
    payload?.last_updated,
    payload?.generated_at,
    payload?.generatedAt
  ].filter(Boolean);

  if (candidates.length) return toValidDate(candidates[0]);

  const articleDates = articles
    .map((item) => getFirst(item, ["published_at", "publishedAt", "pubDate", "date", "published", "created_at"]))
    .map(toValidDate)
    .filter(Boolean)
    .sort((a, b) => b - a);

  return articleDates[0] || null;
}

function normalizeArticle(raw, index) {
  const sourceRaw = raw?.source;
  const source =
    typeof sourceRaw === "object"
      ? getFirst(sourceRaw, ["name", "title", "publisher"]) || "출처 미상"
      : sourceRaw || raw?.publisher || raw?.media || raw?.press || "출처 미상";

  const title = cleanText(getFirst(raw, ["title", "headline", "name"]));
  const url = getFirst(raw, ["url", "link", "article_url", "original_url", "href"]) || "#";
  const summary = cleanText(
    getFirst(raw, ["summary", "ai_summary", "description", "snippet", "content", "abstract", "excerpt"])
  );
  const category = cleanText(
    getFirst(raw, ["category", "asset_class", "assetClass", "section", "topic", "type"])
  ) || "기타";
  const region = cleanText(
    getFirst(raw, ["region", "geography", "market", "country"])
  );
  const publishedAt = toValidDate(
    getFirst(raw, ["published_at", "publishedAt", "pubDate", "date", "published", "created_at", "createdAt"])
  );
  const tags = normalizeTags(raw?.tags);
  const id = String(raw?.id || url || `${title}-${index}`);

  return {
    id,
    title,
    url,
    summary: summary || title,
    source: cleanText(source),
    category,
    region,
    publishedAt,
    tags
  };
}

function getFirst(object, keys) {
  for (const key of keys) {
    const value = object?.[key];
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return "";
}

function cleanText(value) {
  if (value === null || value === undefined) return "";
  const wrapper = document.createElement("div");
  wrapper.innerHTML = String(value);
  return (wrapper.textContent || wrapper.innerText || "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeTags(tags) {
  if (Array.isArray(tags)) return tags.map(cleanText).filter(Boolean);
  if (typeof tags === "string") {
    return tags.split(",").map((tag) => tag.trim()).filter(Boolean);
  }
  return [];
}

function toValidDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function deduplicate(articles) {
  const seen = new Set();
  return articles.filter((article) => {
    const key = normalizeKey(article.url !== "#" ? article.url : article.title);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeKey(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFKC")
    .replace(/[^a-z0-9가-힣]/g, "");
}

function renderMeta() {
  els.totalCount.textContent = `${state.allArticles.length.toLocaleString("ko-KR")}개`;
  els.updatedAt.textContent = state.updatedAt
    ? formatDate(state.updatedAt, { includeTime: false })
    : "날짜 정보 없음";
  updateSavedCount();
}

function renderCategories() {
  const counts = new Map();
  state.allArticles.forEach((article) => {
    counts.set(article.category, (counts.get(article.category) || 0) + 1);
  });

  const categories = [
    ["전체", state.allArticles.length],
    ...[...counts.entries()].sort((a, b) => b[1] - a[1])
  ];

  if (!categories.some(([name]) => name === state.category)) {
    state.category = "전체";
  }

  els.categoryChips.innerHTML = "";

  categories.forEach(([name, count]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `chip ${state.category === name ? "active" : ""}`;
    button.textContent = `${name} ${count}`;
    button.addEventListener("click", () => {
      state.category = name;
      renderCategories();
      applyFilters();
    });
    els.categoryChips.appendChild(button);
  });
}

function applyFilters() {
  const query = state.query.toLowerCase();
  const now = Date.now();
  const periodDays = state.period === "all" ? null : Number(state.period);

  let items = state.allArticles.filter((article) => {
    const matchesView =
      state.view === "all" || state.saved.has(article.id);

    const searchable = [
      article.title,
      article.summary,
      article.source,
      article.category,
      article.region,
      ...article.tags
    ].join(" ").toLowerCase();

    const matchesQuery = !query || searchable.includes(query);
    const matchesCategory =
      state.category === "전체" || article.category === state.category;

    const matchesPeriod =
      !periodDays ||
      !article.publishedAt ||
      now - article.publishedAt.getTime() <= periodDays * 24 * 60 * 60 * 1000;

    return matchesView && matchesQuery && matchesCategory && matchesPeriod;
  });

  items = sortArticles(items);
  state.filteredArticles = items;
  renderArticles();
}

function sortArticles(items) {
  const copy = [...items];

  if (state.sort === "oldest") {
    return copy.sort((a, b) => dateValue(a.publishedAt) - dateValue(b.publishedAt));
  }

  if (state.sort === "source") {
    return copy.sort((a, b) =>
      a.source.localeCompare(b.source, "ko") ||
      dateValue(b.publishedAt) - dateValue(a.publishedAt)
    );
  }

  return copy.sort((a, b) => dateValue(b.publishedAt) - dateValue(a.publishedAt));
}

function dateValue(date) {
  return date ? date.getTime() : 0;
}

function renderArticles() {
  els.newsGrid.innerHTML = "";
  els.resultCount.textContent = `${state.filteredArticles.length.toLocaleString("ko-KR")}개 기사`;
  els.emptyState.classList.toggle("hidden", state.filteredArticles.length > 0);
  els.sectionEyebrow.textContent = state.view === "saved" ? "SAVED" : "LATEST";
  els.sectionTitle.textContent = state.view === "saved" ? "저장한 기사" : "최신 뉴스";

  const fragment = document.createDocumentFragment();
  state.filteredArticles.forEach((article) => {
    fragment.appendChild(createArticleCard(article));
  });
  els.newsGrid.appendChild(fragment);
}

function createArticleCard(article) {
  const card = els.articleTemplate.content.firstElementChild.cloneNode(true);

  card.querySelector(".category-tag").textContent = article.category;

  const regionTag = card.querySelector(".region-tag");
  if (article.region) {
    regionTag.textContent = article.region;
    regionTag.classList.remove("hidden");
  }

  const source = card.querySelector(".article-source");
  source.textContent = article.source;

  const sourceAvatar = card.querySelector(".source-avatar");
  sourceAvatar.textContent = getInitial(article.source);

  const date = card.querySelector(".article-date");
  date.textContent = article.publishedAt
    ? formatDate(article.publishedAt, { includeTime: true })
    : "게시일 미상";
  if (article.publishedAt) {
    date.dateTime = article.publishedAt.toISOString();
  }

  card.querySelector(".article-title").textContent = article.title;
  card.querySelector(".article-summary").textContent = article.summary;

  const link = card.querySelector(".article-link");
  link.href = article.url;
  if (article.url === "#") {
    link.classList.add("hidden");
  }

  const bookmark = card.querySelector(".bookmark-button");
  const isSaved = state.saved.has(article.id);
  bookmark.classList.toggle("saved", isSaved);
  bookmark.querySelector("span").textContent = isSaved ? "★" : "☆";
  bookmark.setAttribute("aria-label", isSaved ? "저장 해제" : "기사 저장");
  bookmark.addEventListener("click", () => toggleSaved(article.id));

  return card;
}

function getInitial(source) {
  const cleaned = String(source || "?").trim();
  if (!cleaned) return "?";
  const first = cleaned[0];
  return /[a-z]/i.test(first) ? first.toUpperCase() : first;
}

function toggleSaved(id) {
  if (state.saved.has(id)) {
    state.saved.delete(id);
    showToast("저장한 기사에서 삭제했습니다.");
  } else {
    state.saved.add(id);
    showToast("이 브라우저에 저장했습니다.");
  }

  saveJson("altbrief-saved", [...state.saved]);
  updateSavedCount();
  applyFilters();
}

function updateSavedCount() {
  const validCount = state.allArticles.filter((article) => state.saved.has(article.id)).length;
  els.savedCount.textContent = validCount;
  els.savedCount.classList.toggle("hidden", validCount === 0);
}

function setView(view) {
  state.view = view;
  $$("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  applyFilters();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setLoading(isLoading) {
  els.loadingState.classList.toggle("hidden", !isLoading);
  if (isLoading) {
    els.errorState.classList.add("hidden");
    els.emptyState.classList.add("hidden");
    els.newsGrid.innerHTML = "";
  }
}

function showError(message) {
  els.errorMessage.textContent = `${message} 기존 news.json 파일이 저장소에 있는지 확인해 주세요.`;
  els.errorState.classList.remove("hidden");
  els.emptyState.classList.add("hidden");
  els.newsGrid.innerHTML = "";
}

function formatDate(date, { includeTime }) {
  const options = includeTime
    ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { year: "numeric", month: "short", day: "numeric" };

  return new Intl.DateTimeFormat("ko-KR", options).format(date);
}

function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function initializeTheme() {
  const savedTheme = localStorage.getItem("altbrief-theme");
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const theme = savedTheme || (prefersDark ? "dark" : "light");
  document.documentElement.dataset.theme = theme;
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("altbrief-theme", next);
}

$$("[data-view]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

els.searchInput.addEventListener("input", debounce((event) => {
  state.query = event.target.value.trim();
  applyFilters();
}));

els.periodSelect.addEventListener("change", (event) => {
  state.period = event.target.value;
  applyFilters();
});

els.sortSelect.addEventListener("change", (event) => {
  state.sort = event.target.value;
  applyFilters();
});

els.refreshButton.addEventListener("click", async () => {
  els.refreshButton.disabled = true;
  els.refreshButton.innerHTML = "<span>↻</span> 불러오는 중";
  await loadNews({ force: true });
  els.refreshButton.disabled = false;
  els.refreshButton.innerHTML = "<span>↻</span> 새로고침";
});

els.retryButton.addEventListener("click", () => loadNews({ force: true }));
els.themeButton.addEventListener("click", toggleTheme);

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    els.searchInput.focus();
  }
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js?v=6", { updateViaCache: "none" }).catch(console.error);
  });
}

initializeTheme();
loadNews();
