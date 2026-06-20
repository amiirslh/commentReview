import os
from .swear_detector import PersianSwearDetector

# ✅ Global model
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'models', 'model.pkl')


class SwearDetectorService:
    """Service layer for swear detection"""

    def __init__(self):
        self.detector = None
        self._load_model()

    def _load_model(self):
        """Load model"""
        try:
            if os.path.exists(MODEL_PATH):
                self.detector = PersianSwearDetector(model_path=MODEL_PATH)
                print(f"✅ Model loaded from {MODEL_PATH}")
            else:
                print(f"⚠️ Model not found at {MODEL_PATH}")
                self.detector = PersianSwearDetector()
        except Exception as e:
            print(f"❌ Error loading model: {str(e)}")
            self.detector = PersianSwearDetector()

    def predict(self, text):
        """
        Predict if text contains swear words

        Returns:
        {
            "text": "original text",
            "processed_text": "normalized text",
            "rule_based_detection": True/False,
            "ml_detection": True/False,
            "ml_confidence": 0.0-1.0,
            "final_prediction": True/False,
            "confidence": 0.0-1.0,
            "used_ml_prediction": True/False
        }
        """
        try:
            if not text or not isinstance(text, str):
                return {
                    "text": str(text),
                    "processed_text": "",
                    "rule_based_detection": False,
                    "ml_detection": False,
                    "ml_confidence": 0.0,
                    "final_prediction": False,
                    "confidence": 0.0,
                    "used_ml_prediction": False
                }

            text = text.strip()

            # ✅ 1. Rule-based detection (بر اساس swear_words)
            rule_based_result = self._rule_based_detect(text)

            # ✅ 2. ML-based detection
            ml_result = self._ml_detect(text)

            # ✅ 3. Final prediction (ترکیبی)
            final_prediction = rule_based_result['detected'] or ml_result['detected']

            # ✅ Confidence (اگر یکی True بود، confidence بیشتر است)
            if rule_based_result['detected']:
                confidence = 0.95  # Rule-based confidence
            else:
                confidence = ml_result['confidence']

            return {
                "text": text,
                "processed_text": self.detector.preprocess_text(text) if self.detector else text,

                # Rule-based
                "rule_based_detection": rule_based_result['detected'],
                "swear_words_found": rule_based_result['swear_words'],

                # ML-based
                "ml_detection": ml_result['detected'],
                "ml_confidence": ml_result['confidence'],

                # Final
                "final_prediction": final_prediction,
                "confidence": confidence,
                "used_ml_prediction": not rule_based_result['detected'] and ml_result['detected']
            }

        except Exception as e:
            print(f"❌ Error in predict: {str(e)}")
            return {
                "text": text,
                "processed_text": "",
                "rule_based_detection": False,
                "ml_detection": False,
                "ml_confidence": 0.0,
                "final_prediction": False,
                "confidence": 0.0,
                "used_ml_prediction": False,
                "error": str(e)
            }

    def _rule_based_detect(self, text):
        """Rule-based detection using swear_words"""
        try:
            if not self.detector or not self.detector.swear_words:
                return {
                    "detected": False,
                    "swear_words": []
                }

            found_words = []
            text_lower = text.lower()

            for swear_word in self.detector.swear_words:
                if swear_word.lower() in text_lower:
                    found_words.append(swear_word)

            return {
                "detected": len(found_words) > 0,
                "swear_words": found_words
            }

        except Exception as e:
            print(f"❌ Error in rule-based detection: {str(e)}")
            return {
                "detected": False,
                "swear_words": []
            }

    def _ml_detect(self, text):
        """ML-based detection using trained model"""
        try:
            if not self.detector or not self.detector.is_trained:
                return {
                    "detected": False,
                    "confidence": 0.0
                }

            result = self.detector.predict(text)

            return {
                "detected": result.get('is_offensive', False),
                "confidence": result.get('confidence', 0.0)
            }

        except Exception as e:
            print(f"❌ Error in ML detection: {str(e)}")
            return {
                "detected": False,
                "confidence": 0.0
            }

    def predict_batch(self, texts):
        """Predict batch of texts"""
        try:
            return [self.predict(text) for text in texts]
        except Exception as e:
            print(f"❌ Error in batch predict: {str(e)}")
            return []


# ✅ Global instance
model = SwearDetectorService()