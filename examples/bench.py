import timeit

from fastidious.parser import _GrammarParser
from fastidious import Parser

grammar = '\n'.join(
    [l.strip() for l in _GrammarParser.__grammar__.splitlines()])

class NotMemoized(Parser):
    __memoize__ = False
    __grammar__ = grammar

bootstrap_stmt = "_GrammarParserBootstraper(%s).grammar()" % repr(grammar)
bs_nb = 50

time = timeit.timeit(
    bootstrap_stmt,
    setup="from fastidious.bootstrap import _GrammarParserBootstraper",
    number=bs_nb)
print"bootstrap\t\t", time, "s   ", time/bs_nb, "s/op   ", bs_nb/time, "op/s"

generated_stmt = "_GrammarParser(%s).grammar()" % repr(grammar)
gnr_nb = 50
time = timeit.timeit(
    generated_stmt,
    setup="from fastidious.parser import _GrammarParser",
    number=gnr_nb)
print"generated\t\t", time, "s   ", time/gnr_nb, "s/op   ", gnr_nb/time, "op/s"

nm_stmt = "NotMemoized(%s).grammar()" % repr(grammar)
nm_nb = 50
time = timeit.timeit(
    nm_stmt,
    setup="from __main__ import NotMemoized",
    number=nm_nb)
print"not memoized\t\t", time, "s   ", time/nm_nb, "s/op   ", nm_nb/time, "op/s"
