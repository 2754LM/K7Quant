"""自定义规则/查询 API (落库到 custom_rules)"""
from fastapi import APIRouter
from pydantic import BaseModel

from backend.common.storage import crud


router = APIRouter()


class RuleRequest(BaseModel):
    name: str
    description: str = ""
    rule_json: dict = {}


@router.get("/list")
def list_all():
    return {"rules": crud.list_rules()}


@router.post("/create")
def create(req: RuleRequest):
    rid = crud.create_rule(req.name, req.description, req.rule_json)
    return {"ok": True, "id": rid}


@router.delete("/{rule_id}")
def delete(rule_id: int):
    crud.delete_rule(rule_id)
    return {"ok": True}
