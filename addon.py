# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import xbmcaddon

from resources.lib.skinparse import get_preferred_font
from resources.lib.photoframe import photoFrameAddon, CFG

import os
import os.path

# https://kodi.wiki/view/About_Add-ons
# https://kodi.wiki/view/Add-on_structure
# https://pillow.readthedocs.io/en/latest/reference/Image.html

# Kodi Documentation 19.0
# https://codedocs.xyz/w3tech/xodi/index.html
#
# Python » Library - xbmcgui => Window
# https://codedocs.xyz/w3tech/xodi/group__python__xbmcgui__window.html
#
# Python » Library - xbmcgui » Control => Subclass - ControlImage
# https://codedocs.xyz/w3tech/xodi/group__python__xbmcgui__control__image.html
#
# Kodi Documentation Latest
# https://codedocs.xyz/xbmc/xbmc/index.html
#
# https://kodi.wiki/view/Context_Item_Add-ons
# https://kodi.wiki/view/JSON-RPC_API

__author__ = "Niccolo Rigacci"
__copyright__ = "Copyright 2019 Niccolo Rigacci <niccolo@rigacci.org>"
__license__ = "GPLv3-or-later"
__email__ = "niccolo@rigacci.org"
__version__ = "0.2.0"


#--------------------------------------------------------------------------
# Get info about this Addon.
#--------------------------------------------------------------------------
ADDON = xbmcaddon.Addon()
ADDONNAME = ADDON.getAddonInfo('name')
__localize__ = ADDON.getLocalizedString

#--------------------------------------------------------------------------
# Define some global configuration settings.
# NOTICE: All Kodi settings are actually strings.
#--------------------------------------------------------------------------
CFG.PLAYLIST = ADDON.getSetting('playlist-name')
CFG.PLAYLIST_EXT = 'm3u'

# Choose a font for image captions (Exif UserComment).
if ADDON.getSetting('font-req-style').lower() in ['true', '1']:
    CFG.REQUIRED_FONT_STYLE = ADDON.getSetting('font-style')
else:
    CFG.REQUIRED_FONT_STYLE = ''
if (ADDON.getSetting('font-auto').lower() in ['true', '1']):
    CFG.REQUIRED_FONT_NAME = ''
else:
    CFG.REQUIRED_FONT_NAME = ADDON.getSetting('font-name')  # See skin.[theme]/xml/Font.xml
CFG.PREFERRED_FONT_SIZE = int(ADDON.getSetting('font-size'))
CFG.CAPTION_FONT, CFG.CAPTION_FONT_SIZE = get_preferred_font(
    CFG.REQUIRED_FONT_NAME,
    CFG.PREFERRED_FONT_SIZE,
    CFG.REQUIRED_FONT_STYLE)
# Characters width/height ratio, used to guess caption width.
# Estuary skin: 0.32 for font37, 0.37 for font36_title
CFG.CAPTION_FONT_RATIO_XY = 0.37

CFG.SLIDE_TIME_DEFAULT = float(ADDON.getSetting('slide-time'))
CFG.SLIDE_TIME_MIN = 3.0
CFG.SLIDE_TIME_MAX = 120.0

# Vertical position of caption, percent of image height.
CFG.CAPTION_Y_POS_PERC = float(ADDON.getSetting('caption-position')) / 100.0
# Max number of lines for image caption.
CFG.CAPTION_MAX_ROWS = int(ADDON.getSetting('caption-max-rows'))
# Text color in AARRGGBB format.
CFG.CAPTION_FG_COLOR = '0xffffff00'


#--------------------------------------------------------------------------
# Addon entry point: get the Context Menu item path and run on that.
#--------------------------------------------------------------------------
if (__name__ == '__main__'):

    # WARNING: Functions that receive paths and filenames must use
    # .encode('utf-8') on that arguments to circumvent a Kodi 19
    # bug: https://forum.kodi.tv/showthread.php?tid=366245
    # The problem is with Kodi Python sys.getfilesystemencoding() = ascii
    #
    #message = 'getdefaultencoding() = "%s", getfilesystemencoding() = %s'
    #    % (sys.getdefaultencoding(), sys.getfilesystemencoding())
    #xbmc.log(msg=message, level=xbmc.LOGINFO)
    #
    # Functions affected:
    #   * os.path.isfile()
    #   * os.path.isdir()
    #   * open()

    contextmenu_item = xbmc.getInfoLabel('ListItem.FilenameAndPath')
    message = '%s: Launched with Context Menu item: "%s"' % (ADDONNAME, contextmenu_item,)
    xbmc.log(msg=message, level=xbmc.LOGINFO)
    if os.path.isfile(contextmenu_item.encode('utf-8')):
        directory = os.path.dirname(contextmenu_item)
        playlist = os.path.basename(contextmenu_item)
    else:
        directory = contextmenu_item
        playlist = None
    if not os.path.isdir(directory.encode('utf-8')):
        line1 = __localize__(32002) % (CFG.PLAYLIST, CFG.PLAYLIST_EXT)
        line2 = __localize__(32003)
        message = "%s\n%s" % (line1, line2)
        xbmcgui.Dialog().ok(ADDONNAME, message)
    else:
        window_instance = photoFrameAddon()
        window_instance.initSlideshow(directory, playlist)
        window_instance.doModal()
        del window_instance
