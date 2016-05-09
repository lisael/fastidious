#! /usr/bin/python
from fastidious import Parser


class JSON (Parser):
    """
    A quick and dirty json parser. Method json() returns the object described
    by the json-encoded input:

    >>> JSON.p_parse('["hello", true]"')
    ['hello', True]

    This is an example using the well-known JSON syntax, It's by no mean intended
    to provided a replacement of built-in json package.
    """

    __grammar__ = r"""
        json <- value:value EOF {@value}
        value <- _ val:(string / number / object / array / true_false_null) _ {@val}  # noqa

        object <- "{" :members "}"
        members <- (first:member rest:("," member)*)? {on_elements}
        member <- :string ":" :value

        array <- "[" :elements "]" {@elements}
        elements <- (first:value rest:("," value)*)?

        true_false_null <- "true" / "false" / "null"

        string <- _ '"' :chars '"' _ {@chars}
        chars <- ~"[^\"]*"

        number <- (int frac exp) / (int exp) / (int frac) / int
        int <- "-"? ((digit1to9 digits) / digit)
        frac <- "." digits
        exp <- e digits
        digits <- digit+
        e <- ~"e[-+]?"i
        digit1to9 <- ~"[1-9]"
        digit <- ~"[0-9]"

        _ <- ~"\\s*"
        EOF <- !.
    """

    def on_elements(self, value, first, rest):
        return [first] + [i[1] for i in rest]

    def on_true_false_null(self, value):
        if value == "true":
            return True
        elif value == "false":
            return False
        return None

    def on_member(self, _, string, value):
        return (string, value[1])

    def on_object(self, _, members):
        return dict(members)


if __name__ == "__main__":
    import sys
    print(JSON.p_parse("".join(sys.argv[1:])))
