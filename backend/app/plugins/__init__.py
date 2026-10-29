"""Plugins: shareable packages bundling skills, MCP servers, and sub-agent definitions."""

from .manifest import load_manifest, validate_manifest
from . import service

__all__ = ["load_manifest", "service", "validate_manifest"]
