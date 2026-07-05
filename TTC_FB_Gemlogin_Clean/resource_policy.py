# -*- coding: utf-8 -*-
"""Resource blocking policy for Playwright pages/contexts.

This module only optimizes browser resource loading. It does not replay or forge
platform requests.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourcePolicy:
    enabled: bool = True
    block_images: bool = True
    block_media: bool = True
    block_fonts: bool = True
    block_stylesheets: bool = False

    @classmethod
    def from_config(cls, cfg: dict | None):
        cfg = cfg or {}
        nested = cfg.get("resource_blocking") or {}
        return cls(
            enabled=bool(cfg.get("resource_blocking_enabled", nested.get("enabled", True))),
            block_images=bool(cfg.get("block_images", nested.get("block_images", True))),
            block_media=bool(cfg.get("block_media", nested.get("block_media", True))),
            block_fonts=bool(cfg.get("block_fonts", nested.get("block_fonts", True))),
            block_stylesheets=bool(cfg.get("block_stylesheets", nested.get("block_stylesheets", False))),
        )

    def should_block(self, resource_type: str, url: str = "") -> bool:
        if not self.enabled:
            return False
        resource_type = (resource_type or "").lower()
        if resource_type == "image":
            return self.block_images
        if resource_type == "media":
            return self.block_media
        if resource_type == "font":
            return self.block_fonts
        if resource_type == "stylesheet":
            return self.block_stylesheets
        return False


def apply_resource_policy(context, policy: ResourcePolicy | None):
    """Attach a route handler to a Playwright browser context."""
    policy = policy or ResourcePolicy(enabled=False)
    if context is None or not policy.enabled:
        return

    def _route(route):
        try:
            request = route.request
            if policy.should_block(request.resource_type, request.url):
                return route.abort()
            return route.continue_()
        except Exception:
            try:
                return route.continue_()
            except Exception:
                return None

    try:
        context.route("**/*", _route)
    except Exception as exc:
        print(f"[ResourcePolicy] route attach failed: {exc}")
