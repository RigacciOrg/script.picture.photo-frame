# -*- coding: utf-8 -*-
"""
Module to get UserComment and Orientation tags from Exif data
of a PIL image. UserComment is properly decoded by character
set and bytes ordering.
"""

import logging
import xbmc
from PIL import ExifTags

__author__ = "Niccolo Rigacci"
__copyright__ = "Copyright 2023 Niccolo Rigacci <niccolo@rigacci.org>"
__license__ = "GPLv3-or-later"
__email__ = "niccolo@rigacci.org"
__version__ = "0.1.0"

def log_debug(string):
    """ Emit some debug information  """
    #logging.error(string)
    #xbmc.log(msg=string, level=xbmc.LOGINFO)
    pass


def utf16_guess_decode(string, hint=None):
    """ Try to guess Little-Endian or Big-Endian bytes ordering """
    try:
        lit_endian = string.decode('utf-16le').strip()
    except:
        lit_endian = ''
    try:
        big_endian = string.decode('utf-16be').strip()
    except:
        big_endian = ''
    if lit_endian == '' and big_endian == '':
        guess = 'I'
    elif lit_endian != '' and hint == 'I':
        guess = 'I'
    elif big_endian != '' and hint == 'M':
        guess = 'M'
    elif lit_endian == '' or ord(lit_endian[0]) >= 0x4000:
        # If the codepoint of first char is too high, use the other guess.
        guess = 'M'
    else:
        guess = 'I'
    if guess == 'I':
        log_debug('Guessed UTF-16 Little-Endian (Intel) bytes ordering')
        return lit_endian
    else:
        log_debug('Guessed UTF-16 Big-Endian (Motorola) bytes ordering')
        return big_endian


def null_terminate(string):
    """ Return the string truncated at the first NULL char """
    i = string.find(b'\0')
    if i >= 0:
        return string[0:i]
    else:
        return string


def decode_exif_usercomment(exif_tag):
    """ Get the string from an Exif UserComment tag, with proper decoding """
    try:
        code_id = exif_tag[0:8].upper()
        content = exif_tag[8:]
        log_debug('Exif code_id: %s' % (code_id,))
        log_debug('Exif content: %s' % (content,))
    except:
        return None
    if code_id.startswith(b'ASCII'):
        log_debug('UserComment char code: ITU-T T.50 IA5 (ASCII)')
        user_comment = null_terminate(content).decode('ascii', 'ignore').rstrip()
    elif code_id.startswith(b'JIS'):
        log_debug('UserComment char code: JIS X208-1990')
        user_comment = null_terminate(content).decode('shift_jis', 'ignore').rstrip()
    elif code_id.startswith(b'UNICODE'):
        # Unicode is UCS-2 (16bit) in Exif, guess the byte order.
        log_debug('UserComment char code: Unicode')
        user_comment = utf16_guess_decode(content).rstrip()
    elif code_id.startswith(b'\0' * 8):
        log_debug("UserComment char code: Undefined ('\\0' * 8); assuming UTF-8")
        user_comment = null_terminate(content).decode('utf-8', 'ignore').rstrip()
    else:
        log_debug('UserComment char code: Unknown; assuming UTF-8')
        user_comment = null_terminate(exif_tag).decode('utf-8', 'ignore').strip()
    if len(user_comment) == 0:
        user_comment = None
    return user_comment


def get_exif_tags(image):
    """ Get a PIL image and return a dictionary with some Exif tags """
    tags = {}
    # Assume Exif Orientation tag = 1, if missing.
    tags['orientation'] = 1
    tags['usercomment'] = None
    try:
        exif_data = image.getexif()
        # Get UserComment.
        i = list(ExifTags.TAGS.values()).index('UserComment')
        k = list(ExifTags.TAGS.keys())[i]
        if k in exif_data:
            tags['usercomment'] = decode_exif_usercomment(exif_data[k])
        # Get Orientation.
        i = list(ExifTags.TAGS.values()).index('Orientation')
        k = list(ExifTags.TAGS.keys())[i]
        if k in exif_data:
            tags['orientation'] = exif_data[k]
    except Exception as e:
        exception_str = str(e)
        log_debug('Error reading Exif data from file: %s' % (str(e),), )
    return tags
