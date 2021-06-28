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

from collections import defaultdict

from django.utils.translation import gettext_lazy as _
from pyicumessageformat import Parser

from weblate.checks.format import BaseFormatCheck

# Unique value for checking tags. Since types are
# always strings, this will never be encountered.
TAG_TYPE = -100

# These types are to be considered numeric. Numeric placeholders
# can be of any numeric type without triggering a warning from
# the checker.
NUMERIC_TYPES = ["number", "plural", "selectordinal"]

# These types have their sub-messages checked to ensure that
# sub-message selectors are valid.
PLURAL_TYPES = ["plural", "selectordinal"]

# ... and these are the valid selectors, along with selectors
# for specific values, formatted such as: =0, =1, etc.
PLURAL_SELECTORS = ["zero", "one", "two", "few", "many", "other"]


# We construct two Parser instances, one for tags and one without.
# Both parsers are configured to allow spaces inside formats, to not
# require other (which we can do better ourselves), and to be
# permissive about what types can have sub-messages.
standard_parser = Parser(
    {
        "loose_submessages": True,
        "allow_format_spaces": True,
        "require_other": False,
        "allow_tags": False,
    }
)

tag_parser = Parser(
    {
        "loose_submessages": True,
        "allow_format_spaces": True,
        "require_other": False,
        "allow_tags": True,
        "tag_type": TAG_TYPE,
    }
)


def parse_icu(source: str, allow_tags: bool, want_tokens=False):
    """Parse an ICU MessageFormat message."""
    ast = None
    err = None
    tokens = [] if want_tokens else None
    parser = tag_parser if allow_tags else standard_parser

    try:
        ast = parser.parse(source, tokens)
    except SyntaxError as e:
        err = e

    return ast, err, tokens


def check_bad_plural_selector(selector):
    if selector in PLURAL_SELECTORS:
        return False
    return selector[0] != "="


def update_maybe_value(value, old):
    """
    Certain values on placeholders can have four values.

    They will be one of: `None`, `True`, `False`, or `0`.

    `None` represents a value that was never set.
    `True` or `False` represents a value that was set.
    `0` represents a value that was set with conflicting values.

    This is useful in case there are multiple placeholders with
    conflicting type information.
    """
    if old is None or old == value:
        return value
    return 0


def extract_placeholders(token, variables=None):
    """Extract all placeholders from an AST and summarize their types."""
    if variables is None:
        variables = {}

    if isinstance(token, str):
        # Skip strings. Those aren't interesting.
        return variables

    if isinstance(token, list):
        # If we have a list, then we have a list of tokens so iterate
        # over the entire list.
        for tok in token:
            extract_placeholders(tok, variables)

        return variables

    if "name" not in token:
        # There should always be a name. This is highly suspicious.
        # Should this raise an exception?
        return variables

    name = token["name"]
    ttype = token.get("type")
    data = variables.setdefault(
        name,
        {
            "name": name,
            "types": set(),
            "formats": set(),
            "is_number": None,
            "is_tag": None,
            "is_empty": None,
        },
    )

    if ttype:
        is_tag = ttype is TAG_TYPE

        data["types"].add(ttype)
        data["is_number"] = update_maybe_value(
            ttype in NUMERIC_TYPES, data["is_number"]
        )
        data["is_tag"] = update_maybe_value(is_tag, data["is_tag"])
        if is_tag:
            data["is_empty"] = update_maybe_value(
                "contents" not in token or not token["contents"], data["is_empty"]
            )

        if "format" in token:
            data["formats"].add(token["format"])

    if "options" in token:
        choices = data.setdefault("choices", set())

        # We need to do three things with options:
        for selector, subast in token["options"].items():
            # First, we log the selector for later comparison.
            choices.add(selector)

            # Second, we make sure the selector is valid if we're working
            # with a plural/selectordinal type.
            if ttype in PLURAL_TYPES:
                if check_bad_plural_selector(selector):
                    data.setdefault("bad_submessage", set()).add(selector)

            # Finally, we process the sub-ast for this option.
            extract_placeholders(subast, variables)

    # Make sure we process the contents sub-ast if one exists.
    if "contents" in token:
        extract_placeholders(token["contents"], variables)

    return variables


