import xbmc
import xbmcgui
import xbmcaddon

from PIL import Image, ExifTags
from collections import deque
import json
import hashlib
import os
import os.path
import re
import threading
import tempfile

# https://kodi.wiki/view/About_Add-ons
# https://kodi.wiki/view/Add-on_structure
# https://pillow.readthedocs.io/en/latest/reference/Image.html
# https://codedocs.xyz/xbmc/xbmc/group__python__xbmcgui__window.html
# https://codedocs.xyz/xbmc/xbmc/group__python__xbmcgui__control__image.html
# https://kodi.wiki/view/Context_Item_Add-ons

__author__ = "Niccolo Rigacci"
__copyright__ = "Copyright 2019 Niccolo Rigacci <niccolo@rigacci.org>"
__license__ = "GPLv3-or-later"
__email__ = "niccolo@rigacci.org"
__version__ = "0.1.2"

#--------------------------------------------------------------------------
#--------------------------------------------------------------------------
PLAYLIST = 'playlist'
PLAYLIST_EXT = 'm3u'
GEOMETRY_RE = '(\d+)x(\d+)\+(\d+)\+(\d+)'
FRAME_RATIOS = ('24x9', '16x9', '3x2', '4x3')

SLIDE_TIME_DEFAULT = 5.0
SLIDE_TIME_MIN = 3.0
SLIDE_TIME_MAX = 60.0

# Search the Exif key for the Orientation tag.
ORIENTATION_TAG = None
for tag in ExifTags.TAGS.keys():
    if ExifTags.TAGS[tag] == 'Orientation':
        ORIENTATION_TAG = tag
        break

# Rotation needed (as per PIL) upon Exif orientation.
EXIF_ROTATE = {
    3: Image.ROTATE_180,
    6: Image.ROTATE_270,
    8: Image.ROTATE_90
}

# Image to instantiate the xbmcgui.ControlImage().
DUMMY_IMAGE = 'resources/slides.jpg'

# Keycodes.
# See https://codedocs.xyz/xbmc/xbmc/group__kodi__key__action__ids.html
ACTION_NONE = 0
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_PAUSE = 12
ACTION_SELECT_ITEM = 7
ACTION_NEXT_PICTURE = 28
ACTION_PREV_PICTURE = 29
ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4

#--------------------------------------------------------------------------
# Get info about this Addon.
#--------------------------------------------------------------------------
ADDON     = xbmcaddon.Addon()
ADDONNAME = ADDON.getAddonInfo('name')
ADDONPATH = ADDON.getAddonInfo('path').decode('utf-8')
__localize__ = ADDON.getLocalizedString

#--------------------------------------------------------------------------
# Kodi default is to emit messages with level >= xbmc.LOGNOTICE, this is
# fixed and can be changed only in userdata/advancedsettings.xml.
# So we make our own configurable logging verbosity.
#--------------------------------------------------------------------------
LOG_LEVEL = {
    'DEBUG':   xbmc.LOGDEBUG,
    'INFO':    xbmc.LOGINFO,
    'NOTICE':  xbmc.LOGNOTICE,
    'WARNING': xbmc.LOGWARNING,
    'ERROR':   xbmc.LOGERROR,
    'FATAL':   xbmc.LOGFATAL
}
# Create the inverse dictionary, to search the label by value.
LOG_LABEL = dict(zip(LOG_LEVEL.values(), LOG_LEVEL.keys()))

#--------------------------------------------------------------------------
#--------------------------------------------------------------------------
def getScreensaver():
    command = {
        'jsonrpc': '2.0', 'id': 0, 'method': 'Settings.getSettingValue',
        'params': { 'setting': 'screensaver.mode' }
    }
    json_rpc = json.loads(xbmc.executeJSONRPC(json.dumps(command)))
    try:
        result = json_rpc['result']['value']
    except:
        result = None
    return result

#--------------------------------------------------------------------------
#--------------------------------------------------------------------------
def setScreensaver(mode):
    command = {
        'jsonrpc': '2.0', 'id': 0, 'method': 'Settings.setSettingValue',
        'params': { 'setting': 'screensaver.mode', 'value': mode}
    }
    json_rpc = json.loads(xbmc.executeJSONRPC(json.dumps(command)))
    try:
        result = json_rpc['result']
    except:
        result = False
    return result


