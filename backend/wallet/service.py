"""Operações de carteira. Toda mutação trava a linha da carteira (SELECT … FOR UPDATE)."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import InsufficientBalance

from .models import LedgerEntry, Reservation, TopUp, Wallet


def get_wallet(organization) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(organization=organization)
    return wallet


def _locked(organization) -> Wallet:
    get_wallet(organization)
    return Wallet.objects.select_for_update().get(organization=organization)


def _post(wallet: Wallet, kind, amount, description, *, ref_type="", ref_id="", key=None, user=None) -> LedgerEntry:
    wallet.balance_cents += amount
    if wallet.balance_cents < 0:
        raise InsufficientBalance()
    wallet.save(update_fields=["balance_cents", "updated_at"])
    return LedgerEntry.objects.create(
        wallet=wallet,
        kind=kind,
        amount_cents=amount,
        balance_after_cents=wallet.balance_cents,
        description=description[:200],
        reference_type=ref_type,
        reference_id=str(ref_id),
        idempotency_key=key,
        created_by=user,
    )


def credit(organization, amount_cents: int, description: str, *, kind=LedgerEntry.Kind.TOPUP, ref_type="", ref_id="", key=None, user=None):
    if amount_cents <= 0:
        raise ValueError("Valor de crédito deve ser positivo.")
    if key and LedgerEntry.objects.filter(idempotency_key=key).exists():
        return LedgerEntry.objects.get(idempotency_key=key)
    try:
        with transaction.atomic():
            wallet = _locked(organization)
            return _post(wallet, kind, amount_cents, description, ref_type=ref_type, ref_id=ref_id, key=key, user=user)
    except IntegrityError:
        return LedgerEntry.objects.get(idempotency_key=key)


def reserve(organization, amount_cents: int, description: str, *, ref_type: str, ref_id, user=None) -> Reservation:
    """Debita o valor antes de chamar o provedor. Lança InsufficientBalance."""
    with transaction.atomic():
        wallet = _locked(organization)
        if wallet.balance_cents < amount_cents:
            raise InsufficientBalance(extra={"balance_cents": wallet.balance_cents, "required_cents": amount_cents})
        reservation = Reservation.objects.create(
            wallet=wallet, amount_cents=amount_cents, reference_type=ref_type, reference_id=str(ref_id), description=description[:200]
        )
        if amount_cents:
            _post(
                wallet,
                LedgerEntry.Kind.RESERVE,
                -amount_cents,
                description,
                ref_type=ref_type,
                ref_id=ref_id,
                key=f"res:{reservation.public_id}",
                user=user,
            )
        return reservation


def capture(reservation: Reservation, final_cents: int | None = None) -> Reservation:
    """Confirma a cobrança. Se o valor final for menor, devolve a diferença."""
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(pk=reservation.wallet_id)
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status != Reservation.Status.HELD:
            return res
        final = res.amount_cents if final_cents is None else min(final_cents, res.amount_cents)
        diff = res.amount_cents - final
        if diff > 0:
            _post(
                wallet,
                LedgerEntry.Kind.CAPTURE_ADJUST,
                diff,
                f"Ajuste: {res.description}",
                ref_type=res.reference_type,
                ref_id=res.reference_id,
                key=f"cap:{res.public_id}",
            )
        res.status = Reservation.Status.CAPTURED
        res.captured_cents = final
        res.save(update_fields=["status", "captured_cents", "updated_at"])
        return res


def release(reservation: Reservation, reason: str = "") -> Reservation:
    """Estorna integralmente uma reserva ainda não capturada."""
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(pk=reservation.wallet_id)
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status != Reservation.Status.HELD:
            return res
        if res.amount_cents:
            _post(
                wallet,
                LedgerEntry.Kind.RELEASE,
                res.amount_cents,
                f"Estorno: {res.description}{' — ' + reason if reason else ''}",
                ref_type=res.reference_type,
                ref_id=res.reference_id,
                key=f"rel:{res.public_id}",
            )
        res.status = Reservation.Status.RELEASED
        res.save(update_fields=["status", "updated_at"])
        return res


def confirm_topup(topup: TopUp, *, user=None) -> TopUp:
    with transaction.atomic():
        topup = TopUp.objects.select_for_update().get(pk=topup.pk)
        if topup.status == TopUp.Status.PAID:
            return topup
        credit(
            topup.organization,
            topup.amount_cents,
            "Recarga de créditos",
            ref_type="topup",
            ref_id=topup.public_id,
            key=f"topup:{topup.public_id}",
            user=user,
        )
        topup.status = TopUp.Status.PAID
        topup.paid_at = timezone.now()
        topup.save(update_fields=["status", "paid_at", "updated_at"])
        return topup


def price_for(code: str) -> int:
    from .models import DEFAULT_PRICES, ServicePrice

    item = ServicePrice.objects.filter(code=code, is_active=True).first()
    return item.price_cents if item else DEFAULT_PRICES.get(code, 0)


def adjust(organization, amount_cents: int, description: str, *, user=None) -> LedgerEntry:
    """Ajuste manual do admin (positivo credita, negativo debita). Nunca deixa saldo negativo."""
    if amount_cents == 0:
        raise ValueError("Valor do ajuste não pode ser zero.")
    with transaction.atomic():
        wallet = _locked(organization)
        return _post(wallet, LedgerEntry.Kind.ADJUSTMENT, amount_cents, description, ref_type="admin", user=user)


def cancel_topup(topup: TopUp) -> TopUp:
    with transaction.atomic():
        topup = TopUp.objects.select_for_update().get(pk=topup.pk)
        if topup.status == TopUp.Status.PENDING:
            topup.status = TopUp.Status.CANCELED
            topup.save(update_fields=["status", "updated_at"])
        return topup
