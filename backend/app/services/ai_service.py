import logging
import re
from datetime import datetime

from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import CAFE_ADDRESS, CAFE_LOCATIONS, CAFE_PHONE, DELIVERY_RADIUS_KM, settings
from app.core.timing import timed
from app.models.chat_history import ChatHistory
from app.prompts.system_prompt import build_system_prompt
from app.prompts.templates import t
from app.schemas.chat import Filters, GeminiChatOutput, OrderItemEntry
from app.services import (
    addon_service,
    cache_service,
    checkout_draft_service,
    customer_profile_service,
    email_service,
    escalation_service,
    faq_service,
    feedback_service,
    geocoding_service,
    loyalty_service,
    menu_context,
    order_service,
    quick_reply_service,
    recommendation_service,
    reservation_draft_service,
    reservation_service,
    session_context_service,
    usage_logger,
)
from app.services.gemini_client import get_client
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "I'm having some trouble right now - please try again in a moment."
EMOJI_ONLY_REPLY = "I couldn't quite understand that - could you type it in words?"
CACHEABLE_INTENTS = {"menu_search", "faq", "recommendation"}
GROUNDABLE_INTENTS = {"menu_search", "recommendation"}
HISTORY_LIMIT = 10

PAYMENT_COMPLETE_MESSAGE = "Payment completed"
RESERVATION_BOOKING_FEE = 50.0

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "\U00002b00-\U00002bff"
    "\U0000fe0f"
    "\U0000200d"
    "]+"
)


def _is_emoji_only(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return _EMOJI_PATTERN.sub("", stripped).strip() == ""


def _fallback_result() -> dict:
    return {
        "reply_text": FALLBACK_MESSAGE,
        "intent": "general_chat",
        "sentiment": "neutral",
        "language": "en",
        "filters": None,
    }


async def _fetch_recent_history(db: AsyncSession, session_id: str) -> list[ChatHistory]:
    async with timed("db.chat_history_fetch"):
        stmt = (
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
            .limit(HISTORY_LIMIT)
        )
        result = await db.execute(stmt)
        return list(reversed(result.scalars().all()))


async def _save_turn(db: AsyncSession, session_id: str, user_message: str, reply_text: str) -> None:
    async with timed("db.save_turn_commit"):
        db.add(ChatHistory(session_id=session_id, role="user", message=user_message))
        db.add(ChatHistory(session_id=session_id, role="assistant", message=reply_text))
        await db.commit()


def _history_to_contents(history: list[ChatHistory], user_message: str) -> list[types.Content]:
    contents = [
        types.Content(
            role="user" if turn.role == "user" else "model",
            parts=[types.Part.from_text(text=turn.message)],
        )
        for turn in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))
    return contents


async def _build_pre_call_context(db: AsyncSession, user_message: str, session_id: str) -> str:
    async with timed("pre_call_context_build"):
        popular = await menu_context.get_popular_items(db)
        blocks = [menu_context.format_items_block(popular, "A few popular picks (small sample, not the full menu)")]

        faq_matches = faq_service.find_matches(user_message)
        if faq_matches:
            blocks.append(faq_service.format_faq_block(faq_matches))

        if recommendation_service.mentions_previous_order(user_message):
            hint = await recommendation_service.get_previous_order_summary(db, session_id)
            if hint:
                blocks.append(hint)

        known_name = await session_context_service.get_name(db, session_id)
        if known_name:
            blocks.append(
                f"Customer's name for this session: {known_name} (use it naturally where it fits - a "
                "greeting, an order confirmation lead-in, etc. - you already know it, so don't ask again)."
            )

        draft = await reservation_draft_service.get_draft(db, session_id)
        if draft is not None:
            progress = reservation_draft_service.describe_progress(draft)
            if progress:
                blocks.append(progress)

        return "\n\n".join(blocks)


def _is_broad_menu_query(filters: Filters | None) -> bool:
    if filters is None:
        return True
    return all(value is None for value in filters.model_dump().values())


def _is_location_question(user_message: str) -> bool:
    return any(match["category"] == "location" for match in faq_service.find_matches(user_message))


def _is_about_question(user_message: str) -> bool:
    # Unlike _is_location_question (any of the top 3 matches), this only fires
    # when "about" is the SINGLE best match - both FAQ entries mention the
    # café/locations heavily, so a loose "any of top 3" check would wrongly
    # steal plain location questions (e.g. "where is the café located?").
    matches = faq_service.find_matches(user_message)
    return bool(matches) and matches[0]["category"] == "about"


def _format_locations_block(locations: list[dict]) -> str:
    return "\n\n".join(
        f"📍 {loc['name']}\n{loc['address']}\nHours: {loc['hours']} | Phone: {loc['phone']}" for loc in locations
    )


def _build_about_reply(language: str) -> str:
    return t("faq_about_intro", language, locations=_format_locations_block(CAFE_LOCATIONS))


async def _ground_reply(
    db: AsyncSession, parsed: GeminiChatOutput, user_message: str
) -> tuple[str, list[dict] | None]:
    if parsed.intent == "recommendation":
        candidates = await menu_context.get_filtered_items(
            db, parsed.filters, limit=menu_context.RECOMMENDATION_POOL_LIMIT
        )
    else:
        candidates = await menu_context.get_filtered_items(db, parsed.filters)

    if not candidates:
        closest, relaxed_field = await menu_context.get_closest_items(db, parsed.filters)
        if not closest:
            return f"{parsed.reply_text} I couldn't find anything on the menu matching that right now.".strip(), None
        reply_text = f"{parsed.reply_text} {menu_context.fallback_intro(relaxed_field)}".strip()
        return reply_text, closest

    if parsed.intent != "recommendation":
        return parsed.reply_text, candidates

    time_of_day_override = parsed.filters.time_of_day if parsed.filters else None
    ranked = recommendation_service.shortlist(candidates, user_message, time_of_day_override=time_of_day_override)
    combo = None
    if parsed.filters and parsed.filters.max_price:
        combo = recommendation_service.combo_within_budget(ranked, parsed.filters.max_price)

    if parsed.filters and parsed.filters.max_price and not combo:
        suggested = sorted(ranked, key=lambda item: item["price"])[:1]
    elif combo:
        suggested = combo
    else:
        suggested = ranked

    return parsed.reply_text, suggested


async def _order_summary_reply(db: AsyncSession, session_id: str, lang: str) -> tuple[str, dict | None, list[dict] | None]:
    draft_order = await order_service.get_active_draft_order(db, session_id)
    summary = await order_service.get_order_summary(db, draft_order.id) if draft_order else None
    if not summary or not summary["items"]:
        last_order = await order_service.get_last_order_for_session(db, session_id)
        if last_order is not None:
            summary = await order_service.get_order_summary(db, last_order.id)

    if summary is None or not summary["items"]:
        # Nothing to look up - a dead-end "your order is empty" isn't useful, so
        # this doubles as an invitation to start ordering. No bill card either -
        # there's nothing on it worth showing.
        menu_display = await menu_context.get_full_menu_display(db)
        return t("order_start_prompt", lang), None, menu_display

    reply_text = order_service.format_summary_text(summary, lang)
    return reply_text, summary, None


