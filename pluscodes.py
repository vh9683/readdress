import re
import math

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

def encode(latitude, longitude, codeLength=PAIR_CODE_LENGTH_):
    if codeLength < 2 or (codeLength < SEPARATOR_POSITION_ and codeLength % 2 == 1):
        raise ValueError('Invalid Open Location Code length' + str(codeLength))
    latitude = clipLatitude(latitude)
    longitude = normalizeLongitude(longitude)
    if latitude == 90:
        latitude = latitude - computeLatitutePrecision(codeLength)
    code = encodePairs(latitude, longitude, min(codeLength, PAIR_CODE_LENGTH_))
    if codeLength > PAIR_CODE_LENGTH_:
        code = code + encodeGrid(latitude, longitude, codeLength - PAIR_CODE_LENGTH_)
    return code

def decode(code):
    if not isFull(code):
        raise ValueError('Passed Open Location Code is not a valid full code' + str(code))
    code = re.sub('[+0]','',code)
    code = code.upper()
    codeArea = decodePairs(code[0:PAIR_CODE_LENGTH_])
    if len(code) <= PAIR_CODE_LENGTH_:
        return codeArea
    gridArea = decodeGrid(code[PAIR_CODE_LENGTH_:])
    return CodeArea(codeArea.latitudeLo + gridArea.latitudeLo,
            codeArea.longitudeLo + gridArea.longitudeLo,
            codeArea.latitudeLo + gridArea.latitudeHi,
            codeArea.longitudeLo + gridArea.longitudeHi,
            codeArea.codeLength + gridArea.codeLength)

def recoverNearest(shortcode, referenceLatitude, referenceLongitude):
    if not isShort(shortcode):
        raise ValueError('Passed short code is not valid' + str(shortcode))
    referenceLatitude = clipLatitude(referenceLatitude)
    referenceLongitude = normalizeLongitude(referenceLongitude)
    shortcode = shortcode.upper()
    paddingLength = SEPARATOR_POSITION_ - shortcode.find(SEPARATOR_)
    resolution = pow(20, 2 - (paddingLength / 2))
    areaToEdge = resolution / 2.0
    roundedLatitude = math.floor(referenceLatitude / resolution) * resolution
    roundedLongitude = math.floor(referenceLongitude / resolution) * resolution
    codeArea = decode(encode(roundedLatitude, roundedLongitude)[0:paddingLength] + shortcode)
    degreesDifference = codeArea.latitudeCenter - referenceLatitude
    if degreesDifference > areaToEdge:
        codeArea.latitudeCenter -= resolution
    elif degreesDifference < -areaToEdge:
        codeArea.latitudeCenter += resolution
    degreesDifference = codeArea.longitudeCenter - referenceLongitude
    if degreesDifference > areaToEdge:
        codeArea.longitudeCenter -= resolution
    elif degreesDifference < -areaToEdge:
        codeArea.longitudeCenter += resolution
    return encode(codeArea.latitudeCenter, codeArea.longitudeCenter, codeArea.codeLength)

def shorten(code,latitude,longitude):
    if not isFull(code):
        raise ValueError('Passed code is not valid and full: ' + str(code))
    if code.find(PADDING_CHARACTER_) != -1:
        raise ValueError('Cannot shorten padded codes: ' + str(code))
    code = code.upper()
    codeArea = decode(code)
    if codeArea.codeLength < MIN_TRIMMABLE_CODE_LEN_:
        raise ValueError('Code length must be at least ' + MIN_TRIMMABLE_CODE_LEN_)
    latitude = clipLatitude(latitude)
    longitude = normalizeLongitude(longitude)
    coderange = max(abs(codeArea.latitudeCenter - latitude), abs(codeArea.longitudeCenter - longitude))
    for i in range(len(PAIR_RESOLUTIONS_) - 2, 0, -1):
        if coderange < (PAIR_RESOLUTIONS_[i] * 0.3):
            return code[(i+1)*2:]
    return code

def clipLatitude(latitude):
    return min(90,max(-90,latitude))

def computeLatitutePrecision(codeLength):
    if codeLength <= 10:
        return pow(20,math.floor((codeLength / -2) + 2))
    return pow(20, -3) / pow(GRID_ROWS_, codeLength - 10)

def normalizeLongitude(longitude):
    while longitude < -180:
        longitude = longitude + 360;
    while longitude >= 180:
        longitude = longitude - 360;
    return longitude;

