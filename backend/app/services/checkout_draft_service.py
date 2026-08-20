from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import session_service

STEPS = ["name", "phone", "email", "fulfillment", "address", "flat_number", "address_confirm", "location", "payment"]


@dataclass
class CheckoutDraft:
    name: str | None = None
    phone: str | None = None
    fulfillment: str | None = None
    address: str | None = None
    address_lat: float | None = None
    address_lon: float | None = None
    # "reuse" (saved profile address) or "autocomplete" (frontend Nominatim
    # suggestion, lat/lon trusted directly) - the ONLY two ways an address can
    # be set at all now that free-text address submission is disabled (see
    # ai_service._handle_checkout_flow's "address" step) - purely diagnostic,
    # not branched on.
    address_source: str | None = None
    address_reuse_offered: bool = False
    address_reuse_declined: bool = False
    address_confirmed: bool = False
    # Retained for schema/staff-tooling stability, but a free-text/unverified
    # address can no longer be submitted at all, so this always stays False.
    delivery_unverified: bool = False
    flat_number: str | None = None
    flat_number_skipped: bool = False
    location: str | None = None
    email: str | None = None
    is_birthday: bool | None = None
    last_prompted_step: str | None = None

    def next_step(self) -> str:
        if self.name is None:
            return "name"
        if self.phone is None:
            return "phone"
        if self.email is None:
            return "email"
        if self.fulfillment is None:
            return "fulfillment"
        if self.fulfillment == "delivery":
            if self.address is None:
                return "address"
            if self.flat_number is None and not self.flat_number_skipped:
                return "flat_number"
            if not self.address_confirmed:
                return "address_confirm"
        # Pickup has no address to geocode, so the customer picks a branch
        # directly instead - delivery's "location" is derived automatically
        # from the address (nearest branch), never asked for separately.
        if self.fulfillment == "pickup" and self.location is None:
            return "location"
        return "payment"


def _to_dict(draft: CheckoutDraft) -> dict:
    return {
        "name": draft.name,
        "phone": draft.phone,
        "fulfillment": draft.fulfillment,
        "address": draft.address,
        "address_lat": draft.address_lat,
        "address_lon": draft.address_lon,
        "address_source": draft.address_source,
        "address_reuse_offered": draft.address_reuse_offered,
        "address_reuse_declined": draft.address_reuse_declined,
        "address_confirmed": draft.address_confirmed,
        "delivery_unverified": draft.delivery_unverified,
        "flat_number": draft.flat_number,
        "flat_number_skipped": draft.flat_number_skipped,
        "location": draft.location,
        "email": draft.email,
        "is_birthday": draft.is_birthday,
        "last_prompted_step": draft.last_prompted_step,
    }


def _from_dict(data: dict) -> CheckoutDraft:
    return CheckoutDraft(
        name=data.get("name"),
        phone=data.get("phone"),
        fulfillment=data.get("fulfillment"),
        address=data.get("address"),
        address_lat=data.get("address_lat"),
        address_lon=data.get("address_lon"),
        address_source=data.get("address_source"),
        address_reuse_offered=data.get("address_reuse_offered", False),
        address_reuse_declined=data.get("address_reuse_declined", False),
        address_confirmed=data.get("address_confirmed", False),
        delivery_unverified=data.get("delivery_unverified", False),
        flat_number=data.get("flat_number"),
        flat_number_skipped=data.get("flat_number_skipped", False),
        location=data.get("location"),
        email=data.get("email"),
        is_birthday=data.get("is_birthday"),
        last_prompted_step=data.get("last_prompted_step"),
    )


_drafts: dict[str, CheckoutDraft] = {}


async def get_draft(db: AsyncSession, session_id: str) -> CheckoutDraft | None:
    if session_id in _drafts:
        return _drafts[session_id]
    state = await session_service.get_state(db, session_id)
    if state.get("checkout_draft"):
        draft = _from_dict(state["checkout_draft"])
        _drafts[session_id] = draft
        return draft
    return None


async def get_or_create_draft(db: AsyncSession, session_id: str) -> CheckoutDraft:
    draft = await get_draft(db, session_id)
    if draft is None:
        draft = CheckoutDraft()
        _drafts[session_id] = draft
    return draft


async def sync_draft(db: AsyncSession, session_id: str) -> None:
    draft = _drafts.get(session_id)
    await session_service.update_state(
        db, session_id, checkout_draft=_to_dict(draft) if draft is not None else None
    )


def clear_draft(session_id: str) -> None:
    _drafts.pop(session_id, None)


def clear() -> None:
    _drafts.clear()
