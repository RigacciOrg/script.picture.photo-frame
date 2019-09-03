# photo-reframe App

Slideshow with on-the-fly, user defined image cropping and resizing

This is a stand-alone program, which requires the Python 3 language
with the PyQt5 and PIL libraries (not tested with Python 2, but should
be feasible).

It requires also the external command line tool **exiv2**, to eventually
fix a wrong Exif Orientation tag in images.

## Slideshow Mode

You can start the slideshow mode in full-screen with the following
command line:

```
photo-reframe --fullscreen --play path/to/directory
```

When running in slideshow mode, the program reads the **playlist.txt** file,
which contains the filename of the images and their respective geometries,
separated by a vertical bar, something like this:

```
IMG_6602.JPG|4000x2250+0+332
IMG_6605.JPG|2971x1671+796+628
IMG_6606.JPG|4000x2250+0+442
IMG_6610.JPG|3810x2143+90+387
IMG_6615.JPG|2828x1590+547+681
IMG_6617.JPG|1633x918+1229+1052
IMG_6624.JPG|2843x1599+393+585
```

Each geometry determines the portion of the image to be shown in the slideshow,
and it is composed by four values:

* **width** of the crop region
* **height** of the crop region
* **X offset** of the top-left corner of the region
* **Y offset** of the top-left corner of the region

The cropped region is resized to occupy the entire screen.
The program receives the name of a **directory** on the command line
and it will search images and the playlist.txt file starting
from that.

In slideshow mode, only images listed in the playlist will be
automatically shown for the time specified by the **--timer**
command line option (default is 4 seconds).

You can arrange the image order etc. editing the playlist file.
Other images contained into the directory will not be shown.

## Playlist Editing Mode

If you stop the slideshow play mode (press the **P** key),
you can interactively prepare the playlist. It is advised
also to exit the full-screen mode pressing the **F** key.

Every image is displayed on the screen, you can adjust the zoom and
pan as desired and then press the **Return** key. The border
of the image becomes **green**, indicating that a geometry
was selected for that image. A **red** border means that
no geometry was defined for the current image (thus that image
will not be displayed in slideshow). A **yellow** border means
that a geometry was defined, but you moved the image into
the frame, so you need to press Return to update its value.

At the end of your work, press the **S** key to save the
playlist with the update geometries.

This is the help for every **keyboard shortcuts**:

```
F1 or ?   Show this help
F11 or F  Toggle fullscreen mode
+         Zoom in
-         Zoom out
1         Zoom to 1:1 pixel
W         Zoom to fit image width
H         Zoom to fit image height
Z         Zoom-in to remove blank space
R         Update image cycling Exif Orientation tag
Return    Accept current geometry for image
G         Zoom to current image geometry
Canc      Forget current geometry (remove from playlist)
I         Print image and window data
Space     Go to next image
Backspace Go to previous image
P         Toggle autoplay
S         Save the playlist with updated gemetries
Q         Quit program
```
