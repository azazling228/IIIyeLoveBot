(() => {
  const telegram = window.Telegram?.WebApp;
  const main = document.getElementById("main");
  const toastNode = document.getElementById("toast");
  const photoCache = new Map();
  const mediaCache = new Map();
  const themeStorageKey = "shue-miniapp-theme";
  const state = {
    tab: "discover",
    profile: null,
    likes: [],
    partner: null,
    messages: [],
    poll: null,
    me: null,
    pendingFile: null,
    quiz: null,
    quizGender: "all",
  };

  applyTheme(localStorage.getItem(themeStorageKey) || "dark");
  telegram?.ready();
  telegram?.expand();

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function displayName(profile) {
    const title = profile.quiz_title
      ? `<small class="user-title-inline ${quizTitleClass(profile.quiz_title)}">${escapeHtml(profile.quiz_title)}</small>`
      : "";
    return `${escapeHtml(profile.name)}${title}`;
  }

  function quizTitleClass(title) {
    return ({
      "Магистр ШУЕ": "title-master",
      "Безумец": "title-mad",
      "Знаток": "title-expert",
      "Почётный зритель": "title-viewer",
      "Позёр": "title-poser",
      "Позер": "title-poser",
    })[title] || "";
  }

  async function api(path, options = {}) {
    const initData = telegram?.initData;
    if (!initData) {
      throw new Error("Открой приложение через Telegram, чтобы войти.");
    }
    const response = await fetch(path, {
      ...options,
      headers: {
        Authorization: `tma ${initData}`,
        ...(options.body && !(options.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...options.headers,
      },
    });
    let result = null;
    if (response.status !== 204) {
      try {
        result = await response.json();
      } catch (error) {
        if (response.ok) throw error;
      }
    }
    if (!response.ok) {
      throw new Error(
        result?.error || `Не удалось выполнить запрос (${response.status}).`,
      );
    }
    return result;
  }

  function showToast(message) {
    toastNode.textContent = message;
    toastNode.classList.add("visible");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      toastNode.classList.remove("visible");
    }, 2600);
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
  }

  function toggleTheme() {
    const nextTheme = document.documentElement.dataset.theme === "dark"
      ? "light"
      : "dark";
    localStorage.setItem(themeStorageKey, nextTheme);
    applyTheme(nextTheme);
    const button = document.getElementById("theme-toggle");
    if (button) {
      button.textContent = nextTheme === "dark" ? "☀️" : "☾";
      button.setAttribute(
        "aria-label",
        nextTheme === "dark" ? "Включить светлую тему" : "Включить тёмную тему",
      );
      button.title = nextTheme === "dark" ? "Светлая тема" : "Тёмная тема";
    }
  }

  function runAction(action) {
    Promise.resolve().then(action).catch((error) => showToast(error.message));
  }

  function showError(error) {
    main.innerHTML = `
      <section class="empty-state">
        <div class="empty-icon">♡</div>
        <h2>Не получилось загрузить</h2>
        <p>${escapeHtml(error.message)}</p>
        <button class="primary-button" id="retry">Попробовать снова</button>
      </section>`;
    document.getElementById("retry").addEventListener("click", () => loadTab(state.tab));
  }

  async function loadPhoto(profileId, image) {
    if (photoCache.has(profileId)) {
      image.src = photoCache.get(profileId);
      return;
    }
    try {
      const initData = telegram?.initData;
      if (!initData) return;
      const response = await fetch(`/api/profiles/${profileId}/photo`, {
        headers: { Authorization: `tma ${initData}` },
      });
      if (!response.ok) return;
      const objectUrl = URL.createObjectURL(await response.blob());
      photoCache.set(profileId, objectUrl);
      image.src = objectUrl;
    } catch (error) {
      console.error("Could not load profile photo", error);
    }
  }

  async function loadChatMedia(partnerId, messageId, element) {
    const cacheKey = `${partnerId}:${messageId}`;
    if (mediaCache.has(cacheKey)) {
      element.src = mediaCache.get(cacheKey);
      return;
    }
    try {
      const initData = telegram?.initData;
      if (!initData) return;
      const response = await fetch(
        `/api/chats/${partnerId}/messages/${messageId}/media`,
        { headers: { Authorization: `tma ${initData}` } },
      );
      if (!response.ok) return;
      const objectUrl = URL.createObjectURL(await response.blob());
      mediaCache.set(cacheKey, objectUrl);
      element.src = objectUrl;
    } catch (error) {
      console.error("Could not load chat attachment", error);
    }
  }

  function setActiveTab(tab) {
    state.tab = tab;
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("active", item.dataset.tab === tab);
    });
    document.querySelector(".bottom-nav").classList.remove("hidden");
    window.clearInterval(state.poll);
    state.poll = null;
  }

  function renderEmpty(icon, title, description, actionLabel, action) {
    main.innerHTML = `
      <section class="empty-state">
        <div class="empty-icon">${icon}</div>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(description)}</p>
        ${actionLabel ? `<button class="primary-button" id="empty-action">${escapeHtml(actionLabel)}</button>` : ""}
      </section>`;
    if (actionLabel) {
      document.getElementById("empty-action").addEventListener("click", () => runAction(action));
    }
  }

  async function discover(force = false) {
    setActiveTab("discover");
    if (state.profile && !force) {
      renderProfileCard(state.profile);
      return;
    }
    const result = await api("/api/discover");
    state.profile = result.profile;
    if (!state.profile) {
      main.innerHTML = `
        ${renderDiscoveryToolbar()}
        <section class="empty-state">
          <div class="empty-icon">♡</div>
          <h2>Анкеты закончились</h2>
          <p>Пока больше некого показать. Загляни сюда позже или начни поиск заново.</p>
          <button class="primary-button" id="empty-action">Показать сначала</button>
        </section>`;
      bindSearchSettings();
      document.getElementById("empty-action").addEventListener(
        "click",
        () => runAction(async () => {
          await api("/api/discover/reset", { method: "POST" });
          await discover(true);
        }),
      );
      return;
    }
    renderProfileCard(state.profile);
  }

  function renderDiscoveryToolbar() {
    const isDark = document.documentElement.dataset.theme !== "light";
    return `
      <div class="discovery-toolbar">
        <h1 class="page-heading">Поиск</h1>
        <div class="discovery-tools">
          <button class="icon-button theme-toggle" id="theme-toggle"
            type="button" aria-label="${isDark ? "Включить светлую тему" : "Включить тёмную тему"}"
            title="${isDark ? "Светлая тема" : "Тёмная тема"}">${isDark ? "☀️" : "☾"}</button>
          <button class="icon-button settings-trigger" id="open-search-settings"
            type="button" aria-label="Настройки поиска" aria-expanded="false">☷</button>
        </div>
      </div>
      ${renderSearchSettingsModal()}`;
  }

  function renderSearchSettingsModal() {
    const profile = state.me;
    const genderOptions = [
      ["male", "Парни"],
      ["female", "Девушки"],
      ["all", "Все"],
    ];
    return `
      <div class="settings-backdrop hidden" id="search-settings-layer">
        <section class="search-settings-sheet" role="dialog" aria-modal="true"
          aria-labelledby="search-settings-title">
          <div class="sheet-handle" aria-hidden="true"></div>
          <div class="sheet-heading">
            <h2 id="search-settings-title">Настройки поиска</h2>
            <button class="icon-button close-settings" id="close-search-settings"
              type="button" aria-label="Закрыть настройки">×</button>
          </div>
          <form class="search-settings-form" id="search-settings-form">
            <span class="field-label">Ищу</span>
            <div class="gender-options" role="group" aria-label="Кого показывать">
              ${genderOptions.map(([value, label]) => `
                <label class="gender-option ${profile?.search_gender === value ? "selected" : ""}">
                  <input type="radio" name="search_gender" value="${value}"
                    ${profile?.search_gender === value ? "checked" : ""}>
                  <span>${label}</span>
                </label>`).join("")}
            </div>
            <span class="field-label age-heading">Возраст</span>
            <div class="age-range-fields">
              <label class="age-field">
                <span class="field-label">От</span>
                <input class="chat-input" type="number" name="search_age_min"
                  min="18" max="100" required value="${profile?.search_age_min ?? 18}">
              </label>
              <label class="age-field">
                <span class="field-label">До</span>
                <input class="chat-input" type="number" name="search_age_max"
                  min="18" max="100" required value="${profile?.search_age_max ?? 100}">
              </label>
            </div>
            <button class="primary-button search-save-button" type="submit">
              Сохранить настройки
            </button>
          </form>
        </section>
      </div>`;
  }

  function bindSearchSettings() {
    document.getElementById("theme-toggle")?.addEventListener("click", toggleTheme);
    const layer = document.getElementById("search-settings-layer");
    const openButton = document.getElementById("open-search-settings");
    const closeSettings = () => {
      layer?.classList.add("hidden");
      openButton?.setAttribute("aria-expanded", "false");
      openButton?.focus();
    };
    openButton?.addEventListener("click", () => {
      layer?.classList.remove("hidden");
      openButton.setAttribute("aria-expanded", "true");
      document.getElementById("close-search-settings")?.focus();
    });
    document.getElementById("close-search-settings")?.addEventListener(
      "click",
      closeSettings,
    );
    layer?.addEventListener("click", (event) => {
      if (event.target === layer) closeSettings();
    });
    layer?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSettings();
    });
    document.getElementById("search-settings-form")?.addEventListener(
      "submit",
      saveSearchSettings,
    );
    document.querySelectorAll('input[name="search_gender"]').forEach((input) => {
      input.addEventListener("change", () => {
        document.querySelectorAll(".gender-option").forEach((option) => {
          option.classList.toggle(
            "selected",
            option.querySelector("input").checked,
          );
        });
      });
    });
  }

  async function saveSearchSettings(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    const payload = {
      search_gender: values.search_gender,
      search_age_min: Number(values.search_age_min),
      search_age_max: Number(values.search_age_max),
    };
    if (
      !Number.isInteger(payload.search_age_min)
      || !Number.isInteger(payload.search_age_max)
      || payload.search_age_min < 18
      || payload.search_age_min > 100
      || payload.search_age_max < 18
      || payload.search_age_max > 100
      || payload.search_age_max < payload.search_age_min
    ) {
      showToast("Проверь диапазон возраста: от 18 до 100 лет.");
      return;
    }
    button.disabled = true;
    try {
      const settings = await api("/api/search-settings", {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      state.me = { ...state.me, ...settings };
      state.profile = null;
      showToast("Настройки поиска сохранены");
      document.getElementById("search-settings-layer")?.classList.add("hidden");
      await discover(true);
    } catch (error) {
      button.disabled = false;
      showToast(error.message);
    }
  }

  function renderProfileCard(profile) {
    main.innerHTML = `
      ${renderDiscoveryToolbar()}
      <section class="discover-wrap">
        <article class="profile-card">
          ${profile.has_photo ? `<img class="profile-photo" id="discover-photo" alt="">` : ""}
          <div class="profile-info">
            <h1 class="profile-title">${displayName(profile)}, ${profile.age}</h1>
            <p class="profile-meta">⌖ ${escapeHtml(profile.city)}</p>
            ${profile.description ? `<p class="profile-description">${escapeHtml(profile.description)}</p>` : ""}
            ${profile.quiz_percent !== null && profile.quiz_percent !== undefined
              ? `<p class="profile-quiz-rating">♛ Рейтинг теста: ${profile.quiz_percent}%</p>`
              : ""}
          </div>
        </article>
        <div class="discover-actions">
          <button class="round-action" id="skip-profile" aria-label="Пропустить">✕</button>
          <button class="round-action message-like" id="message-like-profile" aria-label="Лайкнуть с сообщением">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H7l-3.5 2v-5A7.5 7.5 0 1 1 20 11.5Z"></path>
              <path d="M12 15.6s-3-1.8-3-3.6a1.7 1.7 0 0 1 3-1.1 1.7 1.7 0 0 1 3 1.1c0 1.8-3 3.6-3 3.6Z"></path>
            </svg>
          </button>
          <button class="round-action like" id="like-profile" aria-label="Нравится">♥</button>
        </div>
      </section>`;
    bindSearchSettings();
    if (profile.has_photo) {
      loadPhoto(profile.id, document.getElementById("discover-photo"));
    }
    document.getElementById("skip-profile").addEventListener("click", () => runAction(() => decide("skip")));
    document.getElementById("like-profile").addEventListener("click", () => runAction(() => decide("like")));
    document.getElementById("message-like-profile").addEventListener(
      "click",
      () => openLikeMessageComposer(),
    );
  }

  function openLikeMessageComposer() {
    const layer = document.createElement("div");
    layer.className = "settings-backdrop";
    layer.innerHTML = `
      <section class="search-settings-sheet like-message-sheet" role="dialog"
        aria-modal="true" aria-labelledby="like-message-title">
        <div class="sheet-handle" aria-hidden="true"></div>
        <div class="sheet-heading">
          <h2 id="like-message-title">Лайк с сообщением</h2>
          <button class="icon-button close-settings" type="button"
            aria-label="Закрыть">×</button>
        </div>
        <p class="settings-description">
          Одно короткое сообщение появится у человека вместе с уведомлением о лайке.
        </p>
        <form class="preferences-form" id="like-message-form">
          <textarea class="chat-input like-message-input" maxlength="500"
            required placeholder="Например: привет, го знакомиться"></textarea>
          <p class="field-hint">До 500 символов.</p>
          <button class="primary-button search-save-button" type="submit">
            Отправить лайк
          </button>
        </form>
      </section>`;
    document.body.appendChild(layer);
    const close = () => layer.remove();
    layer.querySelector(".close-settings").addEventListener("click", close);
    layer.addEventListener("click", (event) => {
      if (event.target === layer) close();
    });
    layer.querySelector("#like-message-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = layer.querySelector(".like-message-input");
      const button = event.currentTarget.querySelector("button");
      button.disabled = true;
      try {
        await decide("like", input.value.trim());
        close();
      } catch (error) {
        button.disabled = false;
        showToast(error.message);
      }
    });
    layer.querySelector(".like-message-input").focus();
  }

  async function decide(action, message = "") {
    if (!state.profile) return;
    const viewed = state.profile;
    const controls = main.querySelectorAll(".round-action");
    controls.forEach((button) => { button.disabled = true; });
    let result;
    try {
      result = await api("/api/discover/decision", {
        method: "POST",
        body: JSON.stringify({ profile_id: viewed.id, action, message }),
      });
    } catch (error) {
      controls.forEach((button) => { button.disabled = false; });
      throw error;
    }
    if (result.matched) showToast(`У вас мэтч с ${viewed.name}! 💘`);
    else if (action === "like") showToast("Симпатия отправлена ❤️");
    state.profile = null;
    await discover(true);
  }

  async function loadLikes() {
    setActiveTab("likes");
    const result = await api("/api/likes");
    state.likes = result.profiles;
    updateBadges(state.likes.length, null);
    renderLikes();
  }

  function renderLikes() {
    if (!state.likes.length) {
      renderEmpty("♡", "Пока тихо", "Когда кто-нибудь поставит тебе лайк, анкета появится здесь.", null);
      return;
    }
    const cards = state.likes.map((profile) => `
      <article class="person-row like-row" data-id="${profile.id}">
        ${profile.has_photo ? `<img class="avatar" data-photo-id="${profile.id}" alt="">` : `<div class="avatar"></div>`}
        <span class="person-copy">
          <span class="person-name">${displayName(profile)}, ${profile.age}</span>
          <span class="person-preview">${escapeHtml(profile.city)}${profile.description ? ` · ${escapeHtml(profile.description)}` : ""}</span>
          ${profile.quiz_percent !== null && profile.quiz_percent !== undefined
            ? `<small class="quiz-card-rating">♛ Рейтинг теста: ${profile.quiz_percent}%</small>`
            : ""}
        </span>
        <span class="unread">♥</span>
      </article>
      ${profile.like_message ? `<p class="like-message-preview">💌 ${escapeHtml(profile.like_message)}</p>` : ""}
      <div class="discover-actions compact-actions" data-actions="${profile.id}">
        <button class="secondary-button" data-skip-like="${profile.id}">Пропустить</button>
        <button class="primary-button" data-like-back="${profile.id}">Ответить ❤️</button>
      </div>`).join("");
    main.innerHTML = `<p class="eyebrow">Взаимная симпатия начинается здесь</p>
      <h1 class="page-heading">Твои лайки</h1><section class="content-list">${cards}</section>`;
    main.querySelectorAll("[data-photo-id]").forEach((image) => {
      loadPhoto(Number(image.dataset.photoId), image);
    });
    main.querySelectorAll("[data-like-back]").forEach((button) => {
      button.addEventListener("click", () => runAction(() => respondToLike(Number(button.dataset.likeBack), "like")));
    });
    main.querySelectorAll("[data-skip-like]").forEach((button) => {
      button.addEventListener("click", () => runAction(() => respondToLike(Number(button.dataset.skipLike), "skip")));
    });
  }

  async function respondToLike(profileId, action) {
    const result = await api("/api/likes/respond", {
      method: "POST",
      body: JSON.stringify({ profile_id: profileId, action }),
    });
    if (result.matched) showToast("Это взаимно! У вас мэтч 💘");
    await loadLikes();
  }

  async function loadChats() {
    setActiveTab("chats");
    const result = await api("/api/chats");
    updateBadges(null, result.chats.reduce((total, chat) => total + chat.unread_count, 0));
    if (!result.chats.length) {
      renderEmpty("☏", "Здесь будут ваши чаты", "Когда вы понравитесь друг другу, переписка появится здесь.", "Начать знакомиться", discover);
      return;
    }
    main.innerHTML = `
      <p class="eyebrow">Продолжи знакомство</p>
      <h1 class="page-heading">Твои чаты</h1>
      <section class="content-list">
        ${result.chats.map((chat) => `
          <button class="person-row" data-open-chat="${chat.id}">
            ${chat.has_photo ? `<img class="avatar" data-photo-id="${chat.id}" alt="">` : `<span class="avatar"></span>`}
            <span class="person-copy">
              <span class="person-name">${displayName(chat)}, ${chat.age}</span>
              <span class="person-preview">${escapeHtml(chat.last_message || chat.city)}</span>
              ${chat.quiz_percent !== null && chat.quiz_percent !== undefined
                ? `<small class="quiz-card-rating">♛ ${chat.quiz_percent}%</small>`
                : ""}
            </span>
            ${chat.unread_count ? `<span class="unread">${chat.unread_count}</span>` : ""}
          </button>`).join("")}
      </section>`;
    main.querySelectorAll("[data-photo-id]").forEach((image) => {
      loadPhoto(Number(image.dataset.photoId), image);
    });
    main.querySelectorAll("[data-open-chat]").forEach((button) => {
      button.addEventListener("click", () => runAction(() => openChat(Number(button.dataset.openChat))));
    });
  }

  async function loadMatches() {
    setActiveTab("matches");
    const result = await api("/api/matches");
    if (!result.matches.length) {
      renderEmpty(
        "💘",
        "Пока нет мэтчей",
        "Когда симпатия станет взаимной, ваши мэтчи появятся здесь.",
        "Начать знакомиться",
        discover,
      );
      return;
    }
    main.innerHTML = `
      <p class="eyebrow">Взаимная симпатия</p>
      <h1 class="page-heading">Твои мэтчи</h1>
      <section class="content-list">
        ${result.matches.map((match) => `
          <article class="match-card">
            <div class="person-row match-person">
              ${match.has_photo ? `<img class="avatar" data-photo-id="${match.id}" alt="">` : `<span class="avatar"></span>`}
              <span class="person-copy">
                <span class="person-name">${displayName(match)}, ${match.age}</span>
                <span class="person-preview">${escapeHtml(match.city)}</span>
                ${match.quiz_percent !== null && match.quiz_percent !== undefined
                  ? `<small class="quiz-card-rating">♛ ${match.quiz_percent}%</small>`
                  : ""}
              </span>
              <span class="match-heart">♥</span>
            </div>
            ${match.description ? `<p class="match-description">${escapeHtml(match.description)}</p>` : ""}
            <div class="match-actions">
              <button class="primary-button match-chat-button" data-open-match="${match.id}">
                💬 Открыть чат
              </button>
              <button class="secondary-button delete-match-button" data-delete-match="${match.id}">
                Удалить мэтч
              </button>
            </div>
          </article>`).join("")}
      </section>`;
    main.querySelectorAll("[data-photo-id]").forEach((image) => {
      loadPhoto(Number(image.dataset.photoId), image);
    });
    main.querySelectorAll("[data-open-match]").forEach((button) => {
      button.addEventListener("click", () => {
        runAction(() => openChat(Number(button.dataset.openMatch)));
      });
    });
    main.querySelectorAll("[data-delete-match]").forEach((button) => {
      button.addEventListener("click", () => {
        runAction(() => removeMatch(Number(button.dataset.deleteMatch)));
      });
    });
  }

  async function removeMatch(partnerId) {
    const confirmed = await confirmMatchRemoval();
    if (!confirmed) return;
    await api(`/api/matches/${partnerId}`, { method: "DELETE" });
    showToast("Мэтч и переписка удалены");
    await loadMatches();
    const chats = await api("/api/chats");
    updateBadges(
      null,
      chats.chats.reduce((total, chat) => total + chat.unread_count, 0),
    );
  }

  function confirmMatchRemoval() {
    if (telegram?.showConfirm) {
      return new Promise((resolve) => {
        telegram.showConfirm(
          "Удалить мэтч и всю переписку у вас обоих? Это действие нельзя отменить.",
          resolve,
        );
      });
    }
    return Promise.resolve(window.confirm(
      "Удалить мэтч и всю переписку у вас обоих? Это действие нельзя отменить.",
    ));
  }

  async function openChat(partnerId) {
    window.clearInterval(state.poll);
    state.pendingFile = null;
    state.messages = [];
    state.partner = { id: partnerId };
    document.querySelector(".bottom-nav").classList.add("hidden");
    await refreshChat(true);
    if (state.partner) {
      state.poll = window.setInterval(
        () => refreshChat(false).catch((error) => showToast(error.message)),
        5000,
      );
    }
  }

  async function refreshChat(initial) {
    if (!state.partner) return;
    const oldInput = document.getElementById("chat-input");
    const draft = oldInput?.value || "";
    const wasFocused = document.activeElement === oldInput;
    const oldList = main.querySelector(".chat-messages");
    const wasAtBottom = !oldList || oldList.scrollHeight - oldList.scrollTop - oldList.clientHeight < 48;
    let result;
    try {
      result = await api(`/api/chats/${state.partner.id}/messages`);
    } catch (error) {
      if (error.message.includes("This chat is not available.")) {
        window.clearInterval(state.poll);
        state.poll = null;
        state.partner = null;
        showToast("Мэтч удалён, переписка больше недоступна");
        await loadChats();
        return;
      }
      throw error;
    }
    state.partner = result.partner;
    const previousMessages = state.messages;
    state.messages = result.messages;
    const isAppend = !initial
      && main.querySelector(".chat-messages")
      && previousMessages.length <= result.messages.length
      && previousMessages.every(
        (message, index) => message.id === result.messages[index]?.id,
      );
    if (isAppend) {
      const addedMessages = result.messages.slice(previousMessages.length);
      if (addedMessages.length) appendChatMessages(addedMessages);
    } else {
      renderChat();
    }
    const newInput = document.getElementById("chat-input");
    if (!newInput) return;
    newInput.value = draft;
    if (wasFocused) newInput.focus();
    const newList = main.querySelector(".chat-messages");
    if (initial || wasAtBottom) newList.scrollTop = newList.scrollHeight;
  }

  function renderChat() {
    const partner = state.partner;
    const messages = state.messages.map(renderChatMessage).join("");
    main.innerHTML = `
      <section class="chat-screen">
        <header class="chat-header">
          <button id="back-chats" class="chat-back" aria-label="Назад">‹</button>
          ${partner.has_photo ? `<img class="avatar" id="chat-photo" alt="">` : `<span class="avatar"></span>`}
          <div class="person-copy">
            <span class="person-name">${displayName(partner)}, ${partner.age}</span>
            <span class="person-preview">${escapeHtml(partner.city)}</span>
          </div>
        </header>
        <div class="chat-messages">${messages || `<p class="person-preview">Напиши первое сообщение — начните знакомство ❤️</p>`}</div>
        <form class="chat-form" id="chat-form">
          <label class="attach-button" aria-label="Прикрепить фото или аудио">
            ＋
            <input id="chat-file" class="chat-file-input" type="file"
              accept="image/*,audio/*" aria-label="Выбрать фото или аудиофайл">
          </label>
          <input class="chat-input" id="chat-input" maxlength="3900" autocomplete="off" placeholder="Сообщение…">
          <button class="send-button" aria-label="Отправить">➤</button>
        </form>
        <div class="chat-attachment-pending ${state.pendingFile ? "" : "hidden"}" id="chat-attachment-pending">
          <span id="chat-attachment-name">${escapeHtml(state.pendingFile?.name || "")}</span>
          <button id="clear-chat-attachment" type="button" aria-label="Убрать файл">×</button>
        </div>
      </section>`;
    document.getElementById("back-chats").addEventListener("click", loadChats);
    document.getElementById("chat-form").addEventListener("submit", sendChatMessage);
    document.getElementById("chat-file").addEventListener("change", (event) => {
      state.pendingFile = event.currentTarget.files[0] || null;
      const pending = document.getElementById("chat-attachment-pending");
      pending.classList.toggle("hidden", !state.pendingFile);
      document.getElementById("chat-attachment-name").textContent =
        state.pendingFile?.name || "";
    });
    document.getElementById("clear-chat-attachment").addEventListener("click", () => {
      state.pendingFile = null;
      document.getElementById("chat-file").value = "";
      document.getElementById("chat-attachment-pending").classList.add("hidden");
    });
    main.querySelectorAll("[data-chat-media-id]").forEach((element) => {
      loadChatMedia(partner.id, element.dataset.chatMediaId, element);
    });
    const photo = document.getElementById("chat-photo");
    if (photo) loadPhoto(partner.id, photo);
    const list = main.querySelector(".chat-messages");
    list.scrollTop = list.scrollHeight;
  }

  function renderChatMessage(message) {
    const attachment = message.media_type === "photo"
      ? `<img class="chat-attachment chat-image" data-chat-media-id="${message.id}" alt="Фото">`
      : message.media_type === "audio"
        ? `<audio class="chat-attachment chat-audio" data-chat-media-id="${message.id}" controls preload="metadata"></audio>`
        : "";
    return `
      <div class="bubble ${message.sender_id === state.me?.id ? "mine" : "theirs"}">
        ${attachment}
        ${message.text ? `<div class="chat-caption">${escapeHtml(message.text)}</div>` : ""}
      </div>`;
  }

  function appendChatMessages(messages) {
    const list = main.querySelector(".chat-messages");
    if (!list) return;
    const wasAtBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 48;
    if (!state.messages.length) return;
    list.querySelector(".person-preview")?.remove();
    list.insertAdjacentHTML("beforeend", messages.map(renderChatMessage).join(""));
    messages.forEach((message) => {
      if (message.media_type === "text") return;
      const element = list.querySelector(`[data-chat-media-id="${message.id}"]`);
      if (element) loadChatMedia(state.partner.id, message.id, element);
    });
    if (wasAtBottom) list.scrollTop = list.scrollHeight;
  }

  async function sendChatMessage(event) {
    event.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    const file = state.pendingFile;
    if (!text && !file) return;
    if (file && file.size > 20 * 1024 * 1024) {
      showToast("Размер файла не должен превышать 20 МБ");
      return;
    }
    if (file && text.length > 900) {
      showToast("Подпись к файлу может содержать до 900 символов");
      return;
    }
    input.disabled = true;
    try {
      let result;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("caption", text);
        result = await api(`/api/chats/${state.partner.id}/media`, {
          method: "POST",
          body: form,
        });
      } else {
        result = await api(`/api/chats/${state.partner.id}/messages`, {
          method: "POST",
          body: JSON.stringify({ text }),
        });
      }
      if (result.filtered) {
        showToast("Сообщение скрыто фильтром собеседника");
        return;
      }
      state.pendingFile = null;
      input.value = "";
      if (result.notification_warning) showToast(result.notification_warning);
      else if (result.notification_disabled) {
        showToast("Сообщение сохранено; у собеседника отключены уведомления");
      }
      await refreshChat(false);
    } catch (error) {
      showToast(error.message);
    } finally {
      input.disabled = false;
      input.focus();
    }
  }

  async function loadProfile() {
    setActiveTab("profile");
    const profile = await api("/api/me");
    state.me = profile;
    renderProfile(profile);
  }

  async function loadQuiz() {
    setActiveTab("quiz");
    state.quizGender = "all";
    state.quiz = await api("/api/quiz");
    renderQuizDashboard();
    await loadQuizLeaderboard(state.quizGender);
  }

  function renderQuizDashboard() {
    const quiz = state.quiz;
    const scoreText = quiz.has_result
      ? `${quiz.best_score}/${quiz.total_questions} · ${quiz.percent}%`
      : "Ещё не проходил";
    main.innerHTML = `
      <p class="eyebrow">Проверь свою эрудицию</p>
      <h1 class="page-heading">Тест на знание нижнего интернета</h1>
      <section class="quiz-summary-card">
        <div class="quiz-stat">
          <strong>${scoreText}</strong>
          <span>Лучший результат</span>
        </div>
        <div class="quiz-stat">
          <strong>${quiz.attempts_remaining}</strong>
          <span>Попыток осталось</span>
        </div>
        ${quiz.title ? `<div class="quiz-title-line ${quizTitleClass(quiz.title)}">${escapeHtml(quiz.title)}</div>` : ""}
        ${quiz.has_result
          ? `<label class="quiz-title-toggle">
              <span>Показывать звание рядом с именем</span>
              <input id="quiz-title-visibility" type="checkbox" ${quiz.show_title ? "checked" : ""}>
              <span class="toggle-track" aria-hidden="true"></span>
            </label>`
          : ""}
        <button class="primary-button quiz-start-button" id="quiz-start"
          ${quiz.attempts_remaining <= 0 ? "disabled" : ""}>
          ${quiz.attempts_remaining > 0 ? "Начать тест" : "Попыток пока нет"}
        </button>
        ${quiz.attempts_remaining <= 0
          ? `<p class="field-hint">Новая попытка появится первого числа месяца.</p>`
          : ""}
      </section>
      <section class="quiz-rules-card">
        <h2>Звания за лучший результат</h2>
        <ul class="quiz-title-list">
          <li><span class="title-master">Магистр ШУЕ</span><strong>95–100%</strong></li>
          <li><span class="title-mad">Безумец</span><strong>80–94%</strong></li>
          <li><span class="title-expert">Знаток</span><strong>65–79%</strong></li>
          <li><span class="title-viewer">Почётный зритель</span><strong>50–64%</strong></li>
          <li><span class="title-poser">Позёр</span><strong>меньше 50%</strong></li>
        </ul>
      </section>
      <section class="quiz-leaderboard">
        <div class="quiz-leaderboard-heading">
          <div>
            <p class="eyebrow">Лучшие результаты</p>
            <h2>Таблица лидеров</h2>
          </div>
        </div>
        <div class="quiz-gender-tabs" role="tablist" aria-label="Категория рейтинга">
          <button type="button" data-quiz-gender="all" class="selected">Все</button>
          <button type="button" data-quiz-gender="male">Парни</button>
          <button type="button" data-quiz-gender="female">Девушки</button>
        </div>
        <div id="quiz-leaderboard-list"><div class="loader"></div></div>
      </section>
      ${quiz.has_result
        ? `<button class="secondary-button quiz-delete-result" id="quiz-delete-result">
            Удалить мой результат из рейтинга
          </button>`
        : ""}`;
    document.getElementById("quiz-start").addEventListener(
      "click",
      () => runAction(startQuiz),
    );
    main.querySelectorAll("[data-quiz-gender]").forEach((button) => {
      button.addEventListener("click", () => {
        state.quizGender = button.dataset.quizGender;
        main.querySelectorAll("[data-quiz-gender]").forEach((tab) => {
          tab.classList.toggle("selected", tab === button);
        });
        runAction(() => loadQuizLeaderboard(state.quizGender));
      });
    });
    document.getElementById("quiz-title-visibility")?.addEventListener(
      "change",
      (event) => runAction(() => setQuizTitleVisibility(event.currentTarget.checked)),
    );
    document.getElementById("quiz-delete-result")?.addEventListener(
      "click",
      () => runAction(deleteQuizResult),
    );
  }

  async function loadQuizLeaderboard(gender) {
    const list = document.getElementById("quiz-leaderboard-list");
    if (!list) return;
    const result = await api(`/api/quiz/leaderboard?gender=${gender}`);
    if (!result.entries.length) {
      list.innerHTML = `<p class="quiz-empty-ranking">
        В рейтинге пока пусто. Пройди тест, чтобы попасть в таблицу лидеров.
      </p>`;
      return;
    }
    list.innerHTML = `
      <ol class="quiz-ranking-list">
        ${result.entries.map((entry) => `
          <li class="quiz-ranking-row ${entry.rank <= 3 ? `place-${entry.rank}` : ""}">
            <span class="quiz-rank-number">${entry.rank}</span>
            <span class="quiz-ranking-user">
              <span class="quiz-ranking-name">
                ${escapeHtml(entry.name)}
                ${entry.title ? `<small class="user-title-inline ${quizTitleClass(entry.title)}">${escapeHtml(entry.title)}</small>` : ""}
              </span>
              <small>${entry.score}/${entry.total_questions} правильных</small>
            </span>
            <strong class="quiz-ranking-score">${entry.percent}%</strong>
          </li>`).join("")}
      </ol>`;
  }

  async function startQuiz() {
    const result = await api("/api/quiz/start", { method: "POST" });
    state.quizSession = result;
    renderQuizQuestions(result);
  }

  function renderQuizQuestions(session) {
    main.innerHTML = `
      <p class="eyebrow">Попыток после старта: ${session.attempts_remaining}</p>
      <h1 class="page-heading">Тест</h1>
      <p class="settings-description">
        ${session.questions.length} вопросов. Вопросы и варианты ответов перемешаны.
        Отвечай на все вопросы и отправь результат.
      </p>
      <form class="quiz-form" id="quiz-form">
        ${session.questions.map((question, index) => `
          <fieldset class="quiz-question-card" data-question-id="${escapeHtml(question.id)}">
            <legend><span>${index + 1}.</span> ${escapeHtml(question.question)}</legend>
            <div class="quiz-options">
              ${question.options.map((option) => `
                <label class="quiz-option">
                  <input type="radio" name="${escapeHtml(question.id)}"
                    value="${escapeHtml(option.id)}">
                  <span>${escapeHtml(option.text)}</span>
                </label>`).join("")}
            </div>
          </fieldset>`).join("")}
        <button class="primary-button quiz-start-button" type="submit">Завершить тест</button>
        <button class="secondary-button quiz-cancel-button" id="quiz-cancel"
          type="button">Выйти (попытка уже использована)</button>
      </form>`;
    document.getElementById("quiz-form").addEventListener("submit", submitQuiz);
    document.getElementById("quiz-cancel").addEventListener(
      "click",
      () => runAction(loadQuiz),
    );
  }

  async function submitQuiz(event) {
    event.preventDefault();
    const session = state.quizSession;
    const form = event.currentTarget;
    const answers = {};
    for (const question of session.questions) {
      const fieldset = [...form.querySelectorAll(".quiz-question-card")]
        .find((element) => element.dataset.questionId === question.id);
      const selected = fieldset?.querySelector("input:checked");
      if (!selected) {
        showToast("Ответь на каждый вопрос, чтобы завершить тест.");
        fieldset?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
        return;
      }
      answers[question.id] = selected.value;
    }
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const result = await api("/api/quiz/submit", {
        method: "POST",
        body: JSON.stringify({ session_id: session.session_id, answers }),
      });
      state.quizSession = null;
      state.quiz = await api("/api/quiz");
      state.quizGender = "all";
      renderQuizResult(result);
    } catch (error) {
      button.disabled = false;
      showToast(error.message);
    }
  }

  function renderQuizResult(result) {
    main.innerHTML = `
      <section class="quiz-result-card ${quizTitleClass(result.title)}">
        <div class="quiz-result-crown">♛</div>
        <p class="eyebrow">Тест завершён</p>
        <h1>${result.percent}%</h1>
        <p>${result.score} из ${result.total_questions} правильных ответов</p>
        <h2>${escapeHtml(result.title)}</h2>
        <p>Лучший результат: ${result.best_score}/${result.total_questions} · ${result.best_percent}% — ${escapeHtml(result.best_title)}</p>
        <button class="primary-button" id="quiz-result-leaderboard">Посмотреть рейтинг</button>
        <button class="secondary-button" id="quiz-result-home">В раздел теста</button>
      </section>`;
    document.getElementById("quiz-result-leaderboard").addEventListener(
      "click",
      () => runAction(loadQuiz),
    );
    document.getElementById("quiz-result-home").addEventListener(
      "click",
      () => runAction(loadQuiz),
    );
  }

  async function setQuizTitleVisibility(visible) {
    await api("/api/quiz/title-visibility", {
      method: "PATCH",
      body: JSON.stringify({ visible }),
    });
    state.me = { ...state.me, quiz_show_title: visible };
    showToast(visible ? "Звание будет видно рядом с именем" : "Звание скрыто рядом с именем");
    await loadQuiz();
  }

  async function deleteQuizResult() {
    const confirmed = await confirmAction(
      "Удалить свой лучший результат из таблицы лидеров? Потраченные попытки не восстановятся.",
    );
    if (!confirmed) return;
    await api("/api/quiz/result", { method: "DELETE" });
    state.me = { ...state.me, quiz_percent: null, quiz_title: null };
    showToast("Результат удалён. Попытки не изменились.");
    await loadQuiz();
  }

  function renderProfile(profile) {
    main.innerHTML = `
      <h1 class="page-heading">Твоя анкета</h1>
      <section class="profile-panel">
        ${profile.has_photo ? `<img class="avatar" id="my-photo" alt="">` : `<div class="avatar"></div>`}
        <h2>${displayName(profile)}, ${profile.age}</h2>
        <p>⌖ ${escapeHtml(profile.city)}</p>
        ${profile.description ? `<p>${escapeHtml(profile.description)}</p>` : ""}
        <button class="primary-button" id="edit-profile">Редактировать анкету</button>
        <p class="profile-hint">Фотографию можно изменить в чате с ботом.</p>
      </section>`;
    main.insertAdjacentHTML("beforeend", `
      <section class="profile-stats-card" aria-label="Статистика профиля">
        <div class="profile-stat">
          <span class="profile-stat-value">${profile.like_count ?? 0}</span>
          <span class="profile-stat-label">Лайки</span>
        </div>
        <div class="profile-stat">
          <span class="profile-stat-value">${profile.match_count ?? 0}</span>
          <span class="profile-stat-label">Мэтчи</span>
        </div>
        ${profile.quiz_percent !== null && profile.quiz_percent !== undefined
          ? `<div class="profile-stat">
              <span class="profile-stat-value">${profile.quiz_percent}%</span>
              <span class="profile-stat-label">Тест</span>
            </div>`
          : ""}
      </section>`);
    main.insertAdjacentHTML("beforeend", `
      <section class="profile-settings-card quiz-profile-link-card">
        <button class="profile-setting-row" id="open-profile-quiz" type="button">
          <span class="setting-icon">♛</span>
          <span class="setting-copy">
            <strong>Тест и таблица лидеров</strong>
            <small>${profile.quiz_percent !== null && profile.quiz_percent !== undefined
              ? `Твой лучший результат: ${profile.quiz_percent}%`
              : "Пройди тест, чтобы попасть в рейтинг"}</small>
          </span>
          <span class="setting-chevron">›</span>
        </button>
      </section>`);
    document.getElementById("open-profile-quiz").addEventListener(
      "click",
      () => runAction(loadQuiz),
    );
    main.insertAdjacentHTML("beforeend", `
      <section class="profile-settings-card" aria-label="Настройки анкеты">
        <button class="profile-setting-row" data-profile-setting="notifications">
          <span class="setting-icon">♧</span>
          <span class="setting-copy">
            <strong>Уведомления</strong>
            <small>Лайки, мэтчи и сообщения</small>
          </span>
          <span class="setting-chevron">›</span>
        </button>
        <button class="profile-setting-row" data-profile-setting="banned-words">
          <span class="setting-icon">⛨</span>
          <span class="setting-copy">
            <strong>Бан-слова</strong>
            <small>Фильтр нежелательных сообщений</small>
          </span>
          <span class="setting-chevron">›</span>
        </button>
        <button class="profile-setting-row" data-profile-setting="pause">
          <span class="setting-icon">♙</span>
          <span class="setting-copy">
            <strong>${profile.is_active ? "Приостановить анкету" : "Возобновить анкету"}</strong>
            <small>${profile.is_active ? "Временно скрыть из поиска" : "Снова показывать в поиске"}</small>
          </span>
          <span class="setting-chevron">›</span>
        </button>
        <button class="profile-setting-row destructive-setting" data-profile-setting="delete">
          <span class="setting-icon">⌫</span>
          <span class="setting-copy"><strong>Удалить анкету</strong></span>
          <span class="setting-chevron">›</span>
        </button>
        <a class="profile-legal-link" href="/legal" id="profile-legal-link">
          Правила и конфиденциальность
        </a>
      </section>
      <div class="settings-backdrop hidden" id="profile-settings-layer">
        <section class="search-settings-sheet profile-settings-sheet"
          role="dialog" aria-modal="true" aria-labelledby="profile-settings-title">
          <div class="sheet-handle" aria-hidden="true"></div>
          <div class="sheet-heading">
            <h2 id="profile-settings-title"></h2>
            <button class="icon-button close-settings" id="close-profile-settings"
              type="button" aria-label="Закрыть настройки">×</button>
          </div>
          <div id="profile-settings-content"></div>
        </section>
      </div>`);
    const photo = document.getElementById("my-photo");
    if (photo) loadPhoto(profile.id, photo);
    document.getElementById("edit-profile").addEventListener(
      "click",
      renderProfileEditor,
    );
    bindProfileSettings();
  }

  function bindProfileSettings() {
    const layer = document.getElementById("profile-settings-layer");
    const closeButton = document.getElementById("close-profile-settings");
    const close = () => {
      layer.classList.add("hidden");
    };
    closeButton.addEventListener("click", close);
    layer.addEventListener("click", (event) => {
      if (event.target === layer) close();
    });
    layer.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });
    document.querySelectorAll("[data-profile-setting]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.profileSetting;
        if (action === "notifications") openProfileSettings("notifications");
        else if (action === "banned-words") openProfileSettings("banned-words");
        else if (action === "pause") runAction(toggleProfileStatus);
        else if (action === "delete") runAction(deleteProfile);
      });
    });
    document.getElementById("profile-legal-link").addEventListener(
      "click",
      (event) => {
        if (!telegram?.openLink) return;
        event.preventDefault();
        telegram.openLink(new URL("/legal", window.location.href).href);
      },
    );
  }

  function openProfileSettings(section) {
    const layer = document.getElementById("profile-settings-layer");
    const title = document.getElementById("profile-settings-title");
    const content = document.getElementById("profile-settings-content");
    layer.classList.remove("hidden");
    if (section === "notifications") {
      title.textContent = "Уведомления";
      content.innerHTML = `
        <p class="settings-description">Выбери, о чём бот будет присылать сообщения в Telegram.</p>
        <form class="preferences-form" id="notifications-form">
          ${[
            ["notify_likes", "Лайки"],
            ["notify_matches", "Мэтчи"],
            ["notify_messages", "Сообщения"],
          ].map(([key, label]) => `
            <label class="preference-toggle">
              <span>${label}</span>
              <input type="checkbox" name="${key}" ${state.me[key] ? "checked" : ""}>
              <span class="toggle-track" aria-hidden="true"></span>
            </label>`).join("")}
          <button class="primary-button search-save-button" type="submit">Сохранить</button>
        </form>`;
      document.getElementById("notifications-form").addEventListener(
        "submit",
        saveProfilePreferences,
      );
      return;
    }
    title.textContent = "Бан-слова";
    content.innerHTML = `
      <p class="settings-description">
        Новые входящие сообщения с этими словами или выражениями не будут
        сохранены и доставлены тебе. Каждое слово или выражение — с новой строки.
      </p>
      <form class="preferences-form" id="banned-words-form">
        <label class="field-label" for="banned-words">Твой список</label>
        <textarea class="chat-input banned-words-input" id="banned-words"
          name="banned_words" maxlength="1000"
          placeholder="Одно слово на строке">${escapeHtml(state.me.banned_words || "")}</textarea>
        <p class="field-hint">До 1000 символов всего, не более 100 символов на строку.</p>
        <button class="primary-button search-save-button" type="submit">Сохранить</button>
      </form>`;
    document.getElementById("banned-words-form").addEventListener(
      "submit",
      saveProfilePreferences,
    );
  }

  async function saveProfilePreferences(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    const payload = {
      notify_likes: form.elements.notify_likes
        ? form.elements.notify_likes.checked
        : state.me.notify_likes,
      notify_matches: form.elements.notify_matches
        ? form.elements.notify_matches.checked
        : state.me.notify_matches,
      notify_messages: form.elements.notify_messages
        ? form.elements.notify_messages.checked
        : state.me.notify_messages,
      banned_words: form.elements.banned_words
        ? values.banned_words
        : state.me.banned_words,
    };
    button.disabled = true;
    try {
      const preferences = await api("/api/profile-preferences", {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      state.me = { ...state.me, ...preferences };
      document.getElementById("profile-settings-layer").classList.add("hidden");
      renderProfile(state.me);
      showToast("Настройки сохранены");
    } catch (error) {
      button.disabled = false;
      showToast(error.message);
    }
  }

  async function toggleProfileStatus() {
    const nextActive = !state.me.is_active;
    const confirmed = await confirmAction(
      nextActive
        ? "Возобновить анкету и снова показывать её в поиске?"
        : "Приостановить анкету? Она исчезнет из поиска, но лайки, мэтчи и переписки сохранятся.",
    );
    if (!confirmed) return;
    const result = await api("/api/account/status", {
      method: "PATCH",
      body: JSON.stringify({ is_active: nextActive }),
    });
    state.me = { ...state.me, ...result };
    renderProfile(state.me);
    showToast(nextActive ? "Анкета снова видна в поиске" : "Анкета приостановлена");
  }

  async function deleteProfile() {
    const confirmed = await confirmAction(
      "Удалить анкету без возможности восстановления? Твои мэтчи и переписки в приложении и боте тоже будут удалены.",
    );
    if (!confirmed) return;
    await api("/api/account", { method: "DELETE" });
    window.clearInterval(state.poll);
    state.me = null;
    main.innerHTML = `
      <section class="empty-state">
        <div class="empty-icon">✓</div>
        <h2>Анкета удалена</h2>
        <p>Профиль, мэтчи и переписки удалены из базы приложения. Ранее доставленные сообщения в Telegram могут остаться в истории чатов.</p>
        <button class="primary-button" id="close-deleted-profile">Закрыть приложение</button>
      </section>`;
    document.querySelector(".bottom-nav").classList.add("hidden");
    document.getElementById("close-deleted-profile").addEventListener(
      "click",
      () => telegram?.close(),
    );
  }

  function confirmAction(message) {
    if (telegram?.showConfirm) {
      return new Promise((resolve) => telegram.showConfirm(message, resolve));
    }
    return Promise.resolve(window.confirm(message));
  }

  function renderProfileEditor() {
    const profile = state.me;
    main.innerHTML = `
      <p class="eyebrow">Обнови информацию</p>
      <h1 class="page-heading">Редактирование</h1>
      <form class="profile-panel profile-form" id="profile-form">
        <label class="field-label" for="profile-name">Имя</label>
        <input class="chat-input profile-field" id="profile-name" name="name"
          maxlength="100" required value="${escapeHtml(profile.name)}">
        <label class="field-label" for="profile-city">Город</label>
        <input class="chat-input profile-field" id="profile-city" name="city"
          maxlength="100" required value="${escapeHtml(profile.city)}">
        <label class="field-label" for="profile-description">Описание</label>
        <textarea class="chat-input profile-field profile-description-input"
          id="profile-description" name="description" maxlength="1000">${escapeHtml(profile.description)}</textarea>
        <div class="profile-form-actions">
          <button class="secondary-button" type="button" id="cancel-profile-edit">Отмена</button>
          <button class="primary-button" type="submit">Сохранить</button>
        </div>
        <p class="profile-hint">Фотографию можно изменить в чате с ботом.</p>
      </form>`;
    document.getElementById("cancel-profile-edit").addEventListener(
      "click",
      () => renderProfile(profile),
    );
    document.getElementById("profile-form").addEventListener(
      "submit",
      saveProfile,
    );
  }

  async function saveProfile(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = form.querySelector('button[type="submit"]');
    const payload = Object.fromEntries(new FormData(form));
    submitButton.disabled = true;
    try {
      state.me = await api("/api/me", {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      renderProfile(state.me);
      showToast("Анкета обновлена ❤️");
    } catch (error) {
      submitButton.disabled = false;
      showToast(error.message);
    }
  }

  function updateBadges(likes, chats) {
    if (likes !== null) {
      const badge = document.getElementById("likes-badge");
      badge.textContent = likes > 99 ? "99+" : String(likes);
      badge.classList.toggle("hidden", !likes);
    }
    if (chats !== null) {
      const badge = document.getElementById("chats-badge");
      badge.textContent = chats > 99 ? "99+" : String(chats);
      badge.classList.toggle("hidden", !chats);
    }
  }

  async function loadTab(tab) {
    try {
      if (!state.me) state.me = await api("/api/me");
      if (!state.badgesLoaded) {
        const [likes, chats] = await Promise.all([api("/api/likes"), api("/api/chats")]);
        updateBadges(
          likes.profiles.length,
          chats.chats.reduce((total, chat) => total + chat.unread_count, 0),
        );
        state.badgesLoaded = true;
      }
      if (tab === "discover") await discover();
      else if (tab === "likes") await loadLikes();
      else if (tab === "matches") await loadMatches();
      else if (tab === "chats") await loadChats();
      else if (tab === "quiz") await loadQuiz();
      else await loadProfile();
    } catch (error) {
      showError(error);
    }
  }

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => loadTab(item.dataset.tab));
  });
  document.getElementById("header-action").addEventListener("click", () => loadTab(state.tab));
  loadTab("discover");
})();
