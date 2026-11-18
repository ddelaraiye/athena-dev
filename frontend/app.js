/*=====================================================================
  Athena Voice — Frontend
  Voice-first personal AI companion with push-to-talk, local STT,
  Ollama chat, and browser speechSynthesis output.
=====================================================================*/

const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const messages = document.getElementById("messages");
const sendButton = document.getElementById("send");
const statusText = document.getElementById("status");
const newChatButton = document.getElementById("new-chat");
const stopSpeakingButton = document.getElementById("stop-speaking");

// Voice UI elements
const micButton = document.getElementById("mic-button");
const micLabel = micButton.querySelector(".mic-label");
const recordingIndicator = document.getElementById("recording-indicator");
const transcriptBox = document.getElementById("transcript-box");
const transcriptTextarea = document.getElementById("transcript");
const sendTranscriptButton = document.getElementById("send-transcript");
const cancelTranscriptButton = document.getElementById("cancel-transcript");
const clearTranscriptButton = document.getElementById("clear-transcript");
const voiceError = document.getElementById("voice-error");

let conversationId = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// Speech synthesis state
let synth = window.speechSynthesis;
let currentUtterance = null;
let isSpeaking = false;
let voices = [];

// ── Application state ──────────────────────────────────────

const STATE_IDLE = "idle";
const STATE_PERMISSION = "permission";
const STATE_LISTENING = "listening";
const STATE_TRANSCRIBING = "transcribing";
const STATE_REVIEWING = "reviewing";
const STATE_THINKING = "thinking";
const STATE_SPEAKING = "speaking";
const STATE_ERROR = "error";

let currentState = STATE_IDLE;

function setState(state) {
  currentState = state;

  // Update status text
  const statusMap = {
    [STATE_IDLE]: "Online — Local AI",
    [STATE_PERMISSION]: "Requesting microphone permission…",
    [STATE_LISTENING]: "Listening…",
    [STATE_TRANSCRIBING]: "Transcribing…",
    [STATE_REVIEWING]: "Review your transcript",
    [STATE_THINKING]: "Athena is thinking…",
    [STATE_SPEAKING]: "Athena is speaking…",
    [STATE_ERROR]: "Error",
  };
  statusText.textContent = statusMap[state] || "Online — Local AI";

  // Update UI controls
  const recording = state === STATE_LISTENING;
  const reviewing = state === STATE_REVIEWING;
  const speaking = state === STATE_SPEAKING;
  const busy = state === STATE_LISTENING || state === STATE_TRANSCRIBING ||
    state === STATE_THINKING || state === STATE_SPEAKING;

  micButton.classList.toggle("recording", recording);
  micButton.disabled = busy;
  micLabel.textContent = recording ? "Release to stop" : "Hold to speak";

  recordingIndicator.classList.toggle("hidden", state !== STATE_LISTENING);
  transcriptBox.classList.toggle("hidden", state !== STATE_REVIEWING);
  stopSpeakingButton.disabled = !speaking;

  // Visual feedback on orb
  const orb = document.querySelector(".orb");
  orb.classList.toggle("speaking", speaking);

  // Clear error when leaving error state
  if (state !== STATE_ERROR) {
    voiceError.classList.add("hidden");
    voiceError.textContent = "";
  }

  if (!busy && !reviewing) {
    input.focus();
  }
}

// ── Helpers ────────────────────────────────────────────────

function addMessage(role, content) {
  const welcome = messages.querySelector(".welcome");
  if (welcome) welcome.remove();

  const element = document.createElement("div");
  element.className = `message ${role}`;
  element.textContent = content;

  messages.appendChild(element);
  messages.scrollTop = messages.scrollHeight;
}

function showError(message) {
  voiceError.textContent = message;
  voiceError.classList.remove("hidden");
  setState(STATE_ERROR);
}

// ── Health check ───────────────────────────────────────────

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const result = await response.json();

    statusText.textContent =
      result.ollama === "connected"
        ? "Online — Local AI"
        : "Ollama unavailable";
  } catch {
    statusText.textContent = "Connection unavailable";
  }
}

// ── Text chat (existing, preserved) ────────────────────────

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = input.value.trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";
  sendButton.disabled = true;
  setState(STATE_THINKING);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || "Request failed");
    }

    conversationId = result.conversation_id;
    addMessage("assistant", result.reply);
    setState(STATE_IDLE);

    // Speak the response
    await speak(result.reply);

  } catch (error) {
    addMessage("assistant", `I encountered an error: ${error.message}`);
    setState(STATE_IDLE);
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
});

// ── Speech synthesis ───────────────────────────────────────

function loadVoices() {
  voices = synth.getVoices();
}

function selectEnglishVoice() {
  // Prefer an English voice, fall back to the default
  const englishVoice = voices.find(
    (v) => v.lang.startsWith("en") || v.name.toLowerCase().includes("english")
  );
  return englishVoice || voices[0] || null;
}

