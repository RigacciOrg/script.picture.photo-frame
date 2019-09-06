# Slideshow Add-on Script for Kodi

**Slideshow** add-on for **Kodi** based on **playlists** with user defined image **cropping**.

An add-on for the
**[Kodi Home Theater Software](https://kodi.tv/)**
to play slideshows of images based on playlists. Select the 
images you want to display and sort them; define **zoom and 
pan** for each picture as you want to **avoid black borders** 
and unwanted cropping or stretching.

Crop and resize is perfomed **on-the-fly**, so you don't have to 
store copies of your images. When an image is displayed, the 
next one is prepared in cache. Also the previous image is keept 
in cache, so that switching to the next and to the previous 
slides is almost immediate.

The slideshow can be started selecting the proper **Context 
Menu** entry over a pictures directory. Advancing in slideshow 
is controlled by a timer or via joypad keys.

Playlists can be prepared with the Python-based desktop 
application
**[photo-reframe-app](https://github.com/RigacciOrg/photo-reframe-app)**.

## Playlist Format

The playlist is a text file is saved into the directory that 
contains the images. The default, preferred name is 
**playlist_16x9.m3u** (if your screen is 16:9). A fallback 
default is **playlist.m3u**.

If the screen width/height ratio is different,
the add-on searches also for names with the following
infixes: *24x9*, *16x9*, *3x2* and *4x3*.
You control the slideshow window size in the add-on
settings page.

The playlist contains the filename of the images and their 
respective geometries, separated by a vertical bar, something 
like this:

```
IMG_6602.JPG|4000x2250+0+332
IMG_6605.JPG|2971x1671+796+628
IMG_6606.JPG|4000x2250+0+442
IMG_6610.JPG|3810x2143+90+387
IMG_6615.JPG|2828x1590+547+681
IMG_6617.JPG|1633x918+1229+1052
IMG_6624.JPG|2843x1599+393+585
```

Each geometry determines the portion of the image to be shown in 
the slideshow, and it is composed by four values:

* **width** of the crop region
* **height** of the crop region
* **X offset** of the top-left corner of the region
* **Y offset** of the top-left corner of the region

The cropped region is resized to occupy the entire screen.

## Installing the Add-on

Download the
**[zip archive](https://github.com/RigacciOrg/script.picture.photo-frame/archive/master.zip)**
and store it somewhere on the Kodi fileststem.

From the **Kodi Main menu** follow the links:
Add-ons, Search (Add-on browser), Cancel, **Install from zip file**

## Add-on Settings

You have to **manually set the window size** for the slideshow. 
Default is 1280x720, go to the add-on settings screen to change 
it (Main Menu, Add-ons, Photo Frame, Context Menu).

## Running the Slideshow

From the Pictures section, browse the directories of your Kodi 
system (you can add a pictures root foolder to the Favourites 
menu). When you see a folder containing the playlist and the 
images, activate the **Context Menu** and choose **View in Photo 
Frame**.

The **keys** you can use during the slideshow are:

* **PREVIOUS_MENU** or **NAV_BACK** Exit the slideshow.
* **MOVE_RIGHT** or **NEXT_PICTURE** Stop the slideshow, manually move to the next image.
* **MOVE_LEFT** or **PREV_PICTURE** Stop the slideshow, manually move to the previous image.
* **PAUSE** or **SELECT_ITEM** Stop and start the slideshow.
* **MOVE_UP** or **MOVE_DOWN** Increase or decrease the slideshow timer.

## Kown Problems

### Cannot determine the window width and heigth automatically

Kodi API v.17 has a bug, explained in pull
[#12279](https://github.com/xbmc/xbmc/pull/12279).

When you ask for *xbmcgui.Window.getWidth()* and 
*xbmcgui.Window.getHeight()* you actually get the **screen 
size**, which is different from the **window size** (even if the 
window is the only object which occupies the entire screen).

For example: if Kodi is running at display resolution of 
1360x768, the above API call will return 1360x768 instead of 
1280x720, which actually is the max size of the window you can 
use.

This is why we added a Settings section in this add-on, just to 
allow the user to specifiy the window size. The default is 
1280x720, which should be OK for a Full HD screen.

### Not using the native screen resolution

This add-on uses just a **ControlImage()** which occupy the 
entire **xbmcgui.Window**. Unfortunately the image size is not 
mapped 1:1 to the screen size. In my test case Kodi is running 
at 1360x768 screen resolution, but the xbmcgui.Window cannot be 
bigger that 1280x720, otherwise it overflows out of the screen.

This means that the add-on can prepare images at max 1280x720 
resultion and they will be displayed at 1360x768 resolution, 
after stretching them.

I asked for insight in this
[forum thread](https://forum.kodi.tv/showthread.php?tid=346640),
but is not clear to me if it is possible to get the best from 
the screen hardware.
