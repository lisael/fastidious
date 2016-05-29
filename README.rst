==========
Fastidious
==========
A python `parsing expression grammar
(PEG) <https://en.wikipedia.org/wiki/Parsing_expression_grammar>`_ based parser
generator.  It is loosely based on https://github.com/PuerkitoBio/pigeon

Usage
=====

From `the calculator example
<https://github.com/lisael/fastidious/blob/master/examples/calculator.py>`_.

.. code-block:: python

        #! /usr/bin/python
        from fastidious import Parser


        class Calculator(Parser):

            # __grammar__ is the PEG definition. Each `rulename <- a rule`
            # adds a method `Calculator.rulename()`. This methods tries to
            # match the input at current position
            __grammar__ = r"""
            # the label is ommited. `:expr` is equivalent to `expr:expr`
            eval <- :expr EOF {@expr}

            # action {on_expr} calls `Calculator.on_expr(self, value, first, rest)`
            # on match. `first` and `rest` args are the labeled parts of the rule
            term <- first:factor rest:( _ mult_op _ factor )* {on_expr}

            # Because the Parser has a method named `on_expr` ("on_" + rulename)
            # this method is the implicit action of this rule. We omitted {on_expr}
            expr <- _ first:term rest:( _ add_op _ term  )* _

            # there's no explicit or implicit action. These rules return their exact
            # matches
            add_op <- '+' / '-'
            mult_op <- '*' / '/'

            # action {@fact} means : return only the match of part labeled `fact`.
            factor <- ( '(' fact:expr ')' ) / fact:integer {@fact}

            integer <- '-'? [0-9]+
            _ <- [ \n\t\r]*

            # this one is tricky. `.` means "any char". At EOF there's no char,
            # thus Not any char, thus `!.`
            EOF <- !.
            """

            def on_expr(self, value, first, rest):
                result = first
                for r in rest:
                    op = r[1]
                    if op == '+':
                        result += r[3]
                    elif op == '-':
                        result -= r[3]
                    elif op == '*':
                        result *= r[3]
                    else:
                        result /= r[3]
                return result

            def on_integer(self, value):
                return int(self.flatten(value))

        if __name__ == "__main__":
            import sys
            c = Calculator("".join(sys.argv[1:]))
            print(c.eval())

Then you have a full-fledge state-of-the-art integer only calculator \o/

.. code-block:: sh

        examples/calculator.py "-21 *  ( 3 + 1 ) / -2"
        42

PEG Syntax
==========

The whole syntax is formally defined in `fastidious parser class
<https://github.com/lisael/fastidious/blob/master/fastidious/parser.py>`_, using
the PEG syntax (which is actually used to generate the fastidious parser itself,
so it's THE TRUTH. Yes, I like meta-stuff).  What follows is an informal and
rather incomplete description of this syntax.

Identifiers, whitespace, comments and literals follow a subset of python
notation:

.. code-block::


        # a comment
        'a string literal'
        "a more \"complex\" one with a litteral '\\' \nand a second line"
        _aN_iden7ifi3r

Identifiers MUST be valid python identifiers as they are added as methods on the
parser objects. Parsers have utility methods that are prefixed by `p_` and
`_p_`. Please avoid these names.

Rules
+++++

A PEG grammar consists of a set of rules. A rule is an identifier followed by a
rule definition operator ``<-`` and an expression. An optional display name - a
string literal used in error messages instead of the rule identifier - can be
specified after the rule identifier. An action can also be specified enclosed in
``{}`` after the rule, more on this later.

.. code-block::

        rule_a "friendly name" <- 'a'+ {an_action} # one or more lowercase 'a's

Expressions
+++++++++++

A rule is defined by an expression. The following sections describe the various
expression types. Expressions can be grouped by using parentheses, and a rule
can be referenced by its identifier in place of an expression.

Choice expression
-----------------

The choice expression is a list of expressions that will be tested in the order
they are defined. The first one that matches will be used. Expressions are
separated by the forward slash character "/". E.g.:

.. code-block::

        choice_expr <- A / B / C # A, B and C should be rules declared in the grammar

Because the first match is used, it is important to think about the order of
expressions. For example, in this rule, "<=" would never be used because the "<"
expression comes first:

.. code-block::

        bad_choice_expr <- "<" / "<="

Sequence expression
-------------------

The sequence expression is a list of expressions that must all match in that
same order for the sequence expression to be considered a match. Expressions are
separated by whitespace. E.g.:

.. code-block::

        seq_expr <- "A" "b" "c" # matches "Abc", but not "Acb"

Labeled expression
------------------

A labeled expression consists of an identifier followed by a colon ":" and an
expression. A labeled expression introduces a variable named with the label that
can be referenced in the action of the rule. The variable will have the value of
the expression that follows the colon. E.g.:

.. code-block::

        labeled_expr <- value:[a-z]+ "a suffix" {@value}

If this sequence matches, the rule returns only the ``[a-z]+`` part instead of
``["thevalue", "a suffix"]``

Error reporting
===============

PEG parsers design makes automatic syntax error reporting hard. The parser has
to follow every possible path from the root and fail to parse the document before
it can tell there's a syntax error. It's even harder to tell where is the error,
because at this point, we only know that every path has fail.

However this paper http://arxiv.org/pdf/1405.6646v1.pdf suggest a bunch of
techniques to improve syntax error detection, we implemented some of them and, by
experience, it's satisfying (i.e: I can debug my errors using fastidious messages).

TODO
====

- make a tool to generate standalone modules
- python3
- more tests
- tox
- travis
