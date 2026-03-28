from enum import StrEnum


class InteractionType(StrEnum):
    VIEW = "view"
    PURCHASE = "purchase"


class CooccurrenceType(StrEnum):
    CO_VIEW = "co_view"
    CO_PURCHASE = "co_purchase"

