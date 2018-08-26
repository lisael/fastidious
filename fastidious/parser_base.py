import re
import string
import sys

import six

from fastidious.expressions import (
    AnyCharExpr,
    CharRangeExpr,
    ChoiceExpr,
    LabeledExpr,
    LiteralExpr,
    LookAhead,
    MaybeExpr,
    Not,
    OneOrMoreExpr,
    RegexExpr,
    Rule,
    RuleExpr,
    SeqExpr,
    ZeroOrMoreExpr
)

from fastidious.utils import RuleVisitor

from fastidious.compiler import check_rulenames


if sys.version_info[0] == 3:
    UPPERCASE = string.ascii_uppercase
    LOWERCASE = string.ascii_lowercase
else:

    UPPERCASE = string.uppercase
    LOWERCASE = string.lowercase


class _RuleNameToLabels(RuleVisitor):
    def __init__(self, rules):
        self.rulename = None
        for r in rules:
            self.visit(r)

    def visit_rule(self, node):
        self.rulename = node.name
        self.visit(node.expr)

    def visit_labeledexpr(self, node):
        if node.rulename is None:
            node.rulename = self.rulename
        self.visit(node.expr)


class _register_expressions(RuleVisitor):
    def __init__(self, klass):
        self.klass = klass
        if not hasattr(klass, "__expressions__"):
            klass.__expressions__ = dict()
        for rule in self.klass.__rules__:
            self.visit(rule)

    def generic_action(self, node):
        self.klass.__expressions__[node.id] = node


class ParserMeta(type):

    def __new__(cls, name, bases, attrs):
        if "__grammar__" in attrs:
            if name in ("FastidiousParser", "FastidiousActionParser"):
                from fastidious.bootstrap import _FastidiousParserBootstraper
                parser = _FastidiousParserBootstraper
            else:
                from fastidious.parser import FastidiousParser
                parser = FastidiousParser
            attrs.setdefault("__rules__", [])
            for base in bases:
                attrs["__rules__"] = cls.merge_rules(
                    attrs["__rules__"],
                    getattr(base, "__rules__", [])
                )
            new_rules = cls.parse_grammar(
                attrs["__grammar__"],
                parser
            )
            attrs.setdefault("__default__", new_rules[0].name)
            attrs["__rules__"] = cls.merge_rules(attrs["__rules__"],
                                                 new_rules)
        rules = attrs.setdefault("__rules__", [])
        if rules:
            attrs.setdefault("__default__", rules[0].name)
            check_rulenames(rules)
        new = super(ParserMeta, cls).__new__(cls, name, bases, attrs)
        cls.post_process_rules(new)
        for rule in rules:
            if getattr(new, "__code_gen__", False):
                rule.as_method(new)
            else:
                rule._attach_to(new)
        return new

    @classmethod
    def merge_rules(cls, dest, src):
        names = [r.name for r in dest]

        def remove_rule(name):
            result = [r for r in dest if r.name != name]
            return result
        for rsrc in src:
            if rsrc.name in names:
                dest = remove_rule(rsrc.name)
            dest.append(rsrc)
        return dest

    @classmethod
    def post_process_rules(cls, newcls):
        _RuleNameToLabels(newcls.__rules__)
        _register_expressions(newcls)

    @classmethod
    def parse_grammar(cls, grammar, parser):
        lines = grammar.split('\n')
        lines.append("")
        lno = 0
        # find global indent
        while lines[lno].strip() == "":
            lno += 1
        m = re.match(r"^(\s*)\S", lines[lno])
        indent = m.groups()[0]
        stripped = "\n".join(
            [line.replace(indent, "")
             for line in lines[lno:]])
        rules = parser.p_parse(stripped)
        return rules


class ParserError(Exception):
    pass


