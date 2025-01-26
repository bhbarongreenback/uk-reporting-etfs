import re


def cusip_char_value(c, is_odd):
    # https://en.wikipedia.org/wiki/CUSIP#Check_digit_lookup_table
    if c == '0':
        return 0
    elif c in ('J', 'S'):
        return 0 if is_odd else 1
    elif c in ('1', 'A'):
        return 1 if is_odd else 2
    elif c == 'T':
        return 1 if is_odd else 3
    elif c in ('2', 'B', 'K'):
        return 2 if is_odd else 4
    elif c in ('3', 'C', 'L', 'U'):
        return 3 if is_odd else 6
    elif c in ('4', 'D', 'M', 'V'):
        return 4 if is_odd else 8
    elif c in ('E', 'N', 'W'):
        return 5 if is_odd else 0
    elif c == '5':
        return 5 if is_odd else 1
    elif c in ('O', 'X'):
        return 6 if is_odd else 2
    elif c in ('6', 'F'):
        return 6 if is_odd else 3
    elif c == 'Y':
        return 7 if is_odd else 4
    elif c in ('7', 'G', 'P'):
        return 7 if is_odd else 5
    elif c in ('8', 'H', 'Q', 'Z'):
        return 8 if is_odd else 7
    elif c in ('9', 'I', 'R'):
        return 9
    raise Exception('unknown character: ' + c)


def cusip_check_digit(s):
    """
    Given the first eight characters of a CUSIP, calculate
    the check digit we'd expect to see as the ninth character.
    """
    x = sum(cusip_char_value(c, i % 2 == 0) for i, c in enumerate(s))
    return str((10 - (x % 10)) % 10)


def isin_check_digit(s):
    """
    Given the first eleven characters of an ISIN, calculate
    the check digit we'd expect to see as the twelfth character.
    """
    s = re.sub('[A-Z]', lambda m: str(ord(m.group(0)) - 55), s)
    odds = ''.join(c for i, c in enumerate(s) if i % 2 == 0)
    evens = ''.join(c for i, c in enumerate(s) if i % 2 == 1)
    if len(evens) == len(odds):
        evens = re.sub(r'\d', lambda m: str(int(m.group(0)) * 2), evens)
    else:
        odds = re.sub(r'\d', lambda m: str(int(m.group(0)) * 2), odds)
    x = sum(int(c) for c in (evens + odds))
    return str((10 - (x % 10)) % 10)


def make_isin_from_cusip(cusip):
    '''
    Given a CUSIP, return the corresponding ISIN (which is just the
    CUSIP with "US" prepended to the front and a check digit appended
    at the end).
    '''
    return 'US' + cusip + isin_check_digit('US' + cusip)
