(() => {
  const telegram = window.Telegram?.WebApp;
  const main = document.getElementById("main");
  const toastNode = document.getElementById("toast");
  const photoCache = new Map();
  const themeStorageKey = "shue-miniapp-theme";
  const state = {
    tab: "discover",
    profile: null,
    likes: [],
    partner: null,
    messages: [],
    poll: null,
    me: null,
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

  async function api(path, options = {}) {
    const initData = telegram?.initData;
    if (!initData) {
      throw new Error("Открой приложение через Telegram, чтобы войти.");
    }
    const response = await fetch(path, {
      ...options,
      headers: {
        Authorization: `tma ${initData}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    const result = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      throw new Error(result?.error || "Не удалось выполнить запрос.");
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
            <h1 class="profile-title">${escapeHtml(profile.name)}, ${profile.age}</h1>
            <p class="profile-meta">⌖ ${escapeHtml(profile.city)}</p>
            ${profile.description ? `<p class="profile-description">${escapeHtml(profile.description)}</p>` : ""}
          </div>
        </article>
        <div class="discover-actions">
          <button class="round-action" id="skip-profile" aria-label="Пропустить">✕</button>
          <button class="round-action like" id="like-profile" aria-label="Нравится">♥</button>
        </div>
      </section>`;
    bindSearchSettings();
    if (profile.has_photo) {
      loadPhoto(profile.id, document.getElementById("discover-photo"));
    }
    document.getElementById("skip-profile").addEventListener("click", () => runAction(() => decide("skip")));
    document.getElementById("like-profile").addEventListener("click", () => runAction(() => decide("like")));
  }

  async function decide(action) {
    if (!state.profile) return;
    const viewed = state.profile;
    const controls = main.querySelectorAll(".round-action");
    controls.forEach((button) => { button.disabled = true; });
    let result;
    try {
      result = await api("/api/discover/decision", {
        method: "POST",
        body: JSON.stringify({ profile_id: viewed.id, action }),
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
          <span class="person-name">${escapeHtml(profile.name)}, ${profile.age}</span>
          <span class="person-preview">${escapeHtml(profile.city)}${profile.description ? ` · ${escapeHtml(profile.description)}` : ""}</span>
        </span>
        <span class="unread">♥</span>
      </article>
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
              <span class="person-name">${escapeHtml(chat.name)}, ${chat.age}</span>
              <span class="person-preview">${escapeHtml(chat.last_message || chat.city)}</span>
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
                <span class="person-name">${escapeHtml(match.name)}, ${match.age}</span>
                <span class="person-preview">${escapeHtml(match.city)}</span>
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
    state.messages = result.messages;
    renderChat();
    const newInput = document.getElementById("chat-input");
    newInput.value = draft;
    if (wasFocused) newInput.focus();
    const newList = main.querySelector(".chat-messages");
    if (initial || wasAtBottom) newList.scrollTop = newList.scrollHeight;
  }

  function renderChat() {
    const partner = state.partner;
    const messages = state.messages.map((message) => `
      <div class="bubble ${message.sender_id === state.me?.id ? "mine" : "theirs"}">${escapeHtml(message.text)}</div>`).join("");
    main.innerHTML = `
      <section class="chat-screen">
        <header class="chat-header">
          <button id="back-chats" class="chat-back" aria-label="Назад">‹</button>
          ${partner.has_photo ? `<img class="avatar" id="chat-photo" alt="">` : `<span class="avatar"></span>`}
          <div class="person-copy">
            <span class="person-name">${escapeHtml(partner.name)}, ${partner.age}</span>
            <span class="person-preview">${escapeHtml(partner.city)}</span>
          </div>
        </header>
        <div class="chat-messages">${messages || `<p class="person-preview">Напиши первое сообщение — начните знакомство ❤️</p>`}</div>
        <form class="chat-form" id="chat-form">
          <input class="chat-input" id="chat-input" maxlength="3900" autocomplete="off" placeholder="Сообщение…">
          <button class="send-button" aria-label="Отправить">➤</button>
        </form>
      </section>`;
    document.getElementById("back-chats").addEventListener("click", loadChats);
    document.getElementById("chat-form").addEventListener("submit", sendChatMessage);
    const photo = document.getElementById("chat-photo");
    if (photo) loadPhoto(partner.id, photo);
    const list = main.querySelector(".chat-messages");
    list.scrollTop = list.scrollHeight;
  }

  async function sendChatMessage(event) {
    event.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;
    input.disabled = true;
    try {
      const result = await api(`/api/chats/${state.partner.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      input.value = "";
      if (result.notification_warning) showToast(result.notification_warning);
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

  function renderProfile(profile) {
    main.innerHTML = `
      <h1 class="page-heading">Твоя анкета</h1>
      <section class="profile-panel">
        ${profile.has_photo ? `<img class="avatar" id="my-photo" alt="">` : `<div class="avatar"></div>`}
        <h2>${escapeHtml(profile.name)}, ${profile.age}</h2>
        <p>⌖ ${escapeHtml(profile.city)}</p>
        ${profile.description ? `<p>${escapeHtml(profile.description)}</p>` : ""}
        <button class="primary-button" id="edit-profile">Редактировать анкету</button>
        <p class="profile-hint">Фотографию можно изменить в чате с ботом.</p>
      </section>`;
    main.insertAdjacentHTML("beforeend", `
      <section class="profile-stats-card" aria-label="Статистика профиля">
        <div class="profile-stat">
          <span class="profile-stat-value">${profile.like_count ?? 0}</span>
          <span class="profile-stat-label">Симпатии</span>
        </div>
        <div class="profile-stat">
          <span class="profile-stat-value">${profile.match_count ?? 0}</span>
          <span class="profile-stat-label">Мэтчи</span>
        </div>
      </section>`);
    const photo = document.getElementById("my-photo");
    if (photo) loadPhoto(profile.id, photo);
    document.getElementById("edit-profile").addEventListener(
      "click",
      renderProfileEditor,
    );
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