def encodePairs(latitude, longitude, codeLength):
    code = ''
    adjustedLatitude = latitude + LATITUDE_MAX_
    adjustedLongitude = longitude + LONGITUDE_MAX_
    digitCount = 0
    while digitCount < codeLength:
        placeValue = PAIR_RESOLUTIONS_[math.floor(digitCount / 2)]
        digitValue = math.floor(adjustedLatitude / placeValue)
        adjustedLatitude -= digitValue * placeValue
        code += CODE_ALPHABET_[digitValue]
        digitCount += 1
        digitValue = math.floor(adjustedLongitude / placeValue)
        adjustedLongitude -= digitValue * placeValue
        code += CODE_ALPHABET_[digitValue]
        digitCount += 1
        if digitCount == SEPARATOR_POSITION_ and digitCount < codeLength:
            code += SEPARATOR_
    if len(code) < SEPARATOR_POSITION_:
        code += ''.zfill(SEPARATOR_POSITION_ - len(code))
    if len(code) == SEPARATOR_POSITION_:
        code += SEPARATOR_
    return code

def encodeGrid(latitude, longitude, codeLength):
    code = ''
    latPlaceValue = GRID_SIZE_DEGREES_
    lngPlaceValue = GRID_SIZE_DEGREES_
    adjustedLatitude = (latitude + LATITUDE_MAX_) % latPlaceValue
    adjustedLongitude = (longitude + LONGITUDE_MAX_) % lngPlaceValue
    for i in range(codeLength):
        row = math.floor(adjustedLatitude / (latPlaceValue / GRID_ROWS_))
        col = math.floor(adjustedLongitude / (lngPlaceValue / GRID_COLUMNS_))
        latPlaceValue /= GRID_ROWS_
        lngPlaceValue /= GRID_COLUMNS_
        adjustedLatitude -= row * latPlaceValue
        adjustedLongitude -= col * lngPlaceValue
        code += CODE_ALPHABET_[row * GRID_COLUMNS_ + col]
    return code;

def decodePairs(code):
    latitude = decodePairsSequence(code, 0)
    longitude = decodePairsSequence(code, 1)
    return CodeArea( latitude[0] - LATITUDE_MAX_,
                     longitude[0] - LONGITUDE_MAX_,
                     latitude[1] - LATITUDE_MAX_,
                     longitude[1] - LONGITUDE_MAX_,
                     len(code))

def decodePairsSequence(code, offset):
    i = 0
    value = 0
    while (i * 2 + offset < len(code)):
        value += CODE_ALPHABET_.find(code[i * 2 + offset]) * PAIR_RESOLUTIONS_[i]
        i += 1
    return [value, value + PAIR_RESOLUTIONS_[i - 1]]

def decodeGrid(code):
    latitudeLo = 0.0
    longitudeLo = 0.0
    latPlaceValue = GRID_SIZE_DEGREES_
    lngPlaceValue = GRID_SIZE_DEGREES_
    i = 0
    while i < len(code):
        codeIndex = CODE_ALPHABET_.find(code[i])
        row = math.floor(codeIndex / GRID_COLUMNS_)
        col = codeIndex % GRID_COLUMNS_
        latPlaceValue /= GRID_ROWS_
        lngPlaceValue /= GRID_COLUMNS_
        latitudeLo += row * latPlaceValue
        longitudeLo += col * lngPlaceValue
        i += 1
    return CodeArea( latitudeLo, longitudeLo, latitudeLo + latPlaceValue,
                     longitudeLo + lngPlaceValue, len(code));

class CodeArea:
    def __init__(self,latitudeLo, longitudeLo, latitudeHi, longitudeHi, codeLength):
        self.latitudeLo = latitudeLo
        self.longitudeLo = longitudeLo
        self.latitudeHi = latitudeHi
        self.longitudeHi = longitudeHi
        self.codeLength = codeLength
        self.latitudeCenter = min( latitudeLo + (latitudeHi - latitudeLo) / 2, LATITUDE_MAX_)
        self.longitudeCenter = min( longitudeLo + (longitudeHi - longitudeLo) / 2, LONGITUDE_MAX_)

    def __repr__(self):
        return str([self.latitudeLo,
                self.longitudeLo,
                self.latitudeHi,
                self.longitudeHi,
                self.latitudeCenter,
                self.longitudeCenter,
                self.codeLength])

    def latlng(self):
        return [self.latitudeCenter, self.longitudeCenter]
