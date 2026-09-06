// ---------------- Chatbot widget ----------------
(function () {
  const toggle = document.getElementById("chat-toggle");
  const panel = document.getElementById("chat-panel");
  const closeBtn = document.getElementById("chat-close");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const messages = document.getElementById("chat-messages");

  if (!toggle) return;

  let greeted = false;

  function addMessage(text, sender) {
    const div = document.createElement("div");
    div.className = "chat-msg " + sender;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  toggle.addEventListener("click", () => {
    panel.classList.toggle("hidden");
    if (!greeted && !panel.classList.contains("hidden")) {
      greeted = true;
      addMessage("Hello! I'm the scheme assistant. Ask me about any government scheme, its eligibility, or required documents.", "bot");
    }
  });

  closeBtn.addEventListener("click", () => panel.classList.add("hidden"));

  const chatMic = document.getElementById("chat-mic");
  if (chatMic && window.attachVoiceInput) {
    const currentLang = document.documentElement.getAttribute("data-lang") || "en";
    window.attachVoiceInput(chatMic, input, currentLang);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;
    addMessage(msg, "user");
    input.value = "";

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      const data = await res.json();
      addMessage(data.reply, "bot");
    } catch (err) {
      addMessage("Sorry, I couldn't reach the assistant right now. Please try again.", "bot");
    }
  });
})();

// ---------------- Multi-step questionnaire ----------------
(function () {
  const steps = document.querySelectorAll(".q-step");
  if (!steps.length) return;

  let current = 0;
  const segs = document.querySelectorAll(".progress-seg");

  function show(index) {
    steps.forEach((s, i) => s.classList.toggle("visible", i === index));
    segs.forEach((s, i) => s.classList.toggle("active", i <= index));
    current = index;
  }

  function validateStep(index) {
    const step = steps[index];
    const inputs = step.querySelectorAll("input, select");
    for (const inp of inputs) {
      if (inp.type === "radio") {
        const group = step.querySelectorAll(`input[name="${inp.name}"]`);
        const anyChecked = Array.from(group).some((g) => g.checked);
        if (!anyChecked) return false;
      } else if (!inp.value) {
        return false;
      }
    }
    return true;
  }

  document.querySelectorAll(".next-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!validateStep(current)) {
        alert("Please answer this question before continuing.");
        return;
      }
      if (current < steps.length - 1) show(current + 1);
    });
  });

  document.querySelectorAll(".back-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (current > 0) show(current - 1);
    });
  });

  show(0);
})();
