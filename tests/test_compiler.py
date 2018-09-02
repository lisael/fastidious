from unittest import TestCase

from fastidious.parser import parse_grammar, Parser
from fastidious.compilers import check_rulenames, gendot
from fastidious.compilers.sanitize import (DuplicateRule, UnknownRule,
                                           LeftRecursion)


class TestRulesChecker(TestCase):
    def test_good_check(self):
        grammar = """
        a <- '1'/'2'
        """
        rules = parse_grammar(grammar)
        check_rulenames(rules)

    def test_duplicate_rule(self):
        grammar = """
        a <- '1'/'2'
        a <- '1'/'3'
        """
        rules = parse_grammar(grammar)
        with self.assertRaisesRegexp(DuplicateRule,
                                     "Rule `a` is defined twice."):
            check_rulenames(rules)

    def test_undefined_rule(self):
        grammar = """
        a <- b / c
        """
        rules = parse_grammar(grammar)
        with self.assertRaisesRegexp(
                UnknownRule,
                "Rule `[bc]` referenced in a is not defined"):
            check_rulenames(rules)


class LeftRecursionTest(TestCase):
    def test_direct_left_recursion_detection(self):
        with self.assertRaises(LeftRecursion):
            class Broken(Parser):
                __grammar__ = """
                a <- a 'b'
                """

    def test_indirect_left_recursion_detection(self):
        with self.assertRaises(LeftRecursion):
            class Broken(Parser):
                __grammar__ = """
                Value   <- [0-9.]+ / '(' Expr ')'
                Product <- Expr (('*' / '/') Expr)*
                Expr    <- 'a' / Product / Value
                """

    def test_multiple_indirect_left_recursion_detection(self):
        with self.assertRaises(LeftRecursion):
            class Broken(Parser):
                __grammar__ = """
                Value   <- [0-9.]+ / '(' Expr ')'
                Product <- 'b'/ ProductAlias
                ProductAlias <- Expr (('*' / '/') Expr)*
                Expr    <- 'a' / Product / Value
                """


class TestGendot(TestCase):
    def test_gendot(self):
        grammar = """
        a <- '1'? !'2'/ foo:('2'+ 'bar'*)?
        b <- 'a'* 'b'
        """
        rules = parse_grammar(grammar)
        dot = gendot(rules)
        self.assertEqual(dot, """digraph astgraph {
  node [fontsize=12, fontname="Courier", height=.1];
  ranksep=.3;
  rankdir=LR;
  edge [arrowsize=.5, fontname="Courier"]
    node_1 [label="a", shape="rect", style=bold]
  node_2 [label="\\"1\\""]
  subgraph cluster_3 {
    label="!";
    style="dashed";
  node_4 [label="\\"2\\""]
  }
  node_2 -> node_4
  subgraph cluster_5 {
    label="foo";
    color=grey;
  node_6 [label="\\"2\\""]
  node_6 -> node_6 [label="+"]
  node_7 [label="\\"bar\\""]
  node_7 -> node_7 [label="*"]
  node_6 -> node_7
  }
  node_1 -> node_2
  node_1 -> node_6
 node_8 [label=" ", shape="box"]
  node_4 -> node_8
  node_1 -> node_8 [label="?"]
  node_6 -> node_8
  node_7 -> node_8
  node_1 -> node_4 [label="?"]
  node_9 [label="b", shape="rect", style=bold]
  node_10 [label="\\"a\\""]
  node_10 -> node_10 [label="*"]
  node_11 [label="\\"b\\""]
  node_10 -> node_11
  node_9 -> node_10
 node_12 [label=" ", shape="box"]
  node_11 -> node_12
  node_9 -> node_11
}
""")
