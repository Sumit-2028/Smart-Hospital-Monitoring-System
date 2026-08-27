from pydantic import BaseModel


class CrowdReadingCreate(BaseModel):
    person_count: int
    threshold: int = 20