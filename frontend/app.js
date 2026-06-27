let config = null;
let tokens = null;
let activeProjectId = null;

const els = {
  identity: document.getElementById("identity"),
  signInButton: document.getElementById("signInButton"),
  signOutButton: document.getElementById("signOutButton"),
  projectForm: document.getElementById("projectForm"),
  submitButton: document.getElementById("submitButton"),
  prompt: document.getElementById("prompt"),
  region: document.getElementById("region"),
  statusValue: document.getElementById("statusValue"),
  message: document.getElementById("message"),
  architectureSummary: document.getElementById("architectureSummary"),
  artifactLink: document.getElementById("artifactLink"),
  validationOutput: document.getElementById("validationOutput"),
  costOutput: document.getElementById("costOutput"),
  changeSetOutput: document.getElementById("changeSetOutput"),
  timeline: Array.from(document.querySelectorAll(".timeline span")),
};

function setMessage(text) {
  els.message.textContent = text || "";
}

function setStatus(status) {
  els.statusValue.textContent = status;
  const states = ["RECEIVED", "DESIGNING", "GENERATING_CDK", "VALIDATING", "CHANGE_SET_READY"];
  const index = states.indexOf(status);
  els.timeline.forEach((item) => {
    const itemIndex = states.indexOf(item.dataset.state);
    item.classList.toggle("active", index >= itemIndex && itemIndex >= 0);
  });
}

function pretty(value) {
  return JSON.stringify(value || {}, null, 2);
}

function base64UrlEncode(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

async function sha256(text) {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
}

function randomString(length = 64) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
  const values = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(values, (value) => chars[value % chars.length]).join("");
}

function decodeJwt(token) {
  const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(atob(payload));
}

function saveTokens(nextTokens) {
  tokens = nextTokens;
  sessionStorage.setItem("cloudcompass_tokens", JSON.stringify(nextTokens));
  const claims = decodeJwt(nextTokens.id_token);
  els.identity.textContent = claims.email || claims.sub || "Signed in";
  els.signInButton.hidden = true;
  els.signOutButton.hidden = false;
  els.submitButton.disabled = false;
}

function clearTokens() {
  tokens = null;
  sessionStorage.removeItem("cloudcompass_tokens");
  els.identity.textContent = "Signed out";
  els.signInButton.hidden = false;
  els.signOutButton.hidden = true;
  els.submitButton.disabled = true;
}

async function signIn() {
  const verifier = randomString();
  const challenge = base64UrlEncode(await sha256(verifier));
  sessionStorage.setItem("cloudcompass_pkce", verifier);
  const params = new URLSearchParams({
    client_id: config.userPoolClientId,
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: config.redirectUri,
    code_challenge_method: "S256",
    code_challenge: challenge,
  });
  window.location.assign(`${config.cognitoDomain}/oauth2/authorize?${params.toString()}`);
}

async function exchangeCode(code) {
  const verifier = sessionStorage.getItem("cloudcompass_pkce");
  if (!verifier) {
    throw new Error("Missing PKCE verifier. Start sign-in again.");
  }
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.userPoolClientId,
    code,
    redirect_uri: config.redirectUri,
    code_verifier: verifier,
  });
  const response = await fetch(`${config.cognitoDomain}/oauth2/token`, {
    method: "POST",
    headers: {"content-type": "application/x-www-form-urlencoded"},
    body,
  });
  if (!response.ok) {
    throw new Error(`Token exchange failed with HTTP ${response.status}`);
  }
  saveTokens(await response.json());
  sessionStorage.removeItem("cloudcompass_pkce");
  window.history.replaceState({}, document.title, window.location.pathname);
}

async function apiFetch(path, options = {}) {
  if (!tokens?.id_token) {
    throw new Error("Sign in first.");
  }
  const response = await fetch(`${config.apiUrl.replace(/\/$/, "")}${path}`, {
    ...options,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${tokens.id_token}`,
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed with HTTP ${response.status}`);
  }
  return payload;
}

function renderProject(project) {
  const status = project.status || "RECEIVED";
  setStatus(status);
  activeProjectId = project.project_id || activeProjectId;
  els.architectureSummary.textContent = project.architecture_summary || "Pending.";
  if (project.cdk_artifact_download_url) {
    els.artifactLink.href = project.cdk_artifact_download_url;
    els.artifactLink.textContent = project.cdk_artifact_s3_uri || "Download generated CDK project";
  } else {
    els.artifactLink.removeAttribute("href");
    els.artifactLink.textContent = project.cdk_artifact_s3_uri || "Unavailable";
  }
  els.validationOutput.textContent = pretty(
    project.validation_summary || project.security_findings_json
  );
  els.costOutput.textContent = pretty(project.cost_estimate_json || project.cost_estimate);
  els.changeSetOutput.textContent = pretty({
    change_set_arn: project.change_set_arn,
    stack_name: project.change_set_stack_name,
    template: project.synthesized_template_s3_uri,
    next_action: project.next_action,
  });
}

async function refreshProject() {
  if (!activeProjectId) return;
  const project = await apiFetch(`/projects/${activeProjectId}`);
  renderProject(project);
}

const TERMINAL_STATES = ["CHANGE_SET_READY", "FAILED"];

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function pollUntilDone({intervalMs = 3000, maxMs = 300000} = {}) {
  // The agent runs in the background (~1-2 min); poll GET /projects/{id} until it
  // persists a terminal status, refreshing the UI on each tick.
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    await delay(intervalMs);
    let project;
    try {
      project = await apiFetch(`/projects/${activeProjectId}`);
    } catch (error) {
      setMessage(error.message);
      continue;
    }
    renderProject(project);
    if (TERMINAL_STATES.includes(project.status)) {
      setMessage(project.status === "FAILED" ? project.error_message || "Generation failed." : "");
      return project.status;
    }
    setMessage(`Working… ${project.status || "RECEIVED"}`);
  }
  setMessage("Still running — this is taking longer than usual. It may finish shortly.");
  return null;
}

async function submitProject(event) {
  event.preventDefault();
  setMessage("");
  setStatus("RECEIVED");
  els.submitButton.disabled = true;
  try {
    const response = await apiFetch("/projects", {
      method: "POST",
      body: JSON.stringify({
        prompt: els.prompt.value,
        region: els.region.value || "us-east-1",
      }),
    });
    activeProjectId = response.project_id;
    renderProject(response.project || response);
    setMessage("Working… RECEIVED");
    await pollUntilDone();
  } catch (error) {
    setMessage(error.message);
  } finally {
    els.submitButton.disabled = !tokens;
  }
}

async function init() {
  config = await fetch("./config.json").then((response) => response.json());
  const saved = sessionStorage.getItem("cloudcompass_tokens");
  if (saved) {
    saveTokens(JSON.parse(saved));
  } else {
    clearTokens();
  }

  const params = new URLSearchParams(window.location.search);
  if (params.has("code")) {
    try {
      await exchangeCode(params.get("code"));
    } catch (error) {
      clearTokens();
      setMessage(error.message);
    }
  }
}

els.signInButton.addEventListener("click", signIn);
els.signOutButton.addEventListener("click", () => {
  clearTokens();
  const params = new URLSearchParams({
    client_id: config.userPoolClientId,
    logout_uri: config.redirectUri,
  });
  window.location.assign(`${config.cognitoDomain}/logout?${params.toString()}`);
});
els.projectForm.addEventListener("submit", submitProject);

init().catch((error) => {
  clearTokens();
  setMessage(error.message);
});
