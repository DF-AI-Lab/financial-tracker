"""Made-up 8-month payment history for testing cycles / common / random. All invented.

Wage: ACME MOTORS PLC 2400 on the 28th of Jan..Aug 2024 (cycles 1..8).
Payments for cycle k are dated in the month AFTER its wage (so cycle 8 is the unfinished one).
"""
from datetime import date

from fintrack.models import Txn

PAYER = "ACME MOTORS PLC"
ENERGY = [150, 190, 160, 170, 155, 185, 165, 160]
CORNER = [4, 30, 7, 25, 9, 40, 12, 20]


def T(y, m, d, typ, desc, detail, amt):
    return Txn(date(y, m, d), typ, desc, detail, float(amt), None)


def synth_txns():
    out = [T(2024, 1, 10, "VIS", "EARLY SHOP", "YORK", -5.00)]  # before the first wage
    for k in range(1, 9):
        out.append(T(2024, k, 28, "CR", PAYER, "PAYROLL", 2400))
        m = k + 1
        out += [
            T(2024, m, 1, "SO", "LANDLORD", "RENT", -550),
            T(2024, m, 1, "DD", "GYM CLUB", "", -50),
            T(2024, m, 2, "DD", "ENERGY CO", "", -ENERGY[k - 1]),
            T(2024, m, 5, "VIS", "STREAM VIDEO", "London", -12.99),
            T(2024, m, 8, ")))", "CORNER SHOP 12", "YORK", -CORNER[k - 1]),
        ]
        if k in (1, 3, 5):
            out.append(T(2024, m, 10, ")))", "BARBER", "YORK", -20))
        if k in (2, 4, 6, 7):
            out.append(T(2024, m, 12, "ATM", "CASH MACHINE", "LEEDS", -50))
    out.append(T(2024, 5, 15, "VIS", "CAR DEALER", "LEEDS", -10377))   # cycle 4 one-off
    out.append(T(2024, 6, 20, "CR", "FAMILY", "Sent from bank", 4800))  # cycle 5 money in
    out.append(T(2024, 5, 31, "CR", PAYER, "BONUS", 600))               # cycle 5 extra wage
    out.append(T(2024, 3, 31, "CR", PAYER, "EXPENSES", 300))            # too small to be a wage
    return out
