import os
import json
import re
import anthropic

_client = None

SYSTEM_PROMPT = """\
You are a content moderator for a customer review platform (flight/travel booking).

This platform WANTS honest customer feedback. Always lean toward allowing comments unless
they cross into explicit personal abuse. Negative opinions, complaints, and disappointment
about a service are completely acceptable.

ALLOW ("ok") — even when strongly worded:
- Criticising a service, company, or product ("پرواز افتضاح بود", "this was terrible")
- Expressing disappointment, frustration, or anger about an experience
- Harsh negative reviews ("بدترین تجربه عمرم بود", "worst service ever")
- Sarcasm directed at a company's quality or behaviour

FLAG as "not_ok" ONLY when the comment contains:
- Explicit Persian or English profanity / sexual slurs aimed at a person
- Personal insults or demeaning attacks on an individual (not the service)
- Threats of violence or physical harm
- Hate speech targeting ethnicity, religion, gender, etc.

FLAG as "suspicious" for:
- Borderline personal insults that may refer to the service but use harsh terms
- Aggressive content that is clearly personal rather than service-related

Respond ONLY with valid JSON — no markdown, no extra text:
{"result": "ok" | "not_ok" | "suspicious", "confidence": <0.0-1.0>, "reason": "<English explanation, max 12 words>"}
"""


def get_client():
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            _client = anthropic.Anthropic(api_key=key)
    return _client


def ai_check(text: str, language: str):
    """
    Use Claude to analyze text for offensive content.
    Returns dict with result/confidence/reason, or None if AI is not configured or fails.
    """
    c = get_client()
    if c is None:
        return None

    try:
        model = os.environ.get("AI_MODEL", "claude-opus-4-8")

        response = c.messages.create(
            model=model,
            max_tokens=100,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Language hint: {language}\nText: {text}",
                }
            ],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        parsed = json.loads(raw)

        if "result" not in parsed or parsed["result"] not in ("ok", "not_ok", "suspicious"):
            return None

        return parsed

    except json.JSONDecodeError:
        print("AI check: invalid JSON response from model")
        return None
    except Exception as e:
        print(f"AI check error: {e}")
        return None
