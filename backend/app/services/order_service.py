import difflib
import re

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import COUPONS, TAX_RATE
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.prompts.menu_translations import translated_name_and_description
from app.prompts.templates import t
from app.services import menu_cache_service

FUZZY_MATCH_CUTOFF = 0.5
# Stricter than FUZZY_MATCH_CUTOFF - only used for deciding whether to
# AUTO-ADD a single fuzzy match without asking. A vague category term like
# "cold drink" scores ~0.63 against "Cold Brew" (enough to surface as a
# "did you mean...?" suggestion at the looser cutoff above) but must never
# be confident enough to silently add it - only a genuine near-exact typo
# (e.g. "masala chay" -> "Masala Chai", ~0.91) should clear this bar.
AUTO_MATCH_FUZZY_CUTOFF = 0.72

_UPSELL_DESSERT_CATEGORY = "Bakery"
_UPSELL_SNACK_CATEGORY = "Snacks"


class OrderError(Exception):
    pass


async def get_active_draft_order(db: AsyncSession, session_id: str) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.session_id == session_id, Order.status == "draft")
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_draft_order(db: AsyncSession, session_id: str, user_id: int | None = None) -> Order:
    order = Order(session_id=session_id, user_id=user_id, status="draft")
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def get_or_create_draft_order(db: AsyncSession, session_id: str, user_id: int | None = None) -> Order:
    order = await get_active_draft_order(db, session_id)
    if order is not None:
        return order
    return await create_draft_order(db, session_id, user_id)


