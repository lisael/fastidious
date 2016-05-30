#! /usr/bin/env python
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
    expr "EXPRESSION" <- _ first:term rest:( _ add_op _ term  )* _

    # there's no explicit or implicit action. These rules return their exact
    # matches. The alias OPERATOR is used in error messages
    add_op "OPERATOR" <- '+' / '-'
    mult_op "OPERATOR" <- '*' / '/'

    # action {@fact} means : return only the match of part labeled `fact`.
    factor "EXPRESSION" <- ( '(' fact:expr ')' ) / fact:integer {@fact}

    integer "INT"<- '-'? [0-9]+
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
        return int(self.p_flatten(value))

if __name__ == "__main__":
    import sys
    print(Calculator.p_parse("".join(sys.argv[1:])))
