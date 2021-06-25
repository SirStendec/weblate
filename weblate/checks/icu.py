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
NUMERIC_TYPES = [
    'number',
    'plural',
    'selectordinal'
]

# These types have their sub-messages checked to ensure that
# sub-message selectors are valid.
PLURAL_TYPES = [
    'plural',
    'selectordinal'
]

# ... and these are the valid selectors, along with selectors
# for specific values, formatted such as: =0, =1, etc.
PLURAL_SELECTORS = [
    'zero',
    'one',
    'two',
    'few',
    'many',
    'other'
]


# We construct two Parser instances, one for tags and one without.
# Both parsers are configured to allow spaces inside formats, to not
# require other (which we can do better ourselves), and to be
# permissive about what types can have sub-messages.
standard_parser = Parser({
    'loose_submessages': True,
    'allow_format_spaces': True,
    'require_other': False,
    'allow_tags': False
})

tag_parser = Parser({
    'loose_submessages': True,
    'allow_format_spaces': True,
    'require_other': False,
    'allow_tags': True,
    'tag_type': TAG_TYPE
})


def parseICU(source: str, allow_tags: bool, want_tokens = False):
    """
    Parse an ICU MessageFormat message.
    """

    ast = None
    err = None
    tokens = [] if want_tokens else None
    parser = tag_parser if allow_tags else standard_parser

    try:
        ast = parser.parse(source, tokens)
    except SyntaxError as e:
        err = e

    return ast, err, tokens


def isBadPluralSelector(selector):
    if selector in PLURAL_SELECTORS:
        return False
    return selector[0] != '='


def updateFourValue(value, old):
    """
    Certain values on placeholders can have four values. They will be
    one of: `None`, `True`, `False`, or `0`.

    `None` represents a value that was never set.
    `True` or `False` represents a value that was set.
    `0` represents a value that was set with conflicting values.

    This is useful in case there are multiple placeholders with
    conflicting type information.
    """
    if old is None:
        return value
    if old != value:
        return 0
    return old


def extractPlaceholders(token, variables = None):
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
            extractPlaceholders(tok, variables)

        return variables

    if not 'name' in token:
        # There should always be a name. This is highly suspicious.
        # Should this raise an exception?
        return variables

    name = token['name']
    ttype = token.get('type')
    data = variables.setdefault(name, {
        'name': name,
        'types': set(),
        'formats': set(),
        'is_number': None,
        'is_tag': None,
        'is_empty': None
    })

    if ttype:
        is_tag = ttype is TAG_TYPE

        data['types'].add(ttype)
        data['is_number'] = updateFourValue(ttype in NUMERIC_TYPES, data['is_number'])
        data['is_tag'] = updateFourValue(is_tag, data['is_tag'])
        if is_tag:
            data['is_empty'] = updateFourValue(
                'contents' not in token or not token['contents'],
                data['is_empty']
            )

        if 'format' in token:
            data['formats'].add(token['format'])

    if 'options' in token:
        choices = data.setdefault('choices', set())

        # We need to do three things with options:
        for selector, subast in token['options'].items():
            # First, we log the selector for later comparison.
            choices.add(selector)

            # Second, we make sure the selector is valid if we're working
            # with a plural/selectordinal type.
            if ttype in PLURAL_TYPES:
                if isBadPluralSelector(selector):
                    data.setdefault('bad_plural', set()).add(selector)

            # Finally, we process the sub-ast for this option.
            extractPlaceholders(subast, variables)

    # Make sure we process the contents sub-ast if one exists.
    if 'contents' in token:
        extractPlaceholders(token['contents'], variables)

    return variables