class ParserMixin(object):
    __memoize__ = True
    # __debug___ = True
    __debug___ = False
    __code_gen__ = True

    class NoMatch(object):
        pass

    def __init__(self, input):
        self.input = input
        self.pos = 0
        self.start = 0
        self.args_stack = {}
        self._debug_indent = 0
        self._p_savepoint_stack = []
        self._p_memoized = {}

        self._p_error_stack = [(0, 0)]

    def p_nomatch(self, id):
        head = self._p_error_stack[0]
        if self.pos <= head[0]:
            self._p_error_stack.append((self.pos, id))
        elif self.pos > head[0]:
            self._p_error_stack = [(self.pos, id)]

    def p_suffix(self, length=None, elipsis=False):
        "Return the rest of the input"
        if length is not None:
            result = self.input[self.pos:self.pos + length]
            if elipsis and len(result) == length:
                result += "..."
            return result
        return self.input[self.pos:]

    def p_debug(self, message):
        "Format and print debug messages"
        print("{}{} `{}`".format(self._debug_indent * " ",
                                 message, repr(self.p_suffix(10))))

    def p_peek(self):
        "return the next char, w/o consuming it"
        try:
            return self.input[self.pos]
        except IndexError:
            return None

    def p_next(self):
        "Consume and return the next char"
        try:
            self.pos += 1
            return self.input[self.pos - 1]
        except IndexError:
            return None

    def p_save(self):
        "Push a savepoint on the stack (internal use)"
        self._p_savepoint_stack.append((self.pos, self.start))

    def p_restore(self):
        """
        Pop a savepoint on the stack, and restore the parser state
        (internal use)
        """
        self.pos, self.start = self._p_savepoint_stack.pop()

    def p_discard(self):
        "Pop and forget a savepoint (internal use)"
        self._p_savepoint_stack.pop()

    @property
    def p_current_line(self):
        "Return current line number"
        return self.input[:self.pos].count('\n')

    @property
    def p_current_col(self):
        "Return currnet column in line"
        prefix = self.input[:self.pos]
        nlidx = prefix.rfind('\n')
        if nlidx == -1:
            return self.pos
        return self.pos - nlidx

    def p_pretty_pos(self):
        "Print current line and a pretty cursor below. Used in error messages"
        col = self.p_current_col
        suffix = self.input[self.pos - col + 1:]
        end = suffix.find("\n")
        if end != -1:
            suffix = suffix[:end]
        return "%s\n%s" % (suffix, "-" * (col - 1) + "^")

    def p_parse_error(self, message):
        raise ParserError(
            "Error at line %s, col %s: %s" % (
                self.p_current_line,
                self.p_current_col,
                message
            )
        )

    def p_syntax_error(self, *expected):
        def prettify(i):
            if i.replace("_", "").isalnum():
                return i
            return "`%s`" % i
        expected = set(expected)
        expected = [prettify(item) for item in expected]
        expected = " or ".join(expected)
        raise ParserError(
            "Syntax error at line %s, col %s:"
            "\n\n%s\n\n"
            "Got `%s` expected %s "
            "" % (
                self.p_current_line,
                self.p_current_col,
                self.p_pretty_pos(),
                self.p_suffix(10, elipsis=True).replace(
                    '\n', "\\n") or "EOF",
                expected)
        )

    def p_startswith(self, st, ignorecase=False):
        "Return True if the input starts with `st` at current position"
        length = len(st)
        matcher = result = self.input[self.pos:self.pos + length]
        if ignorecase:
            matcher = result.lower()
            st = st.lower()
        if matcher == st:
            self.pos += length
            return result
        return False

    def p_flatten(self, obj, **kwargs):
        """ Flatten a list of lists of lists... of strings into a string

        This is usually used as the action for sequence expressions:

        .. code-block::

            my_rule <- 'a' . 'c' {p_flatten}

        With the input "abc" and no action, this rule returns [ 'a', 'b', 'c'].
        { p_flatten } procuces "abc".

        >>> parser.p_flatten(['a', ['b', 'c']])
        'abc'

        """
        if isinstance(obj, six.string_types):
            return obj
        result = ""
        for i in obj:
            result += self.p_flatten(i)
        return result

    @classmethod
    def p_parse(cls, input, methodname=None, parse_all=True):
        """
        Parse the `input` using `methodname` as entry point.

        If `parse_all` is true, the input MUST be fully consumed at the end of
        the parsing, otherwise p_parse raises an exception.
        """
        if methodname is None:
            methodname = cls.__default__
        p = cls(input)
        result = getattr(p, methodname)()
        if result is cls.NoMatch or parse_all and p.p_peek() is not None:
            p.p_raise()
        return result

    def p_raise(self):
        expected = []
        current_pos = -1

        if self.__debug___:
            print(self._p_error_stack)

        # check aliased rules
        for pos, id in self._p_error_stack:
            if pos < current_pos:
                break
            try:
                expr = self.__expressions__[id]
            except KeyError:
                continue
            else:
                if expr.is_syntaxic_terminal:
                    current_pos = pos
                    expected += expr.expected

        # none found, fallback to default tips
        if not expected:
            current_pos = -1
            for pos, id in self._p_error_stack:
                if current_pos > -1 and pos < current_pos:
                    continue
                current_pos = pos
                try:
                    expr = self.__expressions__[id]
                except KeyError:
                    continue
                else:
                    if hasattr(expr, "expr") or hasattr(expr, "exprs"):
                        continue
                    expected += expr.expected
        self.pos = current_pos
        return self.p_syntax_error(*expected)


