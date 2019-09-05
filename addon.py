import xbmcaddon
import xbmcgui

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

#--------------------------------------------------------------------------
#--------------------------------------------------------------------------
PLAYLIST = 'playlist'
PLAYLIST_EXT = 'm3u'
GEOMETRY_RE = '(\d+)x(\d+)\+(\d+)\+(\d+)'
FRAME_RATIOS = ('24x9', '16x9', '2x3', '4x3')

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
addon     = xbmcaddon.Addon()
addonname = addon.getAddonInfo('name')
addonpath = addon.getAddonInfo('path').decode('utf-8')


#--------------------------------------------------------------------------
# Kodi default is to emit only messages with level >= LOGNOTICE,
# change this default in userdata/advancedsettings.xml.
# Make our own logging verbosity.
#--------------------------------------------------------------------------
SCRIPT_VERBOSITY = xbmc.LOGINFO
LOG_LABEL = {
    xbmc.LOGDEBUG:   '  DEBUG',
    xbmc.LOGINFO:    '   INFO',
    xbmc.LOGNOTICE:  ' NOTICE',
    xbmc.LOGWARNING: 'WARNING',
    xbmc.LOGERROR:   '  ERROR',
    xbmc.LOGFATAL:   '  FATAL'
}
def myLog(msg, level):
    if level >= SCRIPT_VERBOSITY:
        message = '%s: %s: %s' % (addonname, LOG_LABEL[level], msg,)
        xbmc.log(msg=message.encode('utf-8'), level=xbmc.LOGNOTICE)

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
    myLog(u'getScreenaver(): "%s"' % (result,), xbmc.LOGINFO)
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
    myLog(u'setScreenaver("%s"): %s' % (mode, result,), xbmc.LOGINFO)
    return result

