from pydantic import BaseModel
from pydantic import Field


class CrowdReadingCreate(BaseModel):
    person_count: int = Field(ge=0)
    threshold: int | None = Field(default=None, gt=0)
    camera_id: int | None = None
