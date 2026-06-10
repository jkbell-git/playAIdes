"""REST surface for the persona domain (spec 2026-06-10, component 4).

Mirrors backend/api/conversation.py: a self-contained APIRouter behind
require_api_key, reaching its service via request.app.state (503 when absent).
History gets NO REST surface this slice — rehydration stays on the WS
history_loaded frame at activation.

Status mapping (spec table): PersonaNotFound → 404; PersonaExists → 409;
PersonaActive → 409; pydantic ValidationError → 422; store ValueError
(path-traversal guard) → 404 without leaking guard details. NOTE:
ValidationError subclasses ValueError, so it MUST be caught first.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError

from backend.api.deps import require_api_key
from backend.services.persona import PersonaActive, PersonaExists, PersonaNotFound

router = APIRouter(
    prefix="/api/v1",
    tags=["personas"],
    dependencies=[Depends(require_api_key)],
)


class PersonaCreateIn(BaseModel):
    name: str
    description: str = ""


def _service(request: Request):
    svc = getattr(request.app.state, "persona_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="persona service unavailable")
    return svc


def _not_found(persona_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"persona not found: {persona_id}")


@router.get("/personas")
def list_personas(request: Request) -> list:
    return _service(request).list()


@router.post("/personas", status_code=201)
def create_persona(body: PersonaCreateIn, request: Request) -> dict:
    try:
        return _service(request).create(body.name, body.description)
    except PersonaExists:
        raise HTTPException(status_code=409, detail=f"persona already exists: {body.name}")


@router.get("/personas/{persona_id}")
def get_persona(persona_id: str, request: Request) -> dict:
    try:
        return _service(request).get(persona_id)
    except (PersonaNotFound, ValueError):
        raise _not_found(persona_id)


@router.put("/personas/{persona_id}")
def update_persona(persona_id: str, body: dict, request: Request) -> dict:
    try:
        return _service(request).update(persona_id, body)
    except PersonaNotFound:
        raise _not_found(persona_id)
    except ValidationError as e:           # before ValueError — it subclasses it
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError:
        raise _not_found(persona_id)


@router.delete("/personas/{persona_id}", status_code=204)
def delete_persona(persona_id: str, request: Request) -> Response:
    try:
        _service(request).delete(persona_id)
    except PersonaNotFound:
        raise _not_found(persona_id)
    except PersonaActive:
        raise HTTPException(status_code=409, detail="cannot delete the active persona")
    except ValueError:
        raise _not_found(persona_id)
    return Response(status_code=204)


@router.get("/personas/{persona_id}/triggers")
def get_triggers(persona_id: str, request: Request) -> list:
    try:
        return _service(request).get_triggers(persona_id)
    except (PersonaNotFound, ValueError):
        raise _not_found(persona_id)


@router.put("/personas/{persona_id}/triggers")
def replace_triggers(persona_id: str, request: Request, triggers: list = Body(...)) -> list:
    try:
        return _service(request).replace_triggers(persona_id, triggers)
    except PersonaNotFound:
        raise _not_found(persona_id)
    except ValidationError as e:           # before ValueError — it subclasses it
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError:
        raise _not_found(persona_id)
