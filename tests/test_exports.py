"""Tests for simple_contacts.exports."""

import pytest
from simple_contacts.exports import (
    _apply_number_swaps,
    _parse_custom_directory_contacts,
    _parse_number_swaps,
    _sanitize_contact_number,
    _split_name_parts,
    build_microsip_directory_items,
    build_yealink_phonebook_xml,
)


# ---- _sanitize_contact_number ----

class TestSanitizeContactNumber:
    def test_digits_only(self):
        assert _sanitize_contact_number("555-123-4567") == "5551234567"

    def test_empty(self):
        assert _sanitize_contact_number("") == ""
        assert _sanitize_contact_number(None) == ""

    def test_no_digits(self):
        assert _sanitize_contact_number("abc") == ""

    def test_int_input(self):
        assert _sanitize_contact_number(12345) == "12345"


# ---- _split_name_parts ----

class TestSplitNameParts:
    def test_two_part_name(self):
        assert _split_name_parts("Alice Smith") == ("Alice", "Smith")

    def test_three_part_name(self):
        assert _split_name_parts("Alice Jane Smith") == ("Alice Jane", "Smith")

    def test_single_name(self):
        assert _split_name_parts("Alice") == ("Alice", "")

    def test_empty(self):
        assert _split_name_parts("") == ("", "")
        assert _split_name_parts(None) == ("", "")


# ---- _parse_custom_directory_contacts ----

class TestParseCustomContacts:
    def test_basic(self):
        result = _parse_custom_directory_contacts("Reception, 1001\nSecurity, 1002")
        assert len(result) == 2
        assert result[0]["name"] == "Reception"
        assert result[0]["sanitized_number"] == "1001"

    def test_comments_and_blanks(self):
        result = _parse_custom_directory_contacts("# header\n\nFront Desk, 100")
        assert len(result) == 1

    def test_no_comma(self):
        result = _parse_custom_directory_contacts("No comma here")
        assert len(result) == 0

    def test_no_digits(self):
        result = _parse_custom_directory_contacts("Name, abc")
        assert len(result) == 0

    def test_none(self):
        assert _parse_custom_directory_contacts(None) == []


# ---- _parse_number_swaps ----

class TestParseNumberSwaps:
    def test_dict_list_input(self):
        result = _parse_number_swaps([
            {"find": "+972 369,", "replace": ""},
            {"find": ",", "replace": " ext "},
        ])
        assert len(result) == 2
        # Longest find first
        assert result[0] == {"find": "+972 369,", "replace": ""}
        assert result[1] == {"find": ",", "replace": " ext "}

    def test_legacy_string_list(self):
        result = _parse_number_swaps(["+972 369,", "+1"])
        assert len(result) == 2
        assert result[0] == {"find": "+972 369,", "replace": ""}
        assert result[1] == {"find": "+1", "replace": ""}

    def test_legacy_newline_string(self):
        result = _parse_number_swaps("+972 369,\n+1 ")
        assert len(result) == 2
        assert result[0]["find"] == "+972 369,"
        assert result[1]["find"] == "+1"

    def test_empty_find_skipped(self):
        result = _parse_number_swaps([{"find": "", "replace": "x"}])
        assert result == []

    def test_none_and_empty(self):
        assert _parse_number_swaps(None) == []
        assert _parse_number_swaps("") == []
        assert _parse_number_swaps([]) == []


# ---- _apply_number_swaps ----

class TestApplyNumberSwaps:
    def test_delete_prefix(self):
        swaps = [{"find": "+972 31234567,", "replace": ""}]
        assert _apply_number_swaps("+972 31234567,202", swaps) == "202"

    def test_replaces_all_occurrences(self):
        swaps = [{"find": "-", "replace": ""}]
        assert _apply_number_swaps("555-867-5309", swaps) == "5558675309"

    def test_replace_comma_with_ext(self):
        swaps = [{"find": ",", "replace": " ext "}]
        assert _apply_number_swaps("+972 31234567,202", swaps) == "+972 31234567 ext 202"

    def test_no_match(self):
        swaps = [{"find": "+972 369,", "replace": ""}]
        assert _apply_number_swaps("555-1234", swaps) == "555-1234"

    def test_empty_swaps(self):
        assert _apply_number_swaps("555-1234", []) == "555-1234"

    def test_empty_value(self):
        assert _apply_number_swaps("", [{"find": "+972", "replace": ""}]) == ""

    def test_case_insensitive(self):
        swaps = [{"find": "ABC", "replace": "XYZ"}]
        assert _apply_number_swaps("abc123", swaps) == "XYZ123"

    def test_longest_find_wins(self):
        swaps = [
            {"find": "+972 31234567,", "replace": ""},
            {"find": "+972", "replace": "0"},
        ]
        # Longest find matches first; "+972" no longer present after first swap
        assert _apply_number_swaps("+972 31234567,202", swaps) == "202"

    def test_multiple_swaps_applied_sequentially(self):
        swaps = [
            {"find": " ext ", "replace": ""},
            {"find": "-", "replace": ""},
        ]
        assert _apply_number_swaps("+1 555-867-5309 ext 106", swaps) == "+1 5558675309106"

    def test_replace_then_delete(self):
        swaps = [
            {"find": ",", "replace": " ext "},
            {"find": "+972 ", "replace": ""},
        ]
        assert _apply_number_swaps("+972 31234567,202", swaps) == "31234567 ext 202"

    def test_replace_to_empty_strips_whitespace(self):
        swaps = [{"find": "+972 369,", "replace": ""}]
        assert _apply_number_swaps("+972 369, 202", swaps) == "202"

    def test_match_in_middle(self):
        swaps = [{"find": ",", "replace": " ext "}]
        assert _apply_number_swaps("100,202", swaps) == "100 ext 202"