_ORDER_SUMMARY_KEYWORDS = (
    "what did i order",
    "what did i just order",
    "whats in my order",
    "whats in my cart",
    "my order summary",
    "show my order",
    "show me my order",
)


def _is_order_summary_question(text: str) -> bool:
    # Punctuation stripped first (matches _normalize_word's own approach) so
    # "what's" and "whats" both normalize to the same thing before matching.
    normalized = re.sub(r"[^\w\s]", "", text.lower())
    return any(phrase in normalized for phrase in _ORDER_SUMMARY_KEYWORDS)


_NAME_RECALL_KEYWORDS = (
    "whats my name",
    "what is my name",
    "who am i",
    "do you know my name",
    "do you remember my name",
)


def _is_name_recall_question(text: str) -> bool:
    normalized = re.sub(r"[^\w\s]", "", text.lower())
    return any(phrase in normalized for phrase in _NAME_RECALL_KEYWORDS)


async def _handle_order_intent(
    db: AsyncSession, parsed: GeminiChatOutput, session_id: str, user_id: int | None
) -> tuple[str, dict | None, list[dict] | None]:
    action = parsed.order_action
    lang = parsed.language

    if action is not None and action.action == "view_summary":
        return await _order_summary_reply(db, session_id, lang)

    order = await order_service.get_or_create_draft_order(db, session_id, user_id)

    # (template_key, kwargs) for a total-dependent message, filled in once from the
    # single get_order_summary() call below instead of computing totals twice.
    pending_reply: tuple[str, dict] | None = None
    reply_suffix = ""

    if action is None:
        reply_text = parsed.reply_text
    else:
        try:
            if action.action == "add":
                # `items` (multiple distinct items in one message, e.g. "one
                # cutting chai and two filter coffee") takes priority; falls
                # back to the singular item_name/quantity shorthand for a
                # single-item message.
                entries = action.items or ([OrderItemEntry(item_name=action.item_name, quantity=action.quantity)] if action.item_name else [])

                if not entries:
                    reply_text = f"{parsed.reply_text} {t('order_ask_what_to_add', lang)}"
                else:
                    added: list[tuple[int, str]] = []
                    not_found: list[str] = []
                    ambiguous_reply: str | None = None

                    for entry in entries:
                        if not entry.item_name:
                            continue
                        resolved = await order_service.resolve_add_entry(db, entry.item_name)
                        quantity = entry.quantity or 1

                        if resolved["type"] == "match":
                            await order_service.add_item(db, order.id, resolved["item"].id, quantity)
                            added.append((quantity, resolved["item"].name))
                        elif resolved["type"] == "ambiguous":
                            options = ", ".join(
                                f"{menu_context.translate_item_name(item.name, lang)} (₹{float(item.price):.0f})"
                                for item in resolved["candidates"]
                            )
                            ambiguous_reply = t("order_ambiguous_options", lang, options=options)
                            break
                        elif resolved["type"] == "split":
                            # Never silently add both halves of a guessed
                            # compound phrase (e.g. "samosa pav" isn't itself
                            # a real request for two items) - ask first, same
                            # as any other ambiguous match.
                            item1, item2 = resolved["items"]
                            ambiguous_reply = t(
                                "order_split_clarify",
                                lang,
                                original=entry.item_name.title(),
                                item1=menu_context.translate_item_name(item1.name, lang),
                                item2=menu_context.translate_item_name(item2.name, lang),
                            )
                            break
                        elif resolved["suggestions"]:
                            options = ", ".join(
                                f"{menu_context.translate_item_name(item.name, lang)} (₹{float(item.price):.0f})"
                                for item in resolved["suggestions"]
                            )
                            ambiguous_reply = t("order_clarify_suggestions", lang, item=entry.item_name, options=options)
                            break
                        else:
                            not_found.append(entry.item_name)

                    if ambiguous_reply is not None:
                        reply_text = ambiguous_reply
                    elif not added:
                        reply_text = f"{parsed.reply_text} {t('order_item_not_on_menu', lang, item=not_found[0])}"
                    else:
                        if len(added) == 1:
                            qty, name = added[0]
                            pending_reply = ("order_added", {"qty": qty, "item": menu_context.translate_item_name(name, lang)})
                        else:
                            items_str = ", ".join(
                                f"{qty} x {menu_context.translate_item_name(name, lang)}" for qty, name in added
                            )
                            pending_reply = ("order_added_multi", {"items": items_str})
                        if not_found:
                            reply_suffix += " " + " ".join(
                                t("order_item_not_on_menu", lang, item=name) for name in not_found
                            )

                        if not order.upsell_shown:
                            upsell_item = await order_service.pick_upsell_item(db, order.id)
                            if upsell_item is not None:
                                reply_suffix += " " + t(
                                    "order_upsell_suggestion",
                                    lang,
                                    item=menu_context.translate_item_name(upsell_item.name, lang),
                                )
                                # Marks the very next reply as "answering this
                                # suggestion" - see the pending_addon check at
                                # the top of _resolve_chat_result, which only
                                # auto-adds on a clear affirmative and drops
                                # the flag (falling through to normal intent
                                # routing) on anything else, instead of the
                                # old loose keyword-in-reply match.
                                await addon_service.mark_pending(db, session_id, upsell_item.id, upsell_item.name, lang)
                            order.upsell_shown = True
                            await db.commit()

            elif action.action == "remove":
                if not action.item_name:
                    reply_text = f"{parsed.reply_text} {t('order_ask_what_to_remove', lang)}"
                else:
                    menu_item = await order_service.resolve_order_line_item(db, order.id, action.item_name)
                    if menu_item is None:
                        reply_text = f"{parsed.reply_text} {t('order_item_not_in_cart', lang, item=action.item_name)}"
                    else:
                        await order_service.remove_item(db, order.id, menu_item.id)
                        pending_reply = ("order_removed", {"item": menu_context.translate_item_name(menu_item.name, lang)})

            elif action.action == "modify":
                if not action.item_name or action.quantity is None:
                    reply_text = f"{parsed.reply_text} {t('order_ask_what_to_modify', lang)}"
                else:
                    menu_item = await order_service.resolve_order_line_item(db, order.id, action.item_name)
                    if menu_item is None:
                        reply_text = f"{parsed.reply_text} {t('order_item_not_in_cart', lang, item=action.item_name)}"
                    elif action.quantity <= 0:
                        await order_service.update_quantity(db, order.id, menu_item.id, action.quantity)
                        pending_reply = ("order_removed", {"item": menu_context.translate_item_name(menu_item.name, lang)})
                    else:
                        await order_service.update_quantity(db, order.id, menu_item.id, action.quantity)
                        pending_reply = (
                            "order_updated",
                            {"item": menu_context.translate_item_name(menu_item.name, lang), "qty": action.quantity},
                        )

            elif action.action == "clear":
                cleared_count = await order_service.clear_cart(db, order.id)
                if cleared_count:
                    pending_reply = ("order_cleared", {})
                else:
                    reply_text = t("order_already_empty", lang)

            else:
                reply_text = parsed.reply_text
        except order_service.OrderError as exc:
            reply_text = f"{parsed.reply_text} {exc}"

    order_summary = await order_service.get_order_summary(db, order.id)
    menu_display = None
    if pending_reply is not None:
        key, kwargs = pending_reply
        reply_text = t(key, lang, total=f"{order_summary['total']:.2f}", **kwargs) + reply_suffix
    elif action is None and not order_summary["items"]:
        # A vague "I want to order" with nothing in the cart yet is a dead end
        # otherwise - show the menu so they can actually start.
        reply_text = t("order_start_prompt", lang)
        menu_display = await menu_context.get_full_menu_display(db)

    # No bill card for an empty cart - nothing on it is worth showing.
    if not order_summary["items"]:
        order_summary = None
    return reply_text, order_summary, menu_display


