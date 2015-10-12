#A separator used to break the code into two parts to aid memorability.
SEPARATOR_ = '+'

#The number of characters to place before the separator.
SEPARATOR_POSITION_ = 8

#The character used to pad codes.
PADDING_CHARACTER_ = '0'

# The character set used to encode the values.
CODE_ALPHABET_ = '23456789CFGHJMPQRVWX'

# The base to use to convert numbers to/from.
ENCODING_BASE_ = len(CODE_ALPHABET_)

# The maximum value for latitude in degrees.
LATITUDE_MAX_ = 90

#The maximum value for longitude in degrees.
LONGITUDE_MAX_ = 180

#Maxiumum code length using lat/lng pair encoding. The area of such a
#code is approximately 13x13 meters (at the equator), and should be suitable
#for identifying buildings. This excludes prefix and separator characters.
PAIR_CODE_LENGTH_ = 10

#The resolution values in degrees for each position in the lat/lng pair
#encoding. These give the place value of each position, and therefore the
#dimensions of the resulting area.
PAIR_RESOLUTIONS_ = [20.0, 1.0, .05, .0025, .000125]

#Number of columns in the grid refinement method.
GRID_COLUMNS_ = 4

#Number of rows in the grid refinement method.
GRID_ROWS_ = 5

#Size of the initial grid in degrees.
GRID_SIZE_DEGREES_ = 0.000125

#Minimum length of a code that can be shortened.
MIN_TRIMMABLE_CODE_LEN_ = 6

SP = '+0'

def isValid(code):
    sep = code.find(SEPARATOR_)
    if code.count(SEPARATOR_) > 1:
        return False
    if len(code) == 1:
        return False
    if sep == -1 or sep > SEPARATOR_POSITION_ or sep % 2 == 1:
        return False
    pad = code.find(PADDING_CHARACTER_)
    if pad != -1:
        if pad == 0:
            return False
        rpad = code.rfind(PADDING_CHARACTER_) + 1
        pads = code[pad:rpad]
        if len(pads) % 2 == 1 or pads.count(PADDING_CHARACTER_) != len(pads):
            return False
        if not code.endswith(SEPARATOR_):
            return False
    if len(code) - sep - 1 == 1:
        return False
    for ch in code:
        if ch.upper() not in CODE_ALPHABET_ and ch not in SP:
            return False
    return True


def isShort(code):
    if not isValid(code):
        return False
    sep = code.find(SEPARATOR_)
    if sep >= 0 and sep < SEPARATOR_POSITION_:
        return True
    return False


def isFull(code):
    if not isValid(code):
        return False
    if isShort(code):
        return False
    firstLatValue = CODE_ALPHABET_.find(code[0].upper()) * ENCODING_BASE_
    if firstLatValue >= LATITUDE_MAX_ * 2:
        return False
    if len(code) > 1:
        firstLngValue = CODE_ALPHABET_.find(code[1].upper()) * ENCODING_BASE_
    if firstLngValue >= LONGITUDE_MAX_ * 2:
        return False
    return True