function speak(text) {
  return new Promise((resolve) => {
    // Cancel any in-flight speech
    cancelSpeech();

    if (!text || !synth) {
      resolve();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    const voice = selectEnglishVoice();
    if (voice) utterance.voice = voice;

    utterance.onstart = () => {
      isSpeaking = true;
      setState(STATE_SPEAKING);
    };

    utterance.onend = () => {
      isSpeaking = false;
      currentUtterance = null;
      setState(STATE_IDLE);
      resolve();
    };

    utterance.onerror = (event) => {
      console.warn("Speech synthesis error:", event.error);
      isSpeaking = false;
      currentUtterance = null;
      setState(STATE_IDLE);
      resolve();
    };

    currentUtterance = utterance;
    synth.speak(utterance);
  });
}

function cancelSpeech() {
  if (synth && (synth.speaking || synth.pending)) {
    synth.cancel();
  }
  isSpeaking = false;
  currentUtterance = null;
  setState(STATE_IDLE);
}

stopSpeakingButton.addEventListener("click", () => {
  cancelSpeech();
  addMessage("assistant", "(speech stopped)");
});

// ── Voice capture (MediaRecorder) ──────────────────────────

async function requestMicrophone() {
  setState(STATE_PERMISSION);
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
    });
    return stream;
  } catch (error) {
    console.error("Microphone permission denied:", error);
    showError(
      "Microphone access was denied. You can still use text chat."
    );
    setState(STATE_IDLE);
    return null;
  }
}

function startRecording(stream) {
  // Check which MIME types are supported; fall back gracefully
  let mimeType = "audio/webm";
  if (!MediaRecorder.isTypeSupported(mimeType)) {
    mimeType = "audio/ogg";
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      mimeType = ""; // let the browser choose
    }
  }

  const options = mimeType ? { mimeType } : {};
  mediaRecorder = new MediaRecorder(stream, options);
  audioChunks = [];

  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) audioChunks.push(event.data);
  };

  mediaRecorder.onstop = async () => {
    // Stop all tracks to release the microphone
    stream.getTracks().forEach((track) => track.stop());

    if (audioChunks.length === 0) {
      showError("No audio was recorded. Please try again.");
      setState(STATE_IDLE);
      return;
    }

    const blob = new Blob(audioChunks, { type: mimeType || "audio/webm" });
    await handleRecordedAudio(blob);
  };

  mediaRecorder.onerror = (error) => {
    console.error("MediaRecorder error:", error);
    showError("Recording failed. Please try again.");
    setState(STATE_IDLE);
  };

  mediaRecorder.start(200); // collect data in 200ms chunks
  isRecording = true;
  setState(STATE_LISTENING);
}

async function stopRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
  }
}

micButton.addEventListener("mousedown", async (event) => {
  event.preventDefault();
  if (isRecording || currentState === STATE_LISTENING) return;

  const stream = await requestMicrophone();
  if (stream) startRecording(stream);
});

micButton.addEventListener("mouseup", (event) => {
  event.preventDefault();
  stopRecording();
});

micButton.addEventListener("mouseleave", (event) => {
  event.preventDefault();
  stopRecording();
});

// ── Transcript handling ────────────────────────────────────

async function handleRecordedAudio(blob) {
  setState(STATE_TRANSCRIBING);

  const formData = new FormData();
  formData.append("upload", blob, "recording.webm");

  try {
    const response = await fetch("/api/transcribe", {
      method: "POST",
      body: formData,
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || "Transcription failed");
    }

    transcriptTextarea.value = result.transcript;
    console.log(
      `Transcription complete: ${result.processing_time_ms}ms`
    );

    setState(STATE_REVIEWING);
    transcriptTextarea.focus();
  } catch (error) {
    console.error("Transcription error:", error);
    showError(error.message || "Transcription failed. Please try again.");
    setState(STATE_IDLE);
  }
}

sendTranscriptButton.addEventListener("click", async () => {
  const transcript = transcriptTextarea.value.trim();
  if (!transcript) return;

  sendTranscriptButton.disabled = true;
  setState(STATE_THINKING);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: transcript,
        conversation_id: conversationId,
      }),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || "Request failed");
    }

    conversationId = result.conversation_id;
    addMessage("user", transcript);
    addMessage("assistant", result.reply);
    setState(STATE_IDLE);

    // Speak the response
    await speak(result.reply);

  } catch (error) {
    addMessage("assistant", `I encountered an error: ${error.message}`);
    setState(STATE_IDLE);
  } finally {
    sendTranscriptButton.disabled = false;
    transcriptTextarea.value = "";
    transcriptBox.classList.add("hidden");
    input.focus();
  }
});

cancelTranscriptButton.addEventListener("click", () => {
  transcriptTextarea.value = "";
  transcriptBox.classList.add("hidden");
  setState(STATE_IDLE);
  input.focus();
});

clearTranscriptButton.addEventListener("click", () => {
  transcriptTextarea.value = "";
});

// ── New conversation ───────────────────────────────────────

newChatButton.addEventListener("click", () => {
  cancelSpeech();
  conversationId = null;
  messages.innerHTML = `
    <div class="welcome">
      <h2>Good to see you.</h2>
      <p>What would you like to explore?</p>
    </div>
  `;
  setState(STATE_IDLE);
});

// ── Voice synthesis readiness ──────────────────────────────

if (typeof speechSynthesis !== "undefined") {
  synth = window.speechSynthesis;
  // Voices may load asynchronously
  if (synth.onvoiceschanged !== undefined) {
    synth.addEventListener("voiceschanged", loadVoices);
  }
  loadVoices();
}

// ── Initialise ─────────────────────────────────────────────

checkHealth();
setState(STATE_IDLE);