class BaseICUMessageFormatCheck(BaseFormatCheck):
    """Check for ICU MessageFormat string."""

    #check_id = "icu_message_format"
    #name = _("ICU MessageFormat")
    description = _(
        "Syntax errors and/or placeholder mismatches in ICU MessageFormat strings."
        )
    allow_tags = None
    source = True

    def check_source_unit(self, source, unit):
        """Checker for source strings. Only check for syntax issues."""
        if not source or not source[0]:
            return False

        _, src_err, _ = parseICU(source[0], self.allow_tags)
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

        src_ast, src_err, _ = parseICU(source, self.allow_tags)

        # Check to see if we're running on a source string only.
        # If we are, then we can only run a syntax check on the
        # source and be done.
        if unit and unit.is_source:
            if src_err:
                result['syntax'].append(src_err)
                return result
            return False

        tgt_ast, tgt_err, _ = parseICU(target, self.allow_tags)
        if tgt_err:
            result['syntax'].append(tgt_err)

        if tgt_err:
            return result
        elif src_err:
            # We cannot run any further checks if the source
            # string isn't valid, so just accept that the target
            # string is valid for now.
            return False

        # Both strings are valid! Congratulations. Let's extract
        # information on all the placeholders in both strings, and
        # compare them to see if anything is wrong.
        src_vars = extractPlaceholders(src_ast)
        tgt_vars = extractPlaceholders(tgt_ast)

        # First, we check all the variables in the target.
        for name, data in tgt_vars.items():
            print_name = '<{}>'.format(name) if data['is_tag'] else name

            # If we have sub-messages, make sure there is
            # an "other" sub-message.
            choices = data.get('choices')
            if choices and not 'other' in choices:
                result['no_other'].append(print_name)

            # Do we have bad plural names?
            bad_plural = data.get('bad_plural')
            if bad_plural:
                result['bad_plural'].append([print_name, bad_plural])

            if name in src_vars:
                # The variable exists in the source, so check
                # if the types match.
                src_data = src_vars[name]

                # Are we dealing with a number and also not
                # with a number?
                if isinstance(src_data['is_number'], bool):
                    if src_data['is_number'] != data['is_number']:
                        result['wrong_type'].append(print_name)

                else:
                    for ttype in data['types']:
                        if ttype not in src_data['types']:
                            result['wrong_type'].append(print_name)
                            break

                # Is there a tag mismatch? Technically this
                # should be covered by the XML markup check
                # but we want to be sure.
                if isinstance(src_data['is_tag'], bool) or data['is_tag'] is not None:
                    if src_data['is_tag']:
                        if not data['is_tag']:
                            result['should_be_tag'].append(print_name)

                        elif isinstance(src_data['is_empty'], bool) and \
                                src_data['is_empty'] != data['is_empty']:
                            if src_data['is_empty']:
                                result['tag_not_empty'].append(print_name)
                            else:
                                result['tag_empty'].append(print_name)

                    elif data['is_tag']:
                        result['not_tag'].append(print_name)

            else:
                # The variable does not exist in the source,
                # which suggests a mistake.
                result['extra'].append(print_name)

        # We also want to check for variables used in the
        # source but not in the target.
        for name, data in src_vars.items():
            if name not in tgt_vars:
                print_name = '<{}>'.format(name) if data['is_tag'] else name
                result['missing'].append(print_name)

        if result:
            return result
        return False


    def check_highlight(self, source, unit):
        # TODO: Should we do anything about highlighting?
        return []


    def format_result(self, result):
        if result.get('syntax'):
            yield _(
                "Syntax error: %s"
            ) % ", ".join(err.msg for err in result['syntax'])

        if result.get('extra'):
            yield _(
                "Unknown placeholder in translation: %s"
            ) % ", ".join(result['extra'])

        if result.get('missing'):
            yield _(
                "Placeholder missing in translation: %s"
            ) % ", ".join(result['missing'])

        if result.get('wrong_type'):
            yield _(
                "Placeholder has wrong type: %s"
            ) % ", ".join(result['wrong_type'])

        if result.get('no_other'):
            yield _(
                "Missing other sub-message for: %s"
            ) % ", ".join(result['no_other'])

        if result.get('bad_plural'):
            yield _(
                "Bad sub-message selectors for: %s"
            ) % ", ".join("{} ({})".format(x[0], x[1]) for x in result['bad_plural'])

        if result.get('should_be_tag'):
            yield _(
                "Placeholder should be XML tag in translation: %s"
            ) % ", ".join(result['should_be_tag'])

        if result.get('not_tag'):
            yield _(
                "Placeholder should not be XML tag in translation: %s"
            ) % ", ".join(result['not_tag'])

        if result.get('tag_not_empty'):
            yield _(
                "XML Tag has unexpected contents in translation: %s"
            ) % ", ".join(result['tag_not_empty'])

        if result.get('tag_empty'):
            yield _(
                "XML Tag missing contents in translation: %s"
            ) % ", ".join(result['tag_empty'])


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
