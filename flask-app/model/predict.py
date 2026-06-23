"""
model/predict.py — ML plug-in contract for receipt inference.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTRACT  (DO NOT CHANGE the function signature)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  predict_receipt(file_bytes: bytes, filename: str) -> dict

  The returned dict MUST contain these string keys:

    "merchant"   — store / vendor name            e.g. "ABC Store"
    "date"       — ISO date of the receipt         e.g. "2026-06-01"
    "amount"     — total amount as a string        e.g. "500.00"
    "status"     — "Valid" | "Invalid" | "Uncertain"
    "confidence" — percentage string               e.g. "92%"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO WIRE IN A REAL MODEL  (instructions for the other intern)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1 — Drop your trained weights file here:
          flask-app/model/receipt_model.pth

Step 2 — Uncomment the PYTORCH SKELETON section below and fill in:
          a) Your model class / architecture
          b) The forward() pass
          c) The output-decoding logic at the bottom of _real_predict()

Step 3 — In predict_receipt() at the bottom of this file,
          replace  _stub_predict  with  _real_predict.

Step 4 — Add  torch  and  torchvision  to requirements.txt
          and rebuild the Docker image.

Nothing else in the app needs to change — the contract above is the
only interface between the ML code and the rest of the service.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PYTORCH SKELETON  — uncomment and fill in once the real model is ready
# ─────────────────────────────────────────────────────────────────────────────
#
# import io
# import torch
# import torch.nn as nn
# from torchvision import transforms
# from PIL import Image
#
# DEVICE     = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# MODEL_PATH = "model/receipt_model.pth"
#
#
# class ReceiptModel(nn.Module):
#     """Replace this with your actual architecture."""
#     def __init__(self):
#         super().__init__()
#         # TODO: define layers here, e.g.
#         # self.backbone = models.resnet18(weights=None)
#         # self.head     = nn.Linear(512, NUM_CLASSES)
#         pass
#
#     def forward(self, x: torch.Tensor) -> torch.Tensor:
#         # TODO: define forward pass
#         pass
#
#
# def _load_model() -> ReceiptModel:
#     """Load weights once when the module is first imported."""
#     model = ReceiptModel().to(DEVICE)
#     state = torch.load(MODEL_PATH, map_location=DEVICE)
#     model.load_state_dict(state)
#     model.eval()
#     logger.info("Model loaded from %s on %s", MODEL_PATH, DEVICE)
#     return model
#
#
# # Module-level singleton — loaded once, reused for every request
# _model = _load_model()
#
# _transform = transforms.Compose([
#     transforms.Resize((224, 224)),
#     transforms.ToTensor(),
#     transforms.Normalize(mean=[0.485, 0.456, 0.406],
#                          std=[0.229, 0.224, 0.225]),
# ])
#
#
# def _real_predict(file_bytes: bytes, filename: str) -> dict:
#     """Run actual inference on the uploaded file."""
#     image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
#     tensor = _transform(image).unsqueeze(0).to(DEVICE)  # shape: (1, 3, 224, 224)
#
#     with torch.no_grad():
#         output = _model(tensor)   # shape depends on your architecture
#
#     # TODO: decode 'output' into the fields below
#     # Example (classification head):
#     #   probs      = torch.softmax(output, dim=1)
#     #   confidence = f"{probs.max().item() * 100:.0f}%"
#     #   label_idx  = probs.argmax().item()
#     #   status     = ["Valid", "Invalid", "Uncertain"][label_idx]
#
#     return {
#         "merchant":   "Decoded Merchant",   # TODO: replace with OCR / NER output
#         "date":       "2026-01-01",          # TODO: replace with extracted date
#         "amount":     "0.00",                # TODO: replace with extracted amount
#         "status":     "Valid",               # TODO: replace with model prediction
#         "confidence": "95%",                 # TODO: replace with model confidence
#     }
#
# ─────────────────────────────────────────────────────────────────────────────


def _stub_predict(file_bytes: bytes, filename: str) -> dict:
    """
    Stub — returns hardcoded values that match the expected response format.
    This is the fallback until the real model is wired in.

    DO NOT change the shape of the returned dict.
    """
    logger.info("[STUB] predict_receipt called — filename=%s  size=%d bytes",
                filename, len(file_bytes))
    return {
        "merchant":   "ABC Store",
        "date":       "2026-06-01",
        "amount":     "500.00",
        "status":     "Valid",
        "confidence": "92%",
    }


# ─── Public entry point ───────────────────────────────────────────────────────

def predict_receipt(file_bytes: bytes, filename: str) -> dict:
    """
    Called by services/receipt_service.py for both /extract and /validate.

    When the real model is ready:
      1. Uncomment the PyTorch skeleton above.
      2. Replace  _stub_predict  with  _real_predict  on the line below.
    """
    return _stub_predict(file_bytes, filename)
    # return _real_predict(file_bytes, filename)   # ← swap in when model is ready