#--------------------------------------------------------------------------
# Add-on main window.
#--------------------------------------------------------------------------
class photoFrameAddon(xbmcgui.Window):

    def initSlideshow(self, directory, playlist=None):
        self.verbosity = xbmc.LOGINFO
        if ADDON.getSetting('LogLevel') in LOG_LEVEL:
            self.verbosity = LOG_LEVEL[ADDON.getSetting('LogLevel')]
        self.myLog(u'initSlideshow(%s, %s)' % (directory, playlist), xbmc.LOGNOTICE)
        self.saved_screensaver = getScreensaver()
        self.myLog(u'getScreenaver(): "%s"' % (self.saved_screensaver,), xbmc.LOGINFO)
        if self.saved_screensaver != '':
            result = setScreensaver('')
            self.myLog(u'setScreenaver("%s"): %s' % ('', result), xbmc.LOGINFO)
        self.directory = directory
        self.slide_time = SLIDE_TIME_DEFAULT
        self.slides = deque([])
        self.filename = {}
        self.geometry = {}
        self.cache = {}
        # NOTICE: API v17 has a bug: getWidth() and getHeight() actually return
        # the display resolution, which is not the same as the Window instance size.
        # See https://github.com/xbmc/xbmc/pull/12279
        # E.g. display resolution is 1360x768, while Window size is 1280x720.
        # self.getResolution() returns RES_DESKTOP = 16, useless and not documented in Kodi 17.6.
        # TODO: How to retrieve the actual Window size in API v17? Workaround: use settings.xml.
        #self.img_w = self.getWidth()
        #self.img_h = self.getHeight()
        self.img_w = int(ADDON.getSetting('WindowWidth'))
        self.img_h = int(ADDON.getSetting('WindowHeight'))
        self.myLog(u'Window: %dx%d, image: %dx%d' % (self.getWidth(), self.getHeight(), self.img_w, self.img_h), xbmc.LOGINFO)

        # Search the best preset to match the window ratio found in add-on settings.
        window_ratio = float(self.img_w) / float(self.img_h)
        min_diff = 999.9
        for preset in FRAME_RATIOS:
            w, h = preset.split('x')
            preset_ratio = float(w) / float(h)
            if abs(preset_ratio - window_ratio) < min_diff:
                min_diff = abs(preset_ratio - window_ratio)
                self.frame_ratio = preset
        self.myLog(u'Best frame ratio in presets is %s' % (self.frame_ratio,), xbmc.LOGINFO)

        self.image = xbmcgui.ControlImage(0, 0, self.img_w, self.img_h, os.path.join(ADDONPATH, DUMMY_IMAGE))
        self.addControl(self.image)
        self.getSlideList(self.directory, playlist, self.frame_ratio)
        self.timer = threading.Timer(self.slide_time, self.nextSlide)
        self.autoPlayStatus = True
        self.mutex = threading.Lock()
        self.cachePrepare()
        self.slides.rotate(1)
        self.nextSlide()

    def myLog(self, msg, level):
        """ Log to Kodi with xbmc.LOGNOTICE, but using our own verbosity """
        if level >= self.verbosity:
            message = '%s: %7s: %s' % (ADDONNAME, LOG_LABEL[level], msg,)
            xbmc.log(msg=message.encode('utf-8'), level=xbmc.LOGNOTICE)

    def filenameHash(self, string):
        """ Return an hash suitable to index a filenames list """
        return hashlib.md5(string).hexdigest()[0:12]

    def cachePrepare(self):
        """ Three temporary files for caching images: current, previous and next """
        for i in range(0, 3):
            t = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            self.cache[self.filenameHash('dummy%d.img' % i)] = t.name

    def cacheRemove(self):
        """ Remove temporary files """
        for i in self.cache:
            os.remove(self.cache[i])

    def getSlideList(self, directory, playlist, frame_ratio):
        """ Initailize slides[], filename{} and geometry{} from directory/playlist """

        if playlist is None:
            # Preferred playlist name is "playlist_16x9.m3u" ...
            p1 = os.path.join(directory, '%s_%s.%s' % (PLAYLIST, frame_ratio, PLAYLIST_EXT))
            # ... fallback is "playlist.m3u"
            p2 = os.path.join(directory, '%s.%s' % (PLAYLIST, PLAYLIST_EXT))
            if os.path.isfile(p1):
                playlist = p1
            else:
                playlist = p2
        else:
            playlist = os.path.join(directory, playlist)
        # Try to read the playlist file.
        try:
            exception_str = None
            with open(playlist, 'r') as f:
                slides_list = f.readlines()
        except Exception as e:
            exception_str = str(e)
            self.myLog(u'Error reading playlist "%s": %s' % (playlist, str(e)), xbmc.LOGERROR)
            slides_list = []
        # Parse all the lines from playlist.
        for line in slides_list:
            line = line.strip()
            if line == '' or line.startswith('#'): continue
            try:
                img_name, img_geometry = line.split('|')
                img_hash = self.filenameHash(img_name)
                self.slides.append(img_hash)
                self.filename[img_hash] = img_name
                self.geometry[img_hash] = img_geometry
            except:
                exception_str = u'Some playlist entries contains errors.'
        self.myLog(u'Playlist "%s" contains %d slides' % (playlist, len(self.slides)), xbmc.LOGINFO)

        if len(self.slides) < 1:
            # Warning message if playlist is empty.
            heading = __localize__(32004)
            message = __localize__(32005)
            if exception_str is not None:
                message = u'%s %s' % (message, exception_str)
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)
        elif exception_str is not None:
            # Warning message if some entries are bad.
            heading = __localize__(32006)
            message = exception_str
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)

    def prepareCachedImage(self, img, cache_keep):
        """ Return the name of a temporary file, with the image cropped/resized """
        self.myLog(u'Keep cache for %s, %s, %s' % (
            self.filename[cache_keep[0]],
            self.filename[cache_keep[1]],
            self.filename[cache_keep[2]]), xbmc.LOGDEBUG)
        if img in self.cache:
            self.myLog(u'Cache hit for %s in %s' % (self.filename[img], self.cache[img]), xbmc.LOGDEBUG)
        else:
            for i in self.cache:
                if i not in cache_keep:
                    # Create a new temporary file, because ControlImage.setImage() cache problem.
                    os.remove(self.cache[i])
                    del self.cache[i]
                    t = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                    self.cache[img] = t.name
                    break
            self.myLog(u'Cache miss for %s, creating %s' % (self.filename[img], self.cache[img]), xbmc.LOGDEBUG)
            self.imageToGeometry(img, self.cache[img])
        return self.cache[img]

    def nextSlide(self, direction=1):
        """Move to the next slide (direction = 1) or previous one (-1) """
        if len(self.slides) < 1: return
        if self.mutex.acquire(False):
            self.slides.rotate(-direction)
            cur_img = self.slides[0]
            self.slides.rotate(-1)
            next_img = self.slides[0]
            self.slides.rotate(2)
            prev_img = self.slides[0]
            self.slides.rotate(-1)
            keep_cached = (prev_img, cur_img, next_img)
            # Prepare current image and show it.
            tmp = self.prepareCachedImage(cur_img, keep_cached)
            self.myLog(u'nextSlide(): Image %s from %s' % (self.filename[cur_img], tmp), xbmc.LOGNOTICE)
            # WARNING: ControlImage.setImage() useCache=False parameter does not work.
            # The prepareCachedImage() creates a new name each time, as a workaround.
            self.image.setImage(tmp, False)
            self.show()
            if self.autoPlayStatus:
                self.timer = threading.Timer(self.slide_time, self.nextSlide)
                self.timer.start()
            # Prepare next and previous images in cache.
            self.prepareCachedImage(next_img, keep_cached)
            self.prepareCachedImage(prev_img, keep_cached)
            self.mutex.release()

    def setAutoPlay(self, autoPlayEnabled):
        if autoPlayEnabled == self.autoPlayStatus:
            return
        heading = __localize__(32007)
        if autoPlayEnabled:
            self.timer = threading.Timer(self.slide_time, self.nextSlide)
            self.timer.start()
            self.autoPlayStatus = True
            message = __localize__(32008)
        else:
            self.timer.cancel()
            self.autoPlayStatus = False
            message = __localize__(32009)
        self.myLog(u'setAutoPlay(): %s' % (message,), xbmc.LOGNOTICE)
        xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_INFO)

    def onAction(self, action):
        actionId = action.getId()
        self.myLog(u'onAction(): action = %s' % (actionId,), xbmc.LOGDEBUG)
        if actionId == ACTION_PREVIOUS_MENU or actionId == ACTION_NAV_BACK:
            self.myLog(u'onAction(): ACTION_PREVIOUS_MENU or ACTION_NAV_BACK', xbmc.LOGINFO)
            self.timer.cancel()
            self.cacheRemove()
            ret = setScreensaver(self.saved_screensaver)
            self.myLog(u'setScreenaver("%s"): %s' % (self.saved_screensaver, ret), xbmc.LOGINFO)
            self.close()
        if actionId == ACTION_MOVE_RIGHT or actionId == ACTION_NEXT_PICTURE:
            self.myLog(u'onAction(): ACTION_MOVE_RIGHT or ACTION_NEXT_PICTURE', xbmc.LOGINFO)
            self.setAutoPlay(False)
            self.nextSlide()
        if actionId == ACTION_MOVE_LEFT or actionId == ACTION_PREV_PICTURE:
            self.myLog(u'onAction(): ACTION_MOVE_LEFT or ACTION_PREV_PICTURE', xbmc.LOGINFO)
            self.setAutoPlay(False)
            self.nextSlide(-1)
        if actionId == ACTION_PAUSE or actionId == ACTION_SELECT_ITEM:
            self.myLog(u'onAction(): ACTION_PAUSE or ACTION_SELECT_ITEM', xbmc.LOGINFO)
            self.setAutoPlay(not self.autoPlayStatus)
        if actionId == ACTION_MOVE_UP or actionId == ACTION_MOVE_DOWN:
            self.myLog(u'onAction(): ACTION_MOVE_UP or ACTION_MOVE_DOWN', xbmc.LOGINFO)
            if actionId == ACTION_MOVE_UP:
                self.slide_time += 1.0
            if actionId == ACTION_MOVE_DOWN:
                self.slide_time -= 1.0
            if self.slide_time > SLIDE_TIME_MAX:
                self.slide_time = SLIDE_TIME_MAX
            elif self.slide_time < SLIDE_TIME_MIN:
                self.slide_time = SLIDE_TIME_MIN
            else:
                heading = __localize__(32010)
                message = __localize__(32011) % (int(self.slide_time),)
                self.myLog(u'onAction(): %s' % (message,), xbmc.LOGINFO)
                xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_INFO)

    def imageToGeometry(self, img, tmpfile):
        """ Crop and resize an image, save it into a temporary cache file """
        try:
            filename = os.path.join(self.directory, self.filename[img])
            image = Image.open(filename)
            # Assume Exif Orientation tag = 1, if missing.
            exif_orientation_tag = 1
            exif_data = image._getexif()
            if exif_data != None:
                exif = dict(exif_data.items())
                if ORIENTATION_TAG in exif.keys():
                    exif_orientation_tag = exif[ORIENTATION_TAG]
            if exif_orientation_tag in EXIF_ROTATE.keys():
                image = image.transpose(EXIF_ROTATE[exif_orientation_tag])
            image_w = image.width
            image_h = image.height
            match = re.match(GEOMETRY_RE, self.geometry[img])
            if match:
                gw = int(match.groups()[0])
                gh = int(match.groups()[1])
                gx = int(match.groups()[2])
                gy = int(match.groups()[3])
            if (not match) or (gx + gw > image_w) or (gy + gh > image_h):
                heading = __localize__(32012)
                message = __localize__(32013) % (self.filename[img],)
                self.myLog(u'%s: %s, image size: %dx%d' % (message, self.geometry[img], image_w, image_h), xbmc.LOGERROR)
                xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)
                gw, gh, gx, gy = image_w, image_h, 0, 0
            image = image.crop((gx, gy, gx + gw, gy + gh)).resize((self.img_w, self.img_h), resample=Image.BILINEAR)
            image.save(tmpfile)
        except Exception, e:
            # TODO: Use broken image.
            heading = __localize__(32014)
            message = __localize__(32015) % (self.filename[img], str(e),)
            self.myLog(message, xbmc.LOGERROR)
            xbmcgui.Dialog().notification(heading.encode('utf-8'), message.encode('utf-8'), xbmcgui.NOTIFICATION_ERROR)


#--------------------------------------------------------------------------
# Addon entry point: get the Context Menu item path and run on that.
#--------------------------------------------------------------------------
if (__name__ == '__main__'):
    contextmenu_item = xbmc.getInfoLabel('ListItem.FilenameAndPath')
    message = u'Launched with Context Menu item: "%s"' % (contextmenu_item,)
    xbmc.log(msg=message.encode('utf-8'), level=xbmc.LOGNOTICE)
    if os.path.isfile(contextmenu_item):
        directory = os.path.dirname(contextmenu_item)
        playlist = os.path.basename(contextmenu_item)
    else:
        directory = contextmenu_item
        playlist = None
    if not os.path.isdir(directory):
        line1 = __localize__(32002) % (PLAYLIST, PLAYLIST_EXT)
        line2 = __localize__(32003)
        xbmcgui.Dialog().ok(ADDONNAME, line1, line2)
    else:
        window_instance = photoFrameAddon()
        window_instance.initSlideshow(directory, playlist)
        window_instance.doModal()
        del window_instance
