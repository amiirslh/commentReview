from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.conf import settings
from swear_persian.swear_detector import PersianSwearDetector
from better_profanity import profanity as en_profanity
from api.ai_checker import ai_check
from api.pii_checker import pii_check

import os
import re
import json
import redis
import base64


# =========================
# CONFIG
# =========================

MODEL_PATH = os.path.join(
    settings.BASE_DIR, "swear_persian", "models", "model.pkl"
)

HARD_CODE_PATH = os.path.join(
    settings.BASE_DIR, "config", "Hard_code_phrases.json"
)

# >= this → not_ok
CONFIDENCE_BLOCK = 0.85

# >= this (and < BLOCK) → suspicious
CONFIDENCE_SUSPICIOUS = 0.50

HARD_CODE_CACHE_KEY = "hard_code_phrases"


# =========================
# REDIS
# =========================

redis_client = redis.StrictRedis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True,
)


# =========================
# PERSIAN MODEL (singleton)
# =========================

_detector = None


def get_detector():
    global _detector
    if _detector is None:
        try:
            if os.path.exists(MODEL_PATH):
                _detector = PersianSwearDetector(model_path=MODEL_PATH)
            else:
                print("Model not found:", MODEL_PATH)
        except Exception as e:
            print("Model load error:", e)
    return _detector


# =========================
# LANGUAGE DETECTION
# =========================
# Uses Unicode block ratios — no extra library needed.
# Persian/Arabic  U+0600–U+06FF
# Latin           ASCII alpha

def detect_language(text: str) -> str:
    persian = sum(1 for c in text if "؀" <= c <= "ۿ")
    latin   = sum(1 for c in text if c.isascii() and c.isalpha())
    total   = persian + latin
    if total == 0:
        return "unknown"
    ratio = persian / total
    if ratio >= 0.65:
        return "persian"
    if ratio <= 0.25:
        return "english"
    return "mixed"


# =========================
# HARD-CODE LIST
# (Base64-encoded, Redis-cached)
# =========================

