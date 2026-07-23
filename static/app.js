const miaFace = document.getElementById("mia-face");
const stateText = document.getElementById("state-text");
const subtitleText = document.getElementById("subtitle-text");

// Conectar con el endpoint SSE
const eventSource = new EventSource('/stream');

const stateInfo = {
    "idle": { text: "DURMIENDO", color: "var(--color-idle)" },
    "listening": { text: "ESCUCHANDO...", color: "var(--color-listen)" },
    "thinking": { text: "PENSANDO...", color: "var(--color-think)" },
    "speaking": { text: "HABLANDO", color: "var(--color-speak)" },
    "vision": { text: "OBSERVANDO", color: "var(--color-vision)" }
};

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    const state = data.state;
    const additionalData = data.data;

    // Remover clases anteriores
    miaFace.className = "anime-face";
    
    // Aplicar la nueva clase de estado (ej: 'state-listening')
    miaFace.classList.add(`state-${state}`);
    
    // Actualizar Textos
    if (stateInfo[state]) {
        stateText.innerText = stateInfo[state].text;
        stateText.style.color = stateInfo[state].color;
    }

    // Actualizar Subtítulos
    if (state === "speaking") {
        subtitleText.innerText = additionalData || "...";
    } else if (state === "idle") {
        subtitleText.innerText = "...";
    } else if (state === "listening") {
        subtitleText.innerText = "(Esperando comando de voz)";
    } else if (state === "thinking") {
        subtitleText.innerText = `Procesando: "${additionalData}"`;
    } else if (state === "vision") {
        subtitleText.innerText = "(Moondream analizando imagen de la cámara...)";
    }
};

eventSource.onerror = function() {
    console.error("Conexión SSE perdida. Reconectando...");
    stateText.innerText = "DESCONECTADO";
    stateText.style.color = "red";
    miaFace.className = "anime-face";
};
