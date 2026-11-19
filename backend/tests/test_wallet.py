import pytest

from core.exceptions import InsufficientBalance
from wallet import service as wallet
from wallet.models import LedgerEntry


def balance(org):
    return wallet.get_wallet(org).balance_cents


def test_reserva_captura_estorno(funded):
    res = wallet.reserve(funded, 30_00, "teste", ref_type="t", ref_id="1")
    assert balance(funded) == 70_00
    wallet.capture(res)
    assert balance(funded) == 70_00

    res2 = wallet.reserve(funded, 20_00, "teste", ref_type="t", ref_id="2")
    wallet.release(res2)
    wallet.release(res2)  # idempotente
    assert balance(funded) == 70_00


def test_captura_parcial_devolve_diferenca(funded):
    res = wallet.reserve(funded, 30_00, "teste", ref_type="t", ref_id="1")
    wallet.capture(res, final_cents=10_00)
    assert balance(funded) == 90_00


def test_sem_saldo(org):
    with pytest.raises(InsufficientBalance):
        wallet.reserve(org, 1, "teste", ref_type="t", ref_id="1")


def test_credito_idempotente_e_saldo_bate_com_razao(funded):
    wallet.credit(funded, 10_00, "x", key="k1")
    wallet.credit(funded, 10_00, "x", key="k1")
    total = sum(LedgerEntry.objects.filter(wallet__organization=funded).values_list("amount_cents", flat=True))
    assert total == balance(funded) == 110_00


def test_lancamento_imutavel(funded):
    entry = LedgerEntry.objects.first()
    entry.amount_cents = 1
    with pytest.raises(ValueError):
        entry.save()
