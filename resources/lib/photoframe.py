# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import xbmcaddon

from resources.lib.exif import get_exif_tags

from PIL import Image, ExifTags
from collections import deque
import json
import hashlib
import os
import os.path
import re
import threading
import tempfile

__author__ = "Niccolo Rigacci"
__copyright__ = "Copyright 2019-2023 Niccolo Rigacci <niccolo@rigacci.org>"
__license__ = "GPLv3-or-later"
__email__ = "niccolo@rigacci.org"
__version__ = "0.2.1"

#--------------------------------------------------------------------------
# Global object to store configuration settings (as attributes).
#--------------------------------------------------------------------------
class CFG:
    pass

#--------------------------------------------------------------------------
# Global constants.
#--------------------------------------------------------------------------
ADDON = xbmcaddon.Addon()
ADDONNAME = ADDON.getAddonInfo('name')
ADDONPATH = ADDON.getAddonInfo('path')
__localize__ = ADDON.getLocalizedString

GEOMETRY_RE = '(\d+)x(\d+)\+(\d+)\+(\d+)'
FRAME_RATIOS = ('24x9', '16x9', '3x2', '4x3')

# See https://codedocs.xyz/w3tech/xodi/group__python__xbmcgui__control__label.html
XBFONT_LEFT       = 0x00000000
XBFONT_RIGHT      = 0x00000001
XBFONT_CENTER_X   = 0x00000002
XBFONT_CENTER_Y   = 0x00000004
XBFONT_TRUNCATED  = 0x00000008
XBFONT_JUSTIFIED  = 0x00000010

# Rotation needed (as per PIL) upon Exif orientation.
EXIF_ROTATE = {
    3: Image.ROTATE_180,
    6: Image.ROTATE_270,
    8: Image.ROTATE_90
}

# Images.
BROKEN_PHOTO = 'resources/media/broken-photo.png'
BLACK_SQUARE = 'resources/media/black-60.png'

# Keycodes.
# See https://codedocs.xyz/xbmc/xbmc/group__kodi__key__action__ids.html
ACTION_NONE = 0
ACTION_PREVIOUS_MENU = 10    # Keyboard "Esc"
ACTION_NAV_BACK = 92         # Keyboard "Backspace"
ACTION_PAUSE = 12            # Keyboard "Space"
ACTION_SELECT_ITEM = 7       # Keyboard "Enter"
ACTION_NEXT_PICTURE = 28
ACTION_PREV_PICTURE = 29
ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4
ACTION_SHOW_SUBTITLES = 25
ACTION_STOP = 13             # Key "x"
ACTION_SHOW_GUI = 18         # Gamepad button "Y"
ACTION_CONTEXT_MENU = 117    # Key "c", gamepad button "X"
ACTION_MENU = 163            # Key "m"
ACTION_SHOW_INFO = 11        # Key "i"

#--------------------------------------------------------------------------
# Kodi default is to emit messages with level >= xbmc.LOGNOTICE, this is
# fixed and can be changed only in userdata/advancedsettings.xml.
# So we make our own configurable logging verbosity.
#--------------------------------------------------------------------------
LOG_LEVEL = {
    'DEBUG':   xbmc.LOGDEBUG,
    'INFO':    xbmc.LOGINFO,
    'WARNING': xbmc.LOGWARNING,
    'ERROR':   xbmc.LOGERROR,
    'FATAL':   xbmc.LOGFATAL
}
# Create the inverse dictionary, to search the label by value.
LOG_LABEL = dict(zip(LOG_LEVEL.values(), LOG_LEVEL.keys()))



