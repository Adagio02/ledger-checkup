"""Chat assistant that reviews scan results with the owner.

Works with any OpenAI-compatible chat API. Defaults target Groq's free tier, but you can
point it at Google Gemini's OpenAI endpoint, OpenRouter free models, or a local Ollama by
changing LLM_BASE_URL / LLM_MODEL / LLM_API_KEY. With no key configured, a rule-based
assistant answers from the scan results so the app still works offline.
"""
from __future__ import annotations

import json
import os

import httpx

from .checks import CHECK_LABELS
from .models import Issue

SYSTEM_PROMPT = """You are a friendly, careful bookkeeping assistant for a small business owner.
You are reviewing the results of an automated scan of their books. Rules:
- Explain issues in plain English, with the dollar impact, and say why each matters.
- Recommend which issues to handle first (critical and high-dollar items first).
- Fixes are only proposals; the owner approves or rejects each one in the dashboard. Never claim
  you changed anything.
- Only use facts from the scan data below. If you do not know, say so. You are not a CPA; suggest
  a professional for tax or legal questions.
- Keep answers short: a few sentences or a short list.

SCAN DATA (JSON):
"""


def config() -> dict:
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
        "model": os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
        "api_key": os.environ.get("LLM_API_KEY", ""),
    }


def is_configured() -> bool:
    cfg = config()
    # Local servers such as Ollama do not need a key.
    return bool(cfg["api_key"]) or "localhost" in cfg["base_url"] or "ollama" in cfg["base_url"]


def build_context(summary: dict, issues: list[Issue], limit: int = 40) -> str:
    compact = [{"id": i.id, "type": CHECK_LABELS.get(i.check, i.check), "severity": i.severity,
                "status": i.status, "title": i.title, "why": i.explanation,
                "amount_at_stake": i.amount_at_stake, "proposed_fix": i.fix.summary}
               for i in issues[:limit]]
    return json.dumps({"summary": summary, "issues": compact,
                       "issues_not_shown": max(0, len(issues) - limit)}, default=str)


async def chat(question: str, history: list[dict], summary: dict, issues: list[Issue]) -> str:
    if not is_configured():
        return fallback_answer(question, summary, issues)
    cfg = config()
    messages = [{"role": "system", "content": SYSTEM_PROMPT + build_context(summary, issues)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
    messages.append({"role": "user", "content": question})
    headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{cfg['base_url']}/chat/completions", headers=headers,
                                  json={"model": cfg["model"], "messages": messages, "temperature": 0.2})
        if r.status_code == 429:
            return "The free AI tier is rate-limited right now. Wait a minute and ask again."
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return (f"I couldn't reach the AI model ({type(e).__name__}). Check LLM_BASE_URL, LLM_MODEL and "
                f"LLM_API_KEY. Here's a basic summary instead:\n\n" + fallback_answer(question, summary, issues))


def fallback_answer(question: str, summary: dict, issues: list[Issue]) -> str:
    """Deterministic answers when no LLM is configured."""
    q = question.lower()
    open_issues = [i for i in issues if i.status == "open"]
    if not open_issues:
        return "There are no open issues. Your books look clean for the data you uploaded."

    for i in issues:
        if i.id.lower() in q:
            return f"**{i.title}**\n\n{i.explanation}\n\nProposed fix: {i.fix.summary}."

    for check, label in CHECK_LABELS.items():
        if check in q or label.lower() in q:
            matches = [i for i in open_issues if i.check == check]
            if not matches:
                return f"There are no open {label.lower()} issues."
            lines = "\n".join(f"- {i.title}: {i.fix.summary}" for i in matches[:8])
            return f"{len(matches)} open {label.lower()} issue(s):\n{lines}"

    top = open_issues[:3]
    lines = "\n".join(f"{n}. **{i.title}** ({i.severity}). {i.fix.summary}." for n, i in enumerate(top, 1))
    return (f"Your books health score is {summary['health_score']}/100 with {summary['open_issues']} open "
            f"issues and about ${summary['amount_at_stake']:,.2f} at stake. Start with these:\n\n{lines}\n\n"
            "(Add an LLM_API_KEY to get full conversational answers.)")
