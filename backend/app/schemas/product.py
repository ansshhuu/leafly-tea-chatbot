from pydantic import BaseModel, ConfigDict


class SizeOption(BaseModel):
    size: str
    price: float


class ProductBase(BaseModel):
    name: str
    description: str | None = None
    price: float
    compare_at_price: float | None = None
    origin: str | None = None
    tea_type: str | None = None
    caffeine_level: str | None = None
    size_options: list[SizeOption] = []
    badge: str | None = None
    is_hamper: bool = False
    hamper_contents: list[str] = []
    tags: list[str] = []
    image_url: str | None = None
    available: bool = True


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
