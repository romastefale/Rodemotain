(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const initData = tg ? tg.initData || "" : "";
  const params = new URLSearchParams(window.location.search);
  const queryId = params.get("query_id") || params.get("chat_join_request_query_id") || "";

  const botIcon = document.getElementById("botIcon");
  const groupSelect = document.getElementById("groupSelect");
  const groupList = document.getElementById("groupList");
  const groupHint = document.getElementById("groupHint");
  const rulesCheck = document.getElementById("rulesCheck");
  const spamCheck = document.getElementById("spamCheck");
  const captchaCheck = document.getElementById("captchaCheck");
  const captchaQuestion = document.getElementById("captchaQuestion");
  const captchaAnswer = document.getElementById("captchaAnswer");
  const submitBtn = document.getElementById("submitBtn");
  const statusEl = document.getElementById("status");

  if (botIcon) {
    botIcon.addEventListener("error", () => {
      const mark = botIcon.closest(".mark");
      if (mark) mark.classList.add("icon-failed");
    });
  }

  const a = Math.floor(Math.random() * 6) + 2;
  const b = Math.floor(Math.random() * 6) + 2;
  const expected = a + b;
  captchaQuestion.textContent = `Pergunta: Quanto é ${a} + ${b}?`;

  function setStatus(text, kind = "") {
    statusEl.textContent = text;
    statusEl.className = kind;
  }

  function selectedGroupId() {
    return String(groupSelect.value || "").trim();
  }

  function canSubmit() {
    const groupOk = !!selectedGroupId();
    const checksOk = rulesCheck.checked && spamCheck.checked && captchaCheck.checked;
    const captchaOk = String(captchaAnswer.value || "").trim() !== "";
    submitBtn.disabled = !(groupOk && checksOk && captchaOk);
  }

  function setSelectedGroup(chatId) {
    groupSelect.value = String(chatId || "");
    for (const button of groupList.querySelectorAll(".group-option")) {
      const active = button.dataset.chatId === groupSelect.value;
      button.setAttribute("aria-checked", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    }
    canSubmit();
  }

  function createGroupButton(group) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "group-option";
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", "false");
    button.dataset.chatId = String(group.chat_id);

    const radio = document.createElement("span");
    radio.className = "group-radio";
    radio.setAttribute("aria-hidden", "true");

    const text = document.createElement("span");
    text.className = "group-text";

    const title = document.createElement("span");
    title.className = "group-title";
    title.textContent = group.title || String(group.chat_id);

    const meta = document.createElement("span");
    meta.className = "group-meta";
    meta.textContent = group.username ? `@${group.username}` : "grupo privado";

    text.appendChild(title);
    text.appendChild(meta);
    button.appendChild(radio);
    button.appendChild(text);

    button.addEventListener("click", () => setSelectedGroup(group.chat_id));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...groupList.querySelectorAll(".group-option")];
      const current = buttons.indexOf(button);
      const next = event.key === "ArrowDown" || event.key === "ArrowRight"
        ? (current + 1) % buttons.length
        : (current - 1 + buttons.length) % buttons.length;
      buttons[next].focus();
      setSelectedGroup(buttons[next].dataset.chatId);
    });

    return button;
  }

  async function loadGroups() {
    try {
      const response = await fetch("/telegram/join-request/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: initData })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "falha ao carregar grupos");
      groupSelect.innerHTML = "";
      groupList.innerHTML = "";
      if (!data.groups.length) {
        groupSelect.innerHTML = "<option value=''>Nenhum grupo registrado ainda</option>";
        groupList.innerHTML = "<div class='group-empty'>Nenhum grupo registrado ainda</div>";
        groupHint.textContent = "O bot precisa receber pelo menos um update do grupo para registrá-lo.";
        return;
      }
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "Selecione um grupo";
      groupSelect.appendChild(empty);
      for (const group of data.groups) {
        const option = document.createElement("option");
        option.value = String(group.chat_id);
        option.textContent = group.title + (group.username ? ` (@${group.username})` : "");
        groupSelect.appendChild(option);
        groupList.appendChild(createGroupButton(group));
      }
      groupSelect.disabled = false;
      groupHint.textContent = "A seleção será validada com a solicitação real recebida pelo Telegram.";
    } catch (err) {
      groupSelect.innerHTML = "<option value=''>Abra esta tela pelo Telegram</option>";
      groupList.innerHTML = "<div class='group-empty'>Abra esta tela pelo Telegram</div>";
      setStatus(String(err.message || err), "error");
    }
  }

  async function submit() {
    if (Number(captchaAnswer.value) !== expected) {
      setStatus("Captcha incorreto. Confira a resposta.", "error");
      return;
    }
    if (!queryId) {
      setStatus("Solicitação sem query_id. Abra pelo botão enviado pelo Telegram ao pedir entrada no grupo.", "error");
      return;
    }
    submitBtn.disabled = true;
    setStatus("Enviando solicitação...");
    try {
      const response = await fetch("/telegram/join-request-query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          init_data: initData,
          query_id: queryId,
          selected_chat_id: selectedGroupId(),
          rules_accepted: rulesCheck.checked,
          no_spam: spamCheck.checked,
          captcha_accepted: captchaCheck.checked,
          result: "queue"
        })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "falha ao enviar solicitação");
      setStatus("Solicitação enviada. Aguarde a análise do grupo selecionado.", "ok");
      if (tg) tg.close();
    } catch (err) {
      submitBtn.disabled = false;
      setStatus(String(err.message || err), "error");
    }
  }

  [rulesCheck, spamCheck, captchaCheck, captchaAnswer].forEach((el) => el.addEventListener("input", canSubmit));
  [rulesCheck, spamCheck, captchaCheck].forEach((el) => el.addEventListener("change", canSubmit));
  submitBtn.addEventListener("click", submit);

  if (tg) {
    tg.ready();
    tg.expand();
  }
  loadGroups().finally(canSubmit);
})();
