# Categoriser & Agent Improvements — Design Spec

**Date:** 2026-06-22  
**Status:** Implemented

---

## Goal

Two separate problems fixed in this batch:

1. **Bulk recategoriser misclassifies well-known merchants** — Edeka, Aldi, Lidl, Netto and others were landing in "Miscellaneous" because a failed or mismatched Gemini batch response caused the fallback to fire for the whole chunk.

2. **Chat agent doesn't extract merchant from "Store for item" phrasing** — typing "Aldi for pink night dress" should produce `merchant=Aldi, description=pink night dress, category=Clothing & Fashion`, not a confused parse.

---

## Fix 1 — Merchant rules in bulk categoriser (`categoriser.py`)

### Problem
`classify_expenses` sends items to Gemini in chunks of 50. If the response length doesn't match the chunk (API error, markdown fence, truncation), the entire chunk falls back to `"Miscellaneous"`. Well-known merchants like Edeka, Aldi, dm are unambiguous and should never need an AI call.

### Solution
Add `_MERCHANT_RULES: dict[str, str]` — a lowercase prefix lookup table mapping known merchant names to their category. Before sending any item to Gemini, check this table. If a match is found, assign the category directly and exclude the item from the Gemini batch.

**Matching rule:** `merchant.lower() == key` OR `merchant.lower().startswith(key + " ")` OR `merchant.lower().startswith(key + "-")`.

### Merchants added to rules
| Merchant | Category |
|----------|----------|
| edeka, aldi, lidl, netto, rewe, kaufland, penny, tegut, norma, nahkauf, hit | Groceries |
| dm, rossmann, müller / muller | Personal Care |
| apotheke | Pharmacy |
| db, deutsche bahn, flixbus, uber, bolt | Transport |
| shell, aral, esso, total | Transport |

### Important: rules apply to bulk categoriser only
These rules are **not** added to the chat agent. When an expense is added via chat, the agent uses the description to infer category (e.g. "shampoo at dm" → Personal Care, "protein at dm" → Health & Fitness). Only no-context bulk imports benefit from the merchant shortcut.

---

## Fix 2 — One-time DB reclassification

### Batch 1 (85 transactions)
Edeka, Aldi, Netto transactions in Miscellaneous → Groceries.  
These had generic `"Import: Edeka"` / `"Import: Aldi"` descriptions with no purchase context.

### Batch 2 (112 transactions)
Action, dm, Tedi, Woolworth transactions with `"Import: X"` or `"Receipt: X"` descriptions → Groceries.  
Transactions with specific descriptions (`"shaving cream"`, `"Oats gluten free"`, `"notebook"`) were left untouched — they already had correct categories or need manual review.

### Remaining Miscellaneous (9 transactions)
Amazon (4), Cash (1), Koblenz cole (1), Action decoration items (1), Muller (1), Action notebook (1). These are genuinely ambiguous and should be corrected manually via the History page inline category editor.

---

## Fix 3 — Agent prompt: "[Store] for [item]" pattern (`agent.py`)

### Problem
The agent only extracted merchants from `"at X"`, `"from X"`, `"bei X"`, `"@ X"` patterns. Typing `"Aldi for pink night dress set"` didn't produce `merchant=Aldi`.

Additionally, category inference was implicitly merchant-driven in some cases — `"pink night dress at Aldi"` could be miscategorised as Groceries because Aldi is a supermarket.

### Solution
Two prompt changes:

1. **New extraction pattern:** When a known store name appears at the start of the message followed by `"for"`, treat the store name as the merchant and everything after `"for"` as the description. Examples:
   - `"Aldi for pink night dress set"` → `merchant=Aldi, description=pink night dress set`
   - `"dm for shampoo"` → `merchant=dm, description=shampoo`

2. **Description-driven categorisation:** Explicitly instruct the agent that category is inferred from the **description** (what was bought), not the merchant (where it was bought). The merchant is just location context.

3. **Aligned category rule names:** The original prompt referenced `"Food"`, `"Bills"`, `"Shopping"`, `"Other"` which don't exist in `CATEGORIES`. Updated all examples to use the actual values: `"Food & Dining"`, `"Housing & Utilities"`, `"Clothing & Fashion"`, `"Electronics"`, `"Miscellaneous"`.

---

## Files Changed

| File | Change |
|------|--------|
| `expense_tracker_agent/categoriser.py` | Added `_MERCHANT_RULES`, `_rule_match()`, updated `classify_expenses()` |
| `expense_tracker_agent/agent.py` | Updated merchant extraction and category inference in `_build_instruction()` |
| DB (`expenses.db`) | One-time UPDATE of 197 transactions (85 + 112) to Groceries |
