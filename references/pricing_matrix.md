# Ground-Truth Calibrated Pricing Matrix & Invoicing Waterfall

This reference documents the exact pricing rates, regional SKU factors, and invoice waterfall formulas calibrated against production Google Cloud Billing for Vertex AI in Google Antigravity.

---

## 1. Calibrated Model Rates (Per 1 Million Tokens)

| Model | Category | Uncached Input | Cached Input (75% off) | Output | Cost Multiplier |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Gemini 3.8 Flash** | Fast / High Velocity | **\$0.10** | **\$0.025** | **\$0.40** | **1.0x (Baseline)** |
| **Gemini 4 Argon** | Frontier / Deep Reasoning | **\$1.25** | **\$0.3125** | **\$5.00** | **12.5x** |
| **Claude Opus 5.5** | Frontier Reasoning | **\$1.25** | **\$0.3125** | **\$5.00** | **12.5x** |
| **Claude Sonnet 5.5** | High Capability | **\$0.80** | **\$0.2000** | **\$3.20** | **8.0x** |

---

## 2. Production Google Cloud Invoice Reconciliation

As verified from Google Cloud Console billing records (`Billing Account: 01250A-7FE9F3-E92F1F`, `Project: gdg-workshop-512510`):

```text
Google Cloud Console Invoicing Waterfall:
├─ Gross List Usage     : $2.05 (Uncached base rates + regional asia-southeast1 SKUs)
├─ Spending Discount    : -$1.02 (-49.9% Context Caching savings)
├─ Promotional Credit   : -$1.02 (Deducted from $5.00 GDP Codelab Credit)
└─ Remaining Balance    : $3.98 (79.6% remaining — Exactly matches Console)
```

---

## 3. Key Operational Rules

1. **Isolation of Vertex AI Steps:**
   Steps executed under personal accounts (`API_PROVIDER_GOOGLE_GEMINI`) are completely ignored when tallying workshop credit consumption. Only `API_PROVIDER_GOOGLE_VERTEX` steps count against the \$5.00 credit grant.
2. **Context Caching Mechanics:**
   Antigravity automatically utilizes prompt caching for conversational histories and repository context, cutting costs by ~50% across extended agent sessions.
3. **12-Hour Destruction Window:**
   The promotional credit is granted via a temporary Codelab billing account. Exactly 12 hours from the claim timestamp, Google Cloud marks the credit `🔴 Expired` and unspent balances are destroyed.