def _order_payment_request(total: float) -> dict:
    return {"amount": total, "label": "Order Total", "purpose": "order"}


async def _handle_checkout_flow(
    db: AsyncSession,
    parsed: GeminiChatOutput,
    session_id: str,
    user_id: int | None,
    user_message: str,
    address_coords: tuple[float, float] | None = None,
) -> tuple[str, list[str] | None, dict | None, dict | None, dict | None, list[dict] | None]:
    is_new_flow = await checkout_draft_service.get_draft(db, session_id) is None
    draft = await checkout_draft_service.get_or_create_draft(db, session_id)
    lang = parsed.language
    # A canned, deterministic acknowledgment - NOT the LLM's freeform reply_text.
    # Gemini's own text is unpredictable in length/content (see STRICT RULE for
    # "order"/"reservation" intents), and gluing it onto a scripted step question
    # was the recurring concatenation bug. During a structured flow, the ENTIRE
    # reply is code-generated; the LLM's reply_text is not used at all.
    ack = t("flow_ack", lang)

    def _address_resolved_reply() -> tuple[str, None, None, None, None, None]:
        # Reuses the previously-dead checkout_delivery_confirmed_branch
        # template as a lead-in, then rolls straight into the flat/house
        # number ask - one turn instead of two, same as the ack+question
        # pattern used everywhere else in this flow.
        draft.last_prompted_step = "flat_number"
        return (
            f"{t('checkout_delivery_confirmed_branch', lang, location=draft.location)} "
            f"{t('checkout_ask_flat_number', lang)}",
            None,
            None,
            None,
            None,
            None,
        )

    order = await order_service.get_or_create_draft_order(db, session_id, user_id)
    summary = await order_service.get_order_summary(db, order.id)

    if not summary["items"]:
        checkout_draft_service.clear_draft(session_id)
        menu_display = await menu_context.get_full_menu_display(db)
        return t("order_start_prompt", lang), None, None, None, None, menu_display

    if draft.name is None:
        known_name = await session_context_service.get_name(db, session_id)
        if known_name:
            draft.name = known_name
    if draft.phone is None:
        known_phone = await session_context_service.get_phone(db, session_id)
        if known_phone:
            draft.phone = known_phone
    if draft.email is None:
        known_email = await session_context_service.get_email(db, session_id)
        if known_email:
            draft.email = known_email

    step_before = draft.next_step()
    was_prompted_for_step_before = draft.last_prompted_step == step_before

    if draft.is_birthday is None and _mentions_birthday(user_message):
        draft.is_birthday = True

    if step_before == "name" and draft.name is None and not is_new_flow and was_prompted_for_step_before:
        name = (parsed.detected_name or user_message).strip()
        draft.name = name or None
        if draft.name:
            await session_context_service.remember_name(db, session_id, draft.name)

    elif (
        step_before == "phone" and draft.phone is None and not is_new_flow and was_prompted_for_step_before
    ):
        phone = _parse_phone(user_message)
        if phone is None:
            return t("reservation_invalid_phone", lang), None, None, None, None, None
        draft.phone = phone
        await session_context_service.remember_phone(db, session_id, phone)
        # No returning-customer greeting here - it was getting stapled onto the
        # checkout flow mid-transaction. If ever brought back, it belongs
        # outside an active flow (e.g. organically at conversation start), not
        # wedged into the phone step.

    elif (
        step_before == "email" and draft.email is None and not is_new_flow and was_prompted_for_step_before
    ):
        email = _parse_email(user_message)
        if email is None:
            return t("invalid_email", lang), None, None, None, None, None
        draft.email = email
        await session_context_service.remember_email(db, session_id, email)

    elif (
        step_before == "fulfillment" and draft.fulfillment is None and not is_new_flow and was_prompted_for_step_before
    ):
        normalized = _normalize_word(user_message)
        if "pickup" in normalized or "pick up" in normalized:
            draft.fulfillment = "pickup"
        elif "delivery" in normalized or "deliver" in normalized:
            draft.fulfillment = "delivery"
        if draft.fulfillment is None:
            draft.last_prompted_step = "fulfillment"
            return t("checkout_ask_fulfillment", lang), ["Pickup", "Delivery"], None, None, None, None

    elif (
        step_before == "address"
        and draft.address is None
        and not is_new_flow
        and draft.last_prompted_step in ("address", "address_reuse")
    ):
        if draft.last_prompted_step == "address_reuse":
            # Answering the "deliver to your last address?" offer - a yes/no
            # decision, not a fresh address to parse. Any reply that isn't a
            # clear "yes" is treated as declining (customer gets asked to
            # type a fresh address next), same as the affirmative/negative
            # pattern used for the reservation "confirm" step.
            if _is_affirmative(user_message):
                saved = await customer_profile_service.get_last_delivery_address(db, draft.phone)
                if saved is not None:
                    nearest, distance = geocoding_service.find_nearest_location(saved["lat"], saved["lon"])
                    if distance > DELIVERY_RADIUS_KM:
                        # Coverage may have changed since it was saved - still
                        # worth re-validating rather than trusting it blindly.
                        # Stay on the address step (not pickup) - let them
                        # pick a different address instead.
                        draft.address_reuse_declined = True
                        draft.last_prompted_step = "address"
                        return (
                            t("checkout_address_out_of_range", lang, phone=CAFE_PHONE),
                            None,
                            None,
                            None,
                            None,
                            None,
                        )
                    draft.address = saved["address"]
                    draft.address_lat = saved["lat"]
                    draft.address_lon = saved["lon"]
                    draft.address_source = "reuse"
                    draft.location = nearest["name"]

            draft.address_reuse_declined = True
            if draft.address is None:
                draft.last_prompted_step = "address"
                return t("checkout_ask_address", lang), None, None, None, None, None
            return _address_resolved_reply()

        # CRITICAL: free-text address submission is disabled entirely - an
        # address can only come from address_coords (the frontend's
        # Nominatim autocomplete dropdown - see AddressAutocomplete.jsx,
        # which now only lets the customer SELECT a suggestion, never submit
        # arbitrary typed text) or from a saved profile address above. Any
        # message reaching here without coords means either the customer
        # typed and hit send without picking a suggestion, or an older/
        # non-browser client - either way, re-ask rather than guessing at an
        # unverified address.
        if address_coords is None:
            draft.last_prompted_step = "address"
            return t("checkout_address_must_select_suggestion", lang), None, None, None, None, None

        candidate_address = user_message.strip()
        lat, lon = address_coords
        nearest, distance = geocoding_service.find_nearest_location(lat, lon)
        if distance > DELIVERY_RADIUS_KM:
            # Stay on the address step (not pickup) - let them pick a
            # different, closer address instead of pushing pickup on them.
            draft.last_prompted_step = "address"
            return t("checkout_address_out_of_range", lang, phone=CAFE_PHONE), None, None, None, None, None
        draft.address = candidate_address
        draft.address_lat, draft.address_lon = lat, lon
        draft.address_source = "autocomplete"
        draft.location = nearest["name"]
        return _address_resolved_reply()

    elif (
        step_before == "flat_number"
        and draft.flat_number is None
        and not draft.flat_number_skipped
        and not is_new_flow
        and was_prompted_for_step_before
    ):
        if _normalize_word(user_message) in _SKIP_WORDS:
            draft.flat_number_skipped = True
        else:
            draft.flat_number = user_message.strip()

    elif (
        step_before == "address_confirm"
        and not draft.address_confirmed
        and not is_new_flow
        and was_prompted_for_step_before
    ):
        if _is_negative(user_message):
            # Let them re-search rather than blocking - clear everything
            # address-related so it's asked fresh, flat number included (it
            # may not apply to whatever address they pick next).
            draft.address = None
            draft.address_lat = None
            draft.address_lon = None
            draft.address_source = None
            draft.delivery_unverified = False
            draft.flat_number = None
            draft.flat_number_skipped = False
            draft.address_confirmed = False
            draft.last_prompted_step = "address"
            return t("checkout_ask_address", lang), None, None, None, None, None
        if not _is_affirmative(user_message):
            return _address_confirm_text(draft, lang), _CONFIRM_QUICK_REPLIES, None, None, None, None
        draft.address_confirmed = True

    elif (
        step_before == "location" and draft.location is None and not is_new_flow and was_prompted_for_step_before
    ):
        matched_location = quick_reply_service.match_location(user_message)
        if matched_location is None:
            draft.last_prompted_step = "location"
            return (
                t("checkout_ask_pickup_location", lang),
                quick_reply_service.LOCATION_OPTIONS,
                None,
                None,
                None,
                None,
            )
        draft.location = matched_location

    elif step_before == "payment" and not is_new_flow and was_prompted_for_step_before:
        if _normalize_word(user_message) != _normalize_word(PAYMENT_COMPLETE_MESSAGE):
            summary = await _checkout_bill_preview(db, order.id, draft.phone)
            payment_ack = _payment_prompt_text("", summary, lang)
            draft.last_prompted_step = "payment"
            return payment_ack, None, summary, _order_payment_request(summary["total"]), None, None

        async with timed("db.order_checkout"):
            checkout_summary = await order_service.checkout(
                db,
                order.id,
                payment_status="mock_paid",
                fulfillment=draft.fulfillment,
                delivery_address=_full_delivery_address(draft),
                guest_name=draft.name,
                guest_phone=draft.phone,
                guest_email=draft.email,
                is_birthday=bool(draft.is_birthday),
                location=draft.location,
                delivery_flat_number=draft.flat_number,
                delivery_unverified=draft.delivery_unverified,
            )
        final_text = t(
            "order_mock_payment_confirmed", lang, fulfillment=draft.fulfillment, order_id=order.id, location=draft.location
        )

        async with timed("db.award_points"):
            points_earned, total_points = await loyalty_service.award_points_and_get_total(
                db, draft.phone, checkout_summary["total"]
            )
        loyalty_card = loyalty_service.format_loyalty_card(total_points)
        if points_earned:
            final_text += f" You earned {points_earned} loyalty points! ({loyalty_card['progress_label']})"

        milestone_tier = loyalty_service.get_newly_unlocked_tier(total_points - points_earned, total_points)
        if milestone_tier is not None:
            if loyalty_card["points_needed"] == 0 and loyalty_card["next_reward_points"] == milestone_tier["points"]:
                final_text += f" 🎉 You've unlocked {milestone_tier['reward']}! You've unlocked every reward tier!"
            else:
                final_text += (
                    f" 🎉 You've unlocked {milestone_tier['reward']}! "
                    f"Your next reward is at {loyalty_card['next_reward_points']} points."
                )
            loyalty_card["milestone"] = {"reward": milestone_tier["reward"], "tier_points": milestone_tier["points"]}

        # Feedback-request prompt disabled for now (was producing broken/errored
        # turns) - re-enable by restoring the feedback_request append + mark_pending
        # call here once that flow is fixed.

        if (
            draft.fulfillment == "delivery"
            and draft.phone
            and draft.address
            and draft.address_lat is not None
            and draft.address_lon is not None
        ):
            await customer_profile_service.remember_delivery_address(
                db, draft.phone, draft.address, draft.address_lat, draft.address_lon
            )

        if draft.email:
            await _send_order_confirmation_email(draft, order.id, checkout_summary)
        await _send_internal_order_notification(draft, order.id, checkout_summary)

        checkout_draft_service.clear_draft(session_id)
        return final_text, None, checkout_summary, None, loyalty_card, None

    step = draft.next_step()
    draft.last_prompted_step = step

    if step == "name":
        name_prompt = t("checkout_ask_name", lang)
        return (name_prompt if is_new_flow else f"{ack} {name_prompt}"), None, None, None, None, None
    if step == "phone":
        return f"{ack} {t('checkout_ask_phone', lang)}", None, None, None, None, None
    if step == "email":
        return f"{ack} {t('checkout_ask_email', lang)}", None, None, None, None, None
    if step == "fulfillment":
        return f"{ack} {t('checkout_ask_fulfillment', lang)}", ["Pickup", "Delivery"], None, None, None, None
    if step == "address":
        if not draft.address_reuse_offered and not draft.address_reuse_declined and draft.phone:
            saved = await customer_profile_service.get_last_delivery_address(db, draft.phone)
            if saved is not None:
                draft.address_reuse_offered = True
                draft.last_prompted_step = "address_reuse"
                return (
                    f"{ack} {t('checkout_ask_reuse_address', lang, address=saved['address'])}",
                    ["Use this address", "Search a new address"],
                    None,
                    None,
                    None,
                    None,
                )
        return f"{ack} {t('checkout_ask_address', lang)}", None, None, None, None, None
    if step == "flat_number":
        return f"{ack} {t('checkout_ask_flat_number', lang)}", None, None, None, None, None
    if step == "address_confirm":
        return _address_confirm_text(draft, lang), _CONFIRM_QUICK_REPLIES, None, None, None, None
    if step == "location":
        return (
            f"{ack} {t('checkout_ask_pickup_location', lang)}",
            quick_reply_service.LOCATION_OPTIONS,
            None,
            None,
            None,
            None,
        )
    summary = await _checkout_bill_preview(db, order.id, draft.phone)
    payment_ack = _payment_prompt_text(ack, summary, lang)
    return payment_ack, None, summary, _order_payment_request(summary["total"]), None, None


