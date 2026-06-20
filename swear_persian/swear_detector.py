import cloudpickle as pickle  # ✅ cloudpickle استفاده کن
import json
import os
from hazm import Normalizer, WordTokenizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline


class PersianSwearDetector:
    """Persian Swear Words Detector using SVM"""

    def __init__(self, model_path=None):
        """Initialize the detector"""
        self.swear_words = set()
        self.is_trained = False
        self.normalizer = Normalizer()
        self.tokenizer = WordTokenizer()

        # ✅ Pipeline with TF-IDF and SVM
        self.pipeline = Pipeline([
            ('vectorizer', TfidfVectorizer(
                ngram_range=(1, 3),
                max_features=10000,
                strip_accents='unicode',
                analyzer='char_wb',
                min_df=2,
                max_df=0.9,
                preprocessor=self.preprocess_text,
                sublinear_tf=True
            )),
            ('classifier', SVC(
                kernel='linear',
                probability=False,
                class_weight='balanced',
                C=1.0,
                max_iter=2000
            ))
        ])

        if model_path and os.path.exists(model_path):
            self.load_model(model_path)

    def preprocess_text(self, text):
        """Preprocess Persian text"""
        try:
            # ✅ Normalize
            normalized = self.normalizer.normalize(text)
            # ✅ Tokenize
            tokens = self.tokenizer.tokenize(normalized)
            # ✅ Join tokens
            return ' '.join(tokens)
        except:
            return text

    def extract_swear_words_from_dataset(self, dataset_path):
        """Extract swear words from dataset"""
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.swear_words = set()

            for item in data:
                if item.get('label') == 'Offensive':
                    text = item.get('text', '').strip()
                    if text:
                        self.swear_words.add(text)

            print(f"✅ Extracted {len(self.swear_words)} swear words")

        except Exception as e:
            print(f"❌ Error extracting swear words: {str(e)}")
            raise

    def train_model(self, dataset_path):
        """Train the model from dataset"""
        try:
            print("🔄 Loading dataset...")

            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # ✅ Extract swear words
            self.extract_swear_words_from_dataset(dataset_path)

            # ✅ Prepare data
            texts = [item['text'] for item in data]
            labels = [1 if item['label'] == 'Offensive' else 0 for item in data]

            print(f"🔄 Training on {len(texts)} samples...")
            print(f"   - Offensive: {sum(labels)}")
            print(f"   - Neutral: {len(labels) - sum(labels)}")
            print(f"   ⏳ This may take a few minutes...")

            # ✅ Train
            self.pipeline.fit(texts, labels)
            self.is_trained = True

            print("✅ Model trained successfully!")

        except Exception as e:
            print(f"❌ Error training model: {str(e)}")
            raise

    def save_model(self, model_path):
        """Save the trained model to file"""
        try:
            os.makedirs(os.path.dirname(model_path) or '.', exist_ok=True)

            model_data = {
                'pipeline': self.pipeline,
                'swear_words': self.swear_words,
                'is_trained': self.is_trained
            }

            # ✅ cloudpickle استفاده کن
            with open(model_path, 'wb') as f:
                pickle.dump(model_data, f)

            file_size = os.path.getsize(model_path)
            print(f"✅ Model saved to {model_path}")
            print(f"   - Size: {file_size / 1024 / 1024:.2f} MB")
            print(f"   - Swear words: {len(self.swear_words)}")
            print(f"   - Is trained: {self.is_trained}")

        except Exception as e:
            print(f"❌ Error saving model: {str(e)}")
            raise

    def load_model(self, model_path):
        """Load a trained model from file"""
        try:
            # ✅ cloudpickle.load
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)

            if isinstance(model_data, dict):
                self.pipeline = model_data['pipeline']
                self.swear_words = model_data['swear_words']
                self.is_trained = model_data['is_trained']
            else:
                self.pipeline = model_data
                self.is_trained = True

            print(f"✅ Model loaded from {model_path}")
            print(f"   - Swear words: {len(self.swear_words)}")
            print(f"   - Is trained: {self.is_trained}")

        except Exception as e:
            print(f"❌ Error loading model: {str(e)}")
            raise

    def predict(self, text):
        """Predict if text is offensive"""
        try:
            if not self.is_trained:
                return {
                    'text': text,
                    'is_offensive': False,
                    'confidence': 0.0,
                    'error': 'Model is not trained'
                }

            # ✅ Preprocess
            preprocessed = self.preprocess_text(text)

            # ✅ Predict
            prediction = self.pipeline.predict([preprocessed])[0]
            probabilities = self.pipeline.decision_function([preprocessed])[0]

            # ✅ Convert to confidence
            confidence = abs(probabilities)

            return {
                'text': text,
                'is_offensive': bool(prediction),
                'confidence': float(confidence),
                'swear_words_found': [word for word in self.swear_words
                                      if word in text]
            }

        except Exception as e:
            return {
                'text': text,
                'is_offensive': False,
                'confidence': 0.0,
                'error': str(e)
            }

    def predict_batch(self, texts):
        """Predict batch of texts"""
        try:
            if not self.is_trained:
                return [
                    {
                        'text': text,
                        'is_offensive': False,
                        'confidence': 0.0,
                        'error': 'Model is not trained'
                    }
                    for text in texts
                ]

            # ✅ Preprocess all
            preprocessed = [self.preprocess_text(text) for text in texts]

            # ✅ Predict
            predictions = self.pipeline.predict(preprocessed)
            probabilities = self.pipeline.decision_function(preprocessed)

            results = []
            for text, pred, prob in zip(texts, predictions, probabilities):
                results.append({
                    'text': text,
                    'is_offensive': bool(pred),
                    'confidence': float(abs(prob)),
                    'swear_words_found': [word for word in self.swear_words
                                          if word in text]
                })

            return results

        except Exception as e:
            print(f"❌ Error in batch prediction: {str(e)}")
            raise