"""Unit tests for field path getter and setter utility."""

import pytest
from pydantic import BaseModel

from document_engine.core.field_paths import (
    get_field_value,
    parse_field_path,
    set_field_value,
)


class SubModel(BaseModel):
    tax_id: str = "0101234567"
    name: str = "Test Seller"


class LineItem(BaseModel):
    description: str
    amount: float


class SampleEnvelope(BaseModel):
    seller: SubModel
    line_items: list[LineItem]


def test_parse_field_path_valid():
    assert parse_field_path("common.seller.tax_id") == [
        ("common", None),
        ("seller", None),
        ("tax_id", None),
    ]
    assert parse_field_path("line_items[0].description") == [
        ("line_items", 0),
        ("description", None),
    ]
    assert parse_field_path("meter_readings[2].consumption") == [
        ("meter_readings", 2),
        ("consumption", None),
    ]


def test_parse_field_path_invalid():
    with pytest.raises(ValueError, match="non-empty string"):
        parse_field_path("")
    with pytest.raises(ValueError, match="Invalid field path token"):
        parse_field_path("common..seller")
    with pytest.raises(ValueError, match="Invalid field path token"):
        parse_field_path("items[-1]")


def test_get_field_value_dict():
    data = {
        "common": {"seller": {"tax_id": "0109998888"}},
        "items": [{"name": "Item A", "price": 100}],
    }
    assert get_field_value(data, "common.seller.tax_id") == "0109998888"
    assert get_field_value(data, "items[0].name") == "Item A"
    assert get_field_value(data, "items[0].price") == 100


def test_get_field_value_pydantic():
    env = SampleEnvelope(
        seller=SubModel(tax_id="0105554444", name="Seller Inc"),
        line_items=[
            LineItem(description="Item 1", amount=150.0),
            LineItem(description="Item 2", amount=250.0),
        ],
    )
    assert get_field_value(env, "seller.tax_id") == "0105554444"
    assert get_field_value(env, "line_items[1].description") == "Item 2"
    assert get_field_value(env, "line_items[0].amount") == 150.0


def test_get_field_value_out_of_bounds():
    env = SampleEnvelope(
        seller=SubModel(),
        line_items=[LineItem(description="Item 1", amount=100.0)],
    )
    with pytest.raises(IndexError):
        get_field_value(env, "line_items[5].description")


def test_set_field_value_dict():
    data = {
        "common": {"document_number": "HD-001"},
        "items": [{"qty": 10}, {"qty": 20}],
    }
    set_field_value(data, "common.document_number", "HD-999")
    assert data["common"]["document_number"] == "HD-999"

    set_field_value(data, "items[1].qty", 50)
    assert data["items"][1]["qty"] == 50


def test_set_field_value_pydantic():
    env = SampleEnvelope(
        seller=SubModel(tax_id="0101112222", name="Old Name"),
        line_items=[LineItem(description="Item 1", amount=100.0)],
    )
    set_field_value(env, "seller.name", "New Name")
    assert env.seller.name == "New Name"

    set_field_value(env, "line_items[0].amount", 999.0)
    assert env.line_items[0].amount == 999.0