async def _checkout_bill_preview(db: AsyncSession, order_id: int, phone: str | None) -> dict:
    await order_service.apply_best_coupon_preview(db, order_id, phone)
    return await order_service.get_order_summary(db, order_id)


def _payment_prompt_text(ack: str, summary: dict, lang: str) -> str:
    text = f"{ack} {t('checkout_payment_prompt', lang)}".strip()
    if summary.get("discount"):
        text += f" You'll save Rs.{summary['discount']:.2f} with coupon {summary['coupon_code']}!"
    return text


def _full_delivery_address(draft: "checkout_draft_service.CheckoutDraft") -> str | None:
    """The verified address plus the customer's house/flat number appended,
    if given - this combined string is what actually gets stored as the
    order's delivery_address and shown in the confirmation echo, per the
    "flat number appended to the resolved address" design (see
    checkout_draft_service.CheckoutDraft.flat_number)."""
    if draft.address is None:
        return None
    if draft.flat_number:
        return f"{draft.flat_number}, {draft.address}"
    return draft.address


def _address_confirm_text(draft: "checkout_draft_service.CheckoutDraft", lang: str) -> str:
    return t("checkout_confirm_address", lang, address=_full_delivery_address(draft))


async def _send_order_confirmation_email(draft: "checkout_draft_service.CheckoutDraft", order_id: int, checkout_summary: dict) -> None:
    sent = await email_service.send_order_confirmation(
        draft.email,
        draft.name,
        order_id,
        checkout_summary["items"],
        checkout_summary["total"],
        draft.fulfillment,
        _full_delivery_address(draft),
        location=draft.location,
    )
    if not sent:
        logger.error("order_confirmation_email.not_sent order_id=%s to=%s", order_id, draft.email)
    if draft.is_birthday:
        birthday_sent = await email_service.send_birthday_wish(draft.email, draft.name)
        if not birthday_sent:
            logger.error("birthday_email.not_sent order_id=%s to=%s", order_id, draft.email)


