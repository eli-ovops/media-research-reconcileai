# Three-minute demo script

1. **Problem (20 seconds):** “Accounts-payable reviewers compare the same values across visually different documents. A plausible extraction is insufficient; they need the source and deterministic controls.”
2. **Upload (20 seconds):** Choose an invoice with ten units at ₹550 and its purchase order with ten units at ₹500.
3. **Processing (25 seconds):** Explain that Docling builds local text and geometry while Gemini produces the typed extraction. The model does not decide whether the documents match.
4. **Finding (35 seconds):** Open the ₹500 overcharge card. Show expected/actual values and click the card to highlight the supporting row in the invoice. Switch to the purchase-order evidence.
5. **Review (35 seconds):** Open “Review JSON,” correct a deliberately blurred or misread field, save, and show all controls rerun with an audit entry.
6. **Evaluation (30 seconds):** Show the held-out report and describe precision, recall, review rate, latency, cost, and one failure example. Do not cite a metric until that report exists.
7. **Engineering close (15 seconds):** Show the API, SQLite persistence, deterministic test run, and spend guard.

Resume bullet after running the held-out benchmark:

> Built an evidence-backed invoice reconciliation system with Gemini, Docling, FastAPI, and deterministic financial controls; achieved **[held-out discrepancy F1]** over **30 held-out document pairs**, with page-level provenance, human review, and measured inference cost.
