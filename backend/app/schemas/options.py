from pydantic import BaseModel


class OptionItem(BaseModel):
    key: str
    label: str
    type: str
    default: str | int | float | bool | None
    choices: list[str] | None = None
    min: int | float | None = None
    max: int | float | None = None
    help: str


class OptionResponse(BaseModel):
    core: list[OptionItem]
    advanced: list[OptionItem]
