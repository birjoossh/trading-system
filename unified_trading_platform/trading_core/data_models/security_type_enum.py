from enum import Enum


class SecurityType(Enum):
    """Security types for different instruments"""

    STOCK = "STK"
    OPTION = "OPT"
    FUTURE = "FUT"
    CASH = "CASH"
    BOND = "BOND"
    CRYPTO = "CRYPTO"
    FOREX = "CASH"
    INDEX = "IND"
    CFD = "CFD"