class _FastidiousParserMixin(object):
    """Parser actions of a fastidious PEG grammar parser"""

    def on_rule(self, value, name, expr, code, alias=None, terminal=False):
        terminal = terminal == '`'
        if code:
            r = Rule(name, expr, code[1], alias=alias, terminal=terminal)
        else:
            r = Rule(name, expr, alias=alias, terminal=terminal)
        return r

    def on_regexp_expr(self, content, lit, flags):
        return RegexExpr(self.p_flatten(lit), flags)

    def on_grammar(self, value, rules):
        return [r[0] for r in rules]

    def on_any_char_expr(self, value):
        return AnyCharExpr()

    def on_choice_expr(self, value, first, rest):
        if not rest:
            # only one choice ? not a choice
            return first
        return ChoiceExpr(*[first] + [r[3] for r in rest])

    def on_seq_expr(self, value, first, rest):
        if not rest:
            # a sequence of one element is an element
            return first
        return SeqExpr(*[first] + [r[1] for r in rest])

    def on_labeled_expr(self, value, label, expr):
        if not label:
            return expr
        if label[0] == "":
            try:
                label[0] = expr.rulename
            except AttributeError:
                self.parse_error(
                    "Label can be omitted only on rule reference"
                )
        return LabeledExpr(label[0], expr)

    def on_rule_expr(self, value, name):
        return RuleExpr(name)

    def on_prefixed_expr(self, value, prefix, expr):
        if not prefix:
            return expr
        prefix = prefix[0]
        if prefix == "!":
            return Not(expr)
        elif prefix == "&":
            return LookAhead(expr)

    def on_suffixed_expr(self, value, suffix, expr):
        if not suffix:
            return expr
        suffix = suffix[1]
        if suffix == "?":
            return MaybeExpr(expr)
        elif suffix == "+":
            return OneOrMoreExpr(expr)
        elif suffix == "*":
            return ZeroOrMoreExpr(expr)

    def on_lit_expr(self, value, lit, ignore):
        return LiteralExpr(self.p_flatten(lit), ignore == "i")

    def on_char_range_expr(self, value, content, ignore):
        content = self.p_flatten(content)
        if ignore == "i":
            # don't use sets to avoid ordering mess
            content = content.lower()
            upper = content.upper()
            content += "".join([c for c in upper if c not in content])
        return CharRangeExpr(content)

    def on_class_char_range(self, value, start, end):
        try:
            if start.islower():
                charset = LOWERCASE
            elif start.isupper():
                charset = UPPERCASE
            elif start.isdigit():
                charset = string.digits
            starti = charset.index(start)
            endi = charset.index(end)
            assert starti <= endi
            return charset[starti:endi + 1]
        except Exception:
            self.parse_error(
                "Invalid char range : `{}`".format(self.p_flatten(value)))

    _escaped = {
        "a": "\a",
        "b": "\b",
        "t": "\t",
        "n": "\n",
        "f": "\f",
        "r": "\r",
        "v": "\v",
        "\\": "\\",
    }

    def on_common_escape(self, value):
        return self._escaped[self.p_flatten(value)]
