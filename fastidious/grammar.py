import re
from functools import partial
import string

from .expressions import *  # noqa


class UnknownRule(Exception):
    pass


class ParserMeta(type):
    def __new__(cls, name, bases, attrs):
        if "__grammar__" in attrs:
            attrs["__rules__"] = cls.parse_grammar(attrs["__grammar__"])
        rules = attrs.get("__rules__", [])
        new = super(ParserMeta, cls).__new__(cls, name, bases, attrs)
        #import ipdb; ipdb.set_trace()  # XXX BREAKPOINT
        for rule in rules:
            rule._attach_to(new)
        cls.post_process_rules(new)
        return new

    @classmethod
    def post_process_rules(cls, newcls):
        cls.check_unknown_rules(newcls)
        cls.fix_named_rulename(newcls)

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
    def check_unknown_rules(cls, newcls):
        rules = getattr(newcls, "__rules__", [])
        rule_names = [r.name for r in rules]

        def check_unknown_visitor(rule):
            if isinstance(rule, RuleExpr):
                if rule.rulename not in rule_names:
                    raise UnknownRule(rule.rulename)

        for r in rules:
            r.visit(check_unknown_visitor)

    @staticmethod
    def parse_grammar(grammar):
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
        rules = GrammarParser(stripped).grammar()
        return rules


class ParserError(Exception):
    pass


class Parser(object):
    __metaclass__ = ParserMeta

    def __init__(self, input):
        self.input = input
        self.pos = 0
        self.start = 0
        self._debug_indent = 0
        self._debug = False

    def peek(self):
        try:
            return self.input[self.pos]
        except IndexError:
            return None

    def next(self):
        try:
            self.pos += 1
            return self.input[self.pos - 1]
        except IndexError:
            return None

    def save(self):
        return (self.pos, self.start)

    def restore(self, savepoint):
        self.pos, self.start = savepoint

    @property
    def current_line(self):
        return self.input[:self.pos].count('\n')

    def parse_error(self, message):
        raise ParserError(
            "Error at line %s: %s" % (self.current_line, message)
        )

    def startswith(self, st, ignorecase=False):
        matcher = self.input[self.pos:self.pos+len(st)]
        if ignorecase:
            matcher = matcher.lower()
            st = st.lower()
        if matcher == st:
            self.pos += len(st)
            return True
        return False

    def flatten(self, obj, **kwargs):
        if isinstance(obj, basestring):
            return obj
        result = ""
        for i in obj:
            result += self.flatten(i)
        return result


