"""Specification 6.2 and 6.4 — registering letters and matching them."""

from __future__ import annotations

import pytest

from recsub.errors import ValidationError

from .conftest import Harness


class TestRegistration:
    def test_registration_records_exactly_what_the_professor_supplied(
        self, harness: Harness
    ):
        path = harness.letter_file("ada-phd.pdf")

        letter_id = harness.app.register_letter(
            file_path=path, applicant_name="  Ada Lovelace  ", purpose="PHD_APPLICATION"
        )

        letter = harness.app.repository.get_letter(letter_id)
        assert letter.applicant_name == "Ada Lovelace"
        assert letter.purpose.value == "PHD_APPLICATION"
        assert letter.file_path == path
        assert letter.registered_at == "2026-11-01T12:00:00Z"

    def test_a_nonexistent_file_is_rejected(self, harness: Harness):
        missing = str(harness.tmp_path / "not-there.pdf")
        with pytest.raises(ValidationError, match="no such file"):
            harness.app.register_letter(
                file_path=missing, applicant_name="Ada Lovelace", purpose="PHD_APPLICATION"
            )
        assert harness.app.list_letters() == []

    def test_a_directory_is_not_a_regular_file(self, harness: Harness):
        directory = harness.tmp_path / "letters"
        directory.mkdir(exist_ok=True)
        with pytest.raises(ValidationError, match="not a regular file"):
            harness.app.register_letter(
                file_path=str(directory),
                applicant_name="Ada Lovelace",
                purpose="PHD_APPLICATION",
            )

    @pytest.mark.parametrize("purpose", ["OTHER", "phd_application", "TENURE", ""])
    def test_an_unsupported_purpose_is_rejected(self, harness: Harness, purpose):
        with pytest.raises(ValidationError):
            harness.app.register_letter(
                file_path=harness.letter_file(), applicant_name="Ada", purpose=purpose
            )
        assert harness.app.list_letters() == []

    @pytest.mark.parametrize("name", ["", "   ", "\t\n"])
    def test_a_blank_applicant_name_is_rejected(self, harness: Harness, name):
        with pytest.raises(ValidationError):
            harness.app.register_letter(
                file_path=harness.letter_file(),
                applicant_name=name,
                purpose="FELLOWSHIP",
            )

    def test_a_revision_registered_at_a_new_path_gets_a_new_letter_id(
        self, harness: Harness
    ):
        first = harness.register(name="ada-v1.pdf")
        second = harness.register(name="ada-v2.pdf")

        assert first != second
        assert len(harness.app.list_letters()) == 2


class TestMatching:
    def _request(self, harness: Harness, **kwargs):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1", **kwargs)
        return harness.app.repository.require_request(request_id)

    def test_matching_requires_exact_applicant_equality(self, harness: Harness):
        request = self._request(harness, applicant="Ada Lovelace")
        harness.register(applicant="ada lovelace")  # different case
        assert harness.app.find_letter_for(request) is None

        harness.register(applicant="Ada  Lovelace", name="two-spaces.pdf")  # different spacing
        assert harness.app.find_letter_for(request) is None

        harness.register(applicant="Ada Lovelace", name="exact.pdf")
        assert harness.app.find_letter_for(request).applicant_name == "Ada Lovelace"

    def test_matching_requires_exact_purpose_equality(self, harness: Harness):
        request = self._request(harness, purpose="FELLOWSHIP")
        harness.register(applicant="Ada Lovelace", purpose="PHD_APPLICATION")
        assert harness.app.find_letter_for(request) is None

        harness.register(applicant="Ada Lovelace", purpose="FELLOWSHIP", name="fellow.pdf")
        assert harness.app.find_letter_for(request).purpose.value == "FELLOWSHIP"

    def test_the_most_recently_registered_compatible_letter_wins(self, harness: Harness):
        request = self._request(harness)
        harness.register(name="v1.pdf")
        harness.clock.advance(hours=1)
        newest = harness.register(name="v2.pdf")

        assert harness.app.find_letter_for(request).letter_id == newest

    def test_equal_timestamps_are_broken_deterministically_by_letter_id(
        self, harness: Harness
    ):
        request = self._request(harness)
        first = harness.register(name="a.pdf")
        second = harness.register(name="b.pdf")  # same clock instant

        letter = harness.app.repository.get_letter(first)
        other = harness.app.repository.get_letter(second)
        assert letter.registered_at == other.registered_at
        assert harness.app.find_letter_for(request).letter_id == max(first, second)

    def test_the_filename_never_determines_compatibility(self, harness: Harness):
        request = self._request(harness, applicant="Ada Lovelace", purpose="PHD_APPLICATION")
        harness.app.register_letter(
            file_path=harness.letter_file("ada-lovelace-phd.pdf"),
            applicant_name="Grace Hopper",
            purpose="FELLOWSHIP",
        )

        assert harness.app.find_letter_for(request) is None

    def test_description_destination_and_deadline_are_not_used(self, harness: Harness):
        request = self._request(harness, description="Stanford CS", deadline="2027-01-01T00:00:00Z")
        letter_id = harness.register()
        assert harness.app.find_letter_for(request).letter_id == letter_id
