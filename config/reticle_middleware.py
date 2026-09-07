"""Dev-only Reticle SDK injection. Never runs when DEBUG is False."""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils.html import escapejs

_SNIPPET_TEMPLATE = """
<script type="module">
  import { reticle } from 'https://cdn.jsdelivr.net/npm/@reticlehq/browser@2.13.1/+esm';
  reticle.connect({ token: '%s' });
</script>
"""


def _pairing_token() -> str:
    env = os.getenv("RETICLE_TOKEN", "").strip()
    if env:
        return env
    path = Path.home() / ".reticle" / "pairing-token"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class ReticleDevMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if not settings.DEBUG:
            return response
        if "text/html" not in response.get("Content-Type", ""):
            return response
        if getattr(response, "streaming", False):
            return response
        token = _pairing_token()
        if not token:
            return response
        try:
            content = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response
        snippet = _SNIPPET_TEMPLATE % escapejs(token)
        if "</head>" in content:
            content = content.replace("</head>", snippet + "</head>", 1)
        elif "</body>" in content:
            content = content.replace("</body>", snippet + "</body>", 1)
        else:
            return response
        response.content = content.encode(response.charset or "utf-8")
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response
