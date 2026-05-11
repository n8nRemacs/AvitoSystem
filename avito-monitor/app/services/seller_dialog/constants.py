"""Hardcoded strings + enums for the seller dialog flow."""

GREETING_TEMPLATE = "Здравствуйте! Меня заинтересовал ваш аппарат. Ещё продаётся?"

# Stage names — keep in sync with the CHECK constraint in migration 0013.
STAGE_CONTACT = "contact"
STAGE_QUESTIONS_SETUP = "questions_setup"
STAGE_QUESTIONS = "questions"
STAGE_PRICE_NEGOTIATION = "price_negotiation"
STAGE_PRICE_CHANGED = "price_changed"
STAGE_PURCHASED = "purchased"
STAGE_SHIPPED = "shipped"
STAGE_RECEIVED = "received"
STAGE_CLOSED = "closed"
STAGE_REJECTED = "rejected"

CLOSED_REASON_SILENT = "silent"
CLOSED_REASON_REFUSED = "refused"
CLOSED_REASON_MANUAL = "manual"

OPENING_LINE = (
    "У меня есть несколько вопросов по Вашему аппарату, "
    "ответьте пожалуйста, если Вас это не затруднит."
)

# Recap status enum values for seller_dialogs.recap_status
RECAP_PENDING_ANSWER = "pending_answer"
RECAP_CONFIRMED = "confirmed"
RECAP_DISPUTED = "disputed"
