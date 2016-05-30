from urlparse import urlparse


from fastidious import Parser


class URLParser(Parser):
    """
    A url parser that uses a big fat regex and returns an
    urlparse.ParseResult on match
    """

    __grammar__ = r"""
    url "URL" <- ~'(?:(?:[0-9a-z+]+)://)(?:\\S+(?::\\S*)?@)?(?:(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}(?:\\.(?:[1-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))|(?:(?:[a-z\\u00a1-\\uffff0-9]+-?)*[a-z\\u00a1-\\uffff0-9]+)(?:\\.(?:[a-z\\u00a1-\\uffff0-9]+-?)*[a-z\\u00a1-\\uffff0-9]+)*(?:\\.(?:[a-z\\u00a1-\\uffff]{2,})))(?::\\d{2,5})?(?:/[^\\s]*)?'
    """  # noqa

    def on_url(self, val):
        return urlparse(val)