#--------------------------------------------------------------------------
# Add-on main window.
#--------------------------------------------------------------------------
class photoFrameAddon(xbmcgui.Window):

    def initSlideshow(self, directory, playlist=None):
        self.verbosity = LOG_LEVEL[ADDON.getSetting('log-level')]
        self.myLog('initSlideshow(%s, %s)' % (directory, playlist), xbmc.LOGINFO)
        self.myLog('Calling built-in InhibitScreensaver(true)', xbmc.LOGINFO)
        xbmc.executebuiltin('InhibitScreensaver(true)')
        self.directory = directory
        self.slide_time = CFG.SLIDE_TIME_DEFAULT
        self.show_caption = True

        self.slides = deque([])
        self.filename = {}
        self.geometry = {}
        self.cache = {}
        self.cache_caption = {}

        # WARNING: API v17 has a bug: getWidth() and getHeight() actually return
        # the display resolution, which is not the same as the Window instance size.
        # See https://github.com/xbmc/xbmc/pull/12279
        # E.g. display resolution is 1360x768, while Window size is 1280x720.
        # self.getResolution() returns RES_DESKTOP = 16, useless and not documented in Kodi 17.6.
        # Workaround to have the actual Window size in API v17: use settings.xml.
        #self.img_w = int(ADDON.getSetting('WindowWidth'))
        #self.img_h = int(ADDON.getSetting('WindowHeight'))

        # With Kodi 19 Matrix self.getWidth() and self.getHeight() are OK.
        self.img_w = self.getWidth()
        self.img_h = self.getHeight()
        self.myLog('Window: %dx%d, image: %dx%d' % (self.getWidth(), self.getHeight(), self.img_w, self.img_h), xbmc.LOGINFO)

        if ADDON.getSetting('playlist-suffix').lower() == 'auto':
            # Search the best preset to match the window ratio.
            window_ratio = float(self.img_w) / float(self.img_h)
            min_diff = 999.9
            for preset in FRAME_RATIOS:
                w, h = preset.split('x')
                preset_ratio = float(w) / float(h)
                if abs(preset_ratio - window_ratio) < min_diff:
                    min_diff = abs(preset_ratio - window_ratio)
                    self.frame_ratio = preset
            self.myLog('Best frame ratio selected: %s' % (self.frame_ratio,), xbmc.LOGINFO)
        else:
            self.frame_ratio = ADDON.getSetting('playlist-suffix')
            self.myLog('Frame ratio from settings: %s' % (self.frame_ratio,), xbmc.LOGINFO)

        self.image = xbmcgui.ControlImage(0, 0, self.img_w, self.img_h, os.path.join(ADDONPATH, BLACK_SQUARE))
        self.addControl(self.image)
        caption_x = 0
        caption_w = self.img_w
        caption_h = int(CFG.CAPTION_FONT_SIZE * CFG.CAPTION_MAX_ROWS)
        caption_y = int(self.img_h * CFG.CAPTION_Y_POS_PERC) - caption_h
        caption_alignment = XBFONT_CENTER_X | XBFONT_TRUNCATED
        # TODO: What if resources path is UTF-8?
        # Cannot use .encode('utf-8') because TypeError: argument 5 must be str, not bytes
        self.captionBackground = xbmcgui.ControlImage(caption_x, caption_y, caption_w, caption_h, os.path.join(ADDONPATH, 'resources', 'media', 'black-60.png'), aspectRatio=0)
        self.addControl(self.captionBackground)
        self.imageCaption = xbmcgui.ControlLabel(caption_x, caption_y, caption_w, caption_h, '', font=CFG.CAPTION_FONT, textColor=CFG.CAPTION_FG_COLOR, alignment=caption_alignment)
        self.addControl(self.imageCaption)
        self.getSlideList(self.directory, playlist, self.frame_ratio)
        self.timer = threading.Timer(self.slide_time, self.nextSlide)
        self.autoPlayStatus = True
        self.mutex = threading.Lock()
        self.cachePrepare()
        self.slides.rotate(1)
        self.nextSlide()


    def myLog(self, msg, level):
        """ Log to Kodi with xbmc.LOGINFO, but using our own verbosity """
        if level >= self.verbosity:
            message = '%s: %7s: %s' % (ADDONNAME, LOG_LABEL[level], msg)
            xbmc.log(msg=message, level=xbmc.LOGINFO)


    def filenameHash(self, string):
        """ Return an hash suitable to index a filenames list """
        return hashlib.md5(string.encode('utf-8')).hexdigest()[0:12]


    def cachePrepare(self):
        """ Three temporary files for caching images: current, previous and next """
        for i in range(0, 3):
            t = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            key = self.filenameHash('dummy%d.img' % i)
            self.cache[key] = t.name
            self.cache_caption[key] = None


    def cacheRemove(self):
        """ Remove temporary files """
        for i in self.cache:
            if os.path.exists(self.cache[i]):
                os.remove(self.cache[i])


    def getSlideList(self, directory, playlist, frame_ratio):
        """ Initailize slides[], filename{} and geometry{} from directory/playlist """
        if playlist is None:
            # Preferred playlist name is "playlist_16x9.m3u" ...
            p1 = os.path.join(directory, '%s_%s.%s' % (CFG.PLAYLIST, frame_ratio, CFG.PLAYLIST_EXT))
            # ... fallback is "playlist.m3u"
            p2 = os.path.join(directory, '%s.%s' % (CFG.PLAYLIST, CFG.PLAYLIST_EXT))
            if os.path.isfile(p1.encode('utf-8')):
                playlist = p1
            else:
                playlist = p2
        else:
            playlist = os.path.join(directory, playlist)
        # Try to read the playlist file.
        try:
            exception_str = None
            with open(playlist.encode('utf-8'), 'r', encoding='utf-8') as f:
                slides_list = f.readlines()
        except Exception as e:
            exception_str = str(e)
            self.myLog('Error reading playlist "%s": %s' % (playlist, str(e)), xbmc.LOGERROR)
            slides_list = []
        # Parse all the lines from playlist.
        for line in slides_list:
            line = line.strip()
            if line == '' or line.startswith('#'): continue
            if '|' not in line: continue
            try:
                img_name, img_geometry = line.split('|')
                if img_geometry == '': continue
                img_hash = self.filenameHash(img_name)
                self.slides.append(img_hash)
                self.filename[img_hash] = img_name
                self.geometry[img_hash] = img_geometry
            except:
                exception_str = __localize__(32020)
        self.myLog('Playlist "%s" contains %d slides' % (playlist, len(self.slides)), xbmc.LOGINFO)

        if len(self.slides) < 1:
            # Warning message if playlist is empty.
            heading = __localize__(32004)
            message = __localize__(32005)
            if exception_str is not None:
                message = '%s %s' % (message, exception_str)
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)
        elif exception_str is not None:
            # Warning message if some entries are bad.
            heading = __localize__(32006)
            message = exception_str
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)


    def prepareCachedImage(self, img, cache_keep):
        """ Return the name of a temporary file, with the image cropped/resized """
        self.myLog('Keep cache for %s, %s, %s' % (
            self.filename[cache_keep[0]],
            self.filename[cache_keep[1]],
            self.filename[cache_keep[2]]), xbmc.LOGDEBUG)
        if img in self.cache:
            self.myLog('Cache hit for %s in %s' % (self.filename[img], self.cache[img]), xbmc.LOGDEBUG)
        else:
            for i in self.cache:
                if i not in cache_keep:
                    # Create a new temporary file, because ControlImage.setImage() cache problem.
                    os.remove(self.cache[i])
                    del self.cache[i]
                    del self.cache_caption[i]
                    t = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                    self.cache[img] = t.name
                    break
            self.myLog('Cache miss for %s, creating %s' % (self.filename[img], self.cache[img]), xbmc.LOGDEBUG)
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
            self.updateImageCaption()
            self.myLog('nextSlide(): Image %s from %s' % (self.filename[cur_img], tmp), xbmc.LOGINFO)
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
            xbmc.executebuiltin('InhibitScreensaver(true)')
            self.timer = threading.Timer(self.slide_time, self.nextSlide)
            self.timer.start()
            self.autoPlayStatus = True
            message = __localize__(32008)
        else:
            xbmc.executebuiltin('InhibitScreensaver(false)')
            self.timer.cancel()
            self.autoPlayStatus = False
            message = __localize__(32009)
        self.myLog('setAutoPlay(): %s' % (message,), xbmc.LOGINFO)
        xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_INFO)


    def onAction(self, action):
        actionId = action.getId()
        self.myLog('onAction(): action = %s' % (actionId,), xbmc.LOGDEBUG)
        if actionId == ACTION_PREVIOUS_MENU or actionId == ACTION_NAV_BACK or actionId == ACTION_STOP:
            # Keyboard Esc, Backspace or "x".
            self.myLog('onAction(): ACTION_PREVIOUS_MENU or ACTION_NAV_BACK or ACTION_STOP', xbmc.LOGINFO)
            self.timer.cancel()
            self.cacheRemove()
            self.myLog('Calling built-in InhibitScreensaver(false)', xbmc.LOGINFO)
            xbmc.executebuiltin('InhibitScreensaver(false)')
            self.close()
        if actionId == ACTION_MOVE_RIGHT or actionId == ACTION_NEXT_PICTURE:
            self.myLog('onAction(): ACTION_MOVE_RIGHT or ACTION_NEXT_PICTURE', xbmc.LOGINFO)
            self.setAutoPlay(False)
            self.nextSlide()
        if actionId == ACTION_MOVE_LEFT or actionId == ACTION_PREV_PICTURE:
            self.myLog('onAction(): ACTION_MOVE_LEFT or ACTION_PREV_PICTURE', xbmc.LOGINFO)
            self.setAutoPlay(False)
            self.nextSlide(-1)
        if actionId == ACTION_PAUSE or actionId == ACTION_SELECT_ITEM:
            self.myLog('onAction(): ACTION_PAUSE or ACTION_SELECT_ITEM', xbmc.LOGINFO)
            self.setAutoPlay(not self.autoPlayStatus)
        #if actionId == ACTION_CONTEXT_MENU or actionId == ACTION_SHOW_INFO:
        #    # Gamepad button "X", keyboard "c", keyboard "i".
        #    # TODO: Show image info.
        if actionId == ACTION_SHOW_GUI or actionId == ACTION_MENU or actionId == ACTION_SHOW_SUBTITLES:
            # Gamepad button "Y" or keyboard "m"
            self.show_caption = not self.show_caption
            self.updateImageCaption()
            heading = __localize__(32022)
            if self.show_caption:
                message = __localize__(32023)
            else:
                message = __localize__(32024)
            self.myLog('onAction(): %s' % (message,), xbmc.LOGINFO)
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_INFO)
        if actionId == ACTION_MOVE_UP or actionId == ACTION_MOVE_DOWN:
            self.myLog('onAction(): ACTION_MOVE_UP or ACTION_MOVE_DOWN', xbmc.LOGINFO)
            if actionId == ACTION_MOVE_UP:
                self.slide_time += 1.0
            if actionId == ACTION_MOVE_DOWN:
                self.slide_time -= 1.0
            if self.slide_time > CFG.SLIDE_TIME_MAX:
                self.slide_time = CFG.SLIDE_TIME_MAX
            elif self.slide_time < CFG.SLIDE_TIME_MIN:
                self.slide_time = CFG.SLIDE_TIME_MIN
            else:
                heading = __localize__(32010)
                message = __localize__(32011) % (int(self.slide_time),)
                self.myLog('onAction(): %s' % (message,), xbmc.LOGINFO)
                xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_INFO)


    def updateImageCaption(self):
        """ Update the image caption content, position and visibility """
        cur_img = self.slides[0]
        self.imageCaption.setVisible(self.show_caption)
        self.captionBackground.setVisible(self.show_caption)
        if not self.show_caption:
            self.imageCaption.setLabel('')
        else:
            caption = self.cache_caption[cur_img]
            if caption is None:
                self.imageCaption.setLabel('')
                self.captionBackground.setVisible(False)
            else:
                # Adjust caption size and position.
                lines_count = caption.count('\n') + 1
                if lines_count > CFG.CAPTION_MAX_ROWS:
                    caption = '\n'.join(caption.split('\n')[0:CFG.CAPTION_MAX_ROWS])
                    lines_count = CFG.CAPTION_MAX_ROWS
                self.imageCaption.setLabel(caption)
                max_line_len = max(len(line) for line in caption.split('\n'))
                caption_height = int(CFG.CAPTION_FONT_SIZE * lines_count)
                caption_y = int(self.img_h * CFG.CAPTION_Y_POS_PERC) - int(CFG.CAPTION_Y_POS_PERC * caption_height)
                background_width = int(float(max_line_len) * CFG.CAPTION_FONT_SIZE * CFG.CAPTION_FONT_RATIO_XY)
                if (float(background_width) / self.img_w) < 0.33:
                    # Compensate width for short captions.
                    background_width = int(float(background_width) * 1.3)
                if background_width > self.img_w:
                    background_width = self.img_w
                background_x = (self.img_w - background_width) // 2
                # WARNING: setHeight() does not work after ControlLabel creation.
                self.imageCaption.setHeight(caption_height)
                self.imageCaption.setPosition(0, caption_y)
                self.captionBackground.setPosition(background_x, caption_y)
                self.captionBackground.setWidth(background_width)
                self.captionBackground.setHeight(caption_height)


    def imageToGeometry(self, img, tmpfile):
        """ Crop and resize an image, save it into a temporary cache file """
        try:
            filename = os.path.join(self.directory, self.filename[img])
            self.myLog('Opening image file "%s"' % (filename,), xbmc.LOGDEBUG)
            image = Image.open(filename.encode('utf-8')).convert('RGB')
            exif_tags = get_exif_tags(image)
            #xbmc.log(msg='Got Exif data = %s' % (exif_tags,), level=xbmc.LOGINFO)
            exif_orientation_tag = exif_tags['orientation']
            self.cache_caption[img] = exif_tags['usercomment']
            if exif_orientation_tag in EXIF_ROTATE.keys():
                image = image.transpose(EXIF_ROTATE[exif_orientation_tag])
            self.myLog('Image "%s": Exif orientation tag: "%s"' % (self.filename[img], exif_orientation_tag,), xbmc.LOGINFO)
            image_w = image.width
            image_h = image.height
            match = re.match(GEOMETRY_RE, self.geometry[img])
            invalid_geometry = False
            if not match:
                self.myLog('Invalid geometry for "%s": "%s" (size: %dx%d)' % (self.filename[img], self.geometry[img], image_w, image_h), xbmc.LOGERROR)
                invalid_geometry = True
            else:
                gw = int(match.groups()[0])
                gh = int(match.groups()[1])
                gx = int(match.groups()[2])
                gy = int(match.groups()[3])
                if gx > image_w:
                    self.myLog('Invalid geometry for "%s": x-offset %d beyond image width %d' % (self.filename[img], gx, image_w), xbmc.LOGERROR)
                    invalid_geometry = True
                if gy > image_h:
                    self.myLog('Invalid geometry for "%s": y-offset %d beyond image height %d' % (self.filename[img], gy, image_h), xbmc.LOGERROR)
                    invalid_geometry = True
            if invalid_geometry:
                heading = __localize__(32012)
                message = __localize__(32013) % (self.filename[img],)
                xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_WARNING)
                fullscreen_image = image.resize((self.img_w, self.img_h), resample=Image.BILINEAR)
            else:
                # Fix the geometry to remove small (< 0.7%) black borders.
                if (gx + gw) > image_w:
                    excess = (gx + gw) - image_w
                    excess_perc = (float(gx + gw) / image_w) - 1.0
                    if excess_perc < 0.007:
                        self.myLog('Fixing black border X: %s px, %0.2f%%' % (excess, excess_perc * 100), xbmc.LOGINFO)
                        gx -= excess
                        if gx < 0:
                            gw += gx
                            gx = 0
                if (gy + gh) > image_h:
                    excess = (gy + gh) - image_h
                    excess_perc = (float(gy + gh) / image_h) - 1.0
                    if excess_perc < 0.007:
                        self.myLog('Fixing black border Y: %s px, %0.2f%%' % (excess, excess_perc * 100), xbmc.LOGINFO)
                        gy -= excess
                        if gy < 0:
                            gh += gy
                            gy = 0
                # Do we need vertical or horizontal black borders?
                black_x = 0.0
                black_y = 0.0
                if (gx + gw) > image_w:
                    black_x = float((gx + gw) - image_w) / 2.0
                if (gy + gh) > image_h:
                    black_y = float((gy + gh) - image_h) / 2.0
                # Calculate crop and offset.
                zoom_x = float(self.img_w) / float(gw)
                zoom_y = float(self.img_h) / float(gh)
                offset_scaled = (int(black_x * zoom_x), int(black_y * zoom_y))
                crop_left = gx
                crop_upper = gy
                crop_right = gx + gw - int(black_x * 2.0)
                crop_lower = gy + gh - int(black_y * 2.0)
                crop_w = crop_right - crop_left
                crop_h = crop_lower - crop_upper
                crop_w_scaled = int(crop_w * zoom_x)
                crop_h_scaled = int(crop_h * zoom_y)
                image = image.crop((crop_left, crop_upper, crop_right, crop_lower)).resize((crop_w_scaled, crop_h_scaled), resample=Image.BILINEAR)
                # Paste the image over a black background.
                fullscreen_image = Image.new('RGB', (self.img_w, self.img_h))
                fullscreen_image.paste(image, offset_scaled)

            fullscreen_image.save(tmpfile)
            self.myLog('Full screen image saved as "%s"' % (tmpfile,), xbmc.LOGINFO)

        except Exception as e:

            self.cache_caption[img] = ''
            # Prepare a fullscreen image with broken image icon.
            filename = os.path.join(ADDONPATH, BROKEN_PHOTO)
            image = Image.open(filename.encode('utf-8')).convert('RGB')
            image_w = image.width
            image_h = image.height
            fullscreen_image = Image.new('RGB', (self.img_w, self.img_h))
            zoom_x = float(self.img_w) / float(image.width)
            zoom_y = float(self.img_h) / float(image.height)
            zoom = min(zoom_x, zoom_y)
            off_x = int((float(self.img_w) - (zoom * image.width)) / 2)
            off_y = int((float(self.img_h) - (zoom * image.height)) / 2)
            resize_x = int(image_w * zoom)
            resize_y = int(image_h * zoom)
            fullscreen_image.paste(image.resize((resize_x, resize_y), resample=Image.BILINEAR), (off_x, off_y))
            fullscreen_image.save(tmpfile)
            # Show error dialog.
            heading = __localize__(32014)
            message = __localize__(32015) % (self.filename[img], str(e),)
            self.myLog(message, xbmc.LOGERROR)
            xbmcgui.Dialog().notification(heading, message, xbmcgui.NOTIFICATION_ERROR)