def get_hard_code():
    try:
        cached = redis_client.get(HARD_CODE_CACHE_KEY)
        if cached:
            return [
                base64.b64decode(i).decode("utf-8")
                for i in json.loads(cached)
            ]
    except Exception as e:
        print("Redis unavailable, loading from file:", e)

    try:
        with open(HARD_CODE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        encoded = [
            base64.b64encode(p.encode("utf-8")).decode("utf-8")
            for p in data
        ]

        try:
            redis_client.set(
                HARD_CODE_CACHE_KEY,
                json.dumps(encoded, ensure_ascii=False),
            )
        except Exception:
            pass

        return data

    except Exception as e:
        print("Hard code load error:", e)
        return []


# =========================
# TEXT NORMALIZATION
# (anti-bypass: spacing, separators, repeated chars)
# =========================

def remove_duplicate_chars(text: str) -> str:
    if not text:
        return text
    result, prev = [], None
    for ch in text:
        if ch != prev:
            result.append(ch)
        prev = ch
    return "".join(result)


def normalize_for_match(text: str) -> str:
    """Strip all separators/spaces/repeated chars for hard-block comparison."""
    text = text.lower()
    text = re.sub(r"[._\-/|،,:؛!?؟‌@#$%^&*()\[\]{}<>~`'\"+\\]", "", text)
    text = re.sub(r"\s+", "", text)
    text = remove_duplicate_chars(text)
    return text


def normalize_tokens(text: str) -> list:
    """
    Split into tokens and merge single-char sequences — catches bypasses like
    'ک ی ر' → 'کیر'  or  'k i r' → 'kir'.
    """
    text = re.sub(r"[\.\-_/|،,:؛!?؟]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    words  = text.split()
    result = []
    buffer = []

    for w in words:
        w = remove_duplicate_chars(w)
        if len(w) == 1:
            buffer.append(w)
        else:
            if len(buffer) >= 2:
                result.append(remove_duplicate_chars("".join(buffer)))
            buffer = []
            result.append(w)

    if len(buffer) >= 2:
        result.append(remove_duplicate_chars("".join(buffer)))

    return list(dict.fromkeys(result))


# =========================
# CHECK: HARD BLOCK
# =========================

def hard_block_check(texts: list, hard_code: list):
    for t in texts:
        nt = normalize_for_match(t)
        for phrase in hard_code:
            if normalize_for_match(phrase) in nt:
                return True, phrase
    return False, None


# =========================
# CHECK: ENGLISH PROFANITY
# =========================

def english_check(text: str):
    """
    Uses better_profanity (covers a comprehensive English swear-word list).
    Also checks each token independently to catch embedded words.
    """
    if en_profanity.contains_profanity(text):
        return True, text

    # Check each whitespace-token individually (catches "you f u c k ing idiot")
    tokens = text.lower().split()
    for tok in tokens:
        cleaned = re.sub(r"[^a-z]", "", tok)
        if cleaned and en_profanity.contains_profanity(cleaned):
            return True, tok

    return False, None


# =========================
# CHECK: PERSIAN ML MODEL
# =========================

def persian_ml_check(texts: list):
    """
    Run the SVM model over every text variant; return the highest-confidence
    offensive hit.

    Returns (result, confidence, matched_text) where
    result ∈ {'not_ok', 'suspicious', 'ok', 'unavailable'}
    """
    d = get_detector()
    if d is None or not d.is_trained:
        return "unavailable", 0.0, None

    best_conf = 0.0
    best_text = None

    for item in texts:
        r = d.predict(item)
        if r.get("is_offensive", False):
            conf = r.get("confidence", 0.0)
            if conf > best_conf:
                best_conf = conf
                best_text  = item

    if best_conf >= CONFIDENCE_BLOCK:
        return "not_ok", best_conf, best_text
    if best_conf >= CONFIDENCE_SUSPICIOUS:
        return "suspicious", best_conf, best_text
    return "ok", best_conf, best_text


# =========================
# API VIEW
# =========================

@api_view(["POST"])
def check_text(request):

    try:
        text = request.data.get("text", "").strip()
        if not text:
            return Response(
                {"status": "error", "message": "Text required!"},
                status=400,
            )

        language          = detect_language(text)
        hard_code         = get_hard_code()
        normalized_tokens = normalize_tokens(text)

        # All variants to test: original + bypass-collapsed tokens
        texts_to_check = list(set([text] + normalized_tokens))

        # ── Stage 1: Hard block (language-agnostic) ───────────────────────
        blocked, matched = hard_block_check(texts_to_check, hard_code)
        if blocked:
            return Response({
                "text":              text,
                "result":            "not_ok",
                "confidence":        1.0,
                "language":          language,
                "matched_text":      matched,
                "reason":            "hard_block",
                "normalized_tokens": normalized_tokens,
                "ai_explanation":    None,
            })

        # ── Stage 2: PII / spam detection (language-agnostic) ────────────
        pii_severity, pii_reason, pii_match = pii_check(texts_to_check)
        if pii_severity is not None:
            return Response({
                "text":              text,
                "result":            pii_severity,
                "confidence":        1.0,
                "language":          language,
                "matched_text":      pii_match,
                "reason":            pii_reason,
                "normalized_tokens": normalized_tokens,
                "ai_explanation":    None,
            })

        # ── Stage 3a: English profanity (english / mixed / unknown) ──────
        if language in ("english", "mixed", "unknown"):
            is_en_bad, en_match = english_check(text)
            if is_en_bad:
                return Response({
                    "text":              text,
                    "result":            "not_ok",
                    "confidence":        1.0,
                    "language":          language,
                    "matched_text":      en_match,
                    "reason":            "english_profanity",
                    "normalized_tokens": normalized_tokens,
                    "ai_explanation":    None,
                })

        # ── Stage 3b: Persian ML model (persian / mixed / unknown) ───────
        svm_result = ("ok", 0.0, None)

        if language in ("persian", "mixed", "unknown"):
            ml_result, ml_conf, ml_text = persian_ml_check(texts_to_check)

            if ml_result == "unavailable":
                return Response(
                    {"status": "error", "message": "Persian model not loaded"},
                    status=500,
                )

            if ml_result == "not_ok":
                # High confidence — return immediately without AI
                return Response({
                    "text":              text,
                    "result":            "not_ok",
                    "confidence":        round(ml_conf, 2),
                    "language":          language,
                    "matched_text":      ml_text,
                    "reason":            "ml_model",
                    "normalized_tokens": normalized_tokens,
                    "ai_explanation":    None,
                })

            svm_result = (ml_result, ml_conf, ml_text)

        # ── Stage 4: AI model (Claude) ────────────────────────────────────
        ai_result = ai_check(text, language)

        if ai_result is not None:
            ai_verdict     = ai_result["result"]
            ai_confidence  = round(float(ai_result.get("confidence", 0.8)), 2)
            ai_explanation = ai_result.get("reason")

            if ai_verdict == "not_ok":
                return Response({
                    "text":              text,
                    "result":            "not_ok",
                    "confidence":        ai_confidence,
                    "language":          language,
                    "matched_text":      None,
                    "reason":            "ai_model",
                    "normalized_tokens": normalized_tokens,
                    "ai_explanation":    ai_explanation,
                })

            if ai_verdict == "suspicious":
                return Response({
                    "text":              text,
                    "result":            "suspicious",
                    "confidence":        ai_confidence,
                    "language":          language,
                    "matched_text":      svm_result[2],
                    "reason":            "ai_model",
                    "normalized_tokens": normalized_tokens,
                    "ai_explanation":    ai_explanation,
                })

        # AI said ok (or is not configured) — honour SVM suspicious if present
        svm_code, svm_conf, svm_text = svm_result
        if svm_code == "suspicious":
            return Response({
                "text":              text,
                "result":            "suspicious",
                "confidence":        round(svm_conf, 2),
                "language":          language,
                "matched_text":      svm_text,
                "reason":            "ml_model",
                "normalized_tokens": normalized_tokens,
                "ai_explanation":    None,
            })

        # ── Stage 5: Clean ────────────────────────────────────────────────
        return Response({
            "text":              text,
            "result":            "ok",
            "confidence":        0.0,
            "language":          language,
            "matched_text":      None,
            "reason":            None,
            "normalized_tokens": normalized_tokens,
            "ai_explanation":    None,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(
            {"status": "error", "message": str(e)},
            status=500,
        )
