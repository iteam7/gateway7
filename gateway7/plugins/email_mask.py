"""Mask conventional ASCII email addresses in message history and model output.

This is a bounded dot-atom/domain detector, not a full RFC mailbox parser. It
rejects quoted local parts, IP domains, single-label domains and Unicode mailbox
names rather than masking a misleading substring. Originals are never retained.
"""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway7.plugin_api import PluginDescriptor
from gateway7.text_policy import TextPolicyMiddleware


# Every repetition is bounded. Unicode word boundaries prevent partial matches
# inside non-ASCII identifiers; only ASCII mailbox characters are recognized.
_ATOM = r"A-Za-z0-9!#$%&'*+/=?^_`{|}~-"
_EMAIL = re.compile(
    rf"(?<![\w.!#$%&'*+/=?^`{{|}}~@-])"
    rf"[{_ATOM}]{{1,64}}(?:\.[{_ATOM}]{{1,64}}){{0,31}}@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.){1,126}"
    r"[A-Za-z]{2,63}"
    r"(?![\w@-]|\.[\w@-])"
)


def mask_email(text: str, replacement: str) -> str:
    def replace(match: re.Match[str]) -> str:
        candidate = match.group(0)
        local, _ = candidate.split("@", 1)
        # Syntax-level bounds alone allow long dot-separated local parts.
        if len(candidate) > 254 or len(local) > 64:
            return candidate
        return replacement

    return _EMAIL.sub(replace, text)


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    phase: Literal["request", "response", "both"] = "both"
    replacement: str = Field(default="[EMAIL]", min_length=1, max_length=128)


@dataclass(frozen=True, init=False)
class EmailMaskPlugin(TextPolicyMiddleware):
    def __init__(self, settings: Settings) -> None:
        def transform(text: str) -> tuple[str, int]:
            return mask_email(text, settings.replacement), int(mask_email(text, "") != text)

        super().__init__(transform, phase=settings.phase, action="redact")


def create(settings: Settings) -> EmailMaskPlugin:
    return EmailMaskPlugin(settings)


PLUGIN = PluginDescriptor(
    id="email-mask", api_version=2, settings_model=Settings, create=create, supports_tools=True
)
