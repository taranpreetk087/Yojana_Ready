// Voice input using the browser's built-in Web Speech API.
// Free, no API key, no backend call -- works in Chrome and most Android
// WebViews out of the box. If unsupported, mic buttons quietly hide
// themselves rather than showing a broken feature.

(function () {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function localeFor(lang) {
    return lang === "hi" ? "hi-IN" : "en-IN";
  }

  function attachVoiceInput(buttonEl, targetEl, lang) {
    if (!SpeechRecognition || !buttonEl || !targetEl) {
      if (buttonEl) buttonEl.style.display = "none";
      return;
    }

    let recognition = null;
    let listening = false;

    buttonEl.addEventListener("click", () => {
      if (listening) {
        recognition && recognition.stop();
        return;
      }
      recognition = new SpeechRecognition();
      recognition.lang = localeFor(lang);
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        listening = true;
        buttonEl.classList.add("listening");
      };
      recognition.onend = () => {
        listening = false;
        buttonEl.classList.remove("listening");
      };
      recognition.onerror = () => {
        listening = false;
        buttonEl.classList.remove("listening");
      };
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        // Always let the user see and edit what was heard before it's
        // submitted -- never auto-submit voice input directly.
        if (targetEl.tagName === "TEXTAREA" || targetEl.tagName === "INPUT") {
          targetEl.value = (targetEl.value ? targetEl.value + " " : "") + transcript;
          targetEl.focus();
        }
      };
      recognition.start();
    });
  }

  window.attachVoiceInput = attachVoiceInput;
})();