class BaseICUMessageFormatCheck(BaseFormatCheck):
    """Check for ICU MessageFormat string."""

    description = _(
        "Syntax errors and/or placeholder mismatches in ICU MessageFormat strings."
    )
    allow_tags = None
    source = True

    def check_source_unit(self, source, unit):
        """Checker for source strings. Only check for syntax issues."""
        if not source or not source[0]:
            return False

        _, src_err, _ = parse_icu(source[0], self.allow_tags)
        if src_err:
            return True
        return False

    def check_format(self, source, target, ignore_missing, unit):
        """Checker for ICU MessageFormat strings."""
        if not target or not source:
            return False

        # TODO: Should this be split up into smaller tests?
        # Could we do so without repeating the work of parsing
        # the messages and extracting placeholders?

        result = defaultdict(list)

        src_ast, src_err, _ = parse_icu(source, self.allow_tags)

        # Check to see if we're running on a source string only.
        # If we are, then we can only run a syntax check on the
        # source and be done.
        if unit and unit.is_source:
            if src_err:
                result["syntax"].append(src_err)
                return result
            return False

        tgt_ast, tgt_err, _ = parse_icu(target, self.allow_tags)
        if tgt_err:
            result["syntax"].append(tgt_err)

        if tgt_err:
            return result
        if src_err:
            # We cannot run any further checks if the source
            # string isn't valid, so just accept that the target
            # string is valid for now.
            return False

        # Both strings are valid! Congratulations. Let's extract
        # information on all the placeholders in both strings, and
        # compare them to see if anything is wrong.
        src_vars = extract_placeholders(src_ast)
        tgt_vars = extract_placeholders(tgt_ast)

        # First, we check all the variables in the target.
        for name, data in tgt_vars.items():
            self.check_for_other(result, name, data)

            if name in src_vars:
                src_data = src_vars[name]

                self.check_bad_submessage(result, name, data, src_data)
                self.check_wrong_type(result, name, data, src_data)
                self.check_tags(result, name, data, src_data)

            else:
                self.check_bad_submessage(result, name, data, None)

                # The variable does not exist in the source,
                # which suggests a mistake.
                result["extra"].append(name)

        # We also want to check for variables used in the
        # source but not in the target.
        for name in src_vars:
            if name not in tgt_vars:
                result["missing"].append(name)

        if result:
            return result
        return False

    def check_for_other(self, result, name, data):
        """Ensure that types with sub-messages have other."""
        choices = data.get("choices")
        if choices and "other" not in choices:
            result["no_other"].append(name)

    def check_bad_submessage(self, result, name, data, src_data):
        """Detect any bad sub-message selectors."""
        # We start with bad_submessage from extraction, which
        # checks for bad plural keys.
        bad = data.get("bad_submessage", set())

        # We also want to check individual select choices.
        if src_data and "select" in data["types"] and "select" in src_data["types"]:
            if "choices" in data and "choices" in src_data:
                choices = data["choices"]
                src_choices = src_data["choices"]

                for selector in choices:
                    if selector not in src_choices:
                        bad.add(selector)

        if bad:
            result["bad_submessage"].append([name, bad])

    def check_wrong_type(self, result, name, data, src_data):
        """Ensure that types match, when possible."""
        # If we're dealing with a number, we want to use
        # special number logic, since numbers work with
        # multiple types.
        if isinstance(src_data["is_number"], bool) and src_data["is_number"]:
            if src_data["is_number"] != data["is_number"]:
                result["wrong_type"].append(name)

        else:
            for ttype in data["types"]:
                if ttype not in src_data["types"]:
                    result["wrong_type"].append(name)
                    break

    def check_tags(self, result, name, data, src_data):
        """Check for errors with XML tags."""
        if not self.allow_tags:
            return

        if isinstance(src_data["is_tag"], bool) or data["is_tag"] is not None:
            if src_data["is_tag"]:
                if not data["is_tag"]:
                    result["should_be_tag"].append(name)

                elif (
                    isinstance(src_data["is_empty"], bool)
                    and src_data["is_empty"] != data["is_empty"]
                ):
                    if src_data["is_empty"]:
                        result["tag_not_empty"].append(name)
                    else:
                        result["tag_empty"].append(name)

            elif data["is_tag"]:
                result["not_tag"].append(name)

    def format_result(self, result):
        if result.get("syntax"):
            yield _("Syntax error: %s") % ", ".join(err.msg for err in result["syntax"])

        if result.get("extra"):
            yield _("Unknown placeholder in translation: %s") % ", ".join(
                result["extra"]
            )

        if result.get("missing"):
            yield _("Placeholder missing in translation: %s") % ", ".join(
                result["missing"]
            )

        if result.get("wrong_type"):
            yield _("Placeholder has wrong type: %s") % ", ".join(result["wrong_type"])

        if result.get("no_other"):
            yield _("Missing other sub-message for: %s") % ", ".join(result["no_other"])

        if result.get("bad_submessage"):
            yield _("Bad sub-message selectors for: %s") % ", ".join(
                f"{x[0]} ({', '.join(x[1])})" for x in result["bad_submessage"]
            )

        if result.get("should_be_tag"):
            yield _("Placeholder should be XML tag in translation: %s") % ", ".join(
                result["should_be_tag"]
            )

        if result.get("not_tag"):
            yield _("Placeholder should not be XML tag in translation: %s") % ", ".join(
                result["not_tag"]
            )

        if result.get("tag_not_empty"):
            yield _("XML Tag has unexpected contents in translation: %s") % ", ".join(
                result["tag_not_empty"]
            )

        if result.get("tag_empty"):
            yield _("XML Tag missing contents in translation: %s") % ", ".join(
                result["tag_empty"]
            )

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return []

        _, _, tokens = parse_icu(source, self.allow_tags, True)

        ret = []
        i = 0
        start = None
        tree = []
        src_len = len(source)

        for token in tokens:
            text = token["text"]
            length = len(text)
            last = tree[-1] if tree else None

            if token["type"] == "syntax":
                if text == "{" or (self.allow_tags and text in ["<", "</"]):
                    tree.append(text)
                    if start is None:
                        start = i

                elif (text == "}" and last == "{") or (
                    self.allow_tags and text in (">", "/>") and last in ("<", "</")
                ):
                    tree.pop()
                    if not tree:
                        end = i + length
                        ret.append((start, end, source[start:end]))
                        start = None

            i += length
            if i >= src_len:
                break

        return ret


class ICUMessageFormatCheck(BaseICUMessageFormatCheck):
    """Check for ICU MessageFormat strings."""

    check_id = "icu_message_format"
    name = _("ICU MessageFormat")
    allow_tags = False


class ICUXMLFormatCheck(BaseICUMessageFormatCheck):
    """Check for ICU MessageFormat strings with simple XML tags."""

    check_id = "icu_xml_format"
    name = _("ICU MessageFormat with Simple XML Tags")
    allow_tags = True
