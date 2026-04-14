/**
 * Helpyy Hand Widget — Embeddable chat for BBVA public website.
 *
 * Vanilla JS, Shadow DOM encapsulated, < 50 KB total.
 * Connects to POST /api/v1/chat with streaming support.
 */
(function () {
  'use strict';

  /* ─── Config ─── */
  const API_URL = window.HELPYY_API_URL || '/api/v1/chat';
  const GREETING = '¡Hola! Soy Helpyy Hand, tu asistente de BBVA Colombia. ' +
    'Puedo ayudarte a abrir tu primera cuenta, consultar productos y mucho más. ¿En qué te puedo ayudar?';
  const GREETING_DELAY = 3000;

  /* ─── SVG icons (inlined to avoid network requests) ─── */
  const ICO = {
    chat: '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/><path d="M7 9h10v2H7zm0-3h10v2H7zm0 6h7v2H7z"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>',
    send: '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>',
    hand: '<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.94-.49-7-3.85-7-7.93 0-.62.08-1.22.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>',
  };

  /* ─── State ─── */
  let sessionId = 'hw_' + Math.random().toString(36).slice(2, 10);
  let isOpen = false;
  let isSending = false;
  let messageHistory = [];

  /* ─── Form state ─── */
  var formPanel = null;
  var FORM_STEP = 0;
  var FORM_DATA = { name: '', cedula: '', income: 0, selfie: null, id_front: null, id_back: null, terms_accepted: false };

  var INCOME_OPTIONS = [
    { label: 'Menos de $500.000', value: 300000 },
    { label: '$500.000 – $1.000.000', value: 750000 },
    { label: '$1.000.000 – $2.000.000', value: 1500000 },
    { label: '$2.000.000 – $5.000.000', value: 3500000 },
    { label: 'Más de $5.000.000', value: 6000000 },
  ];

  var FORM_STEPS_DEF = [
    { icon: '👤', title: '¿Cómo te llamas?', sub: 'Nombre completo como aparece en tu cédula', type: 'name' },
    { icon: '🪪', title: '¿Cuál es tu cédula?', sub: 'Solo el número, sin puntos ni espacios', type: 'cedula' },
    { icon: '💰', title: '¿Cuánto ganas al mes?', sub: 'Un estimado es suficiente — nadie te va a juzgar 😊', type: 'income' },
    { icon: '🤳', title: 'Tómate una selfie', sub: 'Centra tu rostro en el círculo con buena iluminación', type: 'selfie' },
    { icon: '📄', title: 'Cédula — Lado frontal', sub: 'Alinea la cédula con el marco. Que se vea todo el texto.', type: 'id_front' },
    { icon: '🔄', title: 'Cédula — Reverso', sub: 'Voltea la cédula y toma la foto del reverso', type: 'id_back' },
    { icon: '📋', title: 'Términos y condiciones', sub: 'Lee y acepta para abrir tu cuenta', type: 'terms' },
  ];

  /* Actions that open the form instead of going to the agent */
  var FORM_TRIGGER_ACTIONS = ['abrir mi cuenta', 'abrir cuenta', 'quiero abrir una cuenta', 'crear cuenta'];

  /* ─── Shadow DOM setup ─── */
  const host = document.createElement('div');
  host.id = 'helpyy-hand-widget';
  document.body.appendChild(host);
  const shadow = host.attachShadow({ mode: 'open' });

  /* Inject styles — loaded from adjacent CSS file or inlined at build time */
  const style = document.createElement('style');
  shadow.appendChild(style);
  (function loadCSS() {
    /* Try to find script src for base path */
    var scripts = document.querySelectorAll('script[src*="helpyy-widget"]');
    var base = '';
    if (scripts.length) base = scripts[scripts.length - 1].src.replace(/[^/]+$/, '');
    fetch(base + 'helpyy-widget.css')
      .then(function (r) { return r.text(); })
      .then(function (css) { style.textContent = css; })
      .catch(function () { /* styles will be missing but widget still works */ });
  })();

  /* ─── Build DOM ─── */
  const root = document.createElement('div');
  root.innerHTML = `
    <button class="hw-fab hw-hidden" aria-label="Abrir chat Helpyy Hand">
      ${ICO.chat}
    </button>
    <div class="hw-panel" role="dialog" aria-label="Chat Helpyy Hand">
      <div class="hw-header">
        <div class="hw-header-avatar">${ICO.hand}</div>
        <div class="hw-header-info">
          <div class="hw-header-title">Helpyy Hand</div>
          <div class="hw-header-status">En línea</div>
        </div>
        <button class="hw-close" aria-label="Cerrar chat">${ICO.close}</button>
      </div>
      <div class="hw-messages" aria-live="polite"></div>
      <div class="hw-input-bar">
        <textarea class="hw-input" placeholder="Escribe tu mensaje..." rows="1"
                  aria-label="Escribe tu mensaje"></textarea>
        <button class="hw-send" aria-label="Enviar" disabled>${ICO.send}</button>
      </div>
    </div>`;
  shadow.appendChild(root);

  /* ─── Element refs ─── */
  const fab = root.querySelector('.hw-fab');
  const panel = root.querySelector('.hw-panel');
  const msgs = root.querySelector('.hw-messages');
  const input = root.querySelector('.hw-input');
  const sendBtn = root.querySelector('.hw-send');
  const closeBtn = root.querySelector('.hw-close');

  /* ─── Events ─── */
  fab.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener('input', function () {
    sendBtn.disabled = !input.value.trim() || isSending;
    autoGrow(input);
  });

  /* ─── Init: show FAB after delay ─── */
  setTimeout(function () {
    fab.classList.remove('hw-hidden');
  }, GREETING_DELAY);

  /* ─── Public API (for external control) ─── */
  window.HelpyyWidget = { open: open, close: close, reset: reset };

  /* ═══════════════ Functions ═══════════════ */

  function open() {
    if (isOpen) return;
    isOpen = true;
    fab.classList.add('hw-hidden');
    panel.classList.add('hw-open');
    input.focus();
    if (messageHistory.length === 0) {
      addAgentMessage(GREETING, ['Quiero abrir una cuenta', 'Consultar productos', 'Horarios del banco']);
    }
  }

  function close() {
    isOpen = false;
    panel.classList.remove('hw-open');
    setTimeout(function () { fab.classList.remove('hw-hidden'); }, 350);
  }

  function reset() {
    sessionId = 'hw_' + Math.random().toString(36).slice(2, 10);
    messageHistory = [];
    msgs.innerHTML = '';
    isSending = false;
    input.disabled = false;
    sendBtn.disabled = true;
  }

  /* ─── Send message ─── */
  async function send() {
    var text = input.value.trim();
    if (!text || isSending) return;

    isSending = true;
    input.value = '';
    input.style.height = 'auto';
    sendBtn.disabled = true;

    addUserMessage(text);
    messageHistory.push({ role: 'user', content: text });

    var typing = showTyping();

    try {
      var response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          stream: true,
          is_banked: false,
        }),
      });

      removeTyping(typing);

      if (!response.ok) {
        addAgentMessage('Lo siento, hubo un problema. Intenta de nuevo en un momento.');
        return;
      }

      /* ─── Streaming response ─── */
      var contentType = response.headers.get('content-type') || '';

      if (contentType.includes('text/event-stream') || contentType.includes('stream')) {
        await handleStream(response);
      } else {
        /* JSON fallback */
        var data = await response.json();
        var content = data.content || data.message || JSON.stringify(data);
        var actions = data.suggested_actions || [];
        addAgentMessage(content, actions);
        messageHistory.push({ role: 'assistant', content: content });

        if (data.metadata && data.metadata.helpyy_enabled) {
          var displayName = data.metadata.display_name || '';
          var activationCode = data.metadata.activation_code || '';
          showSuccess(displayName, activationCode);
        }
      }
    } catch (err) {
      removeTyping(typing);
      addAgentMessage('No pude conectarme con el servidor. Verifica tu conexión.');
    } finally {
      isSending = false;
      sendBtn.disabled = !input.value.trim();
      input.focus();
    }
  }

  /* ─── Agent name map ─── */
  var AGENT_LABELS = {
    helpyy_general: 'Helpyy Hand',
    onboarding: 'Asistente de Bienvenida',
    credit_evaluator: 'Evaluador de Crédito',
    financial_advisor: 'Asesor Financiero',
  };

  /* ─── Stream handler (SSE / NDJSON / ReadableStream) ─── */
  async function handleStream(response) {
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    /* Per-agent bubble tracking */
    var currentBubble = null;
    var currentFullText = '';
    var currentAgentBubbles = []; /* collect for history */

    function getOrCreateBubble(agentName) {
      if (currentBubble) return currentBubble;
      currentFullText = '';
      currentBubble = createStreamBubbleWithAgent(agentName);
      return currentBubble;
    }

    while (true) {
      var result = await reader.read();
      if (result.done) break;

      buffer += decoder.decode(result.value, { stream: true });

      var lines = buffer.split('\n');
      buffer = lines.pop();

      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) continue;

        if (line.startsWith('data: ')) {
          var payload = line.slice(6);
          if (payload === '[DONE]') continue;
          try {
            var parsed = JSON.parse(payload);

            /* Agent change: close current bubble, add separator, reset */
            if (parsed.agent_change) {
              if (currentBubble && currentFullText) {
                appendTime(currentBubble);
                currentAgentBubbles.push(currentFullText);
              }
              currentBubble = null;
              currentFullText = '';
              addAgentSeparator(parsed.to);
              continue;
            }

            /* Token */
            var text = parsed.token || parsed.content || parsed.text || '';
            if (text) {
              var bubble = getOrCreateBubble(parsed.agent);
              currentFullText += text;
              bubble.textContent = currentFullText;
              scrollToBottom();
            }

            /* Done chunk */
            if (parsed.done) {
              if (parsed.suggested_actions && parsed.suggested_actions.length) {
                addActions(parsed.suggested_actions);
              }
              if (parsed.metadata) {
                if (parsed.metadata.helpyy_enabled) {
                  var displayName = parsed.metadata.display_name || '';
                  var activationCode = parsed.metadata.activation_code || '';
                  setTimeout(function() { showSuccess(displayName, activationCode); }, 500);
                }
              }
            }
          } catch (_) { /* skip malformed */ }
        }
      }
    }

    /* Finalize last bubble */
    if (currentBubble && currentFullText) {
      appendTime(currentBubble);
      currentAgentBubbles.push(currentFullText);
    }

    var combined = currentAgentBubbles.join(' ');
    if (combined) {
      messageHistory.push({ role: 'assistant', content: combined });
    }
  }

  /* ─── DOM helpers ─── */

  function addUserMessage(text) {
    var el = document.createElement('div');
    el.className = 'hw-msg hw-msg-user';
    el.textContent = text;
    appendTime(el);
    msgs.appendChild(el);
    scrollToBottom();
  }

  function addAgentMessage(text, actions) {
    var el = document.createElement('div');
    el.className = 'hw-msg hw-msg-agent';
    el.textContent = text;
    appendTime(el);
    msgs.appendChild(el);
    if (actions && actions.length) addActions(actions);
    scrollToBottom();
  }

  function createStreamBubble() {
    var el = document.createElement('div');
    el.className = 'hw-msg hw-msg-agent';
    msgs.appendChild(el);
    scrollToBottom();
    return el;
  }

  function createStreamBubbleWithAgent(agentName) {
    var label = AGENT_LABELS[agentName] || agentName || 'Helpyy Hand';
    var wrapper = document.createElement('div');
    wrapper.className = 'hw-agent-group';
    var agentLabel = document.createElement('div');
    agentLabel.className = 'hw-agent-label';
    agentLabel.textContent = label;
    var el = document.createElement('div');
    el.className = 'hw-msg hw-msg-agent';
    wrapper.appendChild(agentLabel);
    wrapper.appendChild(el);
    msgs.appendChild(wrapper);
    scrollToBottom();
    return el;
  }

  function addAgentSeparator(toAgent) {
    var label = AGENT_LABELS[toAgent] || toAgent || 'Agente';
    var sep = document.createElement('div');
    sep.className = 'hw-separator';
    sep.innerHTML = '<span>Conectando con ' + label + '</span>';
    msgs.appendChild(sep);
    scrollToBottom();
  }

  function addActions(actions) {
    var wrap = document.createElement('div');
    wrap.className = 'hw-actions';
    actions.forEach(function (text) {
      var btn = document.createElement('button');
      btn.className = 'hw-action-btn';
      btn.textContent = text;
      btn.addEventListener('click', function () {
        // Intercept form-trigger actions — open the form instead of chatting
        if (FORM_TRIGGER_ACTIONS.indexOf(text.toLowerCase()) !== -1) {
          openAccountForm();
          return;
        }
        input.value = text;
        sendBtn.disabled = false;
        send();
      });
      wrap.appendChild(btn);
    });
    msgs.appendChild(wrap);
    scrollToBottom();
  }

  function appendTime(el) {
    var span = document.createElement('div');
    span.className = 'hw-msg-time';
    var now = new Date();
    span.textContent = now.getHours().toString().padStart(2, '0') + ':' +
      now.getMinutes().toString().padStart(2, '0');
    el.appendChild(span);
  }

  function showTyping() {
    var el = document.createElement('div');
    el.className = 'hw-typing';
    el.innerHTML = '<span class="hw-dot"></span><span class="hw-dot"></span><span class="hw-dot"></span>';
    msgs.appendChild(el);
    scrollToBottom();
    return el;
  }

  function removeTyping(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function scrollToBottom() {
    msgs.scrollTop = msgs.scrollHeight;
  }

  function autoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
  }

  /* ─── Success animation ─── */
  function showSuccess(displayName, activationCode) {
    var greeting = displayName ? '¡Bienvenido, ' + displayName + '!' : '¡Cuenta creada!';
    var codeHtml = activationCode
      ? '<div class="hw-activation-code">' +
        '<div class="hw-code-label">Tu código de activación</div>' +
        '<div class="hw-code-value">' + activationCode + '</div>' +
        '<div class="hw-code-hint">Ingresa este código en la app BBVA para comenzar</div>' +
        '</div>'
      : '';
    var overlay = document.createElement('div');
    overlay.className = 'hw-success';
    overlay.innerHTML =
      '<div class="hw-confetti"></div>' +
      '<div class="hw-success-check">' + ICO.check + '</div>' +
      '<div class="hw-success-title">' + greeting + '</div>' +
      '<div class="hw-success-text">Ya eres parte de BBVA Colombia. Tu asistente Helpyy Hand está listo para acompañarte.</div>' +
      codeHtml;
    panel.style.position = 'relative';
    panel.appendChild(overlay);
    spawnConfetti(overlay.querySelector('.hw-confetti'));

    // Don't auto-remove — let user copy the code
    if (!activationCode) {
      setTimeout(function () {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      }, 5000);
    }
  }

  function spawnConfetti(container) {
    var colors = ['#00a870', '#00897b', '#fbbf24', '#ef4444', '#3b82f6', '#8b5cf6'];
    for (var i = 0; i < 30; i++) {
      var dot = document.createElement('i');
      var angle = (Math.random() * 360) * Math.PI / 180;
      var dist = 60 + Math.random() * 120;
      var dx = Math.cos(angle) * dist;
      var dy = Math.sin(angle) * dist - 40;
      dot.style.background = colors[i % colors.length];
      dot.style.animation = 'hw-confetti-fly ' + (0.6 + Math.random() * 0.6).toFixed(2) + 's ease-out forwards';
      dot.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(0)';
      /* Override the keyframe end state inline */
      dot.style.setProperty('--dx', dx + 'px');
      dot.style.setProperty('--dy', dy + 'px');
      dot.animate([
        { transform: 'translate(0,0) scale(1)', opacity: 1 },
        { transform: 'translate(' + dx + 'px,' + dy + 'px) scale(0)', opacity: 0 },
      ], { duration: 600 + Math.random() * 600, easing: 'ease-out', fill: 'forwards' });
      container.appendChild(dot);
    }
  }

  /* ═══════════════ Account Opening Form ═══════════════ */

  function openAccountForm() {
    if (formPanel) return;
    FORM_STEP = 0;
    FORM_DATA = { name: '', cedula: '', income: 0, selfie: null, id_front: null, id_back: null, terms_accepted: false };

    formPanel = document.createElement('div');
    formPanel.className = 'hw-form-panel';
    formPanel.innerHTML =
      '<div class="hw-form-header">' +
        '<button class="hw-form-back" id="hw-fb">' +
          '<svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>' +
        '</button>' +
        '<div class="hw-form-header-info">' +
          '<div class="hw-form-title">Abrir Cuenta BBVA</div>' +
          '<div class="hw-form-subtitle" id="hw-fsub">Paso 1 de 3</div>' +
        '</div>' +
        '<button class="hw-form-x" id="hw-fx">' +
          '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>' +
        '</button>' +
      '</div>' +
      '<div class="hw-form-progress-track"><div class="hw-form-progress-fill" id="hw-fprog"></div></div>' +
      '<div class="hw-form-body" id="hw-fbody"></div>';

    panel.appendChild(formPanel);
    requestAnimationFrame(function () { formPanel.classList.add('hw-form-panel-open'); });

    formPanel.querySelector('#hw-fb').addEventListener('click', formBack);
    formPanel.querySelector('#hw-fx').addEventListener('click', closeAccountForm);

    renderFormStep(0);
  }

  function closeAccountForm() {
    if (!formPanel) return;
    formPanel.classList.remove('hw-form-panel-open');
    var fp = formPanel;
    formPanel = null;
    setTimeout(function () { if (fp.parentNode) fp.parentNode.removeChild(fp); }, 380);
  }

  function updateFormProgress(step) {
    var prog = formPanel.querySelector('#hw-fprog');
    var sub = formPanel.querySelector('#hw-fsub');
    if (step < FORM_STEPS_DEF.length) {
      prog.style.width = Math.round((step + 1) / FORM_STEPS_DEF.length * 100) + '%';
      sub.textContent = 'Paso ' + (step + 1) + ' de ' + FORM_STEPS_DEF.length;
    } else {
      prog.style.width = '100%';
      sub.textContent = 'Confirmar';
    }
  }

  function renderFormStep(step) {
    var body = formPanel.querySelector('#hw-fbody');
    updateFormProgress(step);

    if (step < FORM_STEPS_DEF.length) {
      var s = FORM_STEPS_DEF[step];
      var fieldHtml;

      if (s.type === 'income') {
        fieldHtml = '<div class="hw-income-chips">' +
          INCOME_OPTIONS.map(function (o) {
            return '<button class="hw-income-chip" data-value="' + o.value + '">' + o.label + '</button>';
          }).join('') + '</div>';
      } else if (s.type === 'selfie' || s.type === 'id_front' || s.type === 'id_back') {
        var frameClass = s.type === 'selfie' ? 'hw-photo-circle' : 'hw-photo-card';
        var existingPhoto = FORM_DATA[s.type];
        fieldHtml =
          '<div class="hw-photo-capture">' +
            '<div class="hw-photo-frame ' + frameClass + '" id="hw-photo-frame">' +
              (existingPhoto
                ? '<img src="' + existingPhoto + '" style="width:100%;height:100%;object-fit:cover;" />'
                : '<div class="hw-photo-placeholder"><div class="hw-photo-icon">' + (s.type === 'selfie' ? '🤳' : '🪪') + '</div><span>Sin foto aún</span></div>') +
            '</div>' +
            '<div class="hw-photo-actions">' +
              '<button class="hw-photo-btn hw-photo-btn-camera" id="hw-btn-camera">📷 Cámara</button>' +
              '<button class="hw-photo-btn hw-photo-btn-upload" id="hw-btn-upload">📁 Subir foto</button>' +
            '</div>' +
            '<input type="file" accept="image/*" id="hw-photo-input" style="display:none" />' +
          '</div>';
      } else if (s.type === 'terms') {
        fieldHtml =
          '<div class="hw-terms-scroll">' +
            '<p><strong>Términos y Condiciones — Helpyy Hand por BBVA Colombia</strong></p>' +
            '<p>Al aceptar estos términos, usted autoriza a BBVA Colombia S.A. para:</p>' +
            '<p><strong>1. Datos personales.</strong> Recopilar, almacenar y procesar sus datos conforme a la Ley 1581 de 2012 (Habeas Data) y el Decreto 1377 de 2013. Sus datos no serán vendidos a terceros.</p>' +
            '<p><strong>2. Consulta en centrales de riesgo.</strong> Realizar consultas en DataCrédito y TransUnion para evaluar su perfil crediticio en el momento de solicitar productos de crédito.</p>' +
            '<p><strong>3. Comunicaciones.</strong> Contactarle por medios electrónicos (email, SMS, push) con información sobre productos y servicios de BBVA. Puede cancelar esta autorización en cualquier momento.</p>' +
            '<p><strong>4. Biometría.</strong> Guardar y procesar imagen facial y documentos de identidad conforme a las políticas de seguridad del banco y la normativa vigente.</p>' +
            '<p><strong>5. Cuenta de ahorro.</strong> La cuenta se rige por el reglamento de depósitos de BBVA Colombia. Consulte tarifas en bbva.com.co.</p>' +
            '<p>Helpyy Hand es un servicio de asistencia financiera digital de BBVA Colombia, supervisado por la Superintendencia Financiera de Colombia (SFC).</p>' +
          '</div>' +
          '<label class="hw-terms-check">' +
            '<input type="checkbox" id="hw-terms-cb" ' + (FORM_DATA.terms_accepted ? 'checked' : '') + ' />' +
            '<span>He leído y acepto los Términos y Condiciones de BBVA Colombia</span>' +
          '</label>';
      } else {
        var ph = s.type === 'cedula' ? 'Ej: 1007196166' : 'Nombre y apellido(s)';
        var cur = FORM_DATA[s.type] || '';
        fieldHtml = '<input class="hw-form-input" type="' + (s.type === 'cedula' ? 'tel' : 'text') +
          '" placeholder="' + ph + '" value="' + cur + '" id="hw-fi" autocomplete="off" />';
      }

      body.innerHTML =
        '<div class="hw-form-step hw-form-step-in">' +
          '<div class="hw-form-icon">' + s.icon + '</div>' +
          '<h2 class="hw-form-step-title">' + s.title + '</h2>' +
          '<p class="hw-form-step-sub">' + s.sub + '</p>' +
          '<div class="hw-form-field">' + fieldHtml + '</div>' +
          '<div class="hw-form-error" id="hw-ferr"></div>' +
          '<button class="hw-form-submit" id="hw-fnext">' +
            (step < FORM_STEPS_DEF.length - 1 ? 'Continuar →' : 'Revisar datos') +
          '</button>' +
        '</div>';

      if (s.type === 'income') {
        var chips = body.querySelectorAll('.hw-income-chip');
        chips.forEach(function (chip) {
          chip.addEventListener('click', function () {
            chips.forEach(function (c) { c.classList.remove('hw-income-chip-selected'); });
            chip.classList.add('hw-income-chip-selected');
            FORM_DATA.income = parseInt(chip.dataset.value, 10);
          });
        });
        if (FORM_DATA.income) {
          var sel = body.querySelector('[data-value="' + FORM_DATA.income + '"]');
          if (sel) sel.classList.add('hw-income-chip-selected');
        }
      } else if (s.type === 'selfie' || s.type === 'id_front' || s.type === 'id_back') {
        (function (stepType) {
          var photoInput = body.querySelector('#hw-photo-input');
          body.querySelector('#hw-btn-camera').addEventListener('click', function () {
            openCamera(stepType);
          });
          body.querySelector('#hw-btn-upload').addEventListener('click', function () {
            photoInput.click();
          });
          photoInput.addEventListener('change', function () {
            var file = photoInput.files[0];
            if (!file) return;
            var reader = new FileReader();
            reader.onload = function (e) {
              FORM_DATA[stepType] = e.target.result;
              var frame = formPanel.querySelector('#hw-photo-frame');
              if (frame) frame.innerHTML = '<img src="' + e.target.result + '" style="width:100%;height:100%;object-fit:cover;" />';
            };
            reader.readAsDataURL(file);
          });
        })(s.type);
      } else if (s.type !== 'terms') {
        var fi = body.querySelector('#hw-fi');
        if (fi) {
          fi.focus();
          fi.addEventListener('keydown', function (e) { if (e.key === 'Enter') formNext(); });
        }
      }

      body.querySelector('#hw-fnext').addEventListener('click', formNext);

    } else {
      renderFormConfirmation();
    }
  }

  function formNext() {
    var s = FORM_STEPS_DEF[FORM_STEP];
    var err = formPanel.querySelector('#hw-ferr');
    if (err) err.textContent = '';

    if (s.type === 'income') {
      if (!FORM_DATA.income) { err.textContent = 'Por favor selecciona una opción'; return; }
    } else if (s.type === 'selfie' || s.type === 'id_front' || s.type === 'id_back') {
      if (!FORM_DATA[s.type]) { err.textContent = 'Por favor toma una foto para continuar'; return; }
    } else if (s.type === 'terms') {
      var cb = formPanel.querySelector('#hw-terms-cb');
      if (!cb || !cb.checked) { err.textContent = 'Debes aceptar los términos y condiciones para continuar'; return; }
      FORM_DATA.terms_accepted = true;
    } else {
      var fi = formPanel.querySelector('#hw-fi');
      var val = fi ? fi.value.trim() : '';
      if (!val) { err.textContent = 'Por favor completa este campo'; fi && fi.classList.add('hw-input-error'); return; }
      if (s.type === 'cedula' && (val.length < 8 || val.length > 10 || !/^\d+$/.test(val))) {
        err.textContent = 'La cédula debe tener entre 8 y 10 dígitos numéricos';
        fi && fi.classList.add('hw-input-error');
        return;
      }
      FORM_DATA[s.type] = val;
    }

    FORM_STEP++;
    transitionFormStep(FORM_STEP);
  }

  function formBack() {
    if (FORM_STEP === 0) { closeAccountForm(); return; }
    FORM_STEP--;
    transitionFormStep(FORM_STEP);
  }

  function transitionFormStep(step) {
    var body = formPanel.querySelector('#hw-fbody');
    var cur = body.querySelector('.hw-form-step');
    if (cur) {
      cur.classList.add('hw-form-step-out');
      setTimeout(function () { renderFormStep(step); }, 210);
    } else {
      renderFormStep(step);
    }
  }

  function renderFormConfirmation() {
    var body = formPanel.querySelector('#hw-fbody');
    var incLabel = (INCOME_OPTIONS.find(function (o) { return o.value === FORM_DATA.income; }) || {}).label || '$' + FORM_DATA.income;
    var masked = FORM_DATA.cedula ? '****' + FORM_DATA.cedula.slice(-4) : '—';

    body.innerHTML =
      '<div class="hw-form-step hw-form-step-in">' +
        '<div class="hw-form-icon">📋</div>' +
        '<h2 class="hw-form-step-title">Confirma tus datos</h2>' +
        '<p class="hw-form-step-sub">Revisa que todo esté correcto antes de continuar</p>' +
        '<div class="hw-form-summary">' +
          '<div class="hw-summary-row"><span class="hw-summary-label">Nombre</span><span class="hw-summary-value">' + FORM_DATA.name + '</span></div>' +
          '<div class="hw-summary-row"><span class="hw-summary-label">Cédula</span><span class="hw-summary-value">' + masked + '</span></div>' +
          '<div class="hw-summary-row"><span class="hw-summary-label">Ingreso mensual</span><span class="hw-summary-value">' + incLabel + '</span></div>' +
          '<div class="hw-summary-row"><span class="hw-summary-label">Selfie</span><span class="hw-summary-value hw-check-green">✓ Capturada</span></div>' +
          '<div class="hw-summary-row"><span class="hw-summary-label">Cédula (fotos)</span><span class="hw-summary-value hw-check-green">✓ Ambas caras</span></div>' +
          '<div class="hw-summary-row"><span class="hw-summary-label">Términos</span><span class="hw-summary-value hw-check-green">✓ Aceptados</span></div>' +
        '</div>' +
        '<button class="hw-form-submit" id="hw-fconfirm">✓ Abrir mi cuenta</button>' +
        '<button class="hw-form-back-link" id="hw-fedit">Corregir datos</button>' +
      '</div>';

    formPanel.querySelector('#hw-fsub').textContent = 'Confirmar';
    formPanel.querySelector('#hw-fprog').style.width = '100%';
    body.querySelector('#hw-fconfirm').addEventListener('click', submitAccountForm);
    body.querySelector('#hw-fedit').addEventListener('click', function () { FORM_STEP = 0; transitionFormStep(0); });
  }

  async function submitAccountForm() {
    var body = formPanel.querySelector('#hw-fbody');
    body.innerHTML =
      '<div class="hw-form-step hw-form-step-in hw-form-loading">' +
        '<div class="hw-form-spinner"></div>' +
        '<h2 class="hw-form-step-title">Creando tu cuenta...</h2>' +
        '<p class="hw-form-step-sub">Revisando tu información con BBVA 🏦</p>' +
      '</div>';
    formPanel.querySelector('#hw-fsub').textContent = 'Procesando';
    formPanel.querySelector('#hw-fb').style.visibility = 'hidden';
    formPanel.querySelector('#hw-fx').style.display = 'none';

    var apiBase = API_URL.replace(/\/chat$/, '');

    try {
      var resp = await fetch(apiBase + '/onboarding/create-account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, name: FORM_DATA.name, cedula: FORM_DATA.cedula, income: FORM_DATA.income }),
      });
      var data = await resp.json();
      if (data.success) {
        renderFormSuccess(data);
      } else {
        renderFormFail(data.error || 'Hubo un problema. Intenta de nuevo.');
      }
    } catch (e) {
      renderFormFail('Error de conexión. Verifica tu internet e intenta de nuevo.');
    }
  }

  function renderFormSuccess(data) {
    var body = formPanel.querySelector('#hw-fbody');
    var firstName = data.display_name || FORM_DATA.name.split(' ')[0] || 'amigo';
    var code = data.activation_code || '';
    var eligible = data.credit_eligible;

    var creditHtml = eligible
      ? '<div class="hw-form-credit-badge hw-credit-approved">🎉 ¡También calificas para un microcrédito!</div>'
      : '<div class="hw-form-credit-badge hw-credit-later">💪 Helpyy Hand te ayudará a acceder al microcrédito pronto</div>';

    var codeHtml = code
      ? '<div class="hw-form-code-box">' +
          '<div class="hw-form-code-label">Tu código de activación</div>' +
          '<div class="hw-form-code-value" id="hw-cval">' + code + '</div>' +
          '<div class="hw-form-code-hint">Úsalo en la app BBVA para activar Helpyy Hand</div>' +
          '<button class="hw-form-copy-btn" id="hw-copybtn">📋 Copiar código</button>' +
        '</div>'
      : '';

    body.innerHTML =
      '<div class="hw-form-step hw-form-step-in hw-form-success-step">' +
        '<div class="hw-form-success-check">✓</div>' +
        '<h2 class="hw-form-step-title">¡Bienvenido, ' + firstName + '!</h2>' +
        '<p class="hw-form-step-sub">Tu cuenta BBVA ya está activa 🎊</p>' +
        creditHtml +
        codeHtml +
        '<button class="hw-form-submit hw-form-submit-secondary" id="hw-fdone">Volver al chat</button>' +
      '</div>';

    formPanel.querySelector('#hw-fsub').textContent = '¡Listo!';
    formPanel.querySelector('#hw-fb').style.visibility = 'hidden';
    formPanel.querySelector('#hw-fx').style.display = 'flex';

    var copyBtn = body.querySelector('#hw-copybtn');
    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        navigator.clipboard.writeText(code).then(function () {
          copyBtn.textContent = '✓ Copiado';
        }).catch(function () {
          copyBtn.textContent = code; // fallback: show code on button
        });
      });
    }

    body.querySelector('#hw-fdone').addEventListener('click', function () {
      closeAccountForm();
      var msg = '¡' + firstName + ', tu cuenta está activa! 🎉';
      if (code) msg += ' Usa el código ' + code + ' en la app BBVA para activar Helpyy Hand.';
      msg += ' ¿En qué más te puedo ayudar?';
      addAgentMessage(msg);
    });

    // Confetti
    spawnFormConfetti(body.querySelector('.hw-form-step'));
  }

  function spawnFormConfetti(container) {
    var colors = ['#00a870', '#00897b', '#fbbf24', '#ef4444', '#3b82f6', '#a78bfa'];
    for (var i = 0; i < 22; i++) {
      var dot = document.createElement('i');
      dot.className = 'hw-form-confetti-dot';
      var a = Math.random() * Math.PI * 2;
      var d = 40 + Math.random() * 100;
      dot.style.background = colors[i % colors.length];
      dot.animate([
        { transform: 'translate(0,0) scale(1)', opacity: 1 },
        { transform: 'translate(' + Math.cos(a) * d + 'px,' + (Math.sin(a) * d - 20) + 'px) scale(0)', opacity: 0 },
      ], { duration: 500 + Math.random() * 500, easing: 'ease-out', fill: 'forwards' });
      container.appendChild(dot);
    }
  }

  function renderFormFail(msg) {
    var body = formPanel.querySelector('#hw-fbody');
    body.innerHTML =
      '<div class="hw-form-step hw-form-step-in">' +
        '<div class="hw-form-icon">⚠️</div>' +
        '<h2 class="hw-form-step-title">Algo salió mal</h2>' +
        '<p class="hw-form-step-sub">' + msg + '</p>' +
        '<button class="hw-form-submit" id="hw-fretry">Intentar de nuevo</button>' +
      '</div>';
    formPanel.querySelector('#hw-fb').style.visibility = 'visible';
    formPanel.querySelector('#hw-fx').style.display = 'flex';
    body.querySelector('#hw-fretry').addEventListener('click', function () { FORM_STEP = 0; renderFormStep(0); });
  }

  /* ═══════════════ Camera Capture ═══════════════ */

  function openCamera(stepType) {
    var isId = stepType === 'id_front' || stepType === 'id_back';

    /* SVG guide overlay — card frame for ID, circle for selfie */
    var guideSvg = isId
      ? '<svg class="hw-camera-guide" viewBox="0 0 400 500" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">' +
          '<defs><mask id="hw-cg-mask"><rect width="400" height="500" fill="white"/>' +
          '<rect x="44" y="156" width="312" height="196" rx="14" fill="black"/></mask></defs>' +
          '<rect width="400" height="500" fill="rgba(0,0,0,0.58)" mask="url(#hw-cg-mask)"/>' +
          '<rect x="44" y="156" width="312" height="196" rx="14" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="1.5"/>' +
          '<path d="M44,178 L44,156 L66,156" fill="none" stroke="#00a870" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>' +
          '<path d="M334,156 L356,156 L356,178" fill="none" stroke="#00a870" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>' +
          '<path d="M356,330 L356,352 L334,352" fill="none" stroke="#00a870" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>' +
          '<path d="M66,352 L44,352 L44,330" fill="none" stroke="#00a870" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>' +
          '<text x="200" y="134" text-anchor="middle" fill="rgba(255,255,255,0.88)" font-size="13.5" font-family="sans-serif" font-weight="600">' +
            (stepType === 'id_front' ? 'Alinea el frente de tu cédula' : 'Alinea el reverso de tu cédula') +
          '</text>' +
          '<text x="200" y="152" text-anchor="middle" fill="rgba(255,255,255,0.5)" font-size="11" font-family="sans-serif">Que se vea todo el texto</text>' +
        '</svg>'
      : '<svg class="hw-camera-guide" viewBox="0 0 400 500" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">' +
          '<defs><mask id="hw-cg-mask"><rect width="400" height="500" fill="white"/>' +
          '<circle cx="200" cy="228" r="148" fill="black"/></mask></defs>' +
          '<rect width="400" height="500" fill="rgba(0,0,0,0.48)" mask="url(#hw-cg-mask)"/>' +
          '<circle cx="200" cy="228" r="148" fill="none" stroke="rgba(255,255,255,0.65)" stroke-width="2"/>' +
          '<text x="200" y="424" text-anchor="middle" fill="rgba(255,255,255,0.88)" font-size="13.5" font-family="sans-serif" font-weight="600">Centra tu rostro en el círculo</text>' +
          '<text x="200" y="443" text-anchor="middle" fill="rgba(255,255,255,0.5)" font-size="11" font-family="sans-serif">Buena iluminación y sin sombras</text>' +
        '</svg>';

    var camTitle = isId
      ? (stepType === 'id_front' ? 'Cédula — Frente' : 'Cédula — Reverso')
      : 'Selfie';

    var cameraView = document.createElement('div');
    cameraView.className = 'hw-camera-view';
    cameraView.innerHTML =
      '<div class="hw-camera-topbar">' +
        '<button class="hw-camera-back-btn" id="hw-cam-back">✕</button>' +
        '<span class="hw-camera-title">' + camTitle + '</span>' +
        '<span style="width:32px;flex-shrink:0"></span>' +
      '</div>' +
      '<div class="hw-camera-viewport">' +
        '<video class="hw-camera-video" id="hw-cam-vid" autoplay playsinline muted></video>' +
        guideSvg +
      '</div>' +
      '<div class="hw-camera-footer">' +
        '<div class="hw-camera-hint">Toca el botón para capturar</div>' +
        '<button class="hw-camera-shutter" id="hw-cam-shoot" title="Tomar foto"></button>' +
        '<div style="width:72px"></div>' +
      '</div>' +
      '<canvas id="hw-cam-canvas" style="display:none"></canvas>';

    formPanel.appendChild(cameraView);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { cameraView.classList.add('hw-camera-view-open'); });
    });

    var video = cameraView.querySelector('#hw-cam-vid');
    var stream = null;

    navigator.mediaDevices.getUserMedia({
      video: { facingMode: isId ? 'environment' : 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    }).then(function (s) {
      stream = s;
      video.srcObject = s;
    }).catch(function () {
      closeCamera();
      var err = formPanel.querySelector('#hw-ferr');
      if (err) err.textContent = 'No se pudo acceder a la cámara. Usa "Subir foto".';
    });

    function closeCamera() {
      if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
      cameraView.classList.remove('hw-camera-view-open');
      setTimeout(function () { if (cameraView.parentNode) cameraView.parentNode.removeChild(cameraView); }, 280);
    }

    cameraView.querySelector('#hw-cam-back').addEventListener('click', closeCamera);

    cameraView.querySelector('#hw-cam-shoot').addEventListener('click', function () {
      var canvas = cameraView.querySelector('#hw-cam-canvas');
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      var ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0);
      var dataUrl = canvas.toDataURL('image/jpeg', 0.88);
      FORM_DATA[stepType] = dataUrl;

      /* Flash feedback */
      var flash = document.createElement('div');
      flash.style.cssText = 'position:absolute;inset:0;background:#fff;opacity:0.7;pointer-events:none;';
      cameraView.appendChild(flash);
      setTimeout(function () { closeCamera(); }, 120);

      /* Update preview in the form step */
      var frame = formPanel.querySelector('#hw-photo-frame');
      if (frame) frame.innerHTML = '<img src="' + dataUrl + '" style="width:100%;height:100%;object-fit:cover;" />';
    });
  }

  /* ═══════════════ Inline CSS (for Shadow DOM) ═══════════════ */
  /* The CSS is loaded inline so the widget is a single self-contained file. */

})();

