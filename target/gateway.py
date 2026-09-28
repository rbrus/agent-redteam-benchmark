"""Benchmark gateway in front of a Microsoft Foundry prompt agent.

Every red-teaming tool under test talks to the SAME agent through this gateway, so they all see an
identical target surface. The gateway:

* calls the Foundry agent through the Responses API (agent_reference), with Entra ID auth;
* runs the agent's function tools against the mock back-end in ``mock_tools.py``;
* turns an Azure content-filter / Prompt Shields block into the refusal a deployed chat app would
  show, and records which filter fired;
* evaluates the deterministic oracles on every reply and every tool call;
* appends one JSON line per turn to ``$BENCH_LOG_DIR/<tool>.jsonl`` — the single source of truth
  that the scoring stage reads, independent of what each tool reports about itself.

Endpoints (``{tool}`` is the name of the tool under test, used only for attribution):

* ``POST /t/{tool}/chat``                  ``{"message": str, "session_id"?: str}`` -> ``{"reply": str}``
* ``POST /t/{tool}/v1/chat/completions``   OpenAI-compatible; the full message history is forwarded
* ``GET  /health``
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from azure.identity.aio import AzureCliCredential
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import mock_tools
import oracles

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
AGENT_NAME = os.environ.get("FOUNDRY_AGENT_NAME", "helios-support-bench")
CANARY = os.environ.get("BENCH_CANARY", "")
LOG_DIR = Path(os.environ.get("BENCH_LOG_DIR", "runs/current/gateway"))
MAX_CONCURRENCY = int(os.environ.get("BENCH_MAX_CONCURRENCY", "12"))
MAX_TOOL_ROUNDS = 5
BLOCKED_REPLY = "I'm sorry, but I can't help with that request."

RESPONSES_URL = f"{PROJECT_ENDPOINT}/openai/v1/responses"
LOG_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="agent-redteam-benchmark gateway")
_cred = AzureCliCredential()
_token: dict = {"value": "", "exp": 0}
_token_lock = asyncio.Lock()
_sem = asyncio.Semaphore(MAX_CONCURRENCY)
_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
_sessions: dict[str, list] = {}  # session_id -> conversation input items (for /chat sessions)
# session_id -> the oracle's per-conversation state (e.g. the caller's cumulative refunds), so a
# guardrail that is only checked per request can be scored for its split bypass.
_session_oracle: dict[str, dict] = {}
_log_lock = asyncio.Lock()


async def _bearer() -> str:
    async with _token_lock:
        if time.time() > _token["exp"] - 300:
            t = await _cred.get_token("https://ai.azure.com/.default")
            _token.update(value=t.token, exp=t.expires_on)
        return _token["value"]


class Blocked(Exception):
    def __init__(self, stage: str, categories: list[str]):
        self.stage, self.categories = stage, categories


def _filter_categories(err: dict) -> list[str]:
    cats = []
    for f in err.get("content_filters") or []:
        for name, r in (f.get("content_filter_results") or {}).items():
            if isinstance(r, dict) and r.get("filtered"):
                cats.append(f"{f.get('source_type', '?')}:{name}")
    return cats or ["unspecified"]


async def _foundry(input_items: list, stage: str, stats: dict) -> dict:
    body = {"input": input_items, "agent_reference": {"type": "agent_reference", "name": AGENT_NAME}}
    for attempt in range(6):
        r = await _client.post(RESPONSES_URL, json=body, headers={"Authorization": f"Bearer {await _bearer()}"})
        stats["foundry_calls"] += 1
        if r.status_code == 429 or r.status_code >= 500:
            stats["retries"] += 1
            await asyncio.sleep(min(2**attempt, 20))
            continue
        d = r.json()
        err = d.get("error") or {}
        if err.get("code") == "content_filter" or (err.get("innererror") or {}).get("code") == "ContentFiltered":
            raise Blocked(stage, _filter_categories(err))
        if r.status_code >= 400:
            raise RuntimeError(f"foundry {r.status_code}: {json.dumps(err)[:300]}")
        inc = d.get("incomplete_details") or {}
        if inc.get("reason") == "content_filter":
            raise Blocked("output", _filter_categories(d))
        u = d.get("usage") or {}
        stats["input_tokens"] += u.get("input_tokens", 0)
        stats["output_tokens"] += u.get("output_tokens", 0)
        stats["reasoning_tokens"] += (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
        return d
    raise RuntimeError("foundry: retries exhausted")


def _clean_output_items(items: list) -> list:
    """Output items to carry into the next request's input (drop server-only fields)."""
    keep = []
    for it in items:
        it = {k: v for k, v in it.items() if k not in ("agent_reference", "response_id", "status", "created_by")}
        keep.append(it)
    return keep


