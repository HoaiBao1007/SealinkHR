from app.services.organization_mapping import (
    DEPARTMENT_HIERARCHY,
    DOC_CHILD_UNIT_CODES,
    DOC_PARENT_DEPARTMENT,
    DOC_PRICING_CS_DEPARTMENT,
    EMPLOYEE_PLACEMENTS,
    UNIT_DEFINITIONS,
    placement_for_employee,
)


def test_every_organization_unit_parent_exists() -> None:
    unit_codes = {unit.code for unit in UNIT_DEFINITIONS}
    assert len(unit_codes) == len(UNIT_DEFINITIONS)
    for unit in UNIT_DEFINITIONS:
        assert unit.parent_code is None or unit.parent_code in unit_codes


def test_pdf_employee_is_mapped_to_expected_branch() -> None:
    placement = placement_for_employee("Nguyễn Lê Ngọc Hoa")
    assert placement.unit_code == "DOCS_PRICING_CS"
    assert placement.department_name == DOC_PRICING_CS_DEPARTMENT


def test_doc_child_departments_are_linked_to_doc_parent() -> None:
    assert len(DEPARTMENT_HIERARCHY) == 5
    assert len(DOC_CHILD_UNIT_CODES) == 5
    assert all(parent_name == DOC_PARENT_DEPARTMENT for parent_name, _ in DEPARTMENT_HIERARCHY.values())
    assert sorted(sort_order for _, sort_order in DEPARTMENT_HIERARCHY.values()) == [10, 20, 30, 40, 50]


def test_name_matching_is_unicode_and_case_insensitive() -> None:
    placement = placement_for_employee("  NGUYỄN   THỊ THANH HƯƠNG ")
    assert placement.unit_code == "OVERSEAS"


def test_unknown_employee_is_kept_visible_in_unassigned_branch() -> None:
    placement = placement_for_employee("Nhân viên chưa có trong nguồn")
    assert placement.unit_code == "UNASSIGNED"
    assert placement.department_name == "CHƯA PHÂN NHÓM"


def test_all_explicit_placements_use_existing_units() -> None:
    unit_codes = {unit.code for unit in UNIT_DEFINITIONS}
    assert EMPLOYEE_PLACEMENTS
    assert all(placement.unit_code in unit_codes for placement in EMPLOYEE_PLACEMENTS.values())
