"""Leitura de extrato OFX (SGML 1.x ou XML 2.x), como os bancos brasileiros exportam."""

import re
from datetime import date

from core.exceptions import BusinessError

_TX = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", re.S | re.I)


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}>([^<\r\n]*)", block, re.I)
    return m.group(1).strip() if m else ""


def _amount(text: str) -> int:
    text = text.replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return round(float(text) * 100)
    except ValueError:
        raise BusinessError("Valor inválido no extrato.")


def parse(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if "<OFX" not in text.upper():
        raise BusinessError("O arquivo não parece ser um extrato OFX.")
    out = []
    for block in _TX.findall(text):
        dt = _tag(block, "DTPOSTED")[:8]
        if len(dt) != 8 or not dt.isdigit():
            continue
        out.append(
            {
                "fitid": _tag(block, "FITID")[:80],
                "date": date(int(dt[:4]), int(dt[4:6]), int(dt[6:8])),
                "amount_cents": _amount(_tag(block, "TRNAMT") or "0"),
                "memo": (_tag(block, "MEMO") or _tag(block, "NAME"))[:200],
            }
        )
    if not out:
        raise BusinessError("Nenhuma transação encontrada no extrato.")
    return out
