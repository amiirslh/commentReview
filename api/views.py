from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.conf import settings
from swear_persian.swear_detector import PersianSwearDetector

import os
import re
import json
import redis
import base64


# =========================
# CONFIG
# =========================

MODEL_PATH = os.path.join(
    settings.BASE_DIR,
    "swear_persian",
    "models",
    "model.pkl"
)

HARD_CODE_PATH = os.path.join(
    settings.BASE_DIR,
    "config",
    "Hard_code_phrases.json"
)

CONFIDENCE_THRESHOLD = 0.85

HARD_CODE_CACHE_KEY = "hard_code_phrases"


# =========================
# REDIS
# =========================

redis_client = redis.StrictRedis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)


# =========================
# MODEL (singleton)
# =========================

detector = None


def get_detector():

    global detector

    if detector is None:

        try:

            if os.path.exists(MODEL_PATH):

                print("✅ Loading model:", MODEL_PATH)

                detector = PersianSwearDetector(
                    model_path=MODEL_PATH
                )

            else:

                print("❌ Model not found")

        except Exception as e:

            print("❌ Model error:", e)

    return detector


# =========================
# LOAD HARD CODE
# (Base64 + Redis cache)
# =========================

def get_hard_code():

    cached = redis_client.get(
        HARD_CODE_CACHE_KEY
    )

    # -------------------------
    # READ FROM REDIS
    # -------------------------

    if cached:

        try:

            encoded_list = json.loads(
                cached
            )

            decoded_list = []

            for item in encoded_list:

                decoded_list.append(
                    base64.b64decode(item)
                    .decode("utf-8")
                )

            return decoded_list

        except Exception as e:

            print(
                "❌ Redis decode error:",
                e
            )

    # -------------------------
    # READ FROM FILE
    # -------------------------

    try:

        with open(
            HARD_CODE_PATH,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        encoded_list = []

        for phrase in data:

            encoded_phrase = (
                base64.b64encode(
                    phrase.encode("utf-8")
                )
                .decode("utf-8")
            )

            encoded_list.append(
                encoded_phrase
            )

        redis_client.set(
            HARD_CODE_CACHE_KEY,
            json.dumps(
                encoded_list,
                ensure_ascii=False
            )
        )

        print(
            "✅ Hard code loaded from file → Redis"
        )

        return data

    except Exception as e:

        print(
            "❌ Hard code load error:",
            e
        )

        return []


# =========================
# REMOVE REPEATED LETTERS
# =========================

def remove_duplicate_chars(text):

    if not text:
        return text

    result = []

    prev = None

    for ch in text:

        if ch != prev:

            result.append(ch)

        prev = ch

    return ''.join(result)


# =========================
# NORMALIZATION (anti bypass)
# =========================

def normalize_tokens(text):

    # حذف جداکننده‌ها
    text = re.sub(
        r'[\.\-_/|،,:؛!?؟]+',
        '',
        text
    )

    # حذف فاصله‌های اضافی
    text = re.sub(
        r'\s+',
        ' ',
        text
    ).strip()

    words = text.split()

    result = []

    buffer = []

    for w in words:

        w = remove_duplicate_chars(w)

        if len(w) == 1:

            buffer.append(w)

        else:

            if len(buffer) >= 2:

                merged = ''.join(
                    buffer
                )

                merged = remove_duplicate_chars(
                    merged
                )

                result.append(
                    merged
                )

            buffer = []

            result.append(w)

    if len(buffer) >= 2:

        merged = ''.join(
            buffer
        )

        merged = remove_duplicate_chars(
            merged
        )

        result.append(
            merged
        )

    return list(
        dict.fromkeys(result)
    )


# =========================
# NORMALIZE FOR MATCH
# =========================

def normalize_for_match(text):

    text = text.lower()

    text = re.sub(
        r'[._\-/|،,:؛!?؟‌]',
        '',
        text
    )

    text = re.sub(
        r'\s+',
        '',
        text
    )

    text = remove_duplicate_chars(
        text
    )

    return text


# =========================
# HARD BLOCK CHECK
# =========================

def hard_block_check(
    texts,
    hard_code
):

    for t in texts:

        nt = normalize_for_match(
            t
        )

        for phrase in hard_code:

            np = normalize_for_match(
                phrase
            )

            if np in nt:

                return True, phrase

    return False, None


# =========================
# API VIEW
# =========================

@api_view(["POST"])
def check_text(request):

    try:

        text = request.data.get(
            "text",
            ""
        ).strip()

        if not text:

            return Response(
                {
                    "status": "error",
                    "message": "Text required!"
                },
                status=400
            )

        detector = get_detector()

        if (
            detector is None
            or not detector.is_trained
        ):

            return Response(
                {
                    "status": "error",
                    "message": "Model not loaded"
                },
                status=500
            )

        # -------------------------
        # HARD CODE
        # -------------------------

        hard_code = get_hard_code()

        # -------------------------
        # TOKENIZE
        # -------------------------

        normalized_tokens = normalize_tokens(
            text
        )

        texts_to_check = list(
            set(
                [text]
                + normalized_tokens
            )
        )

        # -------------------------
        # HARD BLOCK
        # -------------------------

        blocked, matched = hard_block_check(
            texts_to_check,
            hard_code
        )

        if blocked:

            return Response(
                {
                    "text": text,
                    "result": "not_ok",
                    "confidence": 1.0,
                    "matched_text": matched,
                    "reason": "hard_block"
                },
                status=200
            )

        # -------------------------
        # MODEL CHECK
        # -------------------------

        is_offensive = False

        confidence = 0

        matched_text = None

        for item in texts_to_check:

            result = detector.predict(
                item
            )

            print(
                "CHECK:",
                item,
                result
            )

            current_conf = result.get(
                "confidence",
                0
            )

            if (
                result.get(
                    "is_offensive",
                    False
                )
                and current_conf
                >= CONFIDENCE_THRESHOLD
            ):

                is_offensive = True

                confidence = current_conf

                matched_text = item

                break

        # -------------------------
        # RESPONSE
        # -------------------------

        return Response(
            {
                "text": text,
                "normalized_tokens": normalized_tokens,
                "matched_text": matched_text,
                "result": (
                    "not_ok"
                    if is_offensive
                    else "ok"
                ),
                "confidence": round(
                    confidence,
                    2
                )
            }
        )

    except Exception as e:

        import traceback

        traceback.print_exc()

        return Response(
            {
                "status": "error",
                "message": str(e)
            },
            status=500
        )