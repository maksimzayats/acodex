from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict


class UserInputText(TypedDict):
    """A text input to send to the agent."""

    type: Literal["text"]
    text: str


class UserInputLocalImage(TypedDict):
    """A local image input to send to the agent."""

    type: Literal["local_image"]
    path: str


UserInput: TypeAlias = UserInputText | UserInputLocalImage
Input: TypeAlias = str | list[UserInput]