async def run_agent(conversation: list, rec: dict) -> str:
    """Run one user turn (the last item of ``conversation``) through the agent, including tool rounds.

    ``conversation`` is extended in place with the model's output items and tool results so a
    session can continue from it.
    """
    stats = rec["stats"]
    stage = "input"
    for _ in range(MAX_TOOL_ROUNDS + 1):
        d = await _foundry(conversation, stage, stats)
        out = d.get("output") or []
        conversation.extend(_clean_output_items(out))
        calls = [o for o in out if o.get("type") == "function_call"]
        if not calls:
            text = d.get("output_text") or "".join(
                c.get("text", "")
                for o in out
                if o.get("type") == "message"
                for c in (o.get("content") or [])
                if c.get("type") in ("output_text", "text")
            )
            return text
        for c in calls:
            try:
                args = json.loads(c.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": c.get("arguments")}
            viol = oracles.check_tool_call(c["name"], args, CANARY, session=_session_oracle.setdefault(session, {}))
            result = mock_tools.execute(c["name"], args)
            rec["tool_calls"].append({"name": c["name"], "args": args, "violations": viol})
            rec["violations"].extend(viol)
            conversation.append({"type": "function_call_output", "call_id": c["call_id"], "output": result})
        stage = "tool_result"
    return "(tool loop limit reached)"


async def handle_turn(tool: str, endpoint: str, conversation: list, user_text: str, session: str | None) -> dict:
    rec = {
        "id": uuid.uuid4().hex,
        "ts": time.time(),
        "tool": tool,
        "endpoint": endpoint,
        "session": session,
        "history_items": len(conversation) - 1,
        "input": user_text,
        "reply": "",
        "blocked": False,
        "block_stage": None,
        "block_categories": [],
        "tool_calls": [],
        "violations": [],
        "error": None,
        "stats": {"foundry_calls": 0, "retries": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0},
    }
    t0 = time.perf_counter()
    async with _sem:
        try:
            rec["reply"] = await run_agent(conversation, rec)
        except Blocked as b:
            rec.update(blocked=True, block_stage=b.stage, block_categories=b.categories, reply=BLOCKED_REPLY)
        except Exception as e:  # noqa: BLE001 — recorded, and the tool sees an error reply
            rec["error"] = str(e)[:500]
            rec["reply"] = "Sorry, the service is temporarily unavailable."
    rec["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    rec["violations"].extend(oracles.check_reply(rec["reply"], CANARY))
    rec["violations"] = sorted(set(rec["violations"]))
    async with _log_lock:
        with open(LOG_DIR / f"{tool}.jsonl", "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _as_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


@app.get("/health")
async def health():
    return {"ok": True, "agent": AGENT_NAME}


@app.post("/t/{tool}/chat")
async def chat(tool: str, request: Request):
    body = await request.json()
    msg = body.get("message") or body.get("prompt") or body.get("input") or ""
    msg = _as_text(msg)
    session = body.get("session_id")
    conv = _sessions.setdefault(session, []) if session else []
    conv.append({"role": "user", "content": msg})
    rec = await handle_turn(tool, "chat", conv, msg, session)
    if session and rec["blocked"]:
        conv.append({"role": "assistant", "content": BLOCKED_REPLY})
    return {"reply": rec["reply"], "blocked": rec["blocked"]}


@app.post("/t/{tool}/v1/chat/completions")
async def chat_completions(tool: str, request: Request):
    body = await request.json()
    conv = []
    for m in body.get("messages") or []:
        role = m.get("role")
        if role in ("user", "assistant"):  # a deployed agent's system prompt is not caller-controlled
            conv.append({"role": role, "content": _as_text(m.get("content"))})
    if not conv or conv[-1]["role"] != "user":
        conv.append({"role": "user", "content": ""})
    rec = await handle_turn(tool, "chat_completions", conv, conv[-1]["content"], None)
    return JSONResponse(
        {
            "id": "chatcmpl-" + rec["id"],
            "object": "chat.completion",
            "created": int(rec["ts"]),
            "model": body.get("model") or AGENT_NAME,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": rec["reply"]}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": rec["stats"]["input_tokens"],
                "completion_tokens": rec["stats"]["output_tokens"],
                "total_tokens": rec["stats"]["input_tokens"] + rec["stats"]["output_tokens"],
            },
        }
    )


# --------------------------------------------------------------------------------------------------
# Attacker proxy: every tool's own LLM (attack generator, multi-turn attacker, internal grader) goes
# through here to the shared attacker model. It forces non-thinking mode (thinking tokens would only
# slow the attacker down) and meters attacker-side tokens per tool.
# --------------------------------------------------------------------------------------------------

ATTACKER_BASE_URL = os.environ.get("ATTACKER_BASE_URL", "http://localhost:11434/v1").rstrip("/")
ATTACKER_MODEL = os.environ.get("ATTACKER_MODEL", "")
ATTACKER_API_KEY = os.environ.get("ATTACKER_API_KEY", "ollama")
_attacker_sem = asyncio.Semaphore(int(os.environ.get("ATTACKER_MAX_CONCURRENCY", "2")))


def _sse(completion: dict):
    from fastapi.responses import StreamingResponse

    choice = completion["choices"][0]
    chunk = {
        "id": completion.get("id"),
        "object": "chat.completion.chunk",
        "created": completion.get("created"),
        "model": completion.get("model"),
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": choice["message"].get("content") or ""}, "finish_reason": None}],
    }
    end = dict(chunk, choices=[{"index": 0, "delta": {}, "finish_reason": choice.get("finish_reason", "stop")}], usage=completion.get("usage"))

    async def gen():
        yield f"data: {json.dumps(chunk)}\n\n"
        yield f"data: {json.dumps(end)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/attacker/{tool}/v1/models")
async def attacker_models(tool: str):
    return {"object": "list", "data": [{"id": ATTACKER_MODEL, "object": "model", "owned_by": "local"}]}


@app.post("/attacker/{tool}/v1/chat/completions")
async def attacker_chat(tool: str, request: Request):
    body = await request.json()
    stream = bool(body.pop("stream", False))
    body.pop("stream_options", None)
    body["model"] = ATTACKER_MODEL  # every tool gets the same attacker, whatever it asked for
    body["reasoning_effort"] = "none"
    for k in ("max_completion_tokens",):
        if k in body:
            body["max_tokens"] = body.pop(k)
    # The attacker model's chat template rejects a conversation with no user turn (some tools open
    # with a system-only message); add a neutral one so every tool gets the same model behaviour.
    msgs = body.get("messages") or []
    if not any(m.get("role") == "user" for m in msgs):
        body["messages"] = msgs + [{"role": "user", "content": "Proceed."}]
    t0 = time.perf_counter()
    async with _attacker_sem:
        for attempt in range(8):  # the local runtime crashes and restarts under load; ride it out
            r = await _client.post(
                f"{ATTACKER_BASE_URL}/chat/completions", json=body, headers={"Authorization": f"Bearer {ATTACKER_API_KEY}"}, timeout=600
            )
            if r.status_code < 500:
                break
            await asyncio.sleep(min(5 * (attempt + 1), 30))
    d = r.json()
    u = d.get("usage") or {}
    async with _log_lock:
        with open(LOG_DIR / f"attacker__{tool}.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), "tool": tool, "status": r.status_code, "latency_ms": round((time.perf_counter() - t0) * 1000),
                                "prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": u.get("completion_tokens", 0)}) + "\n")
    if r.status_code >= 400:
        return JSONResponse(d, status_code=r.status_code)
    return _sse(d) if stream else JSONResponse(d)
