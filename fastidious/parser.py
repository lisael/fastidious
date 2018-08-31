import re

import six

from fastidious.parser_base import (_FastidiousParserMixin, ParserMeta,
                                    ParserMixin)

from fastidious.compiler.fastidious import FastidiousCompiler


class BaseParser(six.with_metaclass(ParserMeta, ParserMixin)):
    pass


class Parser(BaseParser):
    """
    Parser
    """
    p_compiler = FastidiousCompiler()


class FastidiousParser(Parser, _FastidiousParserMixin):

    __grammar__ = r"""
        grammar <- __ rules:( rule __ )+

        rule "RULE" <- terminal:"`"? name:identifier_name __ ( :alias _ )? "<-" __ expr:expression code:( __ code_block )? EOS

        code_block "CODE_BLOCK" <- "{" code:code "}" {@code}
        code <- ( ( ![{}] source_char )+ / ( "{" code "}" ) )* {p_flatten}

        alias "ALIAS" <- string_literal {p_flatten}

        expression "EXPRESSION" <- choice_expr
        choice_expr <- first:seq_expr rest:( __ "/" __ seq_expr )*
        primary_expr <- regexp_expr / lit_expr / char_range_expr / any_char_expr / rule_expr / sub_expr
        sub_expr <- "(" __ expr:expression __ ")" {@expr}

        regexp_expr <- "~" lit:string_literal flags:[iLmsux]*

        lit_expr <- lit:string_literal ignore:"i"?

        string_literal <- ( '"' content:double_string_char* '"' ) / ( "'" content:single_string_char* "'" ) {@content}
        double_string_char <- ( !( '"' / "\\" / EOL ) char:source_char ) / ( "\\" char:double_string_escape ) {@char}
        single_string_char <- ( !( "'" / "\\" / EOL ) char:source_char ) / ( "\\" char:single_string_escape ) {@char}
        single_string_escape <- "'" / common_escape
        double_string_escape <- '"' / common_escape

        any_char_expr <- "."

        rule_expr <- name:identifier_name !( __ (string_literal __ )? "<-" )

        seq_expr <- first:labeled_expr rest:( __ labeled_expr )*

        labeled_expr <- label:( identifier? __ ":" __ )? expr:prefixed_expr

        prefixed_expr <- prefix:( prefix __ )? expr:suffixed_expr
        suffixed_expr <- expr:primary_expr suffix:( __ suffix )?
        suffix <- [?+*]
        prefix <- [!&]

        char_range_expr <- "[" content:( class_char_range / class_char )* "]" ignore:"i"?
        class_char_range <- start:class_char "-" end:class_char
        class_char <- ( !( "]" / "\\" / EOL ) char:source_char ) / ( "\\" char:char_class_escape ) {@char}
        char_class_escape <- "]" / common_escape

        common_escape <- single_char_escape
        single_char_escape <- "a" / "b" / "n" / "f" / "r" / "t" / "v" / "\\"

        comment <- "#" ( !EOL source_char )*

        source_char <- .
        identifier <- identifier_name
        identifier_name <- identifier_start identifier_part* {p_flatten}
        identifier_start <- [A-Za-z_]
        identifier_part <- identifier_start / [0-9]

        __ <- ( whitespace / EOL / comment )*
        _ <- whitespace*
        whitespace <- [ \t\r]
        EOL <- "\n"
        EOS <- ( _ comment? EOL ) / ( __ EOF )
        EOF <- !.
    """  # noqa


def parse_grammar(grammar, parser_klass=FastidiousParser):
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
    rules = parser_klass.p_parse(stripped)
    return rules
