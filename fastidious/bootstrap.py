import re
from functools import partial
import string

from .expressions import *  # noqa


class UnknownRule(Exception):
    pass


class ParserMeta(type):
    _parser = None

    def __new__(cls, name, bases, attrs):
        if "__grammar__" in attrs:
            if name == "_GrammarParser":
                parser = _GrammarParserBootstraper
            else:
                from .parser import _GrammarParser
                parser = _GrammarParser
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
        rules = attrs.get("__rules__", [])
        if rules:
            attrs.setdefault("__default__", rules[0].name)
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
        cls.check_unknown_rules(newcls)
        cls.fix_named_rulename(newcls)
        cls.register_exprs(newcls)

    @classmethod
    def fix_named_rulename(cls, newcls):
        rules = getattr(newcls, "__rules__", [])

        def fix_named_visitor(rulename, expr):
            if isinstance(expr, LabeledExpr):
                if expr.rulename is None:
                    expr.rulename = rulename

        for r in rules:
            r.visit(partial(fix_named_visitor, r.name))

    @classmethod
    def register_exprs(cls, newcls):
        idmap = getattr(newcls, "__expressions__", dict())
        rules = getattr(newcls, "__rules__", [])

        def register(rmap, expr):
            rmap[expr.id] = expr

        for r in rules:
            r.visit(partial(register, idmap))

        newcls.__expressions__ = idmap

    @classmethod
    def check_unknown_rules(cls, newcls):
        rules = getattr(newcls, "__rules__", [])
        rule_names = [r.name for r in rules]

        def check_unknown_visitor(rule):
            if isinstance(rule, RuleExpr):
                if rule.rulename not in rule_names:
                    raise UnknownRule(rule.rulename)

        for r in rules:
            r.visit(check_unknown_visitor)

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
            result = self.input[self.pos:self.pos+length]
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
        matcher = result = self.input[self.pos:self.pos+length]
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

            my_rule <- 'a' . 'c' { p_flatten }

        With the input "abc" and no action, this rule returns [ 'a', 'b', 'c'].
        { p_flatten } procuces "abc".

        >>> parser.p_flatten(['a', ['b', 'c']])
        'abc'

        """
        if isinstance(obj, basestring):
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
        if result is NoMatch or parse_all and p.p_peek() is not None:
            p.p_raise()
        return result

    def p_raise(self):
        expected = []
        current_pos = -1

        if self.__debug___:
            print self._p_error_stack

        # check aliased rules
        for pos, id in self._p_error_stack:
            if pos < current_pos:
                break
            expr = self.__expressions__[id]
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
                expr = self.__expressions__[id]
                if hasattr(expr, "expr") or hasattr(expr, "exprs"):
                    continue
                expected += expr.expected
        self.pos = current_pos
        return self.p_syntax_error(*expected)


class Parser(ParserMixin):
    """
    Base class for parsers. It calls the metaclass that generates the code
    """
    __metaclass__ = ParserMeta


class _GrammarParserMixin(object):

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
        return SeqExpr(*[first]+[r[1] for r in rest])

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
                charset = string.lowercase
            elif start.isupper():
                charset = string.uppercase
            elif start.isdigit():
                charset = string.digits
            starti = charset.index(start)
            endi = charset.index(end)
            assert starti <= endi
            return charset[starti:endi+1]
        except:
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


class _GrammarParserBootstraper(Parser,
                                _GrammarParserMixin):

    __rules__ = [

        # grammar <- __ rules:( rule __ )+
        Rule(
            "grammar",
            SeqExpr(
                RuleExpr("__"),
                LabeledExpr(
                    "rules",
                    OneOrMoreExpr(
                        SeqExpr(
                            RuleExpr("rule"),
                            RuleExpr("__")
                        )
                    ),
                ),
            ),
            "on_grammar"
        ),


        # rule <- terminal:"`"? name:identifier_name __ ( :alias _ )? "<-" __ expr:expression code:( __ code_block )? EOS  # noqa
        Rule(
            "rule",
            SeqExpr(
                LabeledExpr(
                    "terminal",
                    MaybeExpr(
                        LiteralExpr("`")
                    ),
                ),
                LabeledExpr(
                    "name",
                    RuleExpr("identifier_name"),
                ),
                RuleExpr("__"),
                MaybeExpr(
                    SeqExpr(
                        LabeledExpr(
                            "alias",
                            RuleExpr("alias")
                        ),
                        RuleExpr("_"),
                    ),
                ),
                LiteralExpr("<-"),
                RuleExpr("__"),
                LabeledExpr(
                    "expr",
                    RuleExpr("expression"),
                ),
                LabeledExpr(
                    "code",
                    MaybeExpr(
                        SeqExpr(
                            RuleExpr("__"),
                            RuleExpr("code_block"),
                        )
                    )
                ),
                RuleExpr("EOS")
            ),
            "on_rule"
        ),

        # alias <- string_literal {p_flatten}
        Rule(
            "alias",
            RuleExpr("string_literal"),
            "p_flatten"
        ),

        # code_block <- "{" :code "}"
        Rule(
            "code_block",
            SeqExpr(
                LiteralExpr("{"),
                LabeledExpr(
                    "code",
                    RuleExpr("code"),
                ),
                LiteralExpr("}"),
            ),
            "@code"
        ),

        # code <- ( ( ![{}] source_char )+ / "{" code "}" )*
        Rule(
            "code",
            ZeroOrMoreExpr(
                ChoiceExpr(
                    OneOrMoreExpr(
                        SeqExpr(
                            Not(
                                CharRangeExpr("{}")
                            ),
                            RuleExpr("source_char")
                        )
                    ),
                    SeqExpr(
                        LiteralExpr("{"),
                        RuleExpr("code"),
                        LiteralExpr("}"),
                    ),
                )
            ),
            "p_flatten"
        ),

        # expression <- choice_expr
        Rule(
            "expression",
            RuleExpr("choice_expr")
        ),

        # choice_expr <- first:seq_expr rest:( __ "/" __ seq_expr )*
        Rule(
            "choice_expr",
            SeqExpr(
                LabeledExpr(
                    "first",
                    RuleExpr("seq_expr"),
                ),
                LabeledExpr(
                    "rest",
                    ZeroOrMoreExpr(
                        SeqExpr(
                            RuleExpr("__"),
                            LiteralExpr("/"),
                            RuleExpr("__"),
                            RuleExpr("seq_expr")
                        )
                    ),
                )
            ),
            "on_choice_expr"
        ),

        # primary_expr <- lit_expr / char_range_expr / any_char_expr / rule_expr / SemanticPredExpr / sub_expr  # noqa
        Rule(
            "primary_expr",
            ChoiceExpr(
                RuleExpr("lit_expr"),
                RuleExpr("char_range_expr"),
                RuleExpr("any_char_expr"),
                RuleExpr("rule_expr"),
                RuleExpr("sub_expr")
            )
        ),

        # sub_expr <- "(" __ expr:expression __ ")"
        Rule(
            "sub_expr",
            SeqExpr(
                LiteralExpr("("),
                RuleExpr("__"),
                LabeledExpr(
                    "expr",
                    RuleExpr("expression")
                ),
                RuleExpr("__"),
                LiteralExpr(")")
            ),
            "@expr"
        ),

        # lit_expr <- lit:string_literal ignore:"i"?
        Rule(
            "lit_expr",
            SeqExpr(
                LabeledExpr(
                    "lit",
                    RuleExpr("string_literal")
                ),
                LabeledExpr(
                    "ignore",
                    MaybeExpr(
                        LiteralExpr("i")
                    )
                ),
            ),
            "on_lit_expr"
        ),

        # string_literal <- '"' content:double_string_char* '"' / "'" single_string_char* "'" / '`' RawStringChar '`' )  # noqa
        Rule(
            "string_literal",
            ChoiceExpr(
                SeqExpr(
                    LiteralExpr('"'),
                    LabeledExpr(
                        "content",
                        ZeroOrMoreExpr(
                            RuleExpr("double_string_char")
                        ),
                    ),
                    LiteralExpr('"'),
                ),
                SeqExpr(
                    LiteralExpr("'"),
                    LabeledExpr(
                        "content",
                        ZeroOrMoreExpr(
                            RuleExpr("single_string_char")
                        ),
                    ),
                    LiteralExpr("'"),
                )
            ),
            "@content"
        ),

        # double_string_char <- !( '"' / "\\" / EOL ) source_char / "\\" double_string_escape  # noqa
        Rule(
            "double_string_char",
            ChoiceExpr(
                SeqExpr(
                    Not(
                        ChoiceExpr(
                            LiteralExpr('"'),
                            LiteralExpr('\\'),
                            RuleExpr("EOL")
                        )
                    ),
                    LabeledExpr(
                        "char",
                        RuleExpr("source_char")
                    ),
                ),
                SeqExpr(
                    LiteralExpr("\\"),
                    LabeledExpr(
                        "char",
                        RuleExpr("double_string_escape")
                    )
                )
            ),
            "@char"
        ),

        # single_string_char <- !( "'" / "\\" / EOL ) char:source_char / "\\" char:single_string_escape  # noqa
        Rule(
            "single_string_char",
            ChoiceExpr(
                SeqExpr(
                    Not(
                        ChoiceExpr(
                            LiteralExpr("'"),
                            LiteralExpr('\\'),
                            RuleExpr("EOL")
                        )
                    ),
                    LabeledExpr(
                        "char",
                        RuleExpr("source_char")
                    )
                ),
                SeqExpr(
                    LiteralExpr("\\"),
                    LabeledExpr(
                        "char",
                        RuleExpr("single_string_escape")
                    )
                )
            ),
            "@char"
        ),

        # single_string_escape <- char:"'" / char:common_escape
        Rule(
            "single_string_escape",
            ChoiceExpr(
                LiteralExpr("'"),
                RuleExpr("common_escape")
            ),
        ),

        # double_string_escape <- char:'"' / char:common_escape
        Rule(
            "double_string_escape",
            ChoiceExpr(
                LiteralExpr('"'),
                RuleExpr("common_escape")
            ),
        ),


        # common_escape <- single_char_escape / OctalEscape / HexEscape / LongUnicodeEscape / ShortUnicodeEscape  # noqa
        Rule(
            "common_escape",
            RuleExpr("single_char_escape"),
            "on_common_escape"
        ),

        # single_char_escape <- 'a' / 'b' / 'n' / 'f' / 'r' / 't' / 'v' / '\\'
        Rule(
            "single_char_escape",
            ChoiceExpr(
                LiteralExpr("a"),
                LiteralExpr("b"),
                LiteralExpr("n"),
                LiteralExpr("f"),
                LiteralExpr("r"),
                LiteralExpr("t"),
                LiteralExpr("v"),
                LiteralExpr("\\"),
            ),
        ),

        # any_char_expr <- "."
        Rule(
            "any_char_expr",
            LiteralExpr("."),
            "on_any_char_expr"
        ),

        # rule_expr <- name:identifier_name !( __ "<-" )
        # rule_expr <- name:identifier_name !( __ (string_literal __ )? "<-" )
        Rule(
            "rule_expr",
            SeqExpr(
                LabeledExpr(
                    "name",
                    RuleExpr("identifier_name")
                ),
                Not(
                    SeqExpr(
                        RuleExpr("__"),
                        MaybeExpr(
                            SeqExpr(
                                RuleExpr("string_literal"),
                                RuleExpr("__")
                            ),
                        ),
                        LiteralExpr("<-")
                    )
                )
            ),
            "on_rule_expr"
        ),

        # seq_expr <- first:labeled_expr rest:( __ labeled_expr )*
        Rule(
            "seq_expr",
            SeqExpr(
                LabeledExpr(
                    "first",
                    RuleExpr("labeled_expr")
                ),
                LabeledExpr(
                    "rest",
                    ZeroOrMoreExpr(
                        SeqExpr(
                            RuleExpr("__"),
                            RuleExpr("labeled_expr")
                        )
                    )
                )
            ),
            "on_seq_expr"
        ),

        # labeled_expr <- label:(identifier? __ ':' __)? expr:prefixed_expr
        Rule(
            "labeled_expr",
            SeqExpr(
                LabeledExpr(
                    "label",
                    MaybeExpr(
                        SeqExpr(
                            MaybeExpr(
                                RuleExpr("identifier"),
                            ),
                            RuleExpr("__"),
                            LiteralExpr(":"),
                            RuleExpr("__")
                        )
                    ),
                ),
                LabeledExpr(
                    "expr",
                    RuleExpr("prefixed_expr")
                )
            ),
            "on_labeled_expr"
        ),

        # prefixed_expr <- prefix:( prefix __ )? expr:suffixed_expr
        Rule(
            "prefixed_expr",
            SeqExpr(
                LabeledExpr(
                    "prefix",
                    MaybeExpr(
                        SeqExpr(
                            RuleExpr("prefix"),
                            RuleExpr("__")
                        )
                    )
                ),
                LabeledExpr(
                    "expr",
                    RuleExpr("suffixed_expr")
                )
            ),
            "on_prefixed_expr"
        ),

        # suffixed_expr <- expr:primary_expr suffix:( __ suffix )?
        Rule(
            "suffixed_expr",
            SeqExpr(
                LabeledExpr(
                    "expr",
                    RuleExpr("primary_expr")
                ),
                LabeledExpr(
                    "suffix",
                    MaybeExpr(
                        SeqExpr(
                            RuleExpr("__"),
                            RuleExpr("suffix"),
                        )
                    )
                ),
            ),
            "on_suffixed_expr"
        ),

        # suffix <- [?+*]
        Rule(
            "suffix",
            CharRangeExpr("?+*")
        ),

        # prefix <- [!&]
        Rule(
            "prefix",
            CharRangeExpr("!&")
        ),

        # char_range_expr <- '[' content:( class_char_range / class_char / "\\" UnicodeClassEscape )* ']' ignore:'i'?  # noqa
        Rule(
            "char_range_expr",
            SeqExpr(
                LiteralExpr("["),
                LabeledExpr(
                    "content",
                    ZeroOrMoreExpr(
                        ChoiceExpr(
                            RuleExpr("class_char_range"),
                            RuleExpr("class_char")
                        )
                    ),
                ),
                LiteralExpr("]"),
                LabeledExpr(
                    "ignore",
                    MaybeExpr(
                        LiteralExpr("i")
                    )
                ),
            ),
            "on_char_range_expr"
        ),

        # class_char_range <- class_char '-' class_char
        Rule(
            "class_char_range",
            SeqExpr(
                LabeledExpr(
                    "start",
                    RuleExpr("class_char"),
                ),
                LiteralExpr("-"),
                LabeledExpr(
                    "end",
                    RuleExpr("class_char"),
                )
            ),
            "on_class_char_range"
        ),

        # class_char <- !( "]" / "\\" / EOL ) char:source_char / "\\" char:char_class_escape  # noqa
        Rule(
            "class_char",
            ChoiceExpr(
                SeqExpr(
                    Not(
                        ChoiceExpr(
                            LiteralExpr("]"),
                            LiteralExpr("\\"),
                            RuleExpr("EOL"),
                        )
                    ),
                    LabeledExpr(
                        "char",
                        RuleExpr("source_char")
                    )
                ),
                SeqExpr(
                    LiteralExpr("\\"),
                    LabeledExpr(
                        "char",
                        RuleExpr("char_class_escape")
                    )
                )
            ),
            "@char"
        ),

        # char_class_escape <- ']' / common_escape
        Rule(
            "char_class_escape",
            ChoiceExpr(
                LiteralExpr("]"),
                RuleExpr("common_escape")
            ),
            # "@char"
        ),


        # comment <- "#" ( !EOL source_char )*
        Rule(
            "comment",
            SeqExpr(
                LiteralExpr("#"),
                ZeroOrMoreExpr(
                    SeqExpr(
                        Not(
                            RuleExpr("EOL")
                        ),
                        RuleExpr("source_char")
                    ),
                ),
            ),
        ),

        # source_char <- .
        Rule(
            "source_char",
            AnyCharExpr(),
        ),

        # identifier <- identifier_name
        Rule(
            "identifier",
            RuleExpr("identifier_name"),
        ),

        # identifier_name <- identifier_start identifier_part*
        Rule(
            "identifier_name",
            SeqExpr(
                RuleExpr("identifier_start"),
                ZeroOrMoreExpr(
                    RuleExpr("identifier_part")
                ),
            ),
            "p_flatten"
        ),

        # identifier_start <- [a-z_]i
        Rule(
            "identifier_start",
            CharRangeExpr(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
            ),
        ),

        # identifier_part <- identifier_start / [0-9]
        Rule(
            "identifier_part",
            ChoiceExpr(
                RuleExpr("identifier_start"),
                CharRangeExpr("0123456789")
            ),
        ),

        # __ <- ( whitespace / EOL / comment )*
        Rule(
            "__",
            ZeroOrMoreExpr(
                ChoiceExpr(
                    RuleExpr("whitespace"),
                    RuleExpr("EOL"),
                    RuleExpr("comment"),
                )
            ),
        ),

        # _ <- whitespace*
        Rule(
            "_",
            ZeroOrMoreExpr(
                RuleExpr("whitespace"),
            ),
        ),

        # whitespace <- [ \t\r]
        Rule(
            "whitespace",
            CharRangeExpr(" \t\r"),
        ),

        # EOL <- "\n"
        Rule(
            "EOL",
            LiteralExpr("\n")
        ),

        # EOS <- ( _ comment? EOL ) / ( __ EOF )
        Rule(
            "EOS",
            ChoiceExpr(
                SeqExpr(
                    RuleExpr("_"),
                    MaybeExpr(
                        RuleExpr("comment")
                    ),
                    RuleExpr("EOL")
                ),
                SeqExpr(
                    RuleExpr("__"),
                    RuleExpr("EOF")
                )
            ),
        ),

        # EOF <- !.
        Rule("EOF", Not(AnyCharExpr()))
    ]
