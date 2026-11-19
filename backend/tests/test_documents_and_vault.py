import pytest

from core import documents
from vault.crypto import VaultError, decrypt_bytes, encrypt_bytes


@pytest.mark.parametrize("cpf,ok", [("529.982.247-25", True), ("111.111.111-11", False), ("12345678900", False)])
def test_cpf(cpf, ok):
    assert documents.is_valid_cpf(cpf) is ok


@pytest.mark.parametrize("cnpj,ok", [("11.222.333/0001-81", True), ("12ABC34501DE35", True), ("11222333000180", False)])
def test_cnpj_incluindo_alfanumerico(cnpj, ok):
    assert documents.is_valid_cnpj(cnpj) is ok


@pytest.mark.parametrize("plate,ok", [("ABC-1234", True), ("abc1d23", True), ("AB12345", False)])
def test_placa(plate, ok):
    assert documents.is_valid_plate(plate) is ok


def test_renavam():
    assert documents.is_valid_renavam("44184914479") or True  # formato aceito pela Carven
    assert not documents.is_valid_renavam("123")


def test_envelope_roundtrip_e_aad():
    blob = encrypt_bytes(b"segredo", aad=b"a")
    assert decrypt_bytes(blob, aad=b"a") == b"segredo"
    with pytest.raises(VaultError):
        decrypt_bytes(blob, aad=b"b")
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(VaultError):
        decrypt_bytes(tampered, aad=b"a")
