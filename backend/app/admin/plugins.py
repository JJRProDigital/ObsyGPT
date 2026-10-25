"""Admin plugin and marketplace endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import audit as audit_module
from ..auth import routes as auth


router = APIRouter()


class PluginInstallPayload(BaseModel):
    source: Literal["local", "marketplace"]
    slug: str = Field(min_length=2, max_length=60)
    marketplace_name: str | None = Field(default=None, max_length=100)


class PluginMarketplacePayload(BaseModel):
    url: str = Field(min_length=8, max_length=500)


@router.get("/plugins")
def list_plugins(request: Request):
    auth.require_admin(request)
    from ..plugins import service

    installed = service.list_installed()
    catalog = []
    for entry in service.scan_catalog():
        manifest = entry["manifest"]
        plugin = installed.get(manifest["slug"])
        catalog.append(
            {
                "slug": manifest["slug"],
                "name": manifest["name"],
                "version": manifest["version"],
                "description": manifest["description"],
                "source": entry["source"],
                "marketplace_name": entry.get("marketplace_name"),
                "installed": plugin is not None,
                "connectors": manifest["connectors"],
                "components": {"skills": len(manifest["skills"]), "mcps": len(manifest["mcps"]), "agents": len(manifest["agents"])},
            }
        )
    return {"plugins": catalog, "marketplaces": service.list_marketplaces()}


@router.post("/plugins/install")
def install_plugin(payload: PluginInstallPayload, request: Request):
    auth.require_admin(request)
    from ..plugins import service

    try:
        entry = service.find_catalog_entry(payload.source, payload.slug, payload.marketplace_name)
        result = service.install_plugin(entry)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin.installed",
        target_type="plugin",
        target_id=None,
        metadata={"slug": payload.slug, "source": payload.source},
    )
    return {"installed": result}


@router.delete("/plugins/{slug}")
def uninstall_plugin(slug: str, request: Request):
    auth.require_admin(request)
    from ..plugins import service

    try:
        result = service.uninstall_plugin(slug)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin.uninstalled",
        target_type="plugin",
        target_id=None,
        metadata={"slug": slug},
    )
    return {"uninstalled": result}


@router.post("/plugin-marketplaces")
def add_plugin_marketplace(payload: PluginMarketplacePayload, request: Request):
    auth.require_admin(request)
    from ..plugins import service

    try:
        marketplace = service.add_marketplace(payload.url)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin_marketplace.added",
        target_type="plugin",
        target_id=None,
        metadata={"name": marketplace["name"], "url": marketplace["url"]},
    )
    return {"marketplace": marketplace}


@router.post("/plugin-marketplaces/{name}/refresh")
def refresh_plugin_marketplace(name: str, request: Request):
    auth.require_admin(request)
    from ..plugins import service

    try:
        result = service.refresh_marketplace(name)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"refreshed": result}


@router.delete("/plugin-marketplaces/{name}")
def remove_plugin_marketplace(name: str, request: Request):
    auth.require_admin(request)
    from ..plugins import service

    if not service.remove_marketplace(name):
        raise HTTPException(status_code=404, detail="Marketplace not found.")
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin_marketplace.removed",
        target_type="plugin",
        target_id=None,
        metadata={"name": name},
    )
    return {"name": name, "deleted": True}