class GrammarParser(Parser):

    def on_rule(self, value, name, expr, code):
        if code:
            return Rule(name, expr, code[1])
        return Rule(name, expr)

    def on_rules(self, value, rules):
        return [r[0] for r in rules]

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
            return NotFollowedBy(expr)
        elif prefix == "&":
            return FollowedBy(expr)

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
        return LiteralExpr(self.flatten(lit), ignore == "i")

    def on_char_range_expr(self, value, content, ignore):
        content = self.flatten(content)
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
            self.parse_error("Invalid char range : `{}`".format(self.flatten(value)))

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

    def on_char_class_escape(self, value, escaped=None):
        return self._escaped.get(escaped, self.flatten(value))

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
            "on_rules"
        ),

        # rule <- name:identifier_name __ "<-" __ expr:expression code:( __ CodeBlock )? EOS
        Rule(
            "rule",
            SeqExpr(
                LabeledExpr(
                    "name",
                    RuleExpr("identifier_name"),
                ),
                RuleExpr("__"),
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


        # code_block <- "{" cd:code "}"
        Rule(
            "code_block",
            SeqExpr(
                LiteralExpr("{"),
                LabeledExpr(
                    "cd",
                    RuleExpr("code"),
                ),
                LiteralExpr("}"),
            ),
            "@cd"
        ),

        # code <- ( ( ![{}] source_char )+ / "{" code "}" )*
        Rule(
            "code",
            ZeroOrMoreExpr(
                ChoiceExpr(
                    OneOrMoreExpr(
                        SeqExpr(
                            NotFollowedBy(
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
            "flatten"
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

        # primary_expr <- lit_expr / char_range_expr / any_char_expr / rule_expr / SemanticPredExpr / sub_expr
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

        # string_literal <- '"' content:double_string_char* '"' / "'" single_string_char* "'" / '`' RawStringChar '`' )
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

        # double_string_char <- !( '"' / "\\" / EOL ) source_char / "\\" double_string_escape
        Rule(
            "double_string_char",
            ChoiceExpr(
                SeqExpr(
                    NotFollowedBy(
                        ChoiceExpr(
                            LiteralExpr('"'),
                            LiteralExpr('\\'),
                            RuleExpr("EOL")
                        )
                    ),
                    RuleExpr("source_char")
                ),
                SeqExpr(
                    LiteralExpr("\\"),
                    RuleExpr("double_string_escape")
                )
            ),
            "flatten"
        ),

        # single_string_char <- !( "'" / "\\" / EOL ) source_char / "\\" single_string_escape
        Rule(
            "single_string_char",
            ChoiceExpr(
                SeqExpr(
                    NotFollowedBy(
                        ChoiceExpr(
                            LiteralExpr("'"),
                            LiteralExpr('\\'),
                            RuleExpr("EOL")
                        )
                    ),
                    RuleExpr("source_char")
                ),
                SeqExpr(
                    LiteralExpr("\\"),
                    RuleExpr("single_string_escape")
                )
            ),
            "flatten"
        ),

        # double_string_escape <- "'" / common_escape
        Rule(
            "double_string_escape",
            ChoiceExpr(
                LiteralExpr("'"),
                RuleExpr("common_escape")
            )
        ),

        # single_string_escape <- '"' / common_escape
        Rule(
            "single_string_escape",
            ChoiceExpr(
                LiteralExpr('"'),
                RuleExpr("common_escape")
            )
        ),


        # common_escape <- single_char_escape / OctalEscape / HexEscape / LongUnicodeEscape / ShortUnicodeEscape
        Rule(
            "common_escape",
            RuleExpr("single_char_escape")
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
            )
        ),

        # any_char_expr <- "."
        Rule(
            "any_char_expr",
            LiteralExpr("."),
            lambda x, y: AnyCharExpr()
        ),

        # rule_expr <- name:identifier_name !( __ "<-" )
        Rule(
            "rule_expr",
            SeqExpr(
                LabeledExpr(
                    "name",
                    RuleExpr("identifier_name")
                ),
                NotFollowedBy(
                    SeqExpr(
                        RuleExpr("__"),
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

        # prefixed_expr <- op:( prefix __ )? expr:suffixed_expr
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

        # char_range_expr <- '[' content:( class_char_range / class_char / "\\" UnicodeClassEscape )* ']' ignore:'i'?
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

        # class_char <- !( "]" / "\\" / EOL ) source_char / "\\" escaped:char_class_escape
        Rule(
            "class_char",
            ChoiceExpr(
                SeqExpr(
                    NotFollowedBy(
                        ChoiceExpr(
                            LiteralExpr("]"),
                            LiteralExpr("\\"),
                            RuleExpr("EOL"),
                        )
                    ),
                    RuleExpr("source_char")
                ),
                SeqExpr(
                    LiteralExpr("\\"),
                    RuleExpr("char_class_escape")
                )
            ),
            "on_char_class_escape"
        ),

        # char_class_escape <- ']' / common_escape
        Rule(
            "char_class_escape",
            ChoiceExpr(
                LiteralExpr("]"),
                RuleExpr("common_escape")
            )
        ),


        # comment <- "#" ( !EOL source_char )*
        Rule(
            "comment",
            SeqExpr(
                LiteralExpr("#"),
                ZeroOrMoreExpr(
                    SeqExpr(
                        NotFollowedBy(
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
            "flatten"
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
        Rule("EOF", NotFollowedBy(AnyCharExpr()))
    ]
