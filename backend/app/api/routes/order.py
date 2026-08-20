from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.order_action import OrderActionRequest, OrderActionResponse, OrderSummaryResponse
from app.services import order_service

router = APIRouter()


@router.post("/action", response_model=OrderActionResponse)
async def order_action(payload: OrderActionRequest, db: AsyncSession = Depends(get_db)) -> OrderActionResponse:
    order = await order_service.get_or_create_draft_order(db, payload.session_id, payload.user_id)

    menu_item_id = payload.menu_item_id
    if menu_item_id is None and payload.item_name:
        menu_item = await order_service.resolve_menu_item(db, payload.item_name)
        if menu_item is None:
            raise HTTPException(status_code=404, detail=f'No menu item found matching "{payload.item_name}"')
        menu_item_id = menu_item.id

    try:
        if payload.action == "add":
            if menu_item_id is None:
                raise HTTPException(status_code=422, detail="menu_item_id or item_name is required to add an item")
            await order_service.add_item(db, order.id, menu_item_id, payload.quantity or 1)
            message = "Item added."
        elif payload.action == "remove":
            if menu_item_id is None:
                raise HTTPException(status_code=422, detail="menu_item_id or item_name is required to remove an item")
            await order_service.remove_item(db, order.id, menu_item_id)
            message = "Item removed."
        elif payload.action == "modify":
            if menu_item_id is None or payload.quantity is None:
                raise HTTPException(
                    status_code=422, detail="menu_item_id/item_name and quantity are required to modify"
                )
            await order_service.update_quantity(db, order.id, menu_item_id, payload.quantity)
            message = "Quantity updated."
        elif payload.action == "checkout":
            await order_service.checkout(db, order.id)
            message = "Order confirmed."
        elif payload.action == "clear":
            await order_service.clear_cart(db, order.id)
            message = "Cart cleared."
        else:
            message = "Here's your order summary."
    except order_service.OrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    summary = await order_service.get_order_summary(db, order.id)
    return OrderActionResponse(message=message, summary=summary)


@router.get("/{order_id}/summary", response_model=OrderSummaryResponse)
async def order_summary(order_id: int, db: AsyncSession = Depends(get_db)) -> OrderSummaryResponse:
    summary = await order_service.get_order_summary(db, order_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return summary
