#! /usr/bin/env python
import gc
import sys
from timeit import repeat

from fastidious.parser import FastidiousParser, BaseParser, Parser
from fastidious.fastidious_compiler import FastidiousCompiler
from fastidious.bootstrap import _FastidiousParserBootstraper

grammar = '\n'.join(
    [l.strip() for l in FastidiousParser.__grammar__.splitlines()])

kb = len(grammar) / 1024.0


class Default(Parser):
    __grammar__ = grammar


class NotMemoized(BaseParser):
    p_compiler = FastidiousCompiler(memoize=False)
    __grammar__ = grammar


class NoCodeGen(BaseParser):
    p_compiler = FastidiousCompiler(gen_code=False)
    __grammar__ = grammar


class NotJSONParser(Parser):
    __grammar__ = r"""
        value <- _ (string / number / object / array / true_false_null) _

        object <- "{" members "}"
        members <- (pair ("," pair)*)?
        pair <- string ":" value
        array <- "[" elements "]"
        elements <- (value ("," value)*)?
        true_false_null <- "true" / "false" / "null"

        string <- _ '"' chars '"' _
        chars <- ~"[^\"]*"  # todo implement the real thing
        number <- (int frac exp) / (int exp) / (int frac) / int
        int <- "-"? ((digit1to9 digits) / digit)
        frac <- "." digits
        exp <- e digits
        digits <- digit+
        e <- "e+" / "e-" / "e" / "E+" / "E-" / "E"
        # e <- ~"e[-+]?"i # faster but not in parsimonious' benchmark

        digit1to9 <- ~"[1-9]"
        digit <- ~"[0-9]"
        _ <- ~"\\s*"

    """


if "--json-code" in sys.argv:
    for r in NotJSONParser.__rules__:
        print(r._py_code)
        print("")
    sys.exit(0)


class NotJSONNoCodeGenParser(BaseParser):
    # __code_gen__ = False
    p_compiler = FastidiousCompiler(gen_code=False)
    __grammar__ = NotJSONParser.__grammar__


class NotJSONNoMemoizedParser(Parser):
    p_compiler = FastidiousCompiler(memoize=False)
    __grammar__ = NotJSONParser.__grammar__


father = """{
        "id" : 1,
        "married" : true,
        "name" : "Larry Lopez",
        "sons" : null,
        "daughters" : [
            {
            "age" : 26,
            "name" : "Sandra"
            },
            {
            "age" : 25,
            "name" : "Margaret"
            },
            {
            "age" : 6,
            "name" : "Mary"
            }
            ]
        }"""
more_fathers = ','.join([father] * 60)
json = '{"fathers" : [' + more_fathers + ']}'


def benchit(klass, source, entry_point, ref=None):
    entry_point = getattr(klass, entry_point)
    # test the parser correctness
    p = klass(source)
    entry_point(p)
    assert p.p_suffix() == ""

    gc.collect()

    NUMBER = 1
    REPEAT = 5
    total_seconds = min(repeat(lambda: entry_point(klass(source)),
                               lambda: gc.enable(),
                               repeat=REPEAT,
                               number=NUMBER))
    seconds_each = total_seconds / NUMBER
    t = seconds_each

    if ref is not None:
        if isinstance(ref, float):
            var = "(%.1f%%)" % ((ref - t) * 100 / ref)
        else:
            var = ref
    else:
        var = ""

    kb = len(source) / 1024.0
    print('%-25s: Took %.3fs to parse %.1fKB: %.0fKB/s %s' % (
        klass.__name__, seconds_each, kb, kb / seconds_each, var))
    return seconds_each


if __name__ == "__main__":
    ref = benchit(NotJSONParser, json, "value")
    if "--json-only" in sys.argv:
        sys.exit(0)
    benchit(NotJSONNoCodeGenParser, json, "value", ref)
    benchit(NotJSONNoMemoizedParser, json, "value", ref)
    ref = benchit(FastidiousParser, grammar, "grammar", "(base)")
    benchit(_FastidiousParserBootstraper, grammar, "grammar", ref)
    ref = benchit(Default, grammar, "grammar", "(base)")
    benchit(NoCodeGen, grammar, "grammar", ref)
    benchit(NotMemoized, grammar, "grammar", ref)

    default = Default(grammar).grammar()
    nm = NotMemoized(grammar).grammar()
    assert default == nm