#--------------------------------------------------------------------------
#--------------------------------------------------------------------------
class MyClass(xbmcgui.Window):

    def initSlideshow(self, directory):
        myLog(u'initSlideshow(%s)' % (directory,), xbmc.LOGNOTICE)
        self.saved_screensaver = getScreensaver()
        if self.saved_screensaver != '':
            setScreensaver('')
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
        self.img_w = int(addon.getSetting('WindowWidth'))
        self.img_h = int(addon.getSetting('WindowHeight'))
        myLog(u'Window: %dx%d, image: %dx%d' % (self.getWidth(), self.getHeight(), self.img_w, self.img_h), xbmc.LOGINFO)

        # Search the best preset to match the window ratio set in add-on settings.
        window_ratio = float(self.img_w) / float(self.img_h)
        min_diff = 999.9
        for preset in FRAME_RATIOS:
            w, h = preset.split('x')
            preset_ratio = float(w) / float(h)
            if abs(preset_ratio - window_ratio) < min_diff:
                min_diff = abs(preset_ratio - window_ratio)
                self.frame_ratio = preset
        myLog(u'Best frame ratio in presets is %s' % (self.frame_ratio,), xbmc.LOGINFO)

        self.image = xbmcgui.ControlImage(0, 0, self.img_w, self.img_h, os.path.join(addonpath, DUMMY_IMAGE))
        self.addControl(self.image)
        self.getSlideList(self.directory, self.frame_ratio)
        self.timer = threading.Timer(self.slide_time, self.nextSlide)
        self.autoPlayStatus = True
        self.mutex = threading.Lock()
        self.cachePrepare()
        self.slides.rotate(1)
        self.nextSlide()

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

    def getSlideList(self, directory, frame_ratio):
        """ Initailize slides[], filename{} and geometry{} from directory playlist """

        # Preferred playlist name is "playlist_16x9.m3u" ...
        p1 = os.path.join(directory, '%s_%s.%s' % (PLAYLIST, frame_ratio, PLAYLIST_EXT))
        # ... fallback is "playlist.m3u"
        p2 = os.path.join(directory, '%s.%s' % (PLAYLIST, PLAYLIST_EXT))
        if os.path.isfile(p1):
            playlist = p1
        else:
            playlist = p2
        try:
            exception_str = None
            with open(playlist, 'r') as f:
                slides_list = f.readlines()
        except Exception as e:
            exception_str = str(e)
            myLog(u'Error reading playlist "%s"' % (playlist,), xbmc.LOGERROR)
            slides_list = []

        # Read all the lines from playlist.
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
        myLog(u'Playlist "%s" contains %d slides' % (playlist, len(self.slides)), xbmc.LOGINFO)

        if len(self.slides) < 1:
            # Warning message if playlist is empty.
            heading = u'Playlist Error'
            message = u'Playlist is empty.'
            if exception_str is not None:
                message = u'%s %s' % (message, exception_str)
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)
        elif exception_str is not None:
            # Warning message if some entries are bad.
            heading = u'Errors in Playlist'
            message = exception_str
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)

    def prepareCachedImage(self, img, cache_keep):
        """ Return the name of a temporary file, with the image cropped/resized """
        myLog(u'Keep cache for %s, %s, %s' % (
            self.filename[cache_keep[0]],
            self.filename[cache_keep[1]],
            self.filename[cache_keep[2]]), xbmc.LOGDEBUG)
        if img in self.cache:
            myLog(u'Cache hit for %s in %s' % (self.filename[img], self.cache[img]), xbmc.LOGDEBUG)
        else:
            for i in self.cache:
                if i not in cache_keep:
                    # Create a new temporary file, because ControlImage.setImage() cache problem.
                    os.remove(self.cache[i])
                    del self.cache[i]
                    t = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                    self.cache[img] = t.name
                    break
            myLog(u'Cache miss for %s, creating %s' % (self.filename[img], self.cache[img]), xbmc.LOGDEBUG)
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
            myLog(u'nextSlide(): Image %s from %s' % (self.filename[cur_img], tmp), xbmc.LOGNOTICE)
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
        heading = u'Auto Play'
        if autoPlayEnabled:
            self.timer = threading.Timer(self.slide_time, self.nextSlide)
            self.timer.start()
            self.autoPlayStatus = True
            message = u'Starting slides auto play'
        else:
            self.timer.cancel()
            self.autoPlayStatus = False
            message = u'Stopping slides auto play'
        myLog(u'setAutoPlay(): %s' % (message,), xbmc.LOGNOTICE)
        xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_INFO)

    def onAction(self, action):
        actionId = action.getId()
        myLog(u'onAction(): action = %s' % (actionId,), xbmc.LOGDEBUG)
        if actionId == ACTION_PREVIOUS_MENU or actionId == ACTION_NAV_BACK:
            myLog(u'onAction(): ACTION_PREVIOUS_MENU or ACTION_NAV_BACK', xbmc.LOGINFO)
            self.timer.cancel()
            self.cacheRemove()
            setScreensaver(self.saved_screensaver)
            self.close()
        if actionId == ACTION_MOVE_RIGHT or actionId == ACTION_NEXT_PICTURE:
            myLog(u'onAction(): ACTION_MOVE_RIGHT or ACTION_NEXT_PICTURE', xbmc.LOGINFO)
            self.setAutoPlay(False)
            self.nextSlide()
        if actionId == ACTION_MOVE_LEFT or actionId == ACTION_PREV_PICTURE:
            myLog(u'onAction(): ACTION_MOVE_LEFT or ACTION_PREV_PICTURE', xbmc.LOGINFO)
            self.setAutoPlay(False)
            self.nextSlide(-1)
        if actionId == ACTION_PAUSE or actionId == ACTION_SELECT_ITEM:
            myLog(u'onAction(): ACTION_PAUSE or ACTION_SELECT_ITEM', xbmc.LOGINFO)
            self.setAutoPlay(not self.autoPlayStatus)
        if actionId == ACTION_MOVE_UP or actionId == ACTION_MOVE_DOWN:
            myLog(u'onAction(): ACTION_MOVE_UP or ACTION_MOVE_DOWN', xbmc.LOGINFO)
            if actionId == ACTION_MOVE_UP:
                self.slide_time += 1.0
            if actionId == ACTION_MOVE_DOWN:
                self.slide_time -= 1.0
            if self.slide_time > SLIDE_TIME_MAX:
                self.slide_time = SLIDE_TIME_MAX
            elif self.slide_time < SLIDE_TIME_MIN:
                self.slide_time = SLIDE_TIME_MIN
            else:
                heading = u'Slide Time'
                message = u'Setting timer to %d seconds' % (int(self.slide_time),)
                myLog(u'onAction(): Setting slide time to %d' % (self.slide_time,), xbmc.LOGINFO)
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
                myLog(u'Bad geometry for image %s: %s, image size: %dx%d' % (self.filename[img], self.geometry[img], image_w, image_h), xbmc.LOGERROR)
                heading = u'Bad Geometry'
                message = u'Bad geometry for image %s' % (self.filename[img],)
                xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)
                gw, gh, gx, gy = image_w, image_h, 0, 0
            image = image.crop((gx, gy, gx + gw, gy + gh)).resize((self.img_w, self.img_h), resample=Image.BILINEAR)
            image.save(tmpfile)
        except Exception, e:
            # TODO: Use broken image.
            heading = u'Image Error'
            message = u'Image "%s": imageToGeometry(): Exception: %s' % (self.filename[img], str(e),)
            myLog(message, xbmc.LOGERROR)
            xbmcgui.Dialog().notification(heading.encode('utf-8'), message.encode('utf-8'), xbmcgui.NOTIFICATION_ERROR)


#--------------------------------------------------------------------------
# If called from the Context Menu, get the item path and run on that.
#--------------------------------------------------------------------------
contextmenu_item = xbmc.getInfoLabel('ListItem.FilenameAndPath')
myLog(u'Launched with Context Menu item: "%s"' % (contextmenu_item,), xbmc.LOGINFO)
if not os.path.isdir(contextmenu_item):
    line1 = u'Please, run this add-on over a Pictures folder, from the Context Menu.'
    line2 = u'The folder should contain a "%s" file, listing image names and geometry infomration for re-framing.' % (PLAYLIST_FILENAME,)
    xbmcgui.Dialog().ok(addonname, line1, line2)
else:
    mydisplay = MyClass()
    mydisplay.initSlideshow(contextmenu_item)
    mydisplay.doModal()
    del mydisplay