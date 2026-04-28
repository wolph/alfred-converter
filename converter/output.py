from __future__ import annotations

import json
import sys
import typing
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    title: str
    subtitle: typing.Optional[str] = None
    arg: typing.Optional[str] = None
    uid: typing.Optional[str] = None
    valid: bool = True
    icon: typing.Optional[str] = None
    autocomplete: typing.Optional[str] = None
    text_copy: typing.Optional[str] = None
    text_largetype: typing.Optional[str] = None

    def to_alfred(self) -> typing.Dict[str, typing.Any]:
        data: typing.Dict[str, typing.Any] = {
            "title": self.title,
            "valid": self.valid,
        }
        if self.uid is not None:
            data["uid"] = self.uid
        if self.subtitle is not None:
            data["subtitle"] = self.subtitle
        if self.arg is not None:
            data["arg"] = self.arg
            text_copy = (
                self.text_copy if self.text_copy is not None else self.arg
            )
            data["text"] = {
                "copy": text_copy,
                "largetype": (
                    self.text_largetype
                    if self.text_largetype is not None
                    else self.arg
                ),
            }
        if self.autocomplete is not None:
            data["autocomplete"] = self.autocomplete
        if self.icon is not None:
            data["icon"] = {"path": self.icon}
        return data


@dataclass(frozen=True)
class Response:
    items: typing.List[Item] = field(default_factory=list)
    skipknowledge: bool = False
    rerun: typing.Optional[float] = None

    def to_alfred(self) -> typing.Dict[str, typing.Any]:
        data: typing.Dict[str, typing.Any] = {
            "items": [item.to_alfred() for item in self.items],
        }
        if self.skipknowledge:
            data["skipknowledge"] = True
        if self.rerun is not None:
            data["rerun"] = self.rerun
        return data


def _valid_from_attrib(value: typing.Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"yes", "true", "1"}


def _optional_str(value: typing.Any) -> typing.Optional[str]:
    if value is None:
        return None
    return str(value)


def item_creator():
    def create_item(attrib=None, **kwargs):
        attrib = attrib or {}
        return Item(
            title=str(kwargs["title"]),
            subtitle=kwargs.get("subtitle"),
            icon=kwargs.get("icon"),
            uid=_optional_str(attrib.get("uid")),
            arg=_optional_str(attrib.get("arg")),
            valid=_valid_from_attrib(attrib.get("valid", True)),
            autocomplete=_optional_str(attrib.get("autocomplete")),
        )

    return create_item


def render_json(response: Response) -> str:
    return json.dumps(response.to_alfred(), ensure_ascii=False)


def write_json(response: Response) -> None:
    sys.stdout.write(render_json(response))