async def _send_internal_order_notification(
    draft: "checkout_draft_service.CheckoutDraft", order_id: int, checkout_summary: dict
) -> None:
    sent = await email_service.send_internal_order_notification(
        order_id,
        datetime.now().strftime("%b %d, %Y %I:%M %p"),
        draft.name,
        draft.phone,
        draft.email,
        checkout_summary["items"],
        checkout_summary["subtotal"],
        checkout_summary["discount"],
        checkout_summary["coupon_code"],
        checkout_summary["tax"],
        checkout_summary["total"],
        draft.fulfillment,
        _full_delivery_address(draft),
        location=draft.location,
        delivery_flat_number=draft.flat_number,
        delivery_unverified=draft.delivery_unverified,
    )
    if not sent:
        logger.error("internal_order_notification.not_sent order_id=%s", order_id)


_SKIP_WORDS = {"no", "none", "nah", "skip", "nope", "no thanks", "nothing", "na"}
_AFFIRMATIVE_WORDS = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "y",
    "sure",
    "confirm",
    "confirmed",
    "ok",
    "okay",
    "correct",
    "right",
    "haan",
    "ha",
    "haanji",
    "bilkul",
}
_AFFIRMATIVE_PHRASES = (
    "go ahead",
    "go for it",
    "book it",
    "please book",
    "sounds good",
    "yes please",
    "yes sure",
    "thats right",
    "kar do",
    "book kar do",
    "confirm kar do",
    "use this",
    "use this address",
    "use the same",
    "same address",
    "theek hai",
    "thik hai",
)
_NEGATIVE_WORDS = {"no", "nope", "cancel", "nahi", "nako"}
_NEGATIVE_PHRASES = ("never mind", "nevermind", "don't book", "do not book")
_CONFIRM_QUICK_REPLIES = ["Yes, confirm", "No, cancel"]
_PHONE_RE = re.compile(r"^(?:\+?91[-\s]?)?([6-9]\d{9})$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_BIRTHDAY_KEYWORDS = ("birthday", "bday", "b'day")


def _normalize_word(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _parse_phone(text: str) -> str | None:
    cleaned = re.sub(r"[\s-]", "", text.strip())
    match = _PHONE_RE.match(cleaned)
    return match.group(1) if match else None


def _parse_email(text: str) -> str | None:
    candidate = text.strip()
    return candidate if _EMAIL_RE.match(candidate) else None


def _mentions_birthday(text: str) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in _BIRTHDAY_KEYWORDS)


def _is_affirmative(text: str) -> bool:
    normalized = _normalize_word(text)
    words = set(normalized.split())
    return bool(words & _AFFIRMATIVE_WORDS) or any(phrase in normalized for phrase in _AFFIRMATIVE_PHRASES)


def _is_negative(text: str) -> bool:
    normalized = _normalize_word(text)
    words = set(normalized.split())
    return bool(words & _NEGATIVE_WORDS) or any(phrase in normalized for phrase in _NEGATIVE_PHRASES)


def _confirm_summary_text(draft: "reservation_draft_service.ReservationDraft", lang: str) -> str:
    return t(
        "reservation_confirm_summary",
        lang,
        guests=draft.guests,
        date=draft.date.strftime("%b %d, %Y"),
        time=draft.time.strftime("%I:%M %p"),
        name=draft.name,
        phone=draft.phone,
        location=draft.location,
    )


def _reservation_payment_request() -> dict:
    return {"amount": RESERVATION_BOOKING_FEE, "label": "Booking Fee", "purpose": "reservation"}


async def _handle_reservation_intent(
    db: AsyncSession, parsed: GeminiChatOutput, session_id: str, user_id: int | None, user_message: str
) -> tuple[str, list[str] | None, list[dict] | None, dict | None]:
    is_new_flow = await reservation_draft_service.get_draft(db, session_id) is None
    draft = await reservation_draft_service.get_or_create_draft(db, session_id)
    lang = parsed.language
    # Canned, deterministic acknowledgment - see the matching note in
    # _handle_checkout_flow for why the LLM's own reply_text is never used here.
    ack = t("flow_ack", lang)
    details = parsed.reservation_details

    if draft.email is None:
        known_email = await session_context_service.get_email(db, session_id)
        if known_email:
            draft.email = known_email

    step_before = draft.next_step()
    was_prompted_for_step_before = draft.last_prompted_step == step_before

    if draft.is_birthday is None and _mentions_birthday(user_message):
        draft.is_birthday = True

    if details is not None:
        if draft.date is None and details.date_phrase:
            draft.date = reservation_service.resolve_date_only(details.date_phrase)
            if draft.date is None and step_before == "date":
                return t("reservation_cant_parse", lang), None, None, None
        if draft.time is None and details.time_phrase:
            draft.time = reservation_service.resolve_time_only(details.time_phrase)
            if draft.time is None and step_before == "time":
                time_choices = await quick_reply_service.time_options(
                    db, draft.date, draft.guests or 1, location=draft.location
                )
                return t("reservation_cant_parse", lang), time_choices, None, None
        if draft.guests is None and details.guests is not None and step_before != "guests":
            # Ambient extraction only (e.g. "book a table for 2 tomorrow at 7pm"
            # given before guests was specifically asked about). When guests IS
            # the current step, the AI's number is never trusted - see below -
            # because it can hallucinate a plausible count for a vague reply
            # like "a lot" instead of leaving the field null.
            if reservation_service.validate_guest_count(details.guests) is None:
                draft.guests = details.guests

    if step_before == "location" and draft.location is None and was_prompted_for_step_before:
        matched_location = quick_reply_service.match_location(user_message)
        if matched_location is None:
            draft.last_prompted_step = "location"
            return t("reservation_ask_location", lang), quick_reply_service.LOCATION_OPTIONS, None, None
        draft.location = matched_location

    elif step_before == "guests" and draft.guests is None and was_prompted_for_step_before:
        parsed_guests = reservation_service.parse_guest_count(user_message)
        guest_error = reservation_service.validate_guest_count(parsed_guests)
        if guest_error is not None:
            return guest_error, None, None, None
        draft.guests = parsed_guests

    elif step_before == "name" and draft.name is None and was_prompted_for_step_before:
        name = (parsed.detected_name or user_message).strip()
        draft.name = name or None
        if draft.name:
            await session_context_service.remember_name(db, session_id, draft.name)

    elif step_before == "phone" and draft.phone is None and was_prompted_for_step_before:
        phone = _parse_phone(user_message)
        if phone is None:
            return t("reservation_invalid_phone", lang), None, None, None
        draft.phone = phone
        await session_context_service.remember_phone(db, session_id, phone)
        # No returning-customer greeting here - see matching note in
        # _handle_checkout_flow.

    elif step_before == "email" and draft.email is None and was_prompted_for_step_before:
        email = _parse_email(user_message)
        if email is None:
            return t("invalid_email", lang), None, None, None
        draft.email = email
        await session_context_service.remember_email(db, session_id, email)

    elif (
        step_before == "special_requests"
        and not draft.special_requests_skipped
        and draft.special_requests is None
        and was_prompted_for_step_before
    ):
        if _normalize_word(user_message) in _SKIP_WORDS:
            draft.special_requests_skipped = True
        else:
            draft.special_requests = user_message.strip()

    elif step_before == "confirm" and was_prompted_for_step_before:
        if _is_negative(user_message):
            reservation_draft_service.clear_draft(session_id)
            return t("reservation_cancelled", lang), None, None, None

        if not _is_affirmative(user_message):
            return _confirm_summary_text(draft, lang), _CONFIRM_QUICK_REPLIES, None, None

        draft.confirmed = True

    elif step_before == "payment" and was_prompted_for_step_before:
        if _normalize_word(user_message) != _normalize_word(PAYMENT_COMPLETE_MESSAGE):
            draft.last_prompted_step = "payment"
            return t("reservation_payment_prompt", lang), None, None, _reservation_payment_request()

        reservation, availability = await reservation_service.create_reservation(
            db,
            user_id,
            draft.date,
            draft.time,
            draft.guests,
            draft.special_requests,
            draft.name,
            draft.phone,
            payment_status="mock_paid",
            guest_email=draft.email,
            is_birthday=bool(draft.is_birthday),
            location=draft.location,
        )

        if reservation is None:
            reservation_draft_service.clear_draft(session_id)
            alt_text = ""
            if availability["alternatives"]:
                alt_list = ", ".join(alt["time"].strftime("%I:%M %p") for alt in availability["alternatives"])
                alt_text = t("reservation_alternatives", lang, alts=alt_list)
            reason = t("reservation_unavailable", lang, reason=availability["reason"])
            return f"{reason}{alt_text}", None, None, None

        booked_text = t(
            "reservation_booked",
            lang,
            guests=draft.guests,
            date=draft.date.strftime("%b %d, %Y"),
            time=draft.time.strftime("%I:%M %p"),
            name=draft.name,
            phone=draft.phone,
            location=draft.location,
        )

        # Feedback-request prompt disabled for now - see matching note in
        # _handle_checkout_flow.

        if draft.email:
            sent = await email_service.send_reservation_confirmation(
                draft.email,
                draft.name,
                reservation.id,
                draft.date.strftime("%b %d, %Y"),
                draft.time.strftime("%I:%M %p"),
                draft.guests,
                draft.special_requests,
                location=draft.location,
            )
            if not sent:
                logger.error("reservation_confirmation_email.not_sent reservation_id=%s to=%s", reservation.id, draft.email)
            if draft.is_birthday:
                birthday_sent = await email_service.send_birthday_wish(draft.email, draft.name)
                if not birthday_sent:
                    logger.error("birthday_email.not_sent reservation_id=%s to=%s", reservation.id, draft.email)

        internal_sent = await email_service.send_internal_reservation_notification(
            reservation.id,
            draft.date.strftime("%b %d, %Y"),
            draft.time.strftime("%I:%M %p"),
            draft.guests,
            draft.name,
            draft.phone,
            draft.email,
            draft.special_requests,
            location=draft.location,
        )
        if not internal_sent:
            logger.error("internal_reservation_notification.not_sent reservation_id=%s", reservation.id)

        reservation_draft_service.clear_draft(session_id)
        return booked_text, None, None, None

    step = draft.next_step()
    draft.last_prompted_step = step

    if step == "location":
        location_prompt = t("reservation_ask_location", lang)
        return (
            (location_prompt if is_new_flow else f"{ack} {location_prompt}"),
            quick_reply_service.LOCATION_OPTIONS,
            None,
            None,
        )
    if step == "date":
        days = await quick_reply_service.day_options(db, location=draft.location)
        date_prompt = t("reservation_ask_date", lang)
        return (date_prompt if is_new_flow else f"{ack} {date_prompt}"), None, days, None
    if step == "time":
        time_choices = await quick_reply_service.time_options(db, draft.date, draft.guests or 1, location=draft.location)
        return f"{ack} {t('reservation_ask_time', lang)}", time_choices, None, None
    if step == "guests":
        return f"{ack} {t('reservation_ask_guests', lang)}", None, None, None
    if step == "name":
        return f"{ack} {t('reservation_ask_name', lang)}", None, None, None
    if step == "phone":
        return f"{ack} {t('reservation_ask_phone', lang)}", None, None, None
    if step == "email":
        return f"{ack} {t('reservation_ask_email', lang)}", None, None, None
    if step == "special_requests":
        return f"{ack} {t('reservation_ask_special_requests', lang)}", None, None, None
    if step == "confirm":
        return _confirm_summary_text(draft, lang), _CONFIRM_QUICK_REPLIES, None, None
    return f"{ack} {t('reservation_payment_prompt', lang)}", None, None, _reservation_payment_request()


async def _call_gemini(system_prompt: str, contents: list[types.Content]) -> tuple[GeminiChatOutput, int | None]:
    if settings.test_mode:
        return (
            GeminiChatOutput(
                reply_text="[TEST_MODE] mocked reply - no real Gemini call was made.",
                intent="general_chat",
                sentiment="neutral",
                language="en",
            ),
            0,
        )

    client = get_client()
    async with timed("gemini.generate_content"):
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=GeminiChatOutput,
                temperature=0.4,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

    parsed = response.parsed
    if not isinstance(parsed, GeminiChatOutput):
        parsed = GeminiChatOutput.model_validate_json(response.text)

    tokens_used = getattr(getattr(response, "usage_metadata", None), "total_token_count", None)
    return parsed, tokens_used


async def process_chat_message(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    user_id: int | None = None,
    address_coords: tuple[float, float] | None = None,
) -> dict:
    async with timed(f"chat_turn_total intent_hint={user_message[:24]!r}"):
        result = await _resolve_chat_result(db, session_id, user_message, user_id, address_coords)

    if result["sentiment"] in escalation_service.ESCALATION_SENTIMENTS:
        await escalation_service.log_escalation(db, session_id, user_message, result["sentiment"])

    return result


def _apply_menu_translation(result: dict) -> None:
    """Translates any menu-item payload into result["language"] right before
    it goes out - re-run on EVERY path that can carry menu_display/
    suggested_items, including a cache hit (see the cache_service.get_cached
    branch below). A cached entry's items were only ever translated using
    whatever this function looked like at the moment it was cached - without
    this also running on cache hits, an entry cached before this translation
    step existed (or under a differently-classified language) would keep
    serving stale/untranslated item names for its whole TTL. Both translate_*
    calls are safe to re-run on already-translated input - the lookup is
    keyed by the item's ENGLISH name, so a name that's already in Hindi/
    Marathi simply won't match and passes through unchanged."""
    if result.get("menu_display"):
        result["menu_display"] = menu_context.translate_menu_display(result["menu_display"], result["language"])
    if result.get("suggested_items"):
        result["suggested_items"] = menu_context.translate_suggested_items(result["suggested_items"], result["language"])


async def _confirm_pending_addon(db: AsyncSession, session_id: str, user_message: str, pending_addon: dict) -> dict:
    """Handles a clear "yes" to the just-suggested add-on directly, without a
    Gemini round-trip - the item id/name/language were already pinned down
    when the suggestion was made, so there's nothing left to interpret."""
    lang = pending_addon["language"]
    order = await order_service.get_or_create_draft_order(db, session_id, None)
    await order_service.add_item(db, order.id, pending_addon["item_id"], 1)
    await addon_service.clear_pending(db, session_id)

    order_summary = await order_service.get_order_summary(db, order.id)
    reply_text = t(
        "order_added",
        lang,
        qty=1,
        item=menu_context.translate_item_name(pending_addon["item_name"], lang),
        total=f"{order_summary['total']:.2f}",
    )

    result = {
        "reply_text": reply_text,
        "intent": "order",
        "sentiment": "neutral",
        "language": lang,
        "filters": None,
        "order_summary": order_summary,
    }
    _apply_menu_translation(result)
    await _save_turn(db, session_id, user_message, reply_text)
    return result


async def _resolve_chat_result(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    user_id: int | None,
    address_coords: tuple[float, float] | None = None,
) -> dict:
    if _is_emoji_only(user_message):
        result = {
            "reply_text": EMOJI_ONLY_REPLY,
            "intent": "general_chat",
            "sentiment": "confused",
            "language": "en",
            "filters": None,
        }
        await _save_turn(db, session_id, user_message, result["reply_text"])
        return result

    pending_addon = await addon_service.get_pending(db, session_id)
    if pending_addon is not None:
        # The quick-reply button label is the translated name (matching what
        # was actually shown/tapped) - matched here too so tapping "Add
        # Butter Croissant" behaves identically to a typed "yes", in
        # whatever language the suggestion was made in.
        pending_translated_name = menu_context.translate_item_name(pending_addon["item_name"], pending_addon["language"])
        if addon_service.is_affirmative(user_message, item_name=pending_translated_name):
            return await _confirm_pending_addon(db, session_id, user_message, pending_addon)

        if addon_service.is_ambiguous_filler(user_message):
            # A hedge like "maybe" carries no topic of its own to route
            # anywhere - unlike a real unrelated message, it must NOT be
            # handed to Gemini: Gemini still sees its own "Want to add X?"
            # turn in chat history and can bias toward reading a hedge as
            # confirmation, producing a genuine order_action=add that really
            # adds the item (not just a wrong reply string - this was the
            # actual bug). Short-circuited entirely instead.
            logger.info(
                "addon.ambiguous_filler_not_auto_added session=%s pending_item=%r user_message=%r",
                session_id,
                pending_addon["item_name"],
                user_message,
            )
            lang = pending_addon["language"]
            reply_text = t(
                "order_addon_ambiguous_nudge",
                lang,
                item=menu_context.translate_item_name(pending_addon["item_name"], lang),
            )
            await addon_service.clear_pending(db, session_id)
            result = {
                "reply_text": reply_text,
                "intent": "order",
                "sentiment": "neutral",
                "language": lang,
                "filters": None,
            }
            await _save_turn(db, session_id, user_message, reply_text)
            return result

        # Not a clear "yes" and not a content-free hedge - a genuine
        # unrelated/new message. Drop the pending suggestion and let it fall
        # through to normal intent routing below, same as if no add-on had
        # ever been suggested. Logged explicitly so it's visible in testing
        # that an ambiguous/unrelated reply was NOT silently added to the cart.
        logger.info(
            "addon.reply_not_auto_added session=%s pending_item=%r user_message=%r decline=%s",
            session_id,
            pending_addon["item_name"],
            user_message,
            addon_service.is_decline(user_message),
        )
        await addon_service.clear_pending(db, session_id)

    normalized_query = user_message.strip().lower()

    cached = cache_service.get_cached(normalized_query)
    if cached is not None:
        usage_logger.log_call(session_id=session_id, tokens_used=None, cached=True, fallback=False)
        _apply_menu_translation(cached)
        await _save_turn(db, session_id, user_message, cached["reply_text"])
        return cached

    if not rate_limiter.is_within_limits():
        usage_logger.log_call(session_id=session_id, tokens_used=None, cached=False, fallback=True)
        result = _fallback_result()
        await _save_turn(db, session_id, user_message, result["reply_text"])
        return result

    history = await _fetch_recent_history(db, session_id)
    dynamic_context = await _build_pre_call_context(db, user_message, session_id)
    system_prompt = build_system_prompt(dynamic_context)
    contents = _history_to_contents(history, user_message)

    try:
        parsed, tokens_used = await _call_gemini(system_prompt, contents)
    except Exception:
        logger.exception("Gemini API call failed for session %s", session_id)
        result = _fallback_result()
        await _save_turn(db, session_id, user_message, result["reply_text"])
        return result

    rate_limiter.record_call()
    usage_logger.log_call(session_id=session_id, tokens_used=tokens_used, cached=False, fallback=False)
    logger.debug(
        "gemini.parsed intent=%s order_action=%s filters=%s reservation_details=%s reply_text=%r",
        parsed.intent,
        parsed.order_action.model_dump() if parsed.order_action else None,
        parsed.filters.model_dump() if parsed.filters else None,
        parsed.reservation_details.model_dump() if parsed.reservation_details else None,
        parsed.reply_text,
    )

    if parsed.detected_name:
        await session_context_service.remember_name(db, session_id, parsed.detected_name)

    result = parsed.model_dump()

    known_phone_for_profile = await session_context_service.get_phone(db, session_id)
    if known_phone_for_profile:
        dietary = customer_profile_service.detect_dietary_preference(user_message)
        if dietary:
            await customer_profile_service.remember_dietary_preference(db, known_phone_for_profile, dietary)
        seating = customer_profile_service.detect_seating_preference(user_message)
        if seating:
            await customer_profile_service.remember_seating_preference(db, known_phone_for_profile, seating)

    feedback_excluded = (
        _is_order_summary_question(user_message)
        or _is_name_recall_question(user_message)
        or loyalty_service.is_loyalty_question(user_message)
    )
    if await feedback_service.is_pending(db, session_id) and not feedback_excluded:
        await feedback_service.clear_pending(db, session_id)
        mapped_sentiment = feedback_service.map_sentiment(parsed.sentiment)
        await feedback_service.save_feedback(db, session_id, known_phone_for_profile, user_message, mapped_sentiment)
        if result["sentiment"] in escalation_service.ESCALATION_SENTIMENTS:
            result["reply_text"] = t("escalation_response", result["language"], phone=CAFE_PHONE)
        else:
            result["reply_text"] = t("feedback_thank_you", parsed.language)
        await _save_turn(db, session_id, user_message, result["reply_text"])
        return result

    checkout_requested = (
        parsed.intent == "order" and parsed.order_action is not None and parsed.order_action.action == "checkout"
    )

    async with timed(f"intent_dispatch intent={parsed.intent}"):
        # Informational single-purpose lookups ALWAYS take priority over an
        # in-progress checkout/reservation flow - otherwise the flow hijacks an
        # off-topic question (e.g. "what did I order?" mid-checkout) and answers
        # it with its own next scripted question instead of the actual answer.
        if loyalty_service.is_loyalty_question(user_message):
            known_phone_for_loyalty = await session_context_service.get_phone(db, session_id)
            if known_phone_for_loyalty:
                points = await loyalty_service.get_points(db, known_phone_for_loyalty)
                loyalty_card = loyalty_service.format_loyalty_card(points)
                result["reply_text"] = (
                    f"You have {points} loyalty points! {loyalty_card['progress_label']} "
                    f"(next up: {loyalty_card['next_reward']})."
                )
                result["loyalty_card"] = loyalty_card
            else:
                result["reply_text"] = (
                    "I don't have a phone number on file for you yet this session - "
                    "place an order and I'll start tracking your points!"
                )
        elif _is_order_summary_question(user_message):
            result["reply_text"], result["order_summary"], result["menu_display"] = await _order_summary_reply(
                db, session_id, parsed.language
            )
        elif _is_name_recall_question(user_message):
            known_name = await session_context_service.get_name(db, session_id)
            if known_name:
                result["reply_text"] = f"You're {known_name}! Good to chat with you again."
            else:
                result["reply_text"] = (
                    "I don't have a name on file for you yet this session - "
                    "let me know your name and I'll remember it!"
                )
        else:
            active_res_draft = await reservation_draft_service.get_draft(db, session_id)
            reservation_in_progress = active_res_draft is not None and active_res_draft.next_step() is not None

            active_checkout_draft = await checkout_draft_service.get_draft(db, session_id)
            checkout_in_progress = active_checkout_draft is not None and active_checkout_draft.next_step() is not None

            if reservation_in_progress or parsed.intent == "reservation":
                (
                    result["reply_text"],
                    result["quick_reply_options"],
                    result["date_picker_options"],
                    result["payment_request"],
                ) = await _handle_reservation_intent(db, parsed, session_id, user_id, user_message)
                await reservation_draft_service.sync_draft(db, session_id)
            elif checkout_in_progress or checkout_requested:
                (
                    result["reply_text"],
                    result["quick_reply_options"],
                    result["order_summary"],
                    result["payment_request"],
                    result["loyalty_card"],
                    result["menu_display"],
                ) = await _handle_checkout_flow(db, parsed, session_id, user_id, user_message, address_coords)
                await checkout_draft_service.sync_draft(db, session_id)
                draft_after = await checkout_draft_service.get_draft(db, session_id)
                result["awaiting_address_input"] = bool(
                    draft_after is not None and draft_after.last_prompted_step == "address"
                )
            elif parsed.intent == "menu_search" and _is_broad_menu_query(parsed.filters):
                result["menu_display"] = await menu_context.get_full_menu_display(db)
            elif parsed.intent in GROUNDABLE_INTENTS:
                result["reply_text"], result["suggested_items"] = await _ground_reply(db, parsed, user_message)
            elif parsed.intent == "order":
                result["reply_text"], result["order_summary"], result["menu_display"] = await _handle_order_intent(
                    db, parsed, session_id, user_id
                )
                # If this turn just suggested an add-on (see the
                # addon_service.mark_pending call inside _handle_order_intent),
                # offer it as tappable buttons instead of relying on the
                # customer to type a reply at all - removes the free-text
                # ambiguity risk (see addon.ambiguous_filler_not_auto_added)
                # entirely for anyone who taps rather than types.
                pending_addon_for_buttons = await addon_service.get_pending(db, session_id)
                if pending_addon_for_buttons is not None:
                    translated_name = menu_context.translate_item_name(
                        pending_addon_for_buttons["item_name"], pending_addon_for_buttons["language"]
                    )
                    result["quick_reply_options"] = addon_service.confirm_quick_replies(translated_name)
            elif parsed.intent == "faq" and _is_about_question(user_message):
                result["reply_text"] = _build_about_reply(parsed.language)
            elif parsed.intent == "faq" and _is_location_question(user_message):
                result["reply_text"] = t("faq_location_intro", parsed.language)
                result["location_cards"] = [dict(loc) for loc in CAFE_LOCATIONS]
            elif parsed.intent == "general_chat" and (
                quick_reply_service.is_capability_question(user_message) or quick_reply_service.is_greeting(user_message)
            ):
                result["quick_reply_options"] = list(quick_reply_service.QUICK_ACTION_OPTIONS)

    _apply_menu_translation(result)

    if result["sentiment"] in escalation_service.ESCALATION_SENTIMENTS:
        result["reply_text"] = t("escalation_response", result["language"], phone=CAFE_PHONE)
        result["quick_reply_options"] = None
        result["date_picker_options"] = None
        result["payment_request"] = None
        result["menu_display"] = None
        result["suggested_items"] = None
        result["loyalty_card"] = None
        result["location_cards"] = None

    await _save_turn(db, session_id, user_message, result["reply_text"])

    if parsed.intent in CACHEABLE_INTENTS:
        cache_service.set_cached(normalized_query, result)

    return result
