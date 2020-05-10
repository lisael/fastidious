import six

from fastidious.expressions import (
    AnyCharExpr,
    CharRangeExpr,
    ChoiceExpr,
    LabeledExpr,
    LiteralExpr,
    MaybeExpr,
    Not,
    OneOrMoreExpr,
    Rule,
    RuleExpr,
    SeqExpr,
    ZeroOrMoreExpr
)

from fastidious.parser_base import (ParserMeta, ParserMixin,
                                    _FastidiousParserMixin)

from fastidious.fastidious_compiler import FastidiousCompiler


class _FastidiousParserBootstraper(
        six.with_metaclass(ParserMeta, ParserMixin, _FastidiousParserMixin)):

    p_compiler = FastidiousCompiler()
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
            "on_single_char_escape"
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
