"""
structured.py — Structured output. The agent must return a validated Pydantic
object, not free text. The harness forces the schema via tool-calling and retries
if the model returns incomplete data (robust even with small local models).

Example use case: extract structured fields from an incoming invoice.

    ANTHROPIC_API_KEY=... PYTHONPATH=src python examples/structured.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")

from typing import Literal, Optional

from pydantic import BaseModel, Field

from predicta_harness import Agent


class Invoice(BaseModel):
    vendor: str
    invoice_number: Optional[str] = Field(description="invoice id, or null if not present")
    amount_eur: float
    due_date: Optional[str] = Field(description="ISO date YYYY-MM-DD, or null")
    category: Literal["software", "hardware", "services", "utilities", "other"]
    payment_priority: Literal["high", "medium", "low"]


INVOICE_TEXT = """From: billing@cloudvendor.com
Subject: Invoice INV-2026-0412

Dear customer, please find your monthly invoice attached.
Invoice INV-2026-0412, amount 1,290.00 EUR for cloud compute services.
Payment is due by 2026-07-05. Thank you for your business."""

SYSTEM = (
    "You extract structured data from business documents. Today is 2026-06-21. "
    "Be precise; if a field is absent, use null."
)


def run_extract(model: str) -> None:
    agent = Agent(model=model, system=SYSTEM)
    r = agent.run(f"Extract the invoice fields:\n\n{INVOICE_TEXT}", result_schema=Invoice)
    inv: Invoice = r.data
    print(f"   type: {type(inv).__name__}")
    print(f"   vendor:   {inv.vendor}")
    print(f"   number:   {inv.invoice_number}   amount: {inv.amount_eur} EUR")
    print(f"   due_date: {inv.due_date}   category: {inv.category}   priority: {inv.payment_priority}")
    print(f"   usage: {r.usage}  ({r.steps} steps)")


if __name__ == "__main__":
    print("== Anthropic (claude-sonnet-4-6) ==")
    run_extract("anthropic/claude-sonnet-4-6")
