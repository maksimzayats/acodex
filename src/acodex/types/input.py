from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias


@dataclass(frozen=True, slots=True)
class UserInputText:
    """A text input to send to the agent."""

    text: str
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True, slots=True)
class UserInputLocalImage:
    """A local image input to send to the agent."""

    path: str
    type: Literal["local_image"] = field(default="local_image", init=False)


UserInput: TypeAlias = UserInputText | UserInputLocalImage
Input: TypeAlias = str | list[UserInput]