async def get_last_order_for_session(db: AsyncSession, session_id: str) -> Order | None:
    stmt = select(Order).where(Order.session_id == session_id).order_by(Order.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalars().first()


def _normalize(text: str) -> str:
    """Collapses repeated/leading/trailing whitespace and lowercases, so stray
    double spaces or mixed casing in user input never falsely register as an
    unmatched/compound item name."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _match_or_ambiguous(
    items: list[MenuItem], item_name: str, fuzzy_cutoff: float = FUZZY_MATCH_CUTOFF
) -> tuple[MenuItem | None, list[MenuItem]]:
    """Resolves item_name against items. Returns (match, []) for a confident single
    match, or (None, candidates) when multiple menu items match ambiguously and the
    caller should ask the customer to disambiguate rather than guess.

    fuzzy_cutoff defaults to the looser FUZZY_MATCH_CUTOFF (used for
    remove/modify, where item_name refers to something already known to be
    in the customer's own small cart) - resolve_add_entry passes the
    stricter AUTO_MATCH_FUZZY_CUTOFF instead, since adding is where a vague
    category term (e.g. "cold drink") must never get silently auto-matched
    to a specific item just because it's the closest string."""
    if not items:
        return None, []

    needle = _normalize(item_name)
    if not needle:
        return None, []

    for item in items:
        if _normalize(item.name) == needle:
            return item, []

    substring_matches = [item for item in items if needle in _normalize(item.name) or _normalize(item.name) in needle]
    if len(substring_matches) == 1:
        return substring_matches[0], []
    if len(substring_matches) > 1:
        return None, substring_matches

    names = [_normalize(item.name) for item in items]
    close = difflib.get_close_matches(needle, names, n=1, cutoff=fuzzy_cutoff)
    if not close:
        return None, []
    return next(item for item in items if _normalize(item.name) == close[0]), []


def _best_match(items: list[MenuItem], item_name: str) -> MenuItem | None:
    match, _ = _match_or_ambiguous(items, item_name)
    return match


def _split_candidates(items: list[MenuItem], item_name: str) -> list[MenuItem] | None:
    """If item_name looks like two real menu items typed together with just a
    space (e.g. "samosa pav" meaning Samosa + Vada Pav - not itself a menu
    item), try every whitespace split point and see if exactly one split
    cleanly resolves both halves to distinct real items. Returns the two
    items in order, or None if there's no such unambiguous split."""
    words = _normalize(item_name).split(" ")
    if len(words) < 2:
        return None

    resolved_splits: list[tuple[MenuItem, MenuItem]] = []
    for i in range(1, len(words)):
        left = " ".join(words[:i])
        right = " ".join(words[i:])
        left_match, left_ambiguous = _match_or_ambiguous(items, left)
        right_match, right_ambiguous = _match_or_ambiguous(items, right)
        if left_match and right_match and left_match.id != right_match.id:
            resolved_splits.append((left_match, right_match))

    if len(resolved_splits) == 1:
        return list(resolved_splits[0])
    return None


_MAX_SUGGESTION_WORDS = 4


def _close_suggestions(items: list[MenuItem], item_name: str, limit: int = 3) -> list[MenuItem]:
    needle = _normalize(item_name)
    if not needle:
        return []
    if len(needle.split(" ")) > _MAX_SUGGESTION_WORDS:
        # A long, sentence-like phrase (e.g. an image description that
        # leaked into an order_action.item_name from conversation context,
        # like "vegetable stir-fried noodles with tofu") isn't a plausible
        # menu item name to begin with - fuzzy-matching it character-by-
        # character against short item names produces coincidental,
        # meaningless "close" matches (see FUZZY_MATCH_CUTOFF's own tighter
        # 0.5 cutoff for the same reason). Better to offer no suggestions at
        # all than a garbled, unrelated one.
        return []
    names = [_normalize(item.name) for item in items]
    close = difflib.get_close_matches(needle, names, n=limit, cutoff=FUZZY_MATCH_CUTOFF)
    return [item for name in close for item in items if _normalize(item.name) == name]


async def resolve_add_entry(db: AsyncSession, item_name: str) -> dict:
    """Resolves a single "add" entry's item_name to one of:
    - {"type": "match", "item": MenuItem} - a confident single match.
    - {"type": "ambiguous", "candidates": [...]} - multiple real items could
      be meant (e.g. "chai" matching several chai variants) - ask the
      customer to pick one, never guess.
    - {"type": "split", "items": [MenuItem, MenuItem]} - item_name isn't
      itself a real item, but is unambiguously two real items typed together
      with a space (e.g. "samosa pav") - the caller should ask the customer
      to confirm which one(s) they meant, never silently add both.
    - {"type": "not_found", "suggestions": [...]} - no confident match or
      split; suggestions (possibly empty) are close menu items to offer for
      clarification instead of a flat rejection.
    """
    items = await menu_cache_service.get_available_items(db)
    needle = _normalize(item_name)

    # An exact full-string match always wins outright, before anything else
    # is considered.
    for item in items:
        if _normalize(item.name) == needle:
            return {"type": "match", "item": item}

    # Prefer an unambiguous two-item split over a partial substring/fuzzy
    # guess on the whole string - e.g. "samosa pav" isn't itself a menu item,
    # but a loose substring match would otherwise silently resolve it to just
    # "Samosa" (since "samosa" is a substring of "samosa pav") and drop the
    # "pav" half entirely. Checking for a clean split first catches that.
    split = _split_candidates(items, item_name)
    if split is not None:
        return {"type": "split", "items": split}

    match, ambiguous = _match_or_ambiguous(items, item_name, fuzzy_cutoff=AUTO_MATCH_FUZZY_CUTOFF)
    if match is not None:
        return {"type": "match", "item": match}
    if ambiguous:
        return {"type": "ambiguous", "candidates": ambiguous}

    return {"type": "not_found", "suggestions": _close_suggestions(items, item_name)}


async def resolve_menu_item(db: AsyncSession, item_name: str) -> MenuItem | None:
    items = await menu_cache_service.get_available_items(db)
    return _best_match(items, item_name)


async def resolve_menu_item_with_ambiguity(db: AsyncSession, item_name: str) -> tuple[MenuItem | None, list[MenuItem]]:
    items = await menu_cache_service.get_available_items(db)
    return _match_or_ambiguous(items, item_name)


async def resolve_order_line_item(db: AsyncSession, order_id: int, item_name: str) -> MenuItem | None:
    stmt = (
        select(MenuItem)
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .where(OrderItem.order_id == order_id)
    )
    result = await db.execute(stmt)
    return _best_match(list(result.scalars().all()), item_name)


async def add_item(db: AsyncSession, order_id: int, menu_item_id: int, quantity: int = 1) -> OrderItem:
    if quantity <= 0:
        raise OrderError("Quantity must be positive.")

    menu_item = await db.get(MenuItem, menu_item_id)
    if menu_item is None or not menu_item.available:
        raise OrderError("That item isn't available right now.")

    stmt = select(OrderItem).where(OrderItem.order_id == order_id, OrderItem.menu_item_id == menu_item_id)
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing is not None:
        existing.quantity += quantity
        order_item = existing
    else:
        order_item = OrderItem(
            order_id=order_id,
            menu_item_id=menu_item_id,
            quantity=quantity,
            price_at_order=menu_item.price,
        )
        db.add(order_item)

    await db.commit()
    await db.refresh(order_item)
    return order_item


async def remove_item(db: AsyncSession, order_id: int, menu_item_id: int) -> bool:
    stmt = select(OrderItem).where(OrderItem.order_id == order_id, OrderItem.menu_item_id == menu_item_id)
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing is None:
        return False

    await db.delete(existing)
    await db.commit()
    return True


async def clear_cart(db: AsyncSession, order_id: int) -> int:
    """Empties the draft order's cart entirely (all order_items), keeping the
    order shell itself so the session's draft order id stays stable - the
    next "add" just refills this same draft rather than creating a new one.
    Also resets any coupon applied against the now-gone items so a stale
    discount doesn't linger on an empty cart."""
    result = await db.execute(delete(OrderItem).where(OrderItem.order_id == order_id))

    order = await db.get(Order, order_id)
    if order is not None:
        order.coupon_code = None
        order.discount_amount = 0

    await db.commit()
    return result.rowcount or 0


async def update_quantity(db: AsyncSession, order_id: int, menu_item_id: int, new_quantity: int) -> OrderItem | None:
    if new_quantity <= 0:
        await remove_item(db, order_id, menu_item_id)
        return None

    stmt = select(OrderItem).where(OrderItem.order_id == order_id, OrderItem.menu_item_id == menu_item_id)
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing is None:
        raise OrderError("That item isn't in the order yet.")

    existing.quantity = new_quantity
    await db.commit()
    await db.refresh(existing)
    return existing


async def calculate_totals(db: AsyncSession, order_id: int) -> dict:
    stmt = select(OrderItem).where(OrderItem.order_id == order_id)
    result = await db.execute(stmt)
    order_items = list(result.scalars().all())

    subtotal = round(sum(float(item.price_at_order) * item.quantity for item in order_items), 2)

    order = await db.get(Order, order_id)
    discount = round(float(order.discount_amount), 2) if order is not None and order.discount_amount else 0.0
    discounted_subtotal = max(subtotal - discount, 0.0)
    tax = round(discounted_subtotal * TAX_RATE, 2)
    total = round(discounted_subtotal + tax, 2)

    if order is not None:
        order.tax_amount = tax
        order.total_amount = total
        await db.commit()

    return {
        "subtotal": subtotal,
        "discount": discount,
        "coupon_code": order.coupon_code if order is not None else None,
        "tax": tax,
        "total": total,
    }


def pick_best_coupon(subtotal: float, is_first_order: bool) -> dict | None:
    best: dict | None = None
    for coupon in COUPONS:
        if subtotal < coupon["min_order"]:
            continue
        if coupon.get("first_order_only") and not is_first_order:
            continue
        raw_discount = (
            subtotal * coupon["value"] / 100 if coupon["discount_type"] == "percent" else coupon["value"]
        )
        discount = round(min(raw_discount, subtotal), 2)
        if best is None or discount > best["discount"]:
            best = {"code": coupon["code"], "discount": discount}
    return best


async def has_prior_confirmed_order(db: AsyncSession, phone: str, exclude_order_id: int | None = None) -> bool:
    stmt = select(Order.id).where(Order.guest_phone == phone, Order.status == "confirmed")
    if exclude_order_id is not None:
        stmt = stmt.where(Order.id != exclude_order_id)
    result = await db.execute(stmt.limit(1))
    return result.scalars().first() is not None


async def apply_best_coupon(db: AsyncSession, order_id: int, is_first_order: bool) -> dict:
    stmt = select(OrderItem).where(OrderItem.order_id == order_id)
    result = await db.execute(stmt)
    order_items = list(result.scalars().all())
    subtotal = round(sum(float(item.price_at_order) * item.quantity for item in order_items), 2)

    best = pick_best_coupon(subtotal, is_first_order)

    order = await db.get(Order, order_id)
    if order is not None:
        order.coupon_code = best["code"] if best else None
        order.discount_amount = best["discount"] if best else 0
        await db.commit()

    await calculate_totals(db, order_id)
    return best or {"code": None, "discount": 0.0}


async def apply_best_coupon_preview(db: AsyncSession, order_id: int, phone: str | None) -> dict:
    """Applies the best-available coupon to a still-draft order so it can be shown
    to the customer in the pre-payment bill, instead of only surfacing after payment."""
    is_first_order = False
    if phone:
        is_first_order = not await has_prior_confirmed_order(db, phone, exclude_order_id=order_id)
    return await apply_best_coupon(db, order_id, is_first_order)


async def pick_upsell_item(db: AsyncSession, order_id: int) -> MenuItem | None:
    stmt = (
        select(MenuItem.category, MenuItem.id)
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .where(OrderItem.order_id == order_id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    cart_categories = {category for category, _ in rows}
    cart_item_ids = {item_id for _, item_id in rows}

    if _UPSELL_DESSERT_CATEGORY not in cart_categories:
        missing_category = _UPSELL_DESSERT_CATEGORY
    elif _UPSELL_SNACK_CATEGORY not in cart_categories:
        missing_category = _UPSELL_SNACK_CATEGORY
    else:
        return None

    stmt2 = (
        select(MenuItem)
        .where(MenuItem.category == missing_category, MenuItem.available.is_(True))
        .order_by(MenuItem.id)
    )
    result2 = await db.execute(stmt2)
    candidates = [item for item in result2.scalars().all() if item.id not in cart_item_ids]
    return candidates[0] if candidates else None


async def get_order_summary(db: AsyncSession, order_id: int) -> dict | None:
    order = await db.get(Order, order_id)
    if order is None:
        return None

    stmt = select(OrderItem, MenuItem.name).join(MenuItem, MenuItem.id == OrderItem.menu_item_id).where(
        OrderItem.order_id == order_id
    )
    result = await db.execute(stmt)

    items = []
    for order_item, name in result.all():
        line_total = round(float(order_item.price_at_order) * order_item.quantity, 2)
        items.append(
            {
                "menu_item_id": order_item.menu_item_id,
                "name": name,
                "quantity": order_item.quantity,
                "price_at_order": float(order_item.price_at_order),
                "line_total": line_total,
            }
        )

    totals = await calculate_totals(db, order_id)

    return {
        "order_id": order.id,
        "status": order.status,
        "items": items,
        **totals,
    }


def format_summary_text(summary: dict, lang: str = "en") -> str:
    if not summary["items"]:
        return t("order_summary_empty", lang)

    lines = ", ".join(
        f"{item['quantity']} x {translated_name_and_description(item['name'], None, lang)[0]}"
        for item in summary["items"]
    )
    text = t(
        "order_summary_line",
        lang,
        lines=lines,
        subtotal=f"{summary['subtotal']:.2f}",
        tax=f"{summary['tax']:.2f}",
        total=f"{summary['total']:.2f}",
    )
    if summary.get("discount"):
        text += f" (Coupon {summary['coupon_code']} applied - you saved Rs.{summary['discount']:.2f}!)"
    return text


async def checkout(
    db: AsyncSession,
    order_id: int,
    payment_status: str = "pending",
    fulfillment: str | None = None,
    delivery_address: str | None = None,
    guest_name: str | None = None,
    guest_phone: str | None = None,
    guest_email: str | None = None,
    is_birthday: bool = False,
    location: str | None = None,
    delivery_flat_number: str | None = None,
    delivery_unverified: bool = False,
) -> dict | None:
    """Single-pass checkout: one items fetch, one coupon computation, one
    commit - previously this re-fetched/recomputed totals 3-4 times via
    get_order_summary()+calculate_totals(), each its own DB round trip."""
    order = await db.get(Order, order_id)
    if order is None:
        return None

    stmt = select(OrderItem, MenuItem.name).join(MenuItem, MenuItem.id == OrderItem.menu_item_id).where(
        OrderItem.order_id == order_id
    )
    result = await db.execute(stmt)
    rows = result.all()
    if not rows:
        raise OrderError("Can't check out an empty order.")

    already_confirmed = order.status == "confirmed"

    order.status = "confirmed"
    order.payment_status = payment_status
    if fulfillment is not None:
        order.fulfillment = fulfillment
    if delivery_address is not None:
        order.delivery_address = delivery_address
    if delivery_flat_number is not None:
        order.delivery_flat_number = delivery_flat_number
    order.delivery_unverified = delivery_unverified
    if location is not None:
        order.location = location
    if guest_name is not None:
        order.guest_name = guest_name
    if guest_phone is not None:
        order.guest_phone = guest_phone
    if guest_email is not None:
        order.guest_email = guest_email
    order.is_birthday = is_birthday

    subtotal = round(sum(float(order_item.price_at_order) * order_item.quantity for order_item, _ in rows), 2)

    if not already_confirmed:
        is_first_order = False
        if order.guest_phone:
            is_first_order = not await has_prior_confirmed_order(db, order.guest_phone, exclude_order_id=order.id)
        best = pick_best_coupon(subtotal, is_first_order)
        order.coupon_code = best["code"] if best else None
        order.discount_amount = best["discount"] if best else 0

    discount = round(float(order.discount_amount), 2) if order.discount_amount else 0.0
    discounted_subtotal = max(subtotal - discount, 0.0)
    tax = round(discounted_subtotal * TAX_RATE, 2)
    total = round(discounted_subtotal + tax, 2)
    order.tax_amount = tax
    order.total_amount = total

    await db.commit()

    items = [
        {
            "menu_item_id": order_item.menu_item_id,
            "name": name,
            "quantity": order_item.quantity,
            "price_at_order": float(order_item.price_at_order),
            "line_total": round(float(order_item.price_at_order) * order_item.quantity, 2),
        }
        for order_item, name in rows
    ]

    return {
        "order_id": order.id,
        "status": "confirmed",
        "items": items,
        "subtotal": subtotal,
        "discount": discount,
        "coupon_code": order.coupon_code,
        "tax": tax,
        "total": total,
    }
