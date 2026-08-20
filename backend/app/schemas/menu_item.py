from pydantic import BaseModel, ConfigDict


class MenuItemBase(BaseModel):
    name: str
    description: str | None = None
    price: float
    category: str
    is_veg: bool = True
    is_vegan: bool = False
    is_gluten_free: bool = False
    spice_level: int = 0
    tags: list[str] = []
    image_url: str | None = None
    available: bool = True


class MenuItemCreate(MenuItemBase):
    pass


class MenuItemRead(MenuItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
