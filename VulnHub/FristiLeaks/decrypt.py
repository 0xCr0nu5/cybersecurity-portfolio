import base64
import codecs
import sys

def decodeString(s):
    rot13_decoded = codecs.decode(s[::-1], 'rot_13')       # ROT13 decode + reverse
    base64_decoded = base64.b64decode(rot13_decoded)       # base64 decode (bytes)
    return base64_decoded.decode()                         # bytes -> str

cryptResult = decodeString(sys.argv[1])
print(cryptResult)


