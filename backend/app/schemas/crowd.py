from pydantic import BaseModel
from pydantic import Field


class CrowdReadingCreate(BaseModel):
    person_count: int = Field(ge=0)
    threshold: int = Field(gt=0)
