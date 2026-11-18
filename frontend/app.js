const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const messages = document.getElementById("messages");
const sendButton = document.getElementById("send");
const statusText = document.getElementById("status");
const newChatButton = document.getElementById("new-chat");

let conversationId = null;

function addMessage(role, content) {
    const welcome = messages.querySelector(".welcome");
    if (welcome) welcome.remove();

    const element = document.createElement("div");
    element.className = `message ${role}`;
    element.textContent = content;

    messages.appendChild(element);
    messages.scrollTop = messages.scrollHeight;
}

async function checkHealth() {
    try {
        const response = await fetch("/api/health");
        const result = await response.json();

        statusText.textContent =
            result.ollama === "connected"
                ? "Online · Local AI"
                : "Ollama unavailable";
    } catch {
        statusText.textContent = "Connection unavailable";
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = input.value.trim();
    if (!message) return;

    addMessage("user", message);
    input.value = "";
    sendButton.disabled = true;
    statusText.textContent = "Athena is thinking...";

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message,
                conversation_id: conversationId
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Request failed");
        }

        conversationId = result.conversation_id;
        addMessage("assistant", result.reply);
        statusText.textContent = "Online · Local AI";

    } catch (error) {
        addMessage("assistant", `I encountered an error: ${error.message}`);
        statusText.textContent = "Something went wrong";
    } finally {
        sendButton.disabled = false;
        input.focus();
    }
});

newChatButton.addEventListener("click", () => {
    conversationId = null;
    messages.innerHTML = `
        <div class="welcome">
            <h2>Good to see you.</h2>
            <p>What would you like to explore?</p>
        </div>
    `;
});

checkHealth();
