"""
Sentiment analysis worker using nlptown/bert-base-multilingual-uncased-sentiment.

This script runs under Python 3.13 (with PyTorch + Transformers support).
It is invoked as a subprocess by wordcloud_engine.py which runs on Python 3.14.

Protocol:
  - Reads JSON from stdin: {"texts": ["sentence1", "sentence2", ...]}
  - Writes JSON to stdout: {"results": [{"label": "positive", "stars": 4, "confidence": 0.62}, ...]}

Star mapping:
  1-2 stars → "negative"
  3 stars   → "neutral"
  4-5 stars → "positive"
"""

import json
import sys
import os

# Suppress warnings from huggingface_hub
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def main():
    # Read input from stdin
    raw = sys.stdin.buffer.read()
    request = json.loads(raw.decode("utf-8"))
    texts = request.get("texts", [])

    if not texts:
        json.dump({"results": []}, sys.stdout)
        return

    # Import heavy libs only after reading input (fail fast if no texts)
    from transformers import pipeline  # noqa: E402

    # Load model (cached after first download)
    classifier = pipeline(
        "text-classification",
        model="nlptown/bert-base-multilingual-uncased-sentiment",
        device=-1,  # CPU
        truncation=True,
        max_length=512,
    )

    # Process in batches for efficiency
    batch_size = 32
    all_results = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        # Filter out empty strings — model can't handle them
        non_empty = [(j, t) for j, t in enumerate(batch) if t.strip()]

        batch_results = [None] * len(batch)

        if non_empty:
            indices, valid_texts = zip(*non_empty)
            preds = classifier(list(valid_texts), batch_size=batch_size)
            for idx, pred in zip(indices, preds):
                stars = int(pred["label"].split(" ")[0])
                if stars <= 2:
                    label = "negative"
                elif stars >= 4:
                    label = "positive"
                else:
                    label = "neutral"
                batch_results[idx] = {
                    "label": label,
                    "stars": stars,
                    "confidence": round(pred["score"], 3),
                }

        # Fill in empties
        for j in range(len(batch)):
            if batch_results[j] is None:
                batch_results[j] = {
                    "label": "neutral",
                    "stars": 3,
                    "confidence": 0.0,
                }

        all_results.extend(batch_results)

    json.dump({"results": all_results}, sys.stdout)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
