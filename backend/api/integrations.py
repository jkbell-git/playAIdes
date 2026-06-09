# backend/api/integrations.py
"""Integrations console API — provider connect / configure / scan / map / invoke.

A self-contained APIRouter (no server-instance state) mounted by the app. All
routes sit behind require_api_key (router-level dependency). The HA token is
write-only: POSTed once, persisted, never returned.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import require_api_key
from backend.stores import config_store, secrets_store
from backend.clients.providers import registry

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["integrations"],
    dependencies=[Depends(require_api_key)],
)


class ConfigBody(BaseModel):
    config: dict = {}


class SecretBody(BaseModel):
    key: str
    value: str


class MappingsBody(BaseModel):
    mappings: dict = {}


class InvokeBody(BaseModel):
    capability: str
    target: str
    args: dict = {}


@router.get("")
async def list_integrations():
    store = config_store.load()
    providers = []
    for pid, pconf in (store.get("providers") or {}).items():
        providers.append({
            "id": pid,
            "kind": pconf.get("kind"),
            "enabled": pconf.get("enabled", True),
            "config": pconf.get("config", {}),  # never includes secrets
        })
    return {"providers": providers}


@router.post("/{provider_id}/config")
async def set_integration_config(provider_id: str, body: ConfigBody):
    store = config_store.load()
    prov = store.setdefault("providers", {}).setdefault(provider_id, {})
    prov.setdefault("kind", provider_id)
    prov.setdefault("enabled", True)
    prov["config"] = {**prov.get("config", {}), **body.config}
    config_store.save(store)
    return {"ok": True}


@router.post("/{provider_id}/secret")
async def set_integration_secret(provider_id: str, body: SecretBody):
    # Write-only: persist server-side, never echo the value back.
    secrets_store.set_secret(provider_id, body.key, body.value)
    return {"ok": True, "key": body.key}


@router.get("/{provider_id}/health")
async def integration_health(provider_id: str):
    provider = registry.build_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown or disabled provider")
    status = await asyncio.to_thread(provider.health)
    return {"ok": status.ok, "reason": status.reason}


@router.post("/{provider_id}/scan")
async def scan_integration(provider_id: str):
    provider = registry.build_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown or disabled provider")
    items = await asyncio.to_thread(provider.discover)
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it.domain, []).append({
            "id": it.id, "domain": it.domain, "name": it.name,
            "capabilities": it.capabilities,
        })
    return {"groups": groups}


@router.get("/{provider_id}/mappings")
async def get_integration_mappings(provider_id: str):
    store = config_store.load()
    return {"mappings": store.get("mappings", {})}


@router.put("/{provider_id}/mappings")
async def put_integration_mappings(provider_id: str, body: MappingsBody):
    store = config_store.load()
    store["mappings"] = body.mappings
    config_store.save(store)
    return {"ok": True}


@router.post("/{provider_id}/invoke")
async def invoke_integration(provider_id: str, body: InvokeBody):
    provider = registry.build_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown or disabled provider")
    return await asyncio.to_thread(provider.invoke, body.capability, body.target, body.args)
