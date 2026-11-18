> **sandbranch fork, branch `inkscape-1.4`.** Reworked for Inkscape 1.4 and
> checked by rendering: the result must look like the same drawing under a
> real clip (Object > Clip > Set), compared pixel by pixel in mm, px and
> scaled documents (`tests/test_render.py`). What it fixes:
>
> * The clipping object is the topmost one in stacking order. Upstream took
>   the first id Inkscape passes, which follows the order objects were
>   selected in, so a clip selected last clipped with one of the subjects.
> * The clip may be a rect, circle, ellipse, polygon or line, and it may
>   have curves and arcs. Upstream ignored anything but a path, and on an
>   arc (`A`, which circles turned into paths have) it printed an error and
>   then clipped with a wrong shape built from the arc's radii.
> * Subjects may have curves, arcs and quadratics: they are cut exactly
>   where they cross the clip and stay curves. Upstream drew a straight
>   line in place of each curve. Rects, circles and other shapes are
>   clipped too (they become paths), and groups are clipped object by
>   object instead of being skipped.
> * Transforms on the objects and their groups are taken into account
>   (upstream mixed coordinates from different groups).
> * Lines through a corner of the clip were dropped or kept wrongly (the
>   inside test counted a corner twice).
> * Filled shapes become their closed intersection with the clip (holes
>   too), so the fill looks as it did under the clip. Lines and outlines
>   with no fill are cut into the pieces inside, as before.
> * Objects with nothing left inside the clip are deleted, as a clip would
>   hide them (option "Keep objects that are entirely outside the clip"
>   restores the old behaviour). Option "Delete the clipping object
>   afterwards" removes the clip, as Object > Clip > Set does.
>
> A cut stroke ends square across the line (butt cap), where a real clip
> cuts it along the clip edge; within half a stroke width of the clip edge
> the two can differ. A filled shape that also has a stroke gets a stroke
> along the cut edge too. Text is not clipped (convert it to a path first).
>
> Install for development: `dev/install.sh` (symlinks into the user
> extensions folder). Compare renders yourself: `dev/compare.py OUTDIR`.
> Tests: `PYTHONPATH=/usr/share/inkscape/extensions python3 -m pytest`.

# DestructiveClip
An Inkscape Extension which works like Object|Clip|Set except that the paths clipped are actually **modified**.

Thus the clipping is included when exported, for example as a DXF file.
Select two or more **paths** then choose Extensions|Modify path|Destructive clip.  The topmost path will be used to clip the others.

Notes:-
* Curves (including Arcs) in paths are not supported (use Extensions|Modify path|Flatten Beziers).
* Non-path objects in the selection will be ignored.  Use Object|Ungroup.
* Paths entirely outside the clipping path will remain untouched (rather than modifying them to an empty path)
* Complex paths may take a while (there seems to be no way too show progress)
* Yes, using MBR's to do gross clipping might make it faster
* No, Python is not my first language (C/C++ is)
    
Mark Wilson Feb 2016

# To install
Copy destructiveclip.py & destructiveclip.inx into Inkscape\share\extensions where-ever Inkscape is installed (eg Program Files).
Start Inkscape.  "Destructive Clip" should now be available under the Extensions menu, in the Modify Path submenu.

# Example
clipped.png shows the rectangular blue path clipping the tiled "dovetail" red path.  The red path has been *modified*
