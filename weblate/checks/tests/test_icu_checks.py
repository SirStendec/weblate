#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for ICU MessageFormat checks."""

from weblate.checks.icu import ICUMessageFormatCheck, ICUXMLFormatCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit


class ICUMessageFormatCheckTest(CheckTestCase):
    check = ICUMessageFormatCheck()

    def test_plain(self):
        self.assertFalse(self.check.check_format("string", "string", False, None))

    def test_no_formats(self):
        self.assertFalse(
            self.check.check_format("Hello, {name}!", "Hallo, {name}!", False, None)
        )

    def test_whitespace(self):
        self.assertFalse(
            self.check.check_format(
                "Hello, {  \t name\n  \n}!", "Hallo, {name}!", False, None
            )
        )

    def test_missing_placeholder(self):
        result = self.check.check_format("Hello, {name}!", "Hallo, Fred!", False, None)

        self.assertDictEqual(result, {"missing": ["name"]})

    def test_extra_placeholder(self):
        result = self.check.check_format(
            "Hello, {firstName}!", "Hallo, {firstName} {lastName}!", False, None
        )

        self.assertDictEqual(result, {"extra": ["lastName"]})

    def test_types(self):
        self.assertFalse(
            self.check.check_format(
                "Cost: {value, number, ::currency/USD}",
                "Kosten: {value, number, ::currency/USD}",
                False,
                None,
            )
        )

    def test_wrong_types(self):
        result = self.check.check_format(
            "Cost: {value, number, ::currency/USD}", "Kosten: {value}", False, None
        )

        self.assertDictEqual(result, {"wrong_type": ["value"]})

    def test_plural_types(self):
        self.assertFalse(
            self.check.check_format(
                "You have {count, plural, one {# message} other {# messages}}. "
                "Yes. {count, number}.",
                "Sie haben {count, plural, one {# Nachricht} other "
                "{# Nachrichten}}. Ja. {count, number}.",
                False,
                None,
            )
        )

    def test_no_other(self):
        result = self.check.check_format(
            "{count, number}", "{count, plural, one {typo}}", False, None
        )

        self.assertDictEqual(result, {"no_other": ["count"]})

    def test_bad_plural(self):
        result = self.check.check_format(
            "{count, number}", "{count, plural, bad {typo} other {okay}}", False, None
        )

        self.assertDictEqual(result, {"bad_plural": [["count", {"bad"}]]})

    def test_good_plural(self):
        self.assertFalse(
            self.check.check_format(
                "{count, number}",
                "{count, plural, zero{#} one{#} two{#} few{#} many{#} "
                "other{#} =0{#} =-12{#} =391.5{#}}",
                False,
                None,
            )
        )

    def test_check_highlight(self):
        highlights = self.check.check_highlight(
            "Hello, <link> {na<>me} </link>. You have {count, plural, one "
            "{# message} other {# messages}}.",
            MockUnit("icu_message_format", flags="icu-message-format"),
        )

        self.assertListEqual(highlights, [[14, 22], [41, 92]])


# This is a sub-class of our existing test set because this format is an extension
# of the other format and it should handle all existing syntax properly.
class ICUXMLFormatCheckTest(ICUMessageFormatCheckTest):
    check = ICUXMLFormatCheck()

    def test_tags(self):
        self.assertFalse(
            self.check.check_format(
                "Hello <user/>! <link>Click here!</link>",
                "Hallo <user />! <link>Klicke hier!</link>",
                False,
                None,
            )
        )

    def test_empty_tags(self):
        self.assertFalse(
            self.check.check_format("<empty />", "<empty/><empty></empty>", False, None)
        )

    def test_incorrectly_full_tags(self):
        result = self.check.check_format(
            "<empty /><full>tag</full>", "<full /><empty>tag</empty>", False, None
        )

        self.assertDictEqual(
            result, {"tag_not_empty": ["empty"], "tag_empty": ["full"]}
        )

    def test_tag_vs_placeholder(self):
        result = self.check.check_format(
            "Hello, <bold>{firstName}</bold>.",
            "Hello {bold} <firstName />.",
            False,
            None,
        )

        self.assertDictEqual(
            result,
            {
                "wrong_type": ["bold", "firstName"],
                "should_be_tag": ["bold"],
                "not_tag": ["firstName"],
            },
        )

    def test_check_highlight(self):
        highlights = self.check.check_highlight(
            "Hello, <link> {na<>me} </link>. You have {count, plural, "
            "one {# message} other {# messages}}.",
            MockUnit("icu_xml_format", flags="icu-xml-format"),
        )

        self.assertListEqual(highlights, [[7, 13], [14, 22], [23, 30], [41, 92]])