# ---- build_microsip_directory_items ----

class TestBuildMicrosipDirectory:
    def test_basic_employees(self):
        employees = [
            {"name": "Alice Smith", "phone": "555-1234", "businessPhone": "555-0001",
             "email": "alice@ex.com", "title": "Engineer", "department": "Eng"},
        ]
        items = build_microsip_directory_items(employees, settings={"customDirectoryContacts": ""})
        assert len(items) == 1
        assert items[0]["name"] == "Alice Smith"
        assert items[0]["firstname"] == "Alice"
        assert items[0]["lastname"] == "Smith"

    def test_employees_without_phone_skipped(self):
        employees = [{"name": "No Phone", "phone": "", "businessPhone": ""}]
        items = build_microsip_directory_items(employees, settings={"customDirectoryContacts": ""})
        assert len(items) == 0

    def test_custom_contacts_appended(self):
        employees = [
            {"name": "Alice Smith", "phone": "555-1234", "businessPhone": "",
             "email": "a@b.com"},
        ]
        settings = {"customDirectoryContacts": "Lobby, 9000"}
        items = build_microsip_directory_items(employees, settings=settings)
        assert len(items) == 2
        names = [i["name"] for i in items]
        assert "Lobby" in names

    def test_empty_employees(self):
        items = build_microsip_directory_items([], settings={"customDirectoryContacts": ""})
        assert items == []

    def test_none_employees(self):
        items = build_microsip_directory_items(None, settings={"customDirectoryContacts": ""})
        assert items == []

    def test_dedup_generates_fallback(self):
        employees = [
            {"name": "A", "phone": "100", "businessPhone": ""},
            {"name": "B", "phone": "100", "businessPhone": ""},
        ]
        items = build_microsip_directory_items(employees, settings={"customDirectoryContacts": ""})
        assert len(items) == 2
        numbers = [i["number"] for i in items]
        assert len(set(numbers)) == 2  # unique

    def test_swap_strips_employee_numbers(self):
        employees = [
            {"name": "Alice", "phone": "", "businessPhone": "+972 31234567,202",
             "email": "alice@ex.com"},
        ]
        settings = {
            "customDirectoryContacts": "",
            "directoryNumberSwaps": [{"find": "+972 31234567,", "replace": ""}],
        }
        items = build_microsip_directory_items(employees, settings=settings)
        assert len(items) == 1
        assert items[0]["phone"] == "202"

    def test_swap_replaces_in_employee_numbers(self):
        employees = [
            {"name": "Alice", "phone": "", "businessPhone": "+972 31234567,202",
             "email": "alice@ex.com"},
        ]
        settings = {
            "customDirectoryContacts": "",
            "directoryNumberSwaps": [{"find": ",", "replace": " ext "}],
        }
        items = build_microsip_directory_items(employees, settings=settings)
        assert len(items) == 1
        assert items[0]["phone"] == "+972 31234567 ext 202"

    def test_swap_does_not_affect_custom(self):
        settings = {
            "customDirectoryContacts": "Lobby, +972 31234567,300",
            "directoryNumberSwaps": [{"find": "+972 31234567,", "replace": ""}],
        }
        items = build_microsip_directory_items([], settings=settings)
        assert len(items) == 1
        assert items[0]["phone"] == "+972 31234567,300"


# ---- build_yealink_phonebook_xml ----

class TestBuildYealinkPhonebook:
    def test_basic_xml(self):
        employees = [
            {"name": "Alice Smith", "phone": "555-1234", "businessPhone": "555-0001"},
        ]
        xml = build_yealink_phonebook_xml(employees, settings={"customDirectoryContacts": ""})
        assert '<?xml version="1.0"' in xml
        assert "<YealinkIPPhoneDirectory>" in xml
        assert "<Name>Alice Smith</Name>" in xml
        assert "<Telephone>555-0001</Telephone>" in xml

    def test_no_name_skipped(self):
        employees = [{"name": "", "phone": "555-1234", "businessPhone": ""}]
        xml = build_yealink_phonebook_xml(employees, settings={"customDirectoryContacts": ""})
        assert "<DirectoryEntry>" not in xml

    def test_custom_contacts_in_xml(self):
        xml = build_yealink_phonebook_xml(
            [],
            settings={"customDirectoryContacts": "Lobby, 9000"},
        )
        assert "<Name>Lobby</Name>" in xml
        assert "<Telephone>9000</Telephone>" in xml

    def test_empty(self):
        xml = build_yealink_phonebook_xml([], settings={"customDirectoryContacts": ""})
        assert "<YealinkIPPhoneDirectory>" in xml
        assert "<DirectoryEntry>" not in xml

    def test_swap_strips_employee_numbers(self):
        employees = [
            {"name": "Alice Smith", "phone": "", "businessPhone": "+972 31234567,202"},
        ]
        settings = {
            "customDirectoryContacts": "",
            "directoryNumberSwaps": [{"find": "+972 31234567,", "replace": ""}],
        }
        xml = build_yealink_phonebook_xml(employees, settings=settings)
        assert "<Telephone>202</Telephone>" in xml
        assert "+972 31234567" not in xml

    def test_swap_does_not_affect_custom(self):
        settings = {
            "customDirectoryContacts": "Lobby, +972 31234567,300",
            "directoryNumberSwaps": [{"find": "+972 31234567,", "replace": ""}],
        }
        xml = build_yealink_phonebook_xml([], settings=settings)
        assert "<Telephone>+972 31234567,300</Telephone>" in xml
