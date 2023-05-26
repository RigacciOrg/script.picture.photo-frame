# -*- coding: utf-8 -*-

import xbmc
import xbmcvfs
from xml.dom.minidom import parseString

__author__ = "Niccolo Rigacci"
__copyright__ = "Copyright 2023 Niccolo Rigacci <niccolo@rigacci.org>"
__license__ = "GPLv3-or-later"
__email__ = "niccolo@rigacci.org"
__version__ = "0.1.0"


def get_preferred_font(preferred_name='', preferred_size=36, required_style=''):
    """ Parse Font.xml skin file and return the name of the preferred font """
    # If preferred_name is set, it takes precedence over other parameters.
    # If required_style is set, it is mandatory.
    # The font with the closest size to preferred_size is selected.
    selected_font = 'font13'  # Default font every skin must have.
    selected_size = 24
    skin_font = xbmcvfs.File('special://skin/xml/Font.xml', 'r')
    #skin_font = open('/usr/share/kodi/addons/skin.estuary/xml/Font.xml', 'r')
    font_xml = skin_font.read()
    skin_font.close()
    #xbmc.log(msg=font_xml, level=xbmc.LOGINFO)
    dom = parseString(font_xml)
    min_diff = preferred_size
    for font in dom.documentElement.getElementsByTagName('font'):
        font_tag = {}
        for tag in ['name', 'size', 'style']:
            e = font.getElementsByTagName(tag)
            if len(e) > 0:
                font_tag[tag] = e[0].firstChild.data
        if 'name' not in font_tag or 'size' not in font_tag:
            continue
        if 'style' in font_tag and font_tag['style'] == 'bold':
            font_is_bold = True
        else:
            font_is_bold = False
        #xbmc.log(msg='Font tag: %s' % (font_tag,), level=xbmc.LOGINFO)
        if required_style == 'regular' and font_is_bold:
            continue
        if required_style == 'bold' and not font_is_bold:
            continue
        if preferred_name == font_tag['name']:
            selected_font = font_tag['name']
            selected_size = int(font_tag['size'])
            break
        diff_size = abs(preferred_size - int(font_tag['size']))
        if diff_size < min_diff:
            min_diff = diff_size
            selected_font = font_tag['name']
            selected_size = int(font_tag['size'])
    xbmc.log(msg='Selected font: %s, size: %s' % (selected_font, selected_size,), level=xbmc.LOGINFO)
    return (selected_font, selected_size)
