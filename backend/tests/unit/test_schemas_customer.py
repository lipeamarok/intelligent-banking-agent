"""
Unit tests for app/schemas/customer.py
"""

import pytest
from pydantic import ValidationError

from app.schemas.customer import Customer


def test_valid_customer_passes():
    customer = Customer(
        cpf="12345678901",
        data_nascimento="1990-06-15",
        nome="Maria Silva",
        score_atual=700,
        limite_credito=5000.0,
    )
    assert customer.cpf == "12345678901"
    assert customer.score_atual == 700
    assert customer.limite_credito == 5000.0


def test_customer_score_below_zero_fails():
    with pytest.raises(ValidationError):
        Customer(
            cpf="12345678901",
            data_nascimento="1990-06-15",
            nome="Maria Silva",
            score_atual=-1,
            limite_credito=0.0,
        )


def test_customer_score_above_1000_fails():
    with pytest.raises(ValidationError):
        Customer(
            cpf="12345678901",
            data_nascimento="1990-06-15",
            nome="Maria Silva",
            score_atual=1001,
            limite_credito=0.0,
        )


def test_customer_score_boundary_zero_passes():
    customer = Customer(
        cpf="12345678901",
        data_nascimento="1990-06-15",
        nome="Maria Silva",
        score_atual=0,
        limite_credito=0.0,
    )
    assert customer.score_atual == 0


def test_customer_score_boundary_1000_passes():
    customer = Customer(
        cpf="12345678901",
        data_nascimento="1990-06-15",
        nome="Maria Silva",
        score_atual=1000,
        limite_credito=0.0,
    )
    assert customer.score_atual == 1000


def test_customer_negative_limit_fails():
    with pytest.raises(ValidationError):
        Customer(
            cpf="12345678901",
            data_nascimento="1990-06-15",
            nome="Maria Silva",
            score_atual=500,
            limite_credito=-1.0,
        )


def test_customer_zero_limit_passes():
    customer = Customer(
        cpf="12345678901",
        data_nascimento="1990-06-15",
        nome="Maria Silva",
        score_atual=500,
        limite_credito=0.0,
    )
    assert customer.limite_credito == 0.0


def test_customer_invalid_date_format_fails():
    with pytest.raises(ValidationError):
        Customer(
            cpf="12345678901",
            data_nascimento="15/06/1990",
            nome="Maria Silva",
            score_atual=500,
            limite_credito=1000.0,
        )


def test_customer_valid_iso_date_passes():
    customer = Customer(
        cpf="12345678901",
        data_nascimento="2000-01-01",
        nome="João Costa",
        score_atual=300,
        limite_credito=2000.0,
    )
    assert customer.data_nascimento == "2000-01-01"
