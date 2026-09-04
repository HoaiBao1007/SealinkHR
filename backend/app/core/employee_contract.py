from datetime import date


APPRENTICESHIP = "APPRENTICESHIP"
PROBATION = "PROBATION"
OFFICIAL = "OFFICIAL"
FIXED_TERM_1 = "FIXED_TERM_1"
FIXED_TERM_2 = "FIXED_TERM_2"
INDEFINITE = "INDEFINITE"

CONTRACT_TYPES = frozenset(
    {
        APPRENTICESHIP,
        PROBATION,
        OFFICIAL,
        FIXED_TERM_1,
        FIXED_TERM_2,
        INDEFINITE,
    }
)
FIXED_TERM_CONTRACT_TYPES = frozenset({FIXED_TERM_1, FIXED_TERM_2})


def normalize_contract_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in CONTRACT_TYPES:
        raise ValueError("Loại hợp đồng không hợp lệ.")
    return normalized


def validate_contract_period(
    contract_type: str | None,
    contract_sign_date: date | None,
    contract_start_date: date | None,
    contract_end_date: date | None,
) -> None:
    if not contract_type:
        if contract_sign_date or contract_start_date or contract_end_date:
            raise ValueError("Cần chọn loại hợp đồng trước khi nhập thời hạn hợp đồng.")
        return

    if not contract_sign_date:
        raise ValueError("Ngày ký hợp đồng là bắt buộc.")

    if contract_type in FIXED_TERM_CONTRACT_TYPES:
        if not contract_start_date or not contract_end_date:
            raise ValueError("Hợp đồng lần 1/lần 2 phải có đủ ngày bắt đầu và ngày kết thúc.")
        if contract_end_date < contract_start_date:
            raise ValueError("Ngày kết thúc hợp đồng không được trước ngày bắt đầu.")
