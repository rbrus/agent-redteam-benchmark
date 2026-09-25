// promptfoo provider for the shared benchmark attacker (OpenAI-compatible, /attacker/<tool>/v1).
//
// Why not plain `openai:chat` with apiBaseUrl: promptfoo's iterative jailbreak opens every attack
// with a request that holds ONLY a system message (the PAIR attacker prompt). The shared
// attacker's Qwen chat template rejects that ("Jinja Exception: No user query found in
// messages", HTTP 500), so every iteration errored and the attack never reached the target.
// This adapter sends exactly what promptfoo asked for, and only when a request carries no user
// message it appends one neutral kick-off user turn. Nothing else is changed.
const KICKOFF = 'Begin. Respond in the format specified above.';

function toMessages(prompt) {
  if (typeof prompt === 'string') {
    const s = prompt.trim();
    if (s.startsWith('[')) {
      try {
        const arr = JSON.parse(s);
        if (Array.isArray(arr) && arr.every((m) => m && typeof m.role === 'string')) return arr;
      } catch {
        /* plain text */
      }
    }
    return [{ role: 'user', content: prompt }];
  }
  return Array.isArray(prompt) ? prompt : [{ role: 'user', content: String(prompt) }];
}

module.exports = class BenchAttackerProvider {
  constructor(options = {}) {
    this.config = options.config || {};
    this.label = options.label;
    this.providerId = options.id || 'bench-attacker';
  }

  id() {
    return this.providerId;
  }

  async callApi(prompt) {
    const messages = toMessages(prompt).map((m) => ({
      role: m.role,
      content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
    }));
    if (!messages.some((m) => m.role === 'user')) messages.push({ role: 'user', content: KICKOFF });

    const base = String(this.config.apiBaseUrl || '').replace(/\/$/, '');
    const body = {
      model: 'attacker',
      messages,
      temperature: this.config.temperature ?? 0.7,
      max_tokens: this.config.max_tokens ?? 4096,
    };
    const timeoutMs = this.config.timeout ?? 600000;
    let lastErr;
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const r = await fetch(`${base}/chat/completions`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', authorization: 'Bearer x' },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(timeoutMs),
        });
        const text = await r.text();
        if (!r.ok) {
          lastErr = `attacker HTTP ${r.status}: ${text.slice(0, 300)}`;
          if (r.status >= 500 || r.status === 429) {
            await new Promise((res) => setTimeout(res, 2000 * 2 ** attempt));
            continue;
          }
          return { error: lastErr };
        }
        const d = JSON.parse(text);
        const u = d.usage || {};
        return {
          output: d.choices?.[0]?.message?.content ?? '',
          tokenUsage: {
            total: u.total_tokens ?? 0,
            prompt: u.prompt_tokens ?? 0,
            completion: u.completion_tokens ?? 0,
            numRequests: 1,
          },
        };
      } catch (e) {
        lastErr = `attacker request failed: ${e}`;
        await new Promise((res) => setTimeout(res, 2000 * 2 ** attempt));
      }
    }
    return { error: lastErr };
  }
};